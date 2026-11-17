"""Approximate CT-derived RED on native CT pixel centres inside WC contours."""
from __future__ import annotations

import io
import math
from pathlib import PurePosixPath

from .core import Export, FormatError, _numbers, study_metadata
from .contours import contour_slice
from .dvh import _contour_footprint


def read_calibration(path):
    """Read an explicitly selected Monaco DICOM3 HU-to-RED table."""
    rows = [line.strip() for line in open(path, encoding='ascii') if line.strip()]
    if len(rows) < 4 or rows[0] != '0000100f':
        raise ValueError('Unsupported DICOM3 calibration header')
    try:
        count = int(rows[1])
        values = [float(v.strip()) for row in rows[2:] for v in row.split(',') if v.strip()]
    except ValueError as exc:
        raise ValueError('Invalid DICOM3 calibration values') from exc
    if count < 2 or len(values) != 2 * count or not all(math.isfinite(v) for v in values):
        raise ValueError('Invalid DICOM3 calibration count or values')
    hu, red = values[:count], values[count:]
    if any(b <= a for a, b in zip(hu, hu[1:])) or any(x <= 0 for x in red):
        raise ValueError('Calibration HU must increase and RED must be positive')
    return hu, red


def calculate_ct_red(source, plan, calibration_path):
    """Return voxel-centre HU and calibrated RED statistics for each WC structure.

    This samples only matching head-first supine axial CT/WC planes and
    unions WC polygons.
    It does not model fill, layer or forced density overrides, nor infer the
    active calibration; the caller must select the applicable table.
    """
    import numpy as np
    import pydicom
    from pydicom.dataset import FileMetaDataset
    from pydicom.uid import ImplicitVRLittleEndian
    from shapely import union_all, intersects_xy

    hu_knots, red_knots = read_calibration(calibration_path)
    patient = PurePosixPath(plan['path']).parent.parent
    study_path = str(patient / ('1~' + plan['studyset']))
    with Export(source) as export:
        study = study_metadata(export, study_path)
        structures = study['structures']
        if len({s['name'] for s in structures}) != len(structures):
            raise FormatError('Duplicate studyset structure names prevent unambiguous CT means')
        wc_files = [n for n in export.sizes if str(PurePosixPath(n).parent) == study_path and n.endswith('.WC')]
        ct_files = [n for n in export.sizes if str(PurePosixPath(n).parent) == study_path + '/DCMData' and n.endswith('.CT.DCM')]
        ct_by_z = {}
        for name in ct_files:
            try:
                z = float(PurePosixPath(name).name[:-7])
            except ValueError as exc:
                raise FormatError(f'Unexpected CT cache filename: {name}') from exc
            if z in ct_by_z:
                raise FormatError('Duplicate CT cache slice position')
            ct_by_z[z] = name
        if not wc_files or not ct_files:
            raise FormatError('Studyset needs WC contours and cached DICOM CT slices')
        totals = {s['index']: [] for s in structures}
        for wc_name in wc_files:
            section = contour_slice(export.read(wc_name), wc_name)
            if not section['polygons']:
                continue
            if _numbers(section['raw_header'][6], 6) != [1, 0, 0, 0, 1, 0]:
                raise FormatError('Only axial WC orientation is supported')
            z = section['y_mm']
            if z not in ct_by_z:
                raise FormatError(f'No CT cache slice matching WC position {z:g}')
            ds = pydicom.dcmread(io.BytesIO(export.read(ct_by_z[z])), force=True)
            if not hasattr(ds, 'file_meta') or not getattr(ds.file_meta, 'TransferSyntaxUID', None):
                ds.file_meta = FileMetaDataset()
                ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
            orientation = np.asarray(ds.ImageOrientationPatient, dtype=float)
            position = np.asarray(ds.ImagePositionPatient, dtype=float)
            spacing = np.asarray(ds.PixelSpacing, dtype=float)
            if ds.get('PatientPosition') != 'HFS':
                raise FormatError('CT mean currently supports only head-first supine images')
            if not np.allclose(orientation, [1, 0, 0, 0, 1, 0], atol=1e-5) or not np.isclose(position[2], z, atol=0.01):
                raise FormatError('CT and WC geometry is not matching axial geometry')
            wc_origin = np.asarray(_numbers(section['raw_header'][5], 3))
            if not np.allclose(position, wc_origin, atol=0.01) or np.any(spacing <= 0):
                raise FormatError('CT and WC origins or spacing do not match')
            pixels = ds.pixel_array.astype(float) * float(ds.RescaleSlope) + float(ds.RescaleIntercept)
            # HFS phantom comparison: native WC (x, y, z) maps to
            # DICOM LPS (x, -z, y). WC header origin itself is in DICOM order.
            x = position[0] + np.arange(ds.Columns) * spacing[1]
            native_z = -(position[1] + np.arange(ds.Rows) * spacing[0])
            for index in {p['structure_index'] for p in section['polygons']}:
                if index not in totals:
                    raise FormatError(f'Unknown WC structure index {index}')
                repairs = []
                geometry = union_all([_contour_footprint(p, repairs) for p in section['polygons'] if p['structure_index'] == index])
                if repairs:
                    raise FormatError('Invalid WC contour requires repair; CT mean unavailable')
                xlo, ylo, xhi, yhi = geometry.bounds
                xi = np.flatnonzero((x >= xlo) & (x <= xhi))
                yi = np.flatnonzero((native_z >= ylo) & (native_z <= yhi))
                xx, zz = np.meshgrid(x[xi], native_z[yi])
                selected = pixels[np.ix_(yi, xi)][intersects_xy(geometry, xx, zz)]
                if len(selected):
                    totals[index].append(selected)
    result = {}
    for structure in structures:
        parts = totals[structure['index']]
        if parts:
            values = np.concatenate(parts)
            reds = np.interp(values, hu_knots, red_knots)
            result[structure['name']] = {'mean_hu': float(values.mean()), 'min_hu': float(values.min()),
                'max_hu': float(values.max()), 'mean_red': float(reds.mean()),
                'min_red': float(reds.min()), 'max_red': float(reds.max()), 'samples': len(values)}
    return result
