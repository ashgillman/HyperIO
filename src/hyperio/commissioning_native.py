"""Build local native commissioning candidates from explicitly selected plans.

Only the observed single-prescription Monaco layouts are supported. Native TPS
acceptance and the meaning of settings remain subject to local review.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from .core import Export, FormatError, HypDocument, inspect_export
from .validation_suite import _replace_record, _settings

_SAFE = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
_SETTINGS = {'DOSEGRIDSIZE', 'MCVARIANCE', 'MCSEGMENTVARIANCE',
             'MCVARPERPLAN', 'DOSETOMEDIUM', 'FORCEWATER',
             'STORECOUCHCOILDOSE', 'ISPHANTOMMATERIAL'}
_TEMPLATE_FIELDS = (
    'machine', 'beam', 'model', 'technique', 'phantom', 'shape', 'field_x_cm',
    'field_y_cm', 'field_plane', 'ssd_cm', 'sad_cm', 'mu', 'gantry_deg',
    'collimator_deg', 'incidence_deg', 'modifier', 'aperture', 'cone', 'image_spacing',
)


def _source(source):
    source = Path(source)
    if not source.is_dir() or not source.name.startswith('1~') or not _SAFE.fullmatch(source.name[2:]):
        raise FormatError('select a native patient directory named 1~<patient ID>')
    return source


def list_native_templates(source):
    """Return plan-folder names with readable native metadata, for explicit selection."""
    source = _source(source)
    report = inspect_export(source)
    return [p['name'] for p in report['plans'] if not p['diagnostics'] and p['beams']
            and p['patient_id'] == source.name[2:]]


def _omitted(name):
    base = PurePosixPath(name).name.lower()
    return (base in {'.dirlock', '.editlock', '.templock', 'dose.1'}
            or base.startswith('dose.') or '.dose.' in base
            or base.endswith(('.xlog', '.log')))


def build_native_patient(source, destination, patient_id, patient_name, cases):
    """Create 1~patient_id below destination; return paths and review limitations.

    cases contain name, template, confirmed=True, optional settings, case_id and
    test_id. Confirmation means the selected template matches all requested
    geometry, delivery and machine details; this builder does not edit those.
    Settings are native directive names with typed booleans/numbers. MC variance
    values are fractions. The observed MCVARPERPLAN directive may be added.
    """
    source = _source(source)
    destination = Path(destination)
    if not _SAFE.fullmatch(patient_id or ''):
        raise ValueError('patient ID must contain 1-32 ASCII letters, digits, hyphens or underscores')
    if not isinstance(patient_name, str) or not re.fullmatch(r'[A-Za-z0-9 _-]+\^[A-Za-z0-9 _-]+', patient_name):
        raise ValueError('patient name must be ASCII family^given')
    if patient_id.casefold() == source.name[2:].casefold():
        raise ValueError('new patient ID must differ from source')
    target = destination / ('1~' + patient_id)
    if not destination.is_dir():
        raise ValueError('destination must be an existing directory')
    if source.resolve() == destination.resolve() or source.resolve() in destination.resolve().parents:
        raise ValueError('destination must be outside the source patient')
    if any(p.name.casefold() == target.name.casefold() for p in destination.iterdir()):
        raise FileExistsError(f'patient directory already exists: {target}')
    if not isinstance(cases, list) or not cases:
        raise ValueError('select at least one case')
    report = inspect_export(source)
    plans = {}
    for plan in report['plans']:
        if plan['name'].casefold() in plans:
            raise FormatError('source has ambiguous case-insensitive plan names')
        plans[plan['name'].casefold()] = plan
    selected, seen = [], set()
    assigned_geometry = {}
    for case in cases:
        if not isinstance(case, dict) or set(case) - {'name', 'template', 'confirmed', 'settings', 'case_id', 'test_id', 'values'}:
            raise ValueError('invalid case fields')
        name = case.get('name')
        if not isinstance(name, str) or not _SAFE.fullmatch(name) or name.casefold() in seen:
            raise ValueError('plan names must be unique and contain 1-32 ASCII letters, digits, hyphens or underscores')
        seen.add(name.casefold())
        if case.get('confirmed') is not True:
            raise ValueError(f'{name}: confirm template matches requested geometry, machine and delivery')
        template = case.get('template', '')
        plan = plans.get(template.casefold()) if isinstance(template, str) else None
        if not plan or plan['diagnostics'] or not plan['beams'] or plan['patient_id'] != source.name[2:]:
            raise FormatError(f'{name}: template missing, unsupported, or has a different patient ID')
        settings = case.get('settings', {})
        if not isinstance(settings, dict) or settings.keys() - _SETTINGS:
            raise ValueError(f'{name}: unsupported calculation settings')
        values = case.get('values', {})
        if not isinstance(values, dict):
            raise ValueError(f'{name}: invalid worksheet values')
        geometry = {key: values[key] for key in _TEMPLATE_FIELDS if key in values}
        previous = assigned_geometry.setdefault(plan['path'], {})
        conflicts = [key for key, value in geometry.items() if key in previous and previous[key] != value]
        if conflicts:
            raise ValueError(f'{name}: the same template was assigned to cases with different {", ".join(conflicts)}')
        previous.update(geometry)
        selected.append((case, plan))
    old_id = source.name[2:]
    omitted = []
    with Export(source) as export:
        demographic = 'demographic.' + old_id
        if demographic not in export.sizes:
            raise FormatError('expected patient demographic file')
        demo = export.read(demographic)
        rows = demo.splitlines(keepends=True)
        records = [row.rstrip(b'\r\n') for row in rows]
        if (len(rows) != 40 or records[0] != b'00081017' or records[33] != old_id.encode('ascii')
                or records[2] != records[4] or b'^' not in records[2]):
            raise FormatError('unsupported demographic identity layout')
        # Rows 3–5 carry original demographics, and row 34 the local patient ID.
        for index, value in ((2, patient_name), (3, patient_id), (4, patient_name), (33, patient_id)):
            rows[index] = value.encode('ascii') + rows[index][len(records[index]):]
        demographic_data = b''.join(rows)
        # Prepare in the destination filesystem; rename only after successful read-back.
        with tempfile.TemporaryDirectory(prefix='.hyperio-commissioning-', dir=destination) as tmp:
            root = Path(tmp) / target.name
            root.mkdir()

            def put(rel, original, data=None):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as output:
                    if data is None:
                        with export.open(original) as stream:
                            shutil.copyfileobj(stream, output)
                    else:
                        output.write(data)

            # Retain all studysets and patient-level files, but no original plans.
            for n in sorted(export.sizes):
                parts = PurePosixPath(n).parts
                if parts[0] == 'plan':
                    continue
                if _omitted(n):
                    omitted.append(n)
                    continue
                data = None
                dest = n
                if n == demographic:
                    data = demographic_data
                    dest = 'demographic.' + patient_id
                elif len(parts) == 2 and parts[0].startswith('1~') and parts[1] == 'info':
                    data = export.read(n)
                    if old_id.encode('ascii') not in data.splitlines():
                        raise FormatError(f'{n}: patient identity record not found')
                    data = _replace_record(data, old_id, patient_id)
                put(dest, n, data)
            for case, plan in selected:
                prefix = plan['path'] + '/'
                members = [n for n in export.sizes if n.startswith(prefix)]
                for n in members:
                    rel = n[len(prefix):]
                    if _omitted(n):
                        omitted.append(n)
                        continue
                    data = None
                    if rel == 'plan':
                        data = export.read(n)
                        rows = data.splitlines(keepends=True)
                        for index, value in ((2, case['name']), (4, patient_id)):
                            ending = rows[index][len(rows[index].rstrip(b'\r\n')):]
                            rows[index] = value.encode('ascii') + ending
                        data = b''.join(rows)
                    elif '/' not in rel and rel.lower().endswith('.hyp'):
                        data = export.read(n)
                        doc = HypDocument(data)
                        for key, value in case.get('settings', {}).items():
                            if key in {'DOSEGRIDSIZE', 'MCVARIANCE', 'MCSEGMENTVARIANCE'} and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
                                raise ValueError(f'{key} must be positive')
                        changes = case.get('settings', {})
                        if 'MCVARPERPLAN' in changes and doc.get('MCVARPERPLAN') is None:
                            if type(changes['MCVARPERPLAN']) is not bool or doc.get('MCSEGMENTVARIANCE') is None:
                                raise FormatError('adding MCVARPERPLAN requires a boolean and an existing MCSEGMENTVARIANCE')
                        data = _settings(data, changes)
                        rel = patient_id + '.hyp'
                    put('plan/' + case['name'] + '/' + rel, n, data)
            result = inspect_export(root)
            if len(result['plans']) != len(selected) or any(p['diagnostics'] or p['patient_id'] != patient_id for p in result['plans']):
                raise FormatError('generated native patient failed plan read-back')
            if any(s['diagnostics'] for s in result['studysets']):
                raise FormatError('generated native patient failed studyset read-back')
            reread = {plan['name']: plan for plan in result['plans']}
            for case, source_plan in selected:
                generated = reread[case['name']]
                for key, value in case.get('settings', {}).items():
                    field = generated['settings'].get(key)
                    if field is None or field['value'] != value:
                        raise FormatError(f"{case['name']}: {key} failed read-back")
                if generated['studyset'] != source_plan['studyset']:
                    raise FormatError(f"{case['name']}: studyset association changed")
            if any(p.name.casefold() == target.name.casefold() for p in destination.iterdir()):
                raise FileExistsError(f'patient directory already exists: {target}')
            target.mkdir()
            try:
                for child in root.iterdir():
                    child.rename(target / child.name)
            except Exception:
                shutil.rmtree(target)
                raise
    return {'patient_path': str(target), 'plans': [dict(name=c['name'], template=c['template'], case_id=c.get('case_id'), test_id=c.get('test_id')) for c, _ in selected],
            'omissions': omitted,
            'limitations': ['Template geometry, machine, delivery and MU require user confirmation and Monaco review.',
                            'Native files and settings require Monaco load, save and calculation validation.',
                            'Studyset image UIDs and cached image metadata remain from the phantom source; use a non-patient phantom.',
                            'Plan status, checksum and other undocumented metadata are retained and not validated.']}
