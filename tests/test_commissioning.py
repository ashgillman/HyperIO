"""Regression tests for commissioning worksheet data and exports."""
import json
from pathlib import Path

import pytest

from hyperio.commissioning import (
    PROTOCOL,
    TESTS,
    case_fields,
    load_worksheet,
    make_case,
    save_worksheet,
)


def test_guideline_test_inventory_and_manual_fields():
    expected = [
        *(f'5.{number}' for number in range(1, 10)),
        '6.1', '6.2',
        *(f'7.{number}' for number in range(1, 6)),
        *(f'8.{number}' for number in range(1, 5)),
        '9',
    ]
    assert list(TESTS) == expected
    assert 'mu' not in case_fields('6.1')
    assert 'mu' not in case_fields('7.5')
    assert 'cone' in case_fields('8.2')
    assert 'field_plane' in case_fields('5.7')


def test_round_trip_and_included_export(tmp_path):
    first = make_case('5.8', {
        'name': 'Oblique example', 'shape': 'Rectangle', 'field_x_cm': '10',
        'field_y_cm': '8', 'field_plane': 'Isocentre', 'ssd_cm': '92.5',
        'mu': '125', 'depths_cm': '1.8, 12, 25', 'incidence_deg': '20',
        'image_spacing': '1 × 1 × 5', 'dose_grid_mm': '1',
        'mc_uncertainty_pct': '2', 'mc_uncertainty_mode': 'Per Control Point',
    })
    second = make_case('7.5', {'name': 'Thorax', 'reference': 'Local study E2E-1'}, included=False)
    cases = {'5.8': [first], '7.5': [second]}
    original, selected = tmp_path / 'original.json', tmp_path / 'selected.json'

    save_worksheet(original, cases)
    save_worksheet(selected, cases, included_only=True)

    assert load_worksheet(original) == cases
    assert load_worksheet(selected) == {'5.8': [first]}
    assert json.loads(selected.read_text())['protocol'] == PROTOCOL
    assert first['values']['depths_cm'] == [1.8, 12.0, 25.0]
    assert first['values']['ssd_cm'] == 92.5
    assert first['values']['mc_uncertainty_pct'] == 2


@pytest.mark.parametrize(('values', 'message'), [
    ({'ssd_cm': 'inf'}, 'finite'),
    ({'mu': '-1'}, 'greater than zero'),
    ({'depths_cm': '1,-2'}, 'nonnegative'),
    ({'incidence_deg': '90'}, 'less than 90'),
    ({'shape': 'Unknown shape'}, 'choose'),
    ({'field_x_cm': '10'}, 'field-size plane'),
    ({'image_spacing': '5'}, 'three'),
    ({'mc_uncertainty_pct': '110'}, 'at most 100'),
])
def test_invalid_values(values, message):
    with pytest.raises(ValueError, match=message):
        make_case('5.8', {'name': 'Case', **values})


def test_invalid_worksheet_is_rejected_without_replacing_existing_file(tmp_path):
    path = tmp_path / 'cases.json'
    case = make_case('5.1', {'name': 'Calibration'})
    save_worksheet(path, {'5.1': [case]})
    original = path.read_bytes()
    with pytest.raises(ValueError, match='Duplicate'):
        save_worksheet(path, {'5.1': [case, case]})
    assert path.read_bytes() == original

    document = json.loads(original)
    document['cases']['5.1'][0]['included'] = 'yes'
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match='included'):
        load_worksheet(path)


