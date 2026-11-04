"""Exercise per-tab input selection and complete-patient saving with native Tk."""
import pytest


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


def test_red_application_saves_all_tabs_in_complete_patient(root, monkeypatch, tmp_path):
    import time
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from hyperio.gui import _launch
    from hyperio.core import plan_metadata
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
    monkeypatch.setattr(filedialog, 'asksaveasfilename', lambda **_: str(destination))
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
    button('Add output').invoke()
    # Set the new tab's output-name entry; the first tab keeps its blank name.
    notebook = next(w for w in widgets(root) if w.winfo_class() == 'TNotebook')
    tab = root.nametowidget(notebook.select())
    entry = next(w for w in tab.winfo_children() if w.winfo_class() == 'TEntry' and str(w.cget('state')) == 'normal')
    entry.insert(0, 'PlanCAlt')
    button('Save patient…').invoke()
    until(lambda: (destination / 'plan' / 'PlanCAlt' / 'plan').exists())
    until(lambda: str(button('Save patient…').cget('state')) == 'normal')
    assert plan_metadata((destination / 'plan' / 'PlanCAlt' / 'plan').read_bytes(), 'clone')['name'] == 'PlanCAlt'
    assert (destination / 'plan' / 'PlanCAlt' / 'companion').read_bytes() == b'PlanC'
    assert (destination / 'plan' / 'PlanD' / 'plan').read_bytes() == plan_bytes('PlanD')
    assert (destination / 'CT' / 'structures').read_bytes() == b'original contours'
    assert (source / 'plan' / 'PlanC' / 'plan').read_bytes() == plan_bytes('PlanC')
