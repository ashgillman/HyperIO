"""Generate an all-zero DICOM CT import candidate using the supplied CT template."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import Export, FormatError

TEMPLATE = '1~ZZZELEKTAONEHETERO/1~SemiflexWater/DCMData/-599.5.CT.DCM'
GEOMETRY_SOURCE = 'https://dicom.nema.org/medical/dicom/2024d/output/chtml/part03/sect_C.7.6.2.html'


def build_blank_ct(source: str | Path, destination: str | Path) -> dict:
    """Write a new 100 cubed CT with 5-mm isotropic voxels and zero stored/HU values.

    The source supplies the CT IOD template and axial orientation/volume centre.
    All pixel data, entity identifiers and patient identity are replaced.
    Native Monaco studyset serialization is deliberately left to TPS DICOM import.
    """
    import pydicom
    import numpy as np
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(f'refusing to overwrite existing CT candidate: {destination}')
    if source.is_dir() and (destination.resolve() == source.resolve() or source.resolve() in destination.resolve().parents):
        raise ValueError('output must be outside the source export')
    with Export(source) as export:
        raw = export.read(TEMPLATE)
    template = pydicom.dcmread(io.BytesIO(raw), force=True)
    if (str(template.SOPClassUID) != str(CTImageStorage) or template.Modality != 'CT'
            or template.original_encoding != (True, True)
            or [float(v) for v in template.ImageOrientationPatient] != [1,0,0,0,1,0]):
        raise FormatError('unsupported CT template or orientation in fixture')
    source_uids = {key: str(getattr(template,key)) for key in
                   ('StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID','SOPInstanceUID')}
    centre = [float(template.ImagePositionPatient[0])+(int(template.Columns)-1)*float(template.PixelSpacing[1])/2,
              float(template.ImagePositionPatient[1])+(int(template.Rows)-1)*float(template.PixelSpacing[0])/2,
              float(template.ImagePositionPatient[2])]
    centre = [round(v,7) for v in centre]
    origin = [round(v-247.5,7) for v in centre]
    # Keep the template's standard CT IOD fields, remove acquisition-specific fields
    # that no longer describe a synthetic image, and set synthetic provenance below.
    base = deepcopy(template)
    base.remove_private_tags()
    for elem in list(base):
        if elem.tag.element == 0 or elem.tag.group in (0x0010,0x0018) or elem.VR == 'SQ':
            del base[elem.tag]
    for key in ('PixelData','FloatPixelData','DoubleFloatPixelData','PixelPaddingValue',
                'PixelPaddingRangeLimit','NumberOfFrames','PatientOrientation','PositionReferenceIndicator',
                'InstitutionName','InstitutionAddress','InstitutionalDepartmentName','StationName',
                'AcquisitionDate','AcquisitionTime','AcquisitionDateTime','ReferringPhysicianName'):
        if key in base:
            delattr(base,key)
    base.PatientName = 'zzPHYS^Ash'
    base.PatientID = 'zzzInputOutputAG'
    base.PatientBirthDate = ''
    base.PatientSex = ''
    base.ReferringPhysicianName = ''
    base.AccessionNumber = ''
    base.StudyID = 'HIOZERO001'
    base.StudyDescription = 'HyperIO synthetic zero CT import test'
    base.SeriesDescription = 'ZERO CT 500mm cube 5mm isotropic'
    base.SeriesNumber = 1
    base.AcquisitionNumber = ''
    base.ImageType = ['DERIVED','SECONDARY','AXIAL']
    base.DerivationDescription = ('Synthetic all-zero volume; template metadata only from supplied phantom CT. '
                                  '100x100x100 voxels at 5mm; no acquired anatomy retained.')
    base.Manufacturer = 'HyperIO'
    base.ManufacturerModelName = 'SyntheticZeroCT'
    base.SoftwareVersions = '0.1.0'
    base.PatientPosition = 'HFS'
    base.KVP = ''
    base.ConvolutionKernel = ''
    base.ReconstructionDiameter = 500
    base.SliceThickness = 5
    base.SpacingBetweenSlices = 5
    base.ImageOrientationPatient = [float(v) for v in template.ImageOrientationPatient]
    base.Rows = base.Columns = 100
    base.PixelSpacing = [5,5]
    base.SamplesPerPixel = 1
    base.PhotometricInterpretation = 'MONOCHROME2'
    base.BitsAllocated = base.BitsStored = 16
    base.HighBit = 15
    base.PixelRepresentation = 1
    base.RescaleIntercept = 0
    base.RescaleSlope = 1
    base.RescaleType = 'HU'
    base.WindowCenter = 0
    base.WindowWidth = 400
    base.SmallestImagePixelValue = 0
    base.LargestImagePixelValue = 0
    base.LossyImageCompression = '00'
    now = datetime.now(ZoneInfo('Australia/Brisbane'))
    for prefix in ('Study','Series','Content','InstanceCreation'):
        setattr(base,prefix+'Date',now.strftime('%Y%m%d'))
        setattr(base,prefix+'Time',now.strftime('%H%M%S.%f'))
    base.TimezoneOffsetFromUTC = '+1000'
    uids = {key: generate_uid(prefix=None) for key in
            ('StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID')}
    for key,value in uids.items():
        setattr(base,key,value)
    pixel_bytes = bytes(100*100*2)
    destination.mkdir(parents=True)
    output = destination/'DICOM'
    output.mkdir()
    records = {}
    all_uids = set(uids.values())
    for i in range(100):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid(prefix=None)
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(None,deepcopy(base),file_meta=meta,preamble=bytes(128))
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.InstanceNumber = i+1
        position = [origin[0],origin[1],round(origin[2]+i*5,7)]
        ds.ImagePositionPatient = position
        ds.SliceLocation = position[2]
        ds.PixelData = pixel_bytes
        ds['PixelData'].VR = 'OW'
        target = output/f'CT_{i+1:03d}.dcm'
        pydicom.dcmwrite(target,ds,enforce_file_format=True)
        # Re-read every file and interpret its stored pixels independently of assignment.
        readback = pydicom.dcmread(target)
        values = readback.pixel_array
        if (values.shape != (100,100) or not np.all(values == 0)
                or readback.PixelData != pixel_bytes
                or list(map(float,readback.ImagePositionPatient)) != position
                or str(readback.SOPInstanceUID) in all_uids
                or str(readback.file_meta.MediaStorageSOPInstanceUID) != str(readback.SOPInstanceUID)):
            raise FormatError(f'CT read-back verification failed: {target}')
        all_uids.add(str(readback.SOPInstanceUID))
        data = target.read_bytes()
        records[target.relative_to(destination).as_posix()] = {
            'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),
            'sop_instance_uid':str(readback.SOPInstanceUID),'position_patient_mm':position}
    if all_uids.intersection(source_uids.values()) or len(all_uids) != 103:
        raise FormatError('generated identifiers overlap or are not unique')
    result = {'schema_version':1,'kind':'synthetic_zero_CT_DICOM_import_candidate',
        'patient_id':base.PatientID,'patient_name':str(base.PatientName),
        'generated_at':now.isoformat(),'source':{'archive':str(source),'member':TEMPLATE,
            'member_sha256':hashlib.sha256(raw).hexdigest(),'uids':source_uids,
            'usage':'CT metadata template, axial orientation and centre only; source pixels replaced'},
        'uids':uids,'geometry':{'shape_slices_rows_columns':[100,100,100],
            'voxel_spacing_mm':[5,5,5],'outer_voxel_extent_mm':[500,500,500],
            'voxel_count':1000000,'centre_patient_mm':centre,
            'first_voxel_centre_patient_mm':origin,
            'last_voxel_centre_patient_mm':[round(v+495,7) for v in origin],
            'edge_bounds_patient_mm':[[round(c-250,7),round(c+250,7)] for c in centre],
            'orientation_patient':[1,0,0,0,1,0],'geometry_reference':GEOMETRY_SOURCE},
        'pixels':{'stored_value':0,'rescale_slope':1,'rescale_intercept':0,'HU':0,
            'bits_allocated':16,'signed':True,'padding_tag_present':False},
        'files':records,'validation':{'status':'local_checks_passed_TPS_import_pending',
            'checked':'all 100 files re-read; pixel arrays decoded as 100x100 zeroes; UID uniqueness and positions checked',
            'monaco_import':None,'monaco_save_reopen':None}}
    (destination/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    (destination/'README.md').write_text('''# Zero CT import test: 500 mm cube, 5 mm voxels

Import the `DICOM/` folder using Monaco's CT DICOM import workflow.
This package contains 100 standard DICOM Part 10 CT files, each 100 by 100 pixels.
Every stored pixel is exactly zero; slope 1 and intercept 0 make every voxel 0 HU.
Voxel spacing and slice thickness are 5 mm.
The outer voxel-edge extent is 500 by 500 by 500 mm; first-to-last voxel centres span 495 mm.
The volume is centred on the supplied example slice's image centre, with its axial orientation.
The source supplies metadata only; none of its acquired pixel values are retained.

Patient ID: `zzzInputOutputAG`.
Patient Name: `zzPHYS, Ash` (`zzPHYS^Ash`).
New Study, Series and Frame of Reference UIDs are used, and every CT slice has its own new SOP Instance UID.
See manifest.json for all identifiers, positions, geometry, source-template hash and output hashes.

## TPS review

1. Import all 100 files as a new CT studyset using the DICOM import workflow.
   Do not copy these files into the failed native patient-folder candidates.
2. Confirm the patient ID/name, slice count 100, image dimensions 100 by 100, and spacing 5 mm in all directions.
3. Confirm cursor CT values are 0 HU throughout.
   Uniform images will have no internal visual features; the slice count, geometry and CT-value cursor are the useful checks.
4. Save/reopen the imported studyset and return the native patient/studyset files Monaco creates.
5. Record Monaco build, import result, exact messages, screenshots and geometry checks in REVIEW.md.

No plan or RT Structure Set is included.
The previous native plan candidates have not yet loaded; copying one onto this new CT would leave unverified studyset and frame-of-reference associations.
A successful CT import and returned Monaco-native studyset will provide the next template for that work.
Local DICOM read-back checks do not establish Monaco import acceptance.
''')
    (destination/'REVIEW.md').write_text('''# Zero CT TPS import review

Review status: not_reviewed
Monaco version/build:
Import result / exact messages:
Patient ID and name:
Slices / rows / columns:
Pixel spacing / slice spacing / thickness:
Physical extent:
Cursor CT values (HU):
Save/reopen result:
Screenshots:
Returned native studyset path:
Notes:
''')
    return result
