"""Approximate CT-derived RED on native CT pixel centres inside WC contours."""
from __future__ import annotations

import io
import math
import os
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from .core import Export, FormatError, _numbers, study_metadata
from .contours import contour_slice
from .dvh import _contour_footprint


def calibration_directories():
    """Return user calibration directories in preference order."""
    home = Path.home()
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA')
        preferred = (Path(local) if local else home / 'AppData' / 'Local') / 'HyperIO' / 'data' / 'cttoed'
    elif sys.platform == 'darwin':
        preferred = home / 'Library' / 'Application Support' / 'HyperIO' / 'data' / 'cttoed'
    else:
        xdg = os.environ.get('XDG_DATA_HOME')
        base = Path(xdg) if xdg and Path(xdg).is_absolute() else home / '.local' / 'share'
        preferred = base / 'hyperio' / 'data' / 'cttoed'
    fallback = home / '.hyperio' / 'data' / 'cttoed'
    config = home / '.config' / 'hyperio' / 'data' / 'cttoed'
    return list(dict.fromkeys((preferred, config, fallback)))


def find_calibration(name):
    """Find an exact, case-sensitive DICOM3 filename in a user directory."""
    if not name or name in ('.', '..') or '/' in name or '\\' in name:
        return None
    filename = f'DICOM3.{name}'
    for directory in calibration_directories():
        try:
            for path in directory.iterdir():
                if path.name == filename and path.is_file():
                    return path
        except OSError:
            continue
    return None


def calibration_picker_directory():
    """Use the first existing directory, or create the preferred one lazily."""
    directories = calibration_directories()
    for directory in directories:
        try:
            if directory.is_dir():
                return directory
        except OSError:
            continue
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            return directory
        except OSError:
            continue
    return Path.home()


def linked_study_path(export, plan):
    patient = PurePosixPath(plan['path']).parent.parent
    paths = [str(p.parent) for n in export.sizes if (p := PurePosixPath(n)).name == 'contournames'
             and p.parent.parent == patient and p.parent.name.split('~', 1)[-1] == plan['studyset']]
    if len(paths) != 1:
        raise FormatError(f'Expected one linked studyset, found {len(paths)}')
    return paths[0]


