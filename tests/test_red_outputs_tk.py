"""Exercise per-tab input selection and complete-patient saving with native Tk."""
import pytest


@pytest.mark.parametrize('path', ['DICOM3.Scanner', 'calibrations.zip', ''])
def test_calibration_picker_leaves_arbitrary_suffixes_selectable(path, monkeypatch, tmp_path):
    from unittest.mock import Mock
    from hyperio.red_outputs import REDOutputs
    monkeypatch.setattr('hyperio.red_outputs.calibration_picker_directory', lambda: tmp_path)

    panel = REDOutputs.__new__(REDOutputs)
    panel.filedialog = Mock()
    panel.filedialog.askopenfilename.return_value = path
    tab = {'calibration': Mock()}

    panel.choose_calibration(tab)

    panel.filedialog.askopenfilename.assert_called_once()
    assert 'filetypes' not in panel.filedialog.askopenfilename.call_args.kwargs
    assert panel.filedialog.askopenfilename.call_args.kwargs['initialdir'] == str(tmp_path)
    if path:
        tab['calibration'].set.assert_called_once_with(path)
    else:
        tab['calibration'].set.assert_not_called()


def test_calculation_request_during_busy_does_not_invalidate_result():
    from hyperio.desktop.red import REDWindow
    window = REDWindow.__new__(REDWindow)
    window.busy = True
    tab = {'generation': 2, 'ct_red': {'Insert': {'mean_red': 1.0}}}
    window.calculate_ct_mean(tab, {}, 'DICOM3.table')
    assert tab == {'generation': 2, 'ct_red': {'Insert': {'mean_red': 1.0}}}


def test_plan_selection_autoselects_only_matching_calibration(monkeypatch, tmp_path):
    from unittest.mock import Mock
    from hyperio import ct_red
    from hyperio.red_outputs import REDOutputs
    monkeypatch.setattr(ct_red, 'calibration_directories', lambda: [tmp_path])
    match = tmp_path / 'DICOM3.Scanner'
    match.write_text('not read')
    panel = REDOutputs.__new__(REDOutputs)
    panel.plans = [{'ct_to_ed_name': 'Scanner'}, {'ct_to_ed_name': 'Other'}, {'ct_to_ed_name': None}]
    tab = {'plan_box': Mock(), 'calibration': Mock(), 'manual': {'Insert': {}},
           'ct_red': {'Insert': {}}, 'generation': 2}
    tab['plan_box'].current.return_value = 0
    panel.select_plan_calibration(tab)
    tab['calibration'].set.assert_called_with(str(match))
    tab['plan_box'].current.return_value = 1
    panel.reset_manual(tab)
    assert not tab['manual']
    tab['calibration'].set.assert_called_with('?? Other ??')
    tab['calibration'].get.return_value = '?? Other ??'
    tab['status'] = Mock()
    panel.calculate = Mock()
    panel.request_ct_red(tab)
    panel.calculate.assert_not_called()
    tab['status'].set.assert_called_with('Choose DICOM3.Other or a ZIP containing it.')
    tab['plan_box'].current.return_value = 2
    panel.select_plan_calibration(tab)
    tab['calibration'].set.assert_called_with('?? Curve name unavailable ??')


def test_copy_ct_mean_keeps_mode_and_rejects_out_of_range_value():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from hyperio.red_outputs import REDOutputs

    panel = REDOutputs.__new__(REDOutputs)
    panel.refresh = Mock()
    table = Mock()
    table.identify_row.return_value = 'row'
    table.identify_column.return_value = '#6'
    table.item.return_value = ('Insert',)
    tab = {'table': table, 'status': Mock(), 'manual': {'Insert': {'mode': 'filled'}},
           'ct_red': {'Insert': {'mean_red': 1.23456}}}
    event = SimpleNamespace(x=5, y=5)
    panel.edit_cell(tab, event)
    assert tab['manual']['Insert'] == {'mode': 'filled', 'red': '1.23456'}
    panel.refresh.assert_called_once_with(tab)

    tab['ct_red']['Insert']['mean_red'] = 0.001
    panel.edit_cell(tab, event)
    assert tab['manual']['Insert']['red'] == '1.23456'
    assert 'Cannot copy CT mean RED' in tab['status'].set.call_args.args[0]


