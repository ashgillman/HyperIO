"""Application workflows keep native sources intact and preserve display rows."""
import csv
import json
import os
import zipfile
from pathlib import Path

import pytest

from hyperio.application_io import discover_plans, load_red_mapping, apply_red_mapping, save_plan_copy
from hyperio.dvh_export import display_rows, export_dvh_csv, export_dvh_xlsx


def test_named_red_outputs_start_from_original_and_preserve_header_bytes():
    from hyperio.application_io import prepare_red_output
    from hyperio.core import plan_metadata
    original = plan_bytes()
    first, _, _ = prepare_red_output(original, {'Insert': 1.1}, 'Example RED')
    second, changes, _ = prepare_red_output(original, {}, 'Example retained')
    assert plan_metadata(first, 'first')['name'] == 'Example RED'
    assert second == original.replace(b'Example\r\n', b'Example retained\r\n', 1)
    assert changes == []
    assert plan_metadata(second, 'second')['density_overrides'][0]['uniform_ed'] == 1
    assert original == plan_bytes()
    assert prepare_red_output(original, {}, 'Example')[0] == original


@pytest.mark.parametrize('name', ['', ' ', 'bad\nname', 'bad\rname', 'bad\tname',
                                  'bad/name', 'bad\\name', '..', 'CON', 'name.', '😀'])
def test_red_output_rejects_unsafe_plan_names(name):
    from hyperio.application_io import prepare_red_output
    with pytest.raises(ValueError):
        prepare_red_output(plan_bytes(), {}, name)


@pytest.mark.parametrize('source_zip', [False, True])
@pytest.mark.parametrize('output_zip', [False, True])
@pytest.mark.parametrize('header', [b'00d5101a', b'00be101a'])
def test_red_patient_export_replaces_and_clones_from_original(tmp_path, source_zip, output_zip, header):
    from hyperio.application_io import export_red_patient
    from hyperio.core import Export, plan_metadata
    members = {}
    for name, study in [('PlanA', 'CT1'), ('PlanB', 'CT1'), ('PlanC', 'CT2'), ('PlanD', 'CT2')]:
        prefix = f'Patient/plan/{name}/'
        members[prefix + 'plan'] = plan_bytes(name).replace(b'Study', study.encode()).replace(b'00d5101a', header)
        members[prefix + 'patient.hyp'] = b'original settings'
        members[prefix + 'dose.1'] = b'original dose'
    members['Patient/CT1/structures'] = b'CT1 structures'
    members['Patient/CT2/structures'] = b'CT2 structures'
    source = tmp_path / ('source.zip' if source_zip else 'source')
    if source_zip:
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('Patient/plan/PlanC/empty/', b'')
            for member, data in members.items():
                archive.writestr(member, data)
    else:
        for member, data in members.items():
            target = source / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (source / 'Patient/plan/PlanC/empty').mkdir()
    destination = tmp_path / ('output.zip' if output_zip else 'output')
    edits = [dict(member='Patient/plan/PlanC/plan', name='', mapping={'Insert': 1.1}),
             dict(member='Patient/plan/PlanC/plan', name='PlanCAlt', mapping={'Insert': 1.2})]
    export_red_patient(source, edits, destination, zipped=output_zip)
    if output_zip:
        with zipfile.ZipFile(destination) as archive:
            assert 'Patient/plan/PlanC/empty/' in archive.namelist()
            assert 'Patient/plan/PlanCAlt/empty/' in archive.namelist()
    else:
        assert (destination / 'Patient/plan/PlanC/empty').is_dir()
        assert (destination / 'Patient/plan/PlanCAlt/empty').is_dir()
    with Export(destination) as output:
        for member, data in members.items():
            if member != 'Patient/plan/PlanC/plan':
                assert output.read(member) == data
        for name, red in [('PlanC', 1.1), ('PlanCAlt', 1.2)]:
            prefix = f'Patient/plan/{name}/'
            assert output.read(prefix + 'plan').splitlines()[0] == header
            metadata = plan_metadata(output.read(prefix + 'plan'), prefix)
            assert metadata['name'] == name
            assert metadata['studyset'] == 'CT2'
            assert next(r for r in metadata['density_overrides'] if r['name'] == 'Insert')['uniform_ed'] == red
            assert output.read(prefix + 'patient.hyp') == b'original settings'
            assert output.read(prefix + 'dose.1') == b'original dose'
        assert len(output.sizes) == len(members) + 3
    with Export(source) as original:
        assert {member: original.read(member) for member in original.sizes} == members
    with pytest.raises(FileExistsError):
        export_red_patient(source, edits, destination, zipped=output_zip)


