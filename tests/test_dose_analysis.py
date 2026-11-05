"""Executable examples for native dose geometry and sampled DVH calculations.

These tests use synthetic arrays and polygons with independently known results.
Install the optional analysis dependencies to run them; the GT integration tests
in test_vmat_evidence.py additionally require the private returned archive.
"""
import base64
import json
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('scipy')
pytest.importorskip('shapely')
pytest.importorskip('unlzw3')

from hyperio import DoseGrid, DVH, FormatError, contour_slice, native_dose


def test_native_array_uses_big_endian_counts_and_physical_xyz_geometry():
    """Decode a small independently compressed fixture, then sample native mm.

    The saved array is ordered (y, z, x), while public coordinates are (x,y,z).
    Noncubic dimensions and different spacings catch accidental axis swaps.
    """
    fixture = json.loads((Path(__file__).parent / 'fixtures/native-dose-small.json').read_text())
    grid = native_dose(base64.b64decode(fixture['data_base64']), 'synthetic/dose.1')
    assert grid.values_cgy.shape == (2, 3, 4)
    assert grid.origin_xyz_mm == (-1, 10, 2)
    assert grid.spacing_xyz_mm == (2, 3, 4)
    np.testing.assert_allclose(grid.values_cgy, np.arange(24).reshape(2, 3, 4) / 10)
    assert grid.sample([5, 13, 10]) == pytest.approx(2.3)
    assert grid.sample([0, 11.5, 4]) == pytest.approx(.85)
    assert grid.metadata['codec'] == 'unlzw3 (.Z header adapter)'
    with pytest.raises(FormatError, match='truncated'):
        native_dose(base64.b64decode(fixture['data_base64'])[:-20])


def test_trilinear_sampling_reproduces_an_affine_field_and_rejects_extrapolation():
    """An affine dose field must interpolate exactly between all eight neighbors."""
    y, z, x = np.indices((3, 4, 5))
    values = 2 * x + 3 * y + 5 * z
    grid = DoseGrid(values, (10, -20, 30), (2, 4, 6))
    assert grid.sample([11, -18, 33]) == pytest.approx(5)
    with pytest.raises(ValueError, match='outside'):
        grid.sample([9, -20, 30])
    assert np.isnan(grid.sample([9, -20, 30], outside='nan'))


def test_contour_reader_retains_polygon_count_slice_coordinate_and_tail():
    """Read x/z polygon vertices at a named y slice without discarding the tail."""
    data = (b'00091013\nSynthetic slice\n0\n0,0,0\n0,0,2,2\n0,0,10\n'
            b'1,0,0,0,1,0\n4\n7\n0,0,2,0,2,2,0,2\n0\nBart\n')
    parsed = contour_slice(data, 'T.10.WC')
    assert parsed['y_mm'] == 10
    assert parsed['polygons'][0]['structure_index'] == 7
    assert parsed['polygons'][0]['points_xz_mm'] == [[0, 0], [2, 0], [2, 2], [0, 2]]
    assert parsed['unparsed_tail'] == ['0', 'Bart']
    with pytest.raises(FormatError, match='point count'):
        contour_slice(data.replace(b'4\n7', b'5\n7'), 'T.10.WC')


def test_dvh_preserves_raw_statistics_and_exposes_a_separate_binned_curve():
    """Raw min/max/mean and histogram-based Dx/Vx are distinct quantities.

    Four samples at 0,10,20,30 cGy occupy four mm³ at 1 mm sampling.
    Histogram counts are cumulative at each interval's midpoint.
    """
    dvh = DVH(np.array([0., 10., 20., 30.]), resolution_mm=1, bin_width_cgy=10)
    assert dvh.statistics['volume_cm3'] == .004
    assert dvh.statistics['mean_dose_cgy'] == 15
    assert dvh.statistics['min_dose_cgy'] == 0
    assert dvh.statistics['max_dose_cgy'] == 30
    assert dvh.volume_at_dose(25) == 50
    assert dvh.volume_at_dose(25, absolute=True) == .002
    assert dvh.dose_at_volume(50) == 25
    assert dvh.volume_at_dose(100) == 0
    with pytest.raises(ValueError):
        dvh.dose_at_volume(101)


