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
    Histogram counts are cumulative at each bin's dose coordinate.
    """
    dvh = DVH(np.array([0., 10., 20., 30.]), resolution_mm=1, bin_width_cgy=10)
    assert dvh.statistics['volume_cm3'] == .004
    assert dvh.statistics['mean_dose_cgy'] == 15
    assert dvh.statistics['min_dose_cgy'] == 0
    assert dvh.statistics['max_dose_cgy'] == 30
    assert dvh.volume_at_dose(20) == 50
    assert dvh.volume_at_dose(20, absolute=True) == .002
    assert dvh.dose_at_volume(50) == 20
    assert dvh.volume_at_dose(100) == 0
    with pytest.raises(ValueError):
        dvh.dose_at_volume(101)
