"""Validate depot relationships against the complete user-supplied working archive."""
from pathlib import Path
import io
import json
import pytest
pydicom=pytest.importorskip('pydicom')
pytest.importorskip('numpy')
from hyperio.depot_layout import inspect_working_depot, package_working_layout

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'reference/Monthly QC.zip'


@pytest.mark.skipif(not FIXTURE.exists(),reason='working depot supplied locally')
def test_real_fixture_establishes_uid_order_study_id_and_image_index():
    result=inspect_working_depot(FIXTURE)
    assert result['image_count']==130
    assert result['field_mapping_one_based']['4']=='SeriesInstanceUID'
    assert result['field_mapping_one_based']['5']=='StudyInstanceUID'
    assert result['field_mapping_one_based']['6']=='StudyID'
    assert result['image_filename_pattern']=='CT_<SOPInstanceUID>'
    assert result['image_index_pattern']=='CT_<SeriesInstanceUID>.dir'
    assert result['image_encoding']=='raw_implicit_VR_little_endian'


@pytest.mark.skipif(not FIXTURE.exists(),reason='local fixtures required')
def test_repackaged_depot_matches_proven_layout_and_preserves_image_semantics(tmp_path, zero_ct_candidate):
    SOURCE=zero_ct_candidate
    result=package_working_layout(SOURCE,tmp_path/'out',FIXTURE)
    patient=tmp_path/'out/zzzInputOutputAG'
    original=json.loads((SOURCE/'manifest.json').read_text())
    rows=(patient/'RTDIR.dir').read_text().splitlines()
    assert not (patient/'.rtDir').exists()
    assert rows[3]==original['uids']['SeriesInstanceUID']
    assert rows[4]==original['uids']['StudyInstanceUID']
    assert rows[5]=='HIOZERO001'
    uids=(patient/f'CT_{rows[3]}.dir').read_text().splitlines()
    assert len(uids)==len(set(uids))==100
    first=pydicom.dcmread(SOURCE/'DICOM/CT_001.dcm')
    assert uids[0]==str(first.SOPInstanceUID)
    assert list(map(float,rows[8:11]))==list(map(float,first.ImagePositionPatient))
    assert len(list(patient.iterdir()))==102
    for source_image in (SOURCE/'DICOM').glob('*.dcm'):
        old=pydicom.dcmread(source_image)
        raw=(patient/f'CT_{old.SOPInstanceUID}').read_bytes()
        assert raw[:4]==b'\x08\x00\x05\x00'
        new=pydicom.dcmread(io.BytesIO(raw),force=True)
        assert new.original_encoding==(True,True)
        assert not new.file_meta
        assert str(old.SOPInstanceUID)==str(new.SOPInstanceUID)
        assert old.PixelData==new.PixelData
        assert old.ImagePositionPatient==new.ImagePositionPatient
        assert old.ImageOrientationPatient==new.ImageOrientationPatient
        assert old.Rows==new.Rows==100 and old.Columns==new.Columns==100
        assert old.PixelSpacing==new.PixelSpacing
        # Raw depot datasets have no file-meta header; supply the established encoding in memory for pixel interpretation.
        new.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
        assert new.pixel_array.min()==new.pixel_array.max()==0
    assert result['validation']['monaco_import'] is None
    with pytest.raises(FileExistsError):
        package_working_layout(SOURCE,tmp_path/'out',FIXTURE)
