"""Application workflows keep native sources intact and preserve display rows."""
import csv
import json
import zipfile
from pathlib import Path

import pytest

from hyperio.application_io import discover_plans, load_red_mapping, apply_red_mapping, save_plan_copy
from hyperio.dvh_export import display_rows, export_dvh_csv, export_dvh_xlsx


def plan_bytes(name='Example', patient='PHANTOM'):
    return (f'00d5101a\r\n\r\n{name}\r\nunknown\r\n{patient}\r\n1\r\nStudy\r\n'
            '2\r\nPatient\r\n1,2,1,1,2\r\nInsert\r\n3,1,1,0.8,9\r\n').encode()


def test_discovery_retains_duplicate_names_and_source_paths(tmp_path):
    for patient in ('A', 'B'):
        path = tmp_path / patient / 'plan' / 'Example' / 'plan'
        path.parent.mkdir(parents=True)
        path.write_bytes(plan_bytes(patient=patient))
    plans = discover_plans(tmp_path)
    assert [p['patient_id'] for p in plans] == ['A', 'B']
    assert len({p['path'] for p in plans}) == 2
    assert all('Example' in p['label'] and 'Study' in p['label'] for p in plans)


def test_red_preset_can_read_archive_without_extracting_or_changing_it(tmp_path):
    from hyperio.core import Export
    source = tmp_path / 'patient.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('plan/Example/plan', plan_bytes())
    original = source.read_bytes()
    selected, = discover_plans(source)
    with Export(source) as archive:
        data = archive.read(selected['member'])
    edited, changes, missing = apply_red_mapping(data, {'Insert': 1.1})
    assert len(changes) == 1
    assert missing == []
    destination = tmp_path / 'plan.modified'
    save_plan_copy(edited, source, destination)
    with pytest.raises(ValueError):
        save_plan_copy(edited, source, source)
    assert source.read_bytes() == original
    assert {p.name for p in tmp_path.iterdir()} == {'patient.zip', 'plan.modified'}


def test_mapping_is_exact_forces_only_matches_and_preserves_bytes(tmp_path):
    preset = tmp_path / 'preset.csv'
    preset.write_text('structure,red\nInsert,1.1\nOther,1.2\n')
    mapping = load_red_mapping(preset)
    original = plan_bytes()
    edited, changes, missing = apply_red_mapping(original, mapping)
    assert edited == original.replace(b'3,1,1,0.8,9', b'2,1,1.1000000000000001,0.8,9')
    assert [c['structure'] for c in changes] == ['Insert']
    assert missing == ['Other']
    source = tmp_path / 'plan'
    source.write_bytes(original)
    with pytest.raises(ValueError):
        save_plan_copy(edited, source, source)
    target = tmp_path / 'plan.modified'
    save_plan_copy(edited, source, target)
    with pytest.raises(FileExistsError):
        save_plan_copy(edited, source, target)
    assert source.read_bytes() == original


@pytest.mark.parametrize('rows', ['Insert,nan', 'Insert,0', 'Insert,16', 'Insert,1\nInsert,2'])
def test_mapping_rejects_bad_values_and_duplicate_names(tmp_path, rows):
    path = tmp_path / 'preset.csv'
    path.write_text('structure,red\n' + rows)
    with pytest.raises(ValueError):
        load_red_mapping(path)


def example_result():
    reference = {'dose_cgy': 100., 'volume_cm3': .5, 'volume_percent': 50.,
                 'query': {'quantity': 'dose', 'value': 100.}}
    goal = {'goal_type': 9, 'metric': 'V100cGy', 'operator': '>=', 'limit': 40.,
            'limit_unit': '%', 'tolerance': 5., 'raw': {'Dose': '100'}}
    return {'plan': '=Example', 'structures': [
        {'structure': '=Insert', 'volume_cm3': 1., 'min_dose_cgy': 10.,
         'max_dose_cgy': 200., 'mean_dose_cgy': 100., 'heterogeneity_index': 1.2,
         'percent_in_volume': 100., 'is_in_ss': True,
         'reference_requests': [reference, reference.copy()],
         'criterion_results': [{'goal': goal, 'actual': 50., 'indicator': 'green'}]}],
        'sampling': {'resolution_mm': 1}, 'dose_grid': {}, 'limitations': ['Provisional'],
        'dose_reference_point_samples': []}


