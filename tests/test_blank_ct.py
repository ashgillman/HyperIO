"""Exercise the written CT pixels, identifiers and physical voxel coverage."""
from pathlib import Path
import json
import zipfile

import pytest
pydicom = pytest.importorskip('pydicom')
pytest.importorskip('numpy')
from hyperio.blank_ct import build_blank_ct

REFERENCE = Path(__file__).resolve().parents[1]/'reference/1~ZZZELEKTAONEHETERO.zip'


@pytest.mark.skipif(not REFERENCE.exists(), reason='source archive is local only')
def test_zero_ct_has_full_500mm_coverage_and_fresh_identifiers(tmp_path):
    result = build_blank_ct(REFERENCE, tmp_path/'blank')
    files = sorted((tmp_path/'blank/DICOM').glob('*.dcm'))
    assert len(files) == 100
    datasets = [pydicom.dcmread(p) for p in files]
    old = set(result['source']['uids'].values())
    identifiers = set()
    for i, ds in enumerate(datasets):
        assert ds.PatientID == 'zzzInputOutputAG'
        assert str(ds.PatientName) == 'zzPHYS^Ash'
        assert ds.Rows == ds.Columns == 100
        assert [float(v) for v in ds.PixelSpacing] == [5,5]
        assert float(ds.SliceThickness) == float(ds.SpacingBetweenSlices) == 5
        assert float(ds.RescaleIntercept) == 0 and float(ds.RescaleSlope) == 1
        assert ds.pixel_array.shape == (100,100)
        assert ds.pixel_array.min() == ds.pixel_array.max() == 0
        assert ds.file_meta.MediaStorageSOPInstanceUID == ds.SOPInstanceUID
        assert ds.SOPInstanceUID not in identifiers
        identifiers.add(ds.SOPInstanceUID)
        assert ds.StudyInstanceUID not in old
        assert ds.SeriesInstanceUID not in old
        assert ds.FrameOfReferenceUID not in old
        assert ds.SOPInstanceUID not in old
        assert ds.ImageType[:2] == ['DERIVED','SECONDARY']
        assert not any(e.tag.is_private for e in ds.iterall())
        assert 'PixelPaddingValue' not in ds
        assert not any(e.tag.element == 0 for e in ds)
        assert ds.SeriesInstanceUID == datasets[0].SeriesInstanceUID
        assert ds.FrameOfReferenceUID == datasets[0].FrameOfReferenceUID
        assert int(ds.InstanceNumber) == i+1
    first = [float(v) for v in datasets[0].ImagePositionPatient]
    last = [float(v) for v in datasets[-1].ImagePositionPatient]
    assert last[2] - first[2] == 495
    assert last[2]+2.5 - (first[2]-2.5) == 500
    for axis in (0,1):
        assert first[axis]+99*5+2.5 - (first[axis]-2.5) == 500
    assert result['geometry']['voxel_count'] == 1000000
    assert result['validation']['status'] == 'local_checks_passed_TPS_import_pending'
    assert json.loads((tmp_path/'blank/manifest.json').read_text()) == result
    with pytest.raises(FileExistsError):
        build_blank_ct(REFERENCE,tmp_path/'blank')