def test_red_patient_export_rejects_conflicts_and_nested_output(tmp_path):
    from hyperio.application_io import export_red_patient
    source = tmp_path / 'source'
    for name in ('PlanC', 'PlanD'):
        path = source / 'plan' / name / 'plan'
        path.parent.mkdir(parents=True)
        path.write_bytes(plan_bytes(name))
    edit = dict(member='plan/PlanC/plan', name='', mapping={'Insert': 1.1})
    destination = tmp_path / 'output'
    for edits in ([edit, edit], [dict(edit, name='PlanD')], [dict(edit, name='planc')],
                  [dict(edit, name='../bad')], [dict(edit, member='plan/missing/plan')]):
        with pytest.raises((ValueError, KeyError)):
            export_red_patient(source, edits, destination)
        assert not destination.exists()
    with pytest.raises(ValueError, match='outside'):
        export_red_patient(source, [edit], source / 'output')


@pytest.mark.parametrize('zipped', [False, True])
def test_red_patient_export_copy_failure_does_not_publish_partial_patient(tmp_path, monkeypatch, zipped):
    from hyperio.application_io import export_red_patient
    from hyperio.core import Export
    source = tmp_path / 'source'
    plan = source / 'plan/Example/plan'
    plan.parent.mkdir(parents=True)
    plan.write_bytes(plan_bytes())
    (source / 'CT').write_bytes(b'CT data')
    original_open = Export.open
    def broken_open(self, name):
        if name == 'CT':
            raise OSError('copy failed')
        return original_open(self, name)
    monkeypatch.setattr(Export, 'open', broken_open)
    destination = tmp_path / ('output.zip' if zipped else 'output')
    with pytest.raises(OSError, match='copy failed'):
        export_red_patient(source, [dict(member='plan/Example/plan', name='', mapping={})],
                           destination, zipped=zipped)
    assert not destination.exists()
    assert not list(tmp_path.glob('.hyperio-red-*'))


def plan_bytes(name='Example', patient='PHANTOM'):
    return (f'00d5101a\r\n\r\n{name}\r\nunknown\r\n{patient}\r\n1\r\nStudy\r\n'
            '2\r\nPatient\r\n1,2,1,1,2\r\nInsert\r\n3,1,1,0.8,9\r\n').encode()


def test_unity_header_discovery_and_red_edit_preserve_other_bytes(tmp_path):
    original = plan_bytes().replace(b'00d5101a', b'00be101a')
    path = tmp_path / 'plan/Example/plan'
    path.parent.mkdir(parents=True)
    path.write_bytes(original)
    selected, = discover_plans(tmp_path)
    assert selected['error'] is None
    assert selected['name'] == 'Example'
    assert selected['studyset'] == 'Study'
    edited, changes, missing = apply_red_mapping(original, {'Insert': 1.25})
    assert edited == original.replace(b'3,1,1,0.8,9', b'2,1,1.25,0.8,9')
    assert len(changes) == 1
    assert missing == []
    assert path.read_bytes() == original


@pytest.mark.parametrize('header,prescriptions', [(b'ffffffff', b'1'), (b'00be101a', b'2')])
def test_red_discovery_rejects_unknown_header_and_multiple_prescriptions(tmp_path, header, prescriptions):
    data = plan_bytes().replace(b'00d5101a', header).replace(b'PHANTOM\r\n1\r\n', b'PHANTOM\r\n' + prescriptions + b'\r\n')
    path = tmp_path / 'plan/Example/plan'
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    selected, = discover_plans(tmp_path)
    assert selected['error']


def test_red_mapping_rejects_only_matched_duplicate_names():
    from hyperio.core import FormatError
    original = plan_bytes().replace(b'Patient\r\n', b'Insert\r\n')
    assert apply_red_mapping(original, {}) == (original, [], [])
    assert apply_red_mapping(original, {'Absent': 1.25}) == (original, [], ['Absent'])
    with pytest.raises(FormatError, match='Duplicate.*Insert'):
        apply_red_mapping(original, {'Insert': 1.25})


UNITY_EXAMPLE = Path(os.environ.get('HYPERIO_UNITY_EXAMPLE', 'reference/1~cellIrrad.zip'))


