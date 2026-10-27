"""Reproduce the depot relationships observed in the complete Monthly QC fixture."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import zipfile
from zoneinfo import ZoneInfo

from .depot_index import depot_index_bytes


def inspect_working_depot(archive: str | Path) -> dict:
    """Cross-check both index files with every associated DICOM header."""
    import pydicom
    with zipfile.ZipFile(archive) as z:
        roots=[n for n in z.namelist() if PurePosixPath(n).name=='RTDIR.dir']
        if len(roots)!=1:
            raise ValueError('expected one RTDIR.dir in the working depot example')
        root=PurePosixPath(roots[0]).parent.as_posix()+'/'
        template=z.read(roots[0])
        rows=template.decode('ascii').splitlines()
        if len(rows)!=17 or rows[:3]!=['!Version=2','CT','1.2.840.10008.5.1.4.1.1.2']:
            raise ValueError('unsupported working depot index layout')
        index_name=root+'CT_'+rows[3]+'.dir'
        uids=z.read(index_name).decode('ascii').splitlines()
        if not uids or len(uids)!=len(set(uids)):
            raise ValueError('empty or duplicate SOP instance references')
        expected={root+'CT_'+u for u in uids}|{roots[0],index_name}
        actual={i.filename for i in z.infolist() if not i.is_dir() and i.filename.startswith(root)}
        if expected!=actual:
            raise ValueError('working archive has missing or unassigned members')
        mapping={'3':'SOPClassUID','4':'SeriesInstanceUID','5':'StudyInstanceUID',
                 '6':'StudyID','7':'PatientName','8':'FrameOfReferenceUID'}
        for i,uid in enumerate(uids):
            raw=z.read(root+'CT_'+uid)
            ds=pydicom.dcmread(io.BytesIO(raw),force=True,stop_before_pixels=True)
            if ds.original_encoding!=(True,True) or ds.file_meta or raw[128:132]==b'DICM':
                raise ValueError('working image encoding differs from raw implicit VR little endian')
            if str(ds.SOPInstanceUID)!=uid or ds.Modality!='CT':
                raise ValueError('working filename/list does not match SOP Instance UID')
            if any(str(getattr(ds,key))!=rows[int(line)-1] for line,key in mapping.items()):
                raise ValueError('working index field differs from labelled DICOM header')
            if i==0:
                if (list(map(float,rows[8:11]))!=list(map(float,ds.ImagePositionPatient)) or
                        list(map(float,rows[11:]))!=list(map(float,ds.ImageOrientationPatient))):
                    raise ValueError('working geometry differs from first indexed image')
        return {'archive':str(archive),'archive_sha256':hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
            'image_count':len(uids),'field_mapping_one_based':mapping,
            'image_filename_pattern':'CT_<SOPInstanceUID>',
            'image_index_pattern':'CT_<SeriesInstanceUID>.dir',
            'series_index_filename':'RTDIR.dir','image_encoding':'raw_implicit_VR_little_endian',
            'index_sha256':hashlib.sha256(template).hexdigest(),
            'geometry_mapping':'position and orientation match first SOP listed in series index',
            'scope':'observed on one complete supplied depot; generated TPS acceptance pending'}


def package_working_layout(source: str | Path, destination: str | Path, fixture: str | Path) -> dict:
    """Mirror the working depot layout; preserve pixels, geometry and entity UIDs."""
    import pydicom
    source,destination,fixture=Path(source),Path(destination),Path(fixture)
    if destination.exists():
        raise FileExistsError(f'refusing to overwrite existing depot package: {destination}')
    if source.resolve()==destination.resolve() or source.resolve() in destination.resolve().parents:
        raise ValueError('output must be outside source candidate')
    evidence=inspect_working_depot(fixture)
    with zipfile.ZipFile(fixture) as z:
        template=z.read(next(n for n in z.namelist() if PurePosixPath(n).name=='RTDIR.dir'))
    original=json.loads((source/'manifest.json').read_text())
    images=sorted((source/'DICOM').glob('*.dcm'))
    if len(images)!=100:
        raise ValueError('expected the 100-slice zero CT source candidate')
    loaded=[]
    for path in images:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=original['files']['DICOM/'+path.name]['sha256']:
            raise ValueError('source CT file differs from manifest')
        loaded.append((path,pydicom.dcmread(path)))
    loaded.sort(key=lambda pair:int(pair[1].InstanceNumber))
    first=loaded[0][1]
    for _,ds in loaded:
        if any(str(getattr(ds,key))!=str(getattr(first,key)) for key in
               ('StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID','PatientID','PatientName','StudyID')):
            raise ValueError('source candidate is not a single consistent CT series')
    uids=[str(ds.SOPInstanceUID) for _,ds in loaded]
    if len(uids)!=len(set(uids)):
        raise ValueError('duplicate source SOP instances')
    patient_id=str(first.PatientID)
    if not patient_id or any(c in patient_id for c in '/\\') or patient_id in ('.','..'):
        raise ValueError('patient ID is not a safe directory name')
    index=depot_index_bytes(first,template)
    destination.mkdir(parents=True)
    patient=destination/patient_id
    patient.mkdir()
    records={}
    for oldpath,old in loaded:
        ds=deepcopy(old)
        ds.preamble=None
        if hasattr(ds,'file_meta'):
            del ds.file_meta
        target=patient/f'CT_{ds.SOPInstanceUID}'
        pydicom.dcmwrite(target,ds,implicit_vr=True,little_endian=True,
                        enforce_file_format=False,force_encoding=True)
        raw=target.read_bytes()
        new=pydicom.dcmread(io.BytesIO(raw),force=True)
        # Retain the complete public dataset semantically, apart from file-meta/encoding.
        for element in old:
            if element.tag not in new or new[element.tag].value!=element.value:
                raise ValueError(f'CT element changed during raw reserialization: {element.tag}')
        if new.original_encoding!=(True,True) or new.file_meta or new.PixelData!=old.PixelData:
            raise ValueError('CT dataset encoding/read-back mismatch')
        rel=target.relative_to(destination).as_posix()
        records[rel]={'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw),
            'source_file':'DICOM/'+oldpath.name,'source_sha256':original['files']['DICOM/'+oldpath.name]['sha256'],
            'sop_instance_uid':str(new.SOPInstanceUID),'change':'file encoding only; dataset values unchanged'}
    series_index=patient/f'CT_{first.SeriesInstanceUID}.dir'
    series_index.write_bytes(('\n'.join(uids)+'\n').encode('ascii'))
    (patient/'RTDIR.dir').write_bytes(index)
    for path in (series_index,patient/'RTDIR.dir'):
        raw=path.read_bytes()
        records[path.relative_to(destination).as_posix()]={'sha256':hashlib.sha256(raw).hexdigest(),
            'size':len(raw),'content':'depot index matching working fixture relationships'}
    result=deepcopy(original)
    result.update(kind='synthetic_zero_CT_in_observed_Monaco_depot_layout',
        packaged_at=datetime.now(ZoneInfo('Australia/Brisbane')).isoformat(),
        source_candidate=str(source),files=records,working_depot_evidence=evidence,
        depot_directory=patient_id,
        changes_from_ct002=['RTDIR UID order corrected to series then study',
            'RTDIR description field corrected to StudyID',
            'added CT_<SeriesInstanceUID>.dir listing all 100 SOP UIDs',
            'image filenames changed to CT_<SOPInstanceUID> without extension',
            'image encoding changed to raw implicit VR little endian matching fixture',
            'patient directory named with PatientID; removed speculative .rtDir alias'],
        validation={'status':'fixture_relationships_and_CT_semantics_checked_TPS_pending',
            'monaco_import':None,'monaco_save_reopen':None})
    (destination/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    (destination/'README.md').write_text(f'''# Zero CT depot matching the supplied Monthly QC layout

Extract the whole ZIP.
In Monaco's DICOM import browser, use the extracted `{patient_id}/` patient directory, corresponding to the working example's `Monthly QC/` directory.
If the browser lists patient folders from their parent, select the extracted package directory and choose `{patient_id}` from the patient list.
Keep the 100 `CT_<SOPInstanceUID>` files, `CT_<SeriesInstanceUID>.dir` and `RTDIR.dir` together.
There is no DICOM/ subfolder or .rtDir alias in this version.

The complete supplied example establishes the index field relationships against all 130 source DICOM headers.
Its RTDIR uses Series Instance UID before Study Instance UID, then StudyID rather than SeriesDescription.
Its second index enumerates SOP Instance UIDs; each references a same-folder CT_<UID> file with no extension.
Its CT files are raw implicit-VR little-endian datasets without a Part 10 file header.
This package reproduces those observed relationships and encoding for the generated images.

Patient ID: zzzInputOutputAG; Name: zzPHYS, Ash.
The volume remains 100 slices of 100x100 pixels, 5 mm isotropic spacing, 500 mm outer-edge extent, with all stored pixels and HU equal to zero.
All image dataset values, including geometry and Study/Series/Frame/SOP identifiers, are unchanged from ct-001.
Only DICOM file encoding, filenames and depot metadata/layout changed.

First verify whether Monaco lists the patient and CT series for import.
Then verify image dimensions, spacing, 0 HU values and save/reopen.
Record exact messages or the new log if it still fails.
The layout is established from the working specimen; generated Monaco acceptance remains pending.
No plan or structures are included.
''')
    (destination/'REVIEW.md').write_text('''# Working-layout zero CT review

Review status: not_reviewed
Monaco build:
Browser directory selected:
Patient listed:
CT series listed:
Import result / exact messages:
Slice count / matrix / spacing:
Cursor HU:
Save/reopen:
Screenshots / returned native files:
Notes:
''')
    (destination/'roundtrips').mkdir()
    return result