@pytest.fixture
def root():
    tk = pytest.importorskip('tkinter')
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f'Tk display unavailable: {error}')
    root.withdraw()
    yield root
    root.destroy()


def test_output_tabs_keep_inputs_presets_and_names_independent(root, tmp_path):
    from tkinter import ttk
    from hyperio.red_outputs import REDOutputs
    from test_applications import plan_bytes
    panel = REDOutputs(ttk.Frame(root), lambda: None)
    plans = [dict(name=name, label=name, member=f'plan/{name}/plan', data=plan_bytes(name))
             for name in ('PlanC', 'PlanD')]
    panel.set_plans(plans)
    original = panel.current()
    assert original['name'].get() == ''
    panel.add_output()
    modified = panel.current()
    preset = tmp_path / 'preset.csv'
    preset.write_text('structure,red\nInsert,1.1\n')
    modified['preset'].set(str(preset))
    modified['name'].set('PlanCAlt')
    edits = panel.prepared()
    assert edits == [dict(member='plan/PlanC/plan', name='', mapping={}),
                     dict(member='plan/PlanC/plan', name='PlanCAlt', mapping={'Insert': 1.1})]
    modified['plan_box'].current(1)
    assert panel.prepared()[1]['member'] == 'plan/PlanD/plan'
    panel.notebook.select(original['frame'])
    assert panel.current()['preset'].get() == ''
    assert panel.prepared()[0] == edits[0]
    modified['name'].set('bad/name')
    with pytest.raises(ValueError):
        panel.prepared()
    panel.notebook.select(modified['frame'])
    panel.remove_output()
    assert panel.prepared() == [edits[0]]
    panel.set_plans([])
    with pytest.raises(ValueError, match='Choose a patient'):
        panel.prepared()


@pytest.mark.parametrize('add_to_source', [False, True])
def test_red_application_saves_all_tabs(root, monkeypatch, tmp_path, add_to_source):
    import time
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from hyperio.gui import _launch
    from hyperio.core import plan_metadata
    from hyperio.desktop.red import ADD_TO_SOURCE
    from test_applications import plan_bytes
    source = tmp_path / 'source'
    for name in ('PlanC', 'PlanD'):
        native = source / 'plan' / name / 'plan'
        native.parent.mkdir(parents=True)
        native.write_bytes(plan_bytes(name))
        (native.parent / 'companion').write_bytes(name.encode())
    (source / 'CT').mkdir()
    (source / 'CT' / 'structures').write_bytes(b'original contours')
    destination = tmp_path / 'output'
    monkeypatch.setattr(tk, 'Tk', lambda: root)
    monkeypatch.setattr(root, 'mainloop', lambda: None)
    monkeypatch.setattr(filedialog, 'askdirectory', lambda **_: str(source))
    def save_dialog(**_):
        assert not add_to_source
        return str(destination)
    monkeypatch.setattr(filedialog, 'asksaveasfilename', save_dialog)
    monkeypatch.setattr(messagebox, 'showerror', lambda *args: pytest.fail(str(args)))
    _launch('red')
    def widgets(widget):
        for child in widget.winfo_children():
            yield child
            yield from widgets(child)
    def button(text):
        return next(w for w in widgets(root) if 'text' in w.keys() and w.cget('text') == text)
    def until(predicate):
        deadline = time.monotonic() + 5
        while not predicate():
            root.update()
            if time.monotonic() > deadline:
                pytest.fail('Timed out waiting for application worker')
            time.sleep(.01)
    texts = [w.cget('text') for w in widgets(root) if 'text' in w.keys()]
    assert 'Save current output…' not in texts
    assert 'Save all outputs…' not in texts
    button('Choose directory…').invoke()
    until(lambda: str(button('Save patient…').cget('state')) == 'normal')
    notebook = next(w for w in widgets(root) if w.winfo_class() == 'TNotebook')

    def name_selected_tab(name):
        tab = root.nametowidget(notebook.select())
        entry = next(w for w in tab.winfo_children()
                     if w.winfo_class() == 'TEntry' and str(w.cget('state')) == 'normal')
        entry.insert(0, name)

    if add_to_source:
        output_box = next(w for w in widgets(root)
                          if w.winfo_class() == 'TCombobox' and ADD_TO_SOURCE in w.cget('values'))
        output_box.set(ADD_TO_SOURCE)
        name_selected_tab('PlanCFirst')
        destination = source
    button('Add output').invoke()
    name_selected_tab('PlanCAlt')
    button('Save patient…').invoke()
    until(lambda: (destination / 'plan' / 'PlanCAlt' / 'plan').exists())
    until(lambda: str(button('Save patient…').cget('state')) == 'normal')
    assert plan_metadata((destination / 'plan' / 'PlanCAlt' / 'plan').read_bytes(), 'clone')['name'] == 'PlanCAlt'
    assert (destination / 'plan' / 'PlanCAlt' / 'companion').read_bytes() == b'PlanC'
    assert (destination / 'plan' / 'PlanD' / 'plan').read_bytes() == plan_bytes('PlanD')
    assert (destination / 'CT' / 'structures').read_bytes() == b'original contours'
    assert (source / 'plan' / 'PlanC' / 'plan').read_bytes() == plan_bytes('PlanC')
    if add_to_source:
        assert (source / 'plan' / 'PlanCFirst' / 'companion').read_bytes() == b'PlanC'
        assert {path.name for path in (source / 'plan').iterdir()} == {'PlanC', 'PlanD', 'PlanCFirst', 'PlanCAlt'}