def test_dvh_uses_half_open_intervals_and_midpoint_dose_coordinates():
    """Dose intervals include their lower edge; half bins never use ties-to-even.

    At width 2, [0,2), [2,4), [4,6) contain 3, 1, 1 samples.
    Their midpoint coordinates are 1, 3, 5 cGy and the cumulative counts
    are 5, 2, 1, followed by a zero-count sentinel at 7 cGy.
    """
    dvh = DVH([0., 1., 1.99, 2., 4.], bin_width_cgy=2)
    np.testing.assert_array_equal(dvh.counts, [3, 1, 1, 0])
    np.testing.assert_array_equal(dvh.dose_axis_cgy, [1, 3, 5, 7])
    np.testing.assert_array_equal(dvh.cumulative_counts, [5, 2, 1, 0])
    assert dvh.dose_at_volume(50) == pytest.approx(8 / 3)
    assert dvh.volume_at_dose(2) == 70
    assert dvh.statistics['mean_dose_cgy'] == pytest.approx(1.798)


def test_dvh_quantiles_stay_within_raw_extrema_even_with_wide_bins():
    """Interpolating a binned tail must not exceed the actual sampled range."""
    dvh = DVH([10., 10.1, 10.2], bin_width_cgy=5)
    for percent in [0, .01, 1, 50, 99, 100]:
        assert 10 <= dvh.dose_at_volume(percent) <= 10.2


def test_contour_boundary_policy_changes_raw_volume_and_mean_before_binning():
    """Two square contours span disjoint [0,2), [2,4) nearest-slice slabs.

    Including the square's edges selects x,z = 1,2,3 on four y planes;
    excluding them selects only x=z=2 on those same four planes.
    Dose is x² on grid nodes, so the means follow directly from 1,4,9.
    """
    from hyperio.dvh import _structure_samples
    _, _, x = np.indices((5, 5, 5))
    grid = DoseGrid(x ** 2, (0, 0, 0), (1, 1, 1))
    polygon = {'structure_index': 1, 'points_xz_mm': [[1, 1], [3, 1], [3, 3], [1, 3]]}
    slices = [{'y_mm': y, 'polygons': [polygon]} for y in [1, 3]]
    included, total = _structure_samples(grid, slices, 1, 1, 'include', 100)
    excluded, interior = _structure_samples(grid, slices, 1, 1, 'exclude', 100)
    assert len(included) == total == 36
    assert len(excluded) == interior == 4
    assert DVH(included).statistics['mean_dose_cgy'] == pytest.approx(14 / 3)
    assert DVH(excluded).statistics['mean_dose_cgy'] == 4


def test_unity_native_dose_profile_has_no_timestamp_and_keeps_geometry_and_scaling():
    fixture = json.loads((Path(__file__).parent / 'fixtures/native-dose-small.json').read_text())
    original = base64.b64decode(fixture['data_base64'])
    _, _, body = original.split(b'\n', 2)
    data = b'00be301e\n' + body
    grid = native_dose(data, 'unity/dose.1')
    assert grid.metadata['format_version'] == '00be301e'
    assert len(grid.metadata['raw_header']) == 38
    assert grid.origin_xyz_mm == (-1, 10, 2)
    assert grid.spacing_xyz_mm == (2, 3, 4)
    np.testing.assert_allclose(grid.values_cgy, np.arange(24).reshape(2, 3, 4) / 10)
    assert grid.sample([0, 11.5, 4]) == pytest.approx(.85)
    with pytest.raises(FormatError, match='header profile'):
        native_dose(data.replace(b'00be301e', b'ffffffff', 1))
    with pytest.raises(FormatError, match='truncated'):
        native_dose(data[:-20])