def read_calibration(path, *, expected_name=None):
    """Read a Monaco DICOM3 table, optionally selected by name from a ZIP."""
    path = Path(path)
    if path.suffix.lower() == '.zip' and not path.name.startswith('DICOM3.'):
        if not expected_name:
            raise ValueError('A recorded CT-to-ED name is required to select a curve from ZIP')
        with ZipFile(path) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()
                       and PurePosixPath(info.filename).name == f'DICOM3.{expected_name}']
            if len(members) != 1:
                raise ValueError(f'Expected one DICOM3.{expected_name} in the calibration ZIP, found {len(members)}')
            data = archive.read(members[0])
    else:
        if expected_name and path.name != f'DICOM3.{expected_name}':
            raise ValueError(f'The input studyset selects {expected_name}. Choose DICOM3.{expected_name} or a ZIP containing it.')
        data = path.read_bytes()
    rows = data.decode('ascii').splitlines()
    if len(rows) < 4 or rows[0] not in {'0000100f', '00bc100f', '00d5100f'}:
        raise ValueError('Unsupported DICOM3 calibration header')
    payload = [line.strip() for line in rows[2:] if line.strip()]
    if payload and payload[0] == '0':
        payload = payload[1:]
    if len(payload) < 3:
        raise ValueError('Incomplete DICOM3 calibration')
    try:
        count = int(payload[0])
        values = [float(v.strip()) for row in payload[1:] for v in row.split(',')]
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
    This reports CT-derived density before fill, layer or forced overrides.
    The supplied table must match the studyset's recorded curve name.
    """
    return _calculate_ct_red(source, plan, calibration_path)


def _calculate_ct_red(source, plan, calibration_path, *, structure_names=None, contour_repairs=None,
                      contoured_structures=None):
    """Sample selected structures and optionally collect every name with a WC polygon.

    Collect contour presence independently of the sampling selection and result.
    Accept repaired footprints only when given a repair report collector.
    """
    import numpy as np
    import pydicom
    from pydicom.dataset import FileMetaDataset
    from pydicom.uid import ImplicitVRLittleEndian
    from shapely import union_all, intersects_xy

    with Export(source) as export:
        study_path = linked_study_path(export, plan)
        study = study_metadata(export, study_path)
        selection = study['ct_to_ed_name']
        if not selection:
            raise FormatError('The linked studyset CT-to-ED selection is unavailable or ambiguous')
        hu_knots, red_knots = read_calibration(calibration_path, expected_name=selection['value'])
        structures = [s for s in study['structures'] if structure_names is None or s['name'] in structure_names]
        known_names = {s['index']: s['name'] for s in study['structures']}
        names_by_index = {s['index']: s['name'] for s in structures}
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
        totals = {}
        for wc_name in wc_files:
            section = contour_slice(export.read(wc_name), wc_name)
            polygons = {}
            for record in section['polygons']:
                index = record['structure_index']
                if index not in known_names:
                    raise FormatError(f'{wc_name}: unknown WC structure index {index}')
                if contoured_structures is not None:
                    contoured_structures.add(known_names[index])
                if index in names_by_index:
                    polygons.setdefault(index, []).append(record)
            if not polygons:
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
            if not np.allclose(orientation, [1, 0, 0, 0, 1, 0], atol=1e-5) or not np.isclose(position[2], z, atol=0.01, rtol=0):
                raise FormatError('CT and WC geometry is not matching axial geometry')
            wc_origin = np.asarray(_numbers(section['raw_header'][5], 3))
            if wc_origin.shape != (3,) or not np.allclose(position, wc_origin, atol=0.01, rtol=0) or np.any(spacing <= 0):
                raise FormatError('CT and WC origins or spacing do not match')
            pixels = ds.pixel_array.astype(float) * float(ds.RescaleSlope) + float(ds.RescaleIntercept)
            # HFS phantom comparison: native WC (x, y, z) maps to
            # DICOM LPS (x, -z, y). WC header origin itself is in DICOM order.
            x = position[0] + np.arange(ds.Columns) * spacing[1]
            native_z = -(position[1] + np.arange(ds.Rows) * spacing[0])
            for index, records in polygons.items():
                name = names_by_index[index]
                repairs = []
                try:
                    geometry = union_all([_contour_footprint(record, repairs) for record in records])
                except FormatError as exc:
                    raise FormatError(f'{name}: {exc}') from exc
                if repairs:
                    if contour_repairs is None:
                        raise FormatError(f'{name}: invalid WC contour requires repair; CT mean unavailable. {repairs[0]}')
                    contour_repairs.extend(f'{name}: {repair}' for repair in repairs)
                xlo, ylo, xhi, yhi = geometry.bounds
                xi = np.flatnonzero((x >= xlo) & (x <= xhi))
                yi = np.flatnonzero((native_z >= ylo) & (native_z <= yhi))
                xx, zz = np.meshgrid(x[xi], native_z[yi])
                selected = pixels[np.ix_(yi, xi)][intersects_xy(geometry, xx, zz)]
                if selected.size:
                    reds = np.interp(selected, hu_knots, red_knots)
                    stats = totals.setdefault(index, {'samples': 0, 'sum_hu': 0., 'sum_red': 0.,
                        'min_hu': math.inf, 'max_hu': -math.inf, 'min_red': math.inf, 'max_red': -math.inf})
                    stats['samples'] += selected.size
                    for unit, values in [('hu', selected), ('red', reds)]:
                        stats[f'sum_{unit}'] += float(values.sum())
                        stats[f'min_{unit}'] = min(stats[f'min_{unit}'], float(values.min()))
                        stats[f'max_{unit}'] = max(stats[f'max_{unit}'], float(values.max()))
    for stats in totals.values():
        for unit in ('hu', 'red'):
            stats[f'mean_{unit}'] = stats.pop(f'sum_{unit}') / stats['samples']
    return {s['name']: totals[s['index']] for s in structures if s['index'] in totals}