@pytest.mark.skipif(not UNITY_EXAMPLE.is_file(), reason='local Unity phantom archive is not distributed')
def test_supplied_unity_plans_discover_and_edit_only_density_tokens():
    from hyperio.application_io import load_red_plans, prepare_red_output
    from hyperio.core import plan_metadata
    plans = load_red_plans(UNITY_EXAMPLE)
    assert {p.get('name') for p in plans} == {'Cells1', 'CellTesting', 'CraneR', 'test', 'WaterandAir'}
    for plan in plans:
        assert plan['error'] is None
        original = plan['data']
        assert original.splitlines()[0] == b'00be101a'
        records = plan['density_overrides']
        assert records
        # Exercise each actual record, comparing against the original byte rows
        # independently of the metadata reader's interpretation of the edit.
        for record in records:
            if sum(r['name'] == record['name'] for r in records) > 1:
                from hyperio.core import FormatError
                with pytest.raises(FormatError, match='Duplicate.*patient'):
                    prepare_red_output(original, {record['name']: 1.25}, plan['name'])
                continue
            edited, changes, missing = prepare_red_output(original, {record['name']: 1.25}, plan['name'])
            expected = original.splitlines(keepends=True)
            index = record['source']['line'] - 1
            tokens = expected[index].split(b',')
            tokens[0], tokens[2] = b'2', b'1.25'
            expected[index] = b','.join(tokens)
            assert edited == b''.join(expected)
            assert len(changes) == 1 and missing == []
            result = plan_metadata(edited, plan['member'])
            updated = next(r for r in result['density_overrides'] if r['name'] == record['name'])
            assert updated['mode'] == 'forced' and updated['uniform_ed'] == 1.25


def test_discovery_retains_duplicate_names_and_source_paths(tmp_path):
    for patient in ('A', 'B'):
        path = tmp_path / patient / 'plan' / 'Example' / 'plan'
        path.parent.mkdir(parents=True)
        path.write_bytes(plan_bytes(patient=patient))
    plans = discover_plans(tmp_path)
    assert [p['patient_id'] for p in plans] == ['A', 'B']
    assert len({p['path'] for p in plans}) == 2
    assert all('Example' in p['label'] and 'Study' in p['label'] for p in plans)


@pytest.mark.parametrize('zipped', [False, True])
def test_lazy_discovery_reads_only_bounded_identity_headers(tmp_path, monkeypatch, zipped):
    from hyperio.core import Export
    data = plan_bytes().split(b'2\r\nPatient')[0] + b'x' * 100_000
    source = tmp_path / ('source.zip' if zipped else 'source')
    if zipped:
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('plan/Example/plan', data)
            archive.writestr('images/ct.dcm', b'unread image')
    else:
        path = source / 'plan/Example/plan'
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        image = source / 'images/ct.dcm'
        image.parent.mkdir()
        image.write_bytes(b'unread image')
    monkeypatch.setattr(Export, 'read', lambda *a, **k: pytest.fail('full read during discovery'))
    original_open = Export.open
    reads = []
    class HeaderStream:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def readline(self, limit):
            assert limit == 4096
            row = self.stream.readline(limit)
            reads.append(row)
            return row
    def open_header(export, member):
        assert member == 'plan/Example/plan'
        return HeaderStream(original_open(export, member))
    monkeypatch.setattr(Export, 'open', open_header)
    original_stat = Path.stat
    def stat(path, *args, **kwargs):
        assert path.name not in ('ct.dcm', 'plan'), 'file stat during discovery'
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    selected, = discover_plans(source, lazy=True)
    assert selected['name'] == 'Example'
    assert selected['error'] is None
    assert 'density_overrides' not in selected
    assert len(reads) == 7
    assert sum(map(len, reads)) < 100


def test_scoped_inspection_does_not_read_other_plans_or_studies(tmp_path, monkeypatch):
    from hyperio.core import Export, inspect_export
    for patient in ('A', 'B'):
        path = tmp_path / patient / 'plan/Example/plan'
        path.parent.mkdir(parents=True)
        path.write_bytes(plan_bytes(patient=patient))
        study = tmp_path / patient / '1~Study/contournames'
        study.parent.mkdir()
        study.write_bytes(b'unsupported')
    original = Export.read
    def read(export, member, *args, **kwargs):
        assert member.startswith('B/')
        return original(export, member, *args, **kwargs)
    monkeypatch.setattr(Export, 'read', read)
    result = inspect_export(tmp_path, plan_path='B/plan/Example')
    assert [p['patient_id'] for p in result['plans']] == ['B']
    assert [s['path'] for s in result['studysets']] == ['B/1~Study']