def test_display_keeps_duplicate_reference_rows_without_repeating_criteria():
    rows = display_rows(example_result())
    assert len(rows) == 3
    assert rows[0][0] == '=Insert'
    assert rows[0][-1] is None  # Unverified Monaco CI stays blank.
    assert rows[1][5:8] == [.5, 50., 100.]
    assert rows[2][5:8] == [.5, 50., 100.]
    assert 'V100cGy' in rows[1][8]
    assert rows[2][8] is None


@pytest.mark.parametrize('kind,raw,actual,expected', [
    (5, {'Volume': '50'}, 120., [.5, 50., 120.]),
    (6, {'Volume': '500'}, 120., [.5, 50., 120.]),
    (9, {'Dose': '100'}, 40., [.4, 40., 100.]),
    (10, {'Dose': '100'}, .4, [.4, 40., 100.]),
])
def test_criteria_generate_reference_triplets_with_explicit_units(kind, raw, actual, expected):
    result = example_result()
    structure = result['structures'][0]
    structure['reference_requests'] = []
    criterion = structure['criterion_results'][0]
    criterion['goal'].update(goal_type=kind, raw=raw)
    criterion['actual'] = actual
    assert display_rows(result)[1][5:8] == expected


def test_csv_retains_numbers_blanks_safe_names_and_provenance(tmp_path):
    path = tmp_path / 'dvh.csv'
    sidecar = export_dvh_csv(example_result(), path, source='synthetic')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    assert rows[1][0] == "'=Insert"
    assert float(rows[1][1]) == 1
    assert rows[1][-1] == ''
    assert float(rows[2][5]) == .5
    assert float(rows[2][9]) == 50
    metadata = json.loads(sidecar.read_text())
    assert metadata['plan'] == '=Example'
    assert metadata['source'] == 'synthetic'
    assert metadata['limitations'] == ['Provisional']
    assert metadata['criterion_results'][0]['results'][0]['indicator'] == 'green'