def test_manual_red_and_mode_updates_are_independent(root):
    from tkinter import ttk
    from hyperio.red_outputs import REDOutputs
    from test_applications import plan_bytes
    panel = REDOutputs(ttk.Frame(root), lambda: None)
    panel.set_plans([dict(name='PlanC', label='PlanC', member='plan/PlanC/plan', data=plan_bytes('PlanC'))])
    tab = panel.current()
    tab['manual']['Insert'] = {'mode': 'forced'}
    assert panel.prepared()[0]['mapping'] == {'Insert': {'mode': 'forced'}}
    tab['manual']['Insert']['red'] = '1.25'
    assert panel.prepared()[0]['mapping'] == {'Insert': {'mode': 'forced', 'red': 1.25}}
    tab['manual']['Insert']['red'] = 'invalid'
    with pytest.raises(ValueError):
        panel.prepared()


def test_ct_mean_copy_preserves_mode_and_stale_results_are_discarded(root):
    from types import SimpleNamespace
    from tkinter import ttk
    from hyperio.red_outputs import REDOutputs
    from test_applications import plan_bytes
    requests = []
    panel = REDOutputs(ttk.Frame(root), lambda: None)
    def calculate(tab, plan, calibration):
        panel.clear_ct_red(tab)
        requests.append(tab['generation'])
    panel.calculate = calculate
    panel.set_plans([dict(name='PlanC', label='PlanC', member='plan/PlanC/plan', data=plan_bytes('PlanC'))])
    tab = panel.current()
    tab['calibration'].set('table.DICOM3')
    panel.request_ct_red(tab)
    generation = requests[-1]
    assert panel.set_ct_red(tab, generation, {'Insert': {'mean_red': 1.23456}})
    table = tab['table']
    row = next(row for row in table.get_children() if table.item(row, 'values')[0] == 'Insert')
    tab['manual']['Insert'] = {'mode': 'filled'}
    table.identify_row = lambda _: row
    table.identify_column = lambda _: '#6'
    panel.edit_cell(tab, SimpleNamespace(x=0, y=0))
    assert panel.prepared()[0]['mapping']['Insert'] == {'mode': 'filled', 'red': 1.23456}
    tab['ct_red']['Insert'] = {'mean_red': 0.001}
    panel.edit_cell(tab, SimpleNamespace(x=0, y=0))
    assert 'Cannot copy CT mean RED' in tab['status'].get()
    assert tab['manual']['Insert']['red'] == '1.23456'
    tab['calibration'].set('other.zip')
    assert not tab['ct_red']
    assert not panel.set_ct_red(tab, generation, {'Insert': {'mean_red': 2}})
    panel.request_ct_red(tab)
    generation = requests[-1]
    tab['input'].set('another plan')
    assert not panel.set_ct_red(tab, generation, {'Insert': {'mean_red': 2}})
