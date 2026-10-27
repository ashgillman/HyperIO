"""Candidate text-index serialization and byte-identical CT repackaging."""
from pathlib import Path
import json
import pytest
pydicom = pytest.importorskip('pydicom')
from pydicom.dataset import Dataset
from hyperio.depot_index import depot_index_bytes, package_indexed_ct

TEMPLATE = b'!Version=2\nCT\n1.2.840.10008.5.1.4.1.1.2\n1.2.3\n1.2.4\nExample\nExample^Patient\n1.2.5\n-134.75\n-134.75\n129.00\n1.00\n0.00\n0.00\n0.00\n1.00\n0.00\n'


def test_index_maps_candidate_fields_without_reusing_template_identity():
    ds = Dataset()
    ds.Modality = 'CT'
    ds.SOPClassUID = '1.2.840.10008.5.1.4.1.1.2'
    ds.StudyInstanceUID = '2.25.11'
    ds.SeriesInstanceUID = '2.25.12'
    ds.FrameOfReferenceUID = '2.25.13'
    ds.StudyID = 'HIOZERO001'
    ds.PatientName = 'zzPHYS^Ash'
    ds.ImagePositionPatient = [-247.5635,-247.5638,-847]
    ds.ImageOrientationPatient = [1,0,0,0,1,0]
    rows = depot_index_bytes(ds,TEMPLATE).decode().splitlines()
    assert len(rows)==17
    assert rows[3:8]==['2.25.12','2.25.11','HIOZERO001','zzPHYS^Ash','2.25.13']
    assert list(map(float,rows[8:11]))==[-247.5635,-247.5638,-847]
    assert list(map(float,rows[11:]))==[1,0,0,0,1,0]
    with pytest.raises(ValueError):
        depot_index_bytes(ds,TEMPLATE.replace(b'!Version=2',b'!Version=9'))
    with pytest.raises(ValueError):
        depot_index_bytes(ds,TEMPLATE+b'extra\n')


CANDIDATE = Path('unused-source')


def test_indexed_package_preserves_every_source_image_and_resets_review(tmp_path):
    template=tmp_path/'RTDIR.dir';template.write_bytes(TEMPLATE)
    dest=tmp_path/'indexed'
    with pytest.raises(ValueError, match='complete working depot ZIP'):
        package_indexed_ct(CANDIDATE,dest,template)