def test_xlsx_retains_numbers_blanks_literal_names_and_formatting(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    path = tmp_path / 'DVH.xlsx'
    export_dvh_xlsx(example_result(), path, source='synthetic')
    book = openpyxl.load_workbook(path)
    sheet = book['DVH Statistics']
    assert sheet['A4'].value == '=Insert'
    assert sheet['A4'].data_type == 's'
    assert sheet['B4'].value == 1
    assert sheet['B4'].number_format == '0.000'
    assert sheet['C4'].number_format == '0.0'
    assert sheet['N4'].value is None
    assert sheet['F5'].value == .5
    assert sheet['J5'].value == 50
    assert sheet['J5'].fill.fgColor.rgb.endswith('C6EFCE')
    assert sheet.freeze_panes == 'B4'
    assert book['Provenance']['B1'].value == 'synthetic'
    assert book['Provenance']['B2'].data_type == 's'


def test_dvh_path_disambiguates_identically_named_plans(monkeypatch):
    pytest.importorskip('numpy')
    from hyperio import dvh
    monkeypatch.setattr(dvh, 'inspect_export', lambda _: {'plans': [
        {'name': 'Example', 'path': 'A/plan/Example', 'diagnostics': ['selected A']},
        {'name': 'Example', 'path': 'B/plan/Example', 'diagnostics': ['selected B']}]})
    with pytest.raises(ValueError, match='expected one uniquely named plan'):
        dvh.calculate_plan_dvh('unused', 'Example')
    with pytest.raises(ValueError, match='selected B'):
        dvh.calculate_plan_dvh('unused', 'Example', plan_path='B/plan/Example')


@pytest.mark.parametrize('layout', ['archive', 'patient_directory', 'container_directory', 'patient_root_archive'])
def test_returned_plan_calculates_and_exports_without_screenshot_values(tmp_path, layout):
    for dependency in ('numpy', 'scipy', 'shapely', 'unlzw3'):
        pytest.importorskip(dependency)
    source = Path(__file__).parents[1] / 'reference/plan-library/D291026AG.zip'
    if not source.exists():
        pytest.skip('private returned plan is local only')
    if layout != 'archive':
        patient = '1~zzzInputOutputAGsuite'
        selected_prefix = patient + '/plan/D291026AG/'
        study_prefix = patient + '/1~CT1/'
        with zipfile.ZipFile(source) as archive:
            members = {name: archive.read(name) for name in archive.namelist()
                       if not name.endswith('/') and (name.startswith(selected_prefix)
                       or (name.startswith(study_prefix) and
                           (name.endswith('.WC') or Path(name).name in ('info', 'contournames'))))}
        if layout == 'patient_root_archive':
            source = tmp_path / 'patient-root.zip'
            with zipfile.ZipFile(source, 'w') as archive:
                for name, data in members.items():
                    archive.writestr(name.split('/', 1)[1], data)
        else:
            container = tmp_path / 'export'
            for name, data in members.items():
                path = container / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            source = container / patient if layout == 'patient_directory' else container
    from hyperio.dvh import calculate_plan_dvh
    selected = next(p for p in discover_plans(source) if p['name'] == 'D291026AG')
    result = calculate_plan_dvh(source, selected['name'], plan_path=selected['path'])
    sidecar = export_dvh_csv(result, tmp_path / 'DVH.csv', source=source)
    with (tmp_path / 'DVH.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    assert len(rows[0]) == 14
    assert sum(bool(row[0]) for row in rows[1:]) == len(result['structures'])
    assert sum(bool(row[8]) for row in rows[1:]) == sum(len(s['criterion_results']) for s in result['structures'])
    assert sum(bool(row[7]) for row in rows[1:]) >= sum(len(s['reference_requests']) for s in result['structures'])
    for row in rows[1:]:
        if row[8].startswith(('V', 'D2%', 'D50%')):
            assert all(row[index] != '' for index in (5, 6, 7))
    assert all(row[-1] == '' for row in rows[1:])
    assert json.loads(sidecar.read_text())['plan_path'] == selected['path']


def test_batch_dvh_exports_and_reports_failures(tmp_path, monkeypatch):
    from hyperio import dvh_export
    plans = [
        {'path': 'a', 'patient_id': 'id', 'studyset': 'ss', 'name': 'good'},
        {'path': 'b', 'patient_id': 'id', 'studyset': 'ss', 'name': 'bad'},
        {'path': 'c', 'patient_id': 'id', 'studyset': 'ss', 'name': 'existing'},
    ]
    (tmp_path / 'id-ss-existing.xlsx').write_text('keep')
    def calculate(source, plan, boundary):
        assert boundary == 'exclude'
        if plan['path'] == 'b':
            raise ValueError('missing dose')
        return {'plan': plan['name']}
    monkeypatch.setattr(dvh_export, 'calculate_for_export', calculate)
    monkeypatch.setattr(dvh_export, 'export_dvh_xlsx',
                        lambda result, target, source: target.write_text(result['plan']))
    outcomes = dvh_export.batch_export_dvh('source.zip', plans, tmp_path, boundary='exclude')
    assert (tmp_path / 'id-ss-good.xlsx').read_text() == 'good'
    assert (tmp_path / 'id-ss-existing.xlsx').read_text() == 'keep'
    assert outcomes[0]['error'] is None
    assert 'missing dose' in outcomes[1]['error']
    assert outcomes[2]['error']


def test_batch_dvh_rejects_collisions_and_handles_unreadable(tmp_path, monkeypatch):
    from hyperio import dvh_export
    plans = [
        {'path': 'a', 'patient_id': 'id', 'studyset': 'ss', 'name': 'A/B'},
        {'path': 'b', 'patient_id': 'ID', 'studyset': 'ss', 'name': 'a_b'},
        {'path': 'c', 'error': 'unreadable'},
    ]
    monkeypatch.setattr(dvh_export, 'calculate_for_export', lambda *args: pytest.fail('collision must not calculate'))
    outcomes = dvh_export.batch_export_dvh('source', plans, tmp_path)
    assert all(item['error'] for item in outcomes)
    assert 'collision' in outcomes[0]['error']
    assert 'unreadable' in outcomes[2]['error']
    assert not list(tmp_path.iterdir())
    assert dvh_export.safe_filename_component('CON') == '_CON'
