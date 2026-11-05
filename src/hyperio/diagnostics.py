"""Local support reports with a strict allowlist for anonymised output.

Anonymised reports never copy free text, native records, paths or tracebacks.
Unknown diagnostic text is withheld rather than subjected to name substitution.
"""
from __future__ import annotations

import json
import platform
import re
import traceback
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath

from .core import Export, inspect_export


_ERRORS = {
    'unsupported info version': 'unsupported_info_version',
    'unsupported contournames version': 'unsupported_contournames_version',
    'CT-to-ED selection absent or ambiguous': 'ct_to_ed_selection_absent_or_ambiguous',
    'missing info': 'missing_info',
    'missing contournames': 'missing_contournames',
    'structure count does not match contournames header': 'structure_count_mismatch',
    'unrecognised structure record': 'unrecognised_structure_record',
    'expected one .hyp': 'hyp_file_count_mismatch',
    'no supported beam headers': 'no_supported_beam_headers',
    'unsupported tel.1 version': 'unsupported_beam_version',
    'unsupported plan version': 'unsupported_plan_version',
    'unsupported .hyp version': 'unsupported_hyp_version',
    'unsupported XML metadata version': 'unsupported_xml_metadata_version',
    'expected one linked studyset': 'studyset_link_count_mismatch',
    'multiple prescription files': 'multiple_prescriptions_unsupported',
    'plan has no saved dose.1': 'missing_saved_dose',
    'unknown structure names': 'unknown_structure_names',
    'missing tel.1': 'missing_beam_file',
    'unsupported native dose': 'unsupported_native_dose',
}


def _error_codes(text):
    if not text:
        return []
    codes = [code for phrase, code in _ERRORS.items() if phrase in str(text)]
    return codes or ['unclassified_error_details_withheld']


def classify_dvh_diagnostics(messages):
    """Classify metadata diagnostics for reconstruction from saved dose only.

    Studyset info describes CT calibration, which saved-dose sampling does not
    consume. Unknown diagnostics remain errors; other workflows keep their
    existing validation policy.
    """
    warnings = {'CT-to-ED selection absent or ambiguous', 'missing info',
                'unsupported info version'}
    rows = []
    for message in messages:
        cause = message.rsplit(': ', 1)[-1] if message.startswith('linked studyset ') else message
        rows.append({'severity': 'WARN' if cause in warnings else 'ERROR',
                     'message': message})
    return rows


def build_diagnostic_report(source, *, anonymised=False, events=(), outcomes=()):
    """Inspect metadata without decoding dose/images or modifying the source.

Full reports retain inspection records and session error tracebacks.
Anonymous reports contain only generated IDs, counts, format codes, fixed error
categories and software versions, so even unidentified free-text PHI is excluded.
"""
    try:
        release = version('hyperio-monaco')
    except PackageNotFoundError:
        release = 'source checkout'
    report = {'schema_version': 1, 'anonymised': anonymised,
              'software': {'hyperio': release, 'python': platform.python_version(),
                           'system': platform.system()}, 'files': []}
    if not anonymised:
        report['source'] = str(source)
    try:
        inspection = inspect_export(source)
    except Exception as exc:
        inspection = {'plans': [], 'studysets': []}
        key = 'inspection_error_codes' if anonymised else 'inspection_error'
        report[key] = _error_codes(str(exc)) if anonymised else str(exc)
        if not anonymised:
            report['inspection_traceback'] = traceback.format_exc()

    # Read only bounded magic lines of files relevant to parsing this failure.
    # Never export arbitrary member names or arbitrary first-line contents in
    # the anonymous form, even if the patient export is malformed.
    groups = {}
    try:
        with Export(source) as export:
            for member in sorted(export.sizes):
                path = PurePosixPath(member)
                kind = '.hyp' if path.suffix.lower() == '.hyp' else path.name
                if kind not in {'plan', '.hyp', 'tel.1', 'info', 'contournames',
                                'dose.1', 'dvhparam.xml', 'isodosesettings.xml'}:
                    continue
                parent = str(path.parent)
                group = groups.setdefault(parent, f'folder_{len(groups) + 1:03d}')
                row = {'kind': kind, 'folder_id': group}
                if not anonymised:
                    row['path'] = member
                with export.open(member) as stream:
                    header = stream.read(8192) if kind.endswith('.xml') else stream.readline(64)
                magic = header.strip()
                row['version'] = magic.decode('ascii') if re.fullmatch(rb'[0-9a-fA-F]{8}', magic) else None
                if kind.endswith('.xml'):
                    match = re.search(rb'<Metadata>\s*<Version>([0-9]{1,4})</Version>', header)
                    row['version'] = match[1].decode('ascii') if match else None
                report['files'].append(row)
    except Exception as exc:
        key = 'inventory_error_codes' if anonymised else 'inventory_error'
        report[key] = _error_codes(str(exc)) if anonymised else str(exc)

    for plan in inspection['plans']:
        plan['dvh_diagnostics'] = classify_dvh_diagnostics(plan['diagnostics'])
    if not anonymised:
        report.update(inspection=inspection, events=list(events), outcomes=list(outcomes))
        return report

    report['privacy_policy'] = ('Allowlisted technical fields only. Free text, paths, names, native records, '
                                'timestamps and tracebacks omitted. Unknown errors are withheld.')
    studies = inspection['studysets']
    report['studysets'] = [
        {'id': f'studyset_{i:03d}', 'folder_id': groups.get(study['path']),
         'structure_count': len(study['structures']),
         'error_codes': sorted({code for text in study['diagnostics'] for code in _error_codes(text)})}
        for i, study in enumerate(studies, 1)]
    report['plans'] = []
    plan_ids = {}
    for i, plan in enumerate(inspection['plans'], 1):
        plan_id = f'plan_{i:03d}'
        plan_ids[plan['path']] = plan_id
        linked = [index for index, study in enumerate(studies, 1)
                  if study['name'] == plan['studyset']
                  and PurePosixPath(study['path']).parent == PurePosixPath(plan['path']).parent.parent]
        report['plans'].append({
            'id': plan_id, 'folder_id': groups.get(plan['path']),
            'studyset_id': f'studyset_{linked[0]:03d}' if len(linked) == 1 else None,
            'beam_count': len(plan['beams']),
            'dvh_diagnostics': [{'severity': row['severity'], 'codes': _error_codes(row['message'])}
                                for row in plan['dvh_diagnostics']],
            'error_codes': sorted({code for text in plan['diagnostics'] for code in _error_codes(text)})})
    report['events'] = [{'error_codes': _error_codes(event.get('error'))} for event in events]
    report['outcomes'] = [{'plan_id': plan_ids.get(outcome['path']),
                           'exported': not bool(outcome.get('error')),
                           'severity': 'ERROR' if outcome.get('error') else
                                       'WARN' if outcome.get('diagnostics') else 'INFO',
                           'diagnostics': [{'severity': row['severity'] if row.get('severity') in {'WARN', 'ERROR'} else 'ERROR',
                                            'codes': _error_codes(row.get('message'))}
                                           for row in outcome.get('diagnostics', [])],
                           'error_codes': _error_codes(outcome.get('error'))} for outcome in outcomes]
    return report


def export_diagnostic_report(source, destination, **options):
    report = build_diagnostic_report(source, **options)
    Path(destination).write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str) + '\n',
                                 encoding='utf-8')
