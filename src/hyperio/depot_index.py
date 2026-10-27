"""Monaco depot index fields checked against the complete supplied Monthly QC fixture."""
from __future__ import annotations
from pathlib import Path


def depot_index_bytes(dataset, template: bytes) -> bytes:
    """Retain the field layout observed against labelled DICOM headers in Monthly QC."""
    rows = template.decode('ascii').splitlines()
    if (len(rows)!=17 or rows[:3]!=['!Version=2','CT','1.2.840.10008.5.1.4.1.1.2']):
        raise ValueError('expected the supplied 17-line CT !Version=2 index layout')
    from pydicom.uid import UID
    if not all(UID(rows[i]).is_valid for i in (3,4,7)):
        raise ValueError('invalid UID in depot index specimen')
    list(map(float,rows[8:]))
    if str(dataset.Modality)!='CT' or str(dataset.SOPClassUID)!=rows[2]:
        raise ValueError('index profile supports classic CT only')
    values = ['!Version=2','CT',str(dataset.SOPClassUID),
        str(dataset.SeriesInstanceUID),str(dataset.StudyInstanceUID),
        str(dataset.StudyID),str(dataset.PatientName),str(dataset.FrameOfReferenceUID)]
    values += [format(float(v),'.15g') for v in dataset.ImagePositionPatient]
    values += [format(float(v),'.15g') for v in dataset.ImageOrientationPatient]
    if len(values)!=17 or any('\n' in v or '\r' in v for v in values):
        raise ValueError('metadata cannot be represented by a single 17-line index')
    newline = '\r\n' if b'\r\n' in template else '\n'
    return (newline.join(values)+newline).encode('ascii')


def package_indexed_ct(source: str | Path, destination: str | Path, template: str | Path) -> dict:
    """Compatibility entry point; require the complete depot example, not a lone index."""
    import zipfile
    if not zipfile.is_zipfile(template):
        raise ValueError('a complete working depot ZIP is required; a lone RTDIR.dir cannot establish the layout')
    from .depot_layout import package_working_layout
    return package_working_layout(source,destination,template)