def test_build_native_patient_from_saved_templates(tmp_path):
    from hyperio.commissioning_native import build_native_patient, list_native_templates
    from hyperio.core import inspect_export

    source = Path(__file__).resolve().parents[1] / 'reference/plan-library/1~zzzInputOutputAGsuite'
    if not source.is_dir():
        pytest.skip('local native phantom fixture unavailable')
    assert 'Calculation-A' in list_native_templates(source)
    case = {
        'name': 'MPPG5_1_a', 'template': 'Calculation-A', 'confirmed': True,
        'settings': {'DOSEGRIDSIZE': 1.5, 'MCVARIANCE': 0.015, 'MCSEGMENTVARIANCE': 0.015,
                     'MCVARPERPLAN': True},
        'values': {'ssd_cm': 100},
    }
    inconsistent = {**case, 'name': 'MPPG5_1_b', 'values': {'ssd_cm': 90}}
    with pytest.raises(ValueError, match='different ssd_cm'):
        build_native_patient(source, tmp_path, 'MPPGTest', 'Commissioning^MPPG', [case, inconsistent])
    assert not list(tmp_path.iterdir())

    result = build_native_patient(source, tmp_path, 'MPPGTest', 'Commissioning^MPPG', [
        case, {**case, 'name': 'MPPG5_1_b', 'template': 'Calculation-B'},
    ])
    patient = Path(result['patient_path'])
    assert patient == tmp_path / '1~MPPGTest'
    assert sorted(p.name for p in (patient / 'plan').iterdir()) == ['MPPG5_1_a', 'MPPG5_1_b']
    report = inspect_export(patient)
    assert all(p['patient_id'] == 'MPPGTest' and p['studyset'] == 'Phantom' for p in report['plans'])
    assert report['plans'][0]['settings']['DOSEGRIDSIZE']['value'] == 1.5
    assert (patient / 'plan/MPPG5_1_a/tel.1').read_bytes() == (
        source / 'plan/Calculation-A/tel.1'
    ).read_bytes()
    assert any(n.endswith('/dose.1') for n in result['omissions'])
    assert not list(patient.rglob('dose.1'))
    with pytest.raises(FileExistsError):
        build_native_patient(source, tmp_path, 'MPPGTest', 'Commissioning^MPPG', [case])


def test_tk_edit_save_export_and_reopen(tmp_path, monkeypatch):
    tk = pytest.importorskip('tkinter')
    from tkinter import ttk

    from hyperio.commissioning_gui import CommissioningApp

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f'Tk display unavailable: {error}')

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    def apply_case(**values):
        dialog = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
        widgets = list(descendants(dialog))
        for label, value in values.items():
            field_label = next(widget for widget in widgets if isinstance(widget, ttk.Label)
                               and widget.cget('text') == label)
            position = field_label.grid_info()
            entry, = field_label.master.grid_slaves(row=position['row'], column=position['column'] + 1)
            if isinstance(entry, ttk.Combobox):
                entry.set(value)
            else:
                entry.delete(0, 'end')
                entry.insert(0, value)
        next(widget for widget in widgets if isinstance(widget, ttk.Button)
             and widget.cget('text') == 'Apply case').invoke()
        root.update()

    try:
        app = CommissioningApp(root)
        root.update()
        app.tests.selection_set('5.8')
        root.update()
        assert app.test_id == '5.8'
        app.add_case()
        apply_case(**{
            'Case name': 'Oblique field', 'Field shape': 'Rectangle', 'Field X (cm)': '10',
            'Field Y (cm)': '8', 'Field-size plane': 'Isocentre', 'SSD (cm)': '90', 'MU': '100',
        })
        first = app.selected_case()
        assert first['included'] and first['values']['name'] == 'Oblique field'
        assert app.rows.set(first['id'], 'field_x_cm') == '10.0'
        assert app.rows.set(first['id'], 'mu') == '100.0'
        app.duplicate_case()
        apply_case(**{'Case name': 'Oblique field 2', 'SSD (cm)': '95'})
        second = app.selected_case()
        assert second['id'] != first['id']
        assert second['values']['ssd_cm'] == 95
        assert second['values']['field_x_cm'] == first['values']['field_x_cm']
        app.toggle_case()
        assert not app.selected_case()['included']
        app.tests.selection_set('6.1')
        root.update()
        assert 'mu' not in app.rows['columns']
        app.tests.selection_set('5.8')
        root.update()
        assert len(app.rows.get_children()) == 2

        saved, exported = tmp_path / 'work.json', tmp_path / 'selected.json'
        monkeypatch.setattr(app, 'choose_output', lambda *_: saved)
        assert app.save()
        monkeypatch.setattr(app, 'choose_output', lambda *_: exported)
        app.export()
        assert load_worksheet(exported) == {'5.8': [first]}
        app.new()
        assert app.cases == {}
        monkeypatch.setattr('hyperio.commissioning_gui.filedialog.askopenfilename', lambda **_: str(saved))
        app.open()
        assert app.cases == {'5.8': [first, second]}
        assert len(app.rows.get_children()) == 2

        picked = []
        monkeypatch.setattr('hyperio.commissioning_gui.filedialog.askdirectory', lambda **_: str(tmp_path))
        monkeypatch.setattr('hyperio.commissioning_native.list_native_templates', lambda _: ['Reference'])
        monkeypatch.setattr(app, 'monaco_assignments', lambda *args: picked.append(args))
        app.build_monaco()
        assert picked == [(tmp_path, ['Reference'], [('5.8', first)])]
        request = app.monaco_case('5.8', first, 'Reference')
        assert request['values']['ssd_cm'] == 90
        assert request['template'] == 'Reference'
    finally:
        root.destroy()