def test_unity_contour_slice_uses_same_polygon_records():
    data = (b'00071013\nSlice\n0\n0,0,0\n0,0,2,2\n0,0,10\n'
            b'1,0,0,0,1,0\n4\n7\n0,0,2,0,2,2,0,2\n0\nBart\n')
    parsed = contour_slice(data, 'T.10.WC')
    assert parsed['polygons'][0]['structure_index'] == 7
    assert parsed['polygons'][0]['points_xz_mm'] == [[0, 0], [2, 0], [2, 2], [0, 2]]
    assert parsed['unparsed_tail'] == ['0', 'Bart']


@pytest.mark.parametrize('all_invalid', [False, True])
def test_dvh_reports_failed_structures_and_keeps_other_complete_dvhs(tmp_path, monkeypatch, all_invalid):
    from hyperio import core, dvh
    from hyperio.dvh_export import export_dvh_csv, export_dvh_xlsx
    from openpyxl import load_workbook
    import csv

    study = tmp_path / 'Patient/1~CT'
    study.mkdir(parents=True)
    plan_path = 'Patient/plan/Test'
    (tmp_path / plan_path).mkdir(parents=True)
    (tmp_path / plan_path / 'dose.1').write_bytes(b'synthetic')
    square = '1,1,3,1,3,3,1,3'
    crossing = '1,1,3,3,1,3,3,1'
    for y in (1, 3):
        # Bad has a valid earlier slice: none of it may become a partial DVH.
        bad = square if y == 1 else crossing
        good = crossing if all_invalid else square
        (study / f'T.{y}.WC').write_text(
            '00071013\nSynthetic\n0\n0,0,0\n0,0,4,4\n0,0,0\n1,0,0,0,1,0\n'
            f'4\n1\n{bad}\n4\n2\n{good}\n')
    settings = {'structures': [{'structure': name, 'enabled': True} for name in ('Bad', 'Good')],
                'dose_goals': []}
    plan = {'name': 'Test', 'path': plan_path, 'studyset': 'CT', 'diagnostics': [],
            'dvh_parameters': {'resolution_mm': 1, 'bin_width_cgy': 1},
            'isodose_settings': settings, 'beams': [{'isocentre_raw': [0, 0, 0]}],
            'dose_reference_points': []}
    monkeypatch.setattr(dvh, 'inspect_export', lambda *args, **kwargs: {'plans': [plan]})
    monkeypatch.setattr(core, 'study_metadata', lambda *args: {
        'diagnostics': [], 'structures': [{'name': 'Bad', 'index': 1}, {'name': 'Good', 'index': 2}]})
    monkeypatch.setattr(dvh, 'native_dose', lambda *args: DoseGrid(np.ones((5, 5, 5)), (0, 0, 0), (1, 1, 1)))
    result = dvh.calculate_plan_dvh(tmp_path, 'Test', include_conformity=True)
    assert [row['structure'] for row in result['structures']] == ([] if all_invalid else ['Good'])
    if not all_invalid:
        assert result['structures'][0]['volume_cm3'] == .036
        assert result['structures'][0]['mean_dose_cgy'] == 1
    assert len(result['structure_failures']) == (2 if all_invalid else 1)
    failure = result['structure_failures'][0]
    assert failure['structure'] == 'Bad'
    assert 'T.3.WC:8' in failure['message']
    assert 'Self-intersection' in failure['message']
    assert all(row['severity'] == 'WARN' for row in result['diagnostics'])
    assert 'Bad' in result['diagnostics'][0]['message']
    sidecar = export_dvh_csv(result, tmp_path / 'result.csv')
    assert json.loads(sidecar.read_text())['structure_failures'] == result['structure_failures']
    with (tmp_path / 'result.csv').open(encoding='utf-8-sig') as stream:
        rows = list(csv.reader(stream))
    failed_row = next(row for row in rows[1:] if row[0] == 'Bad')
    assert failed_row[1:8] == [''] * 7
    assert 'DVH unavailable' in failed_row[8]
    export_dvh_xlsx(result, tmp_path / 'result.xlsx')
    book = load_workbook(tmp_path / 'result.xlsx')
    assert ('WARN', result['diagnostics'][0]['message']) in list(book['Provenance'].values)
    assert 'failed' in book['DVH Statistics']['A2'].value
    book.close()