def test_export_reuses_structure_order_from_calculation(monkeypatch):
    from hyperio import core, dvh
    from hyperio.dvh_export import calculate_for_export
    monkeypatch.setattr(core, 'inspect_export', lambda *a, **k: pytest.fail('repeated inspection'))
    def calculate(source, name, **kwargs):
        assert kwargs == {'plan_path': 'plan/Example', 'boundary': 'exclude'}
        return {'structures': [{'structure': 'B'}, {'structure': 'A'}],
                'structure_order': ['A', 'B']}
    monkeypatch.setattr(dvh, 'calculate_plan_dvh', calculate)
    result = calculate_for_export('source', {'name': 'Example', 'path': 'plan/Example'}, 'exclude')
    assert [row['structure'] for row in result['structures']] == ['A', 'B']


@pytest.mark.parametrize('data', [b'00d5101a\n', plan_bytes().replace(b'Example', b'x' * 5000)])
def test_lazy_discovery_rejects_truncated_or_overlong_headers(tmp_path, data):
    path = tmp_path / 'plan/Example/plan'
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    selected, = discover_plans(tmp_path, lazy=True)
    assert selected['error']


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


def test_plot_curve_and_cursor_preserve_histogram_interpolation_and_units():
    pytest.importorskip('numpy')
    from hyperio.dvh import DVH
    from hyperio.dvh_plot import cursor_point
    histogram = DVH([0., 10., 20., 30.], resolution_mm=2, bin_width_cgy=10)
    curve = histogram.curve
    assert curve['dose_cgy'] == [0., 5., 15., 25., 35., 45.]
    structure = {'volume_cm3': histogram.statistics['volume_cm3'], 'dvh_curve': curve}
    for dose in (0, 7.3, 25, 45, 100):
        point = cursor_point(structure, dose, 50)
        assert point['volume_percent'] == pytest.approx(histogram.volume_at_dose(dose))
        assert point['volume_cm3'] == pytest.approx(histogram.volume_at_dose(dose, absolute=True))
        assert point['dose_percent'] == pytest.approx(dose * 2)
    assert cursor_point(structure, 25)['dose_percent'] is None
    for invalid in (0, -1, float('nan'), float('inf')):
        with pytest.raises(ValueError, match='prescription'):
            cursor_point(structure, 25, invalid)


@pytest.mark.parametrize('entry,expected', [
    ('60', 6000.), ('2.5', 250.), ('', None), ('invalid', None),
    ('0', None), ('-1', None), ('nan', None), ('inf', None), ('1e308', None),
])
def test_plot_prescription_accepts_gy_and_normalizes_cgy(entry, expected):
    from types import SimpleNamespace
    from hyperio.dvh_plot import DVHPlot, cursor_point
    plot = DVHPlot.__new__(DVHPlot)
    plot.rx = SimpleNamespace(get=lambda: entry)
    assert plot.prescription() == expected
    if expected is not None:
        structure = {'volume_cm3': 1., 'dvh_curve': {
            'dose_cgy': [0., expected * 2], 'volume_percent': [100., 0.]}}
        assert cursor_point(structure, expected, plot.prescription())['dose_percent'] == 100.


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
    monkeypatch.setattr(dvh, 'inspect_export', lambda _, **kwargs: {'plans': [
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
    from hyperio.dvh_plot import cursor_point
    selected = next(p for p in discover_plans(source) if p['name'] == 'D291026AG')
    result = calculate_plan_dvh(source, selected['name'], plan_path=selected['path'])
    for structure in result['structures']:
        curve = structure['dvh_curve']
        assert len(curve['dose_cgy']) == len(curve['volume_percent'])
        assert curve['volume_percent'][0] == 100
        assert curve['volume_percent'][-1] == 0
        for reference in structure['reference_requests']:
            if reference['query']['quantity'] == 'dose':
                point = cursor_point(structure, reference['dose_cgy'])
                assert point['volume_percent'] == pytest.approx(reference['volume_percent'])
                assert point['volume_cm3'] == pytest.approx(reference['volume_cm3'])
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
