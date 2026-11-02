"""Shared, headless workflows for the desktop applications.

Density edits target only the observed plan table, preserving all other bytes.
They remain experimental native edits; they do not update dose or study defaults.
"""
from __future__ import annotations

import csv
from pathlib import Path, PurePosixPath

from .core import Export, FormatError, plan_metadata
from .experiments import _positive_ed, edit_plan_density


def discover_plans(source):
    """List plans by full member path, keeping duplicate plan names distinct."""
    result = []
    with Export(source) as export:
        for member in sorted(export.sizes):
            path = PurePosixPath(member)
            if path.name != 'plan' or path.parent.parent.name != 'plan':
                continue
            try:
                metadata = plan_metadata(export.read(member), member)
            except FormatError as exc:
                result.append({'path': str(path.parent), 'member': member,
                               'label': f'{path.parent} [unreadable: {exc}]', 'error': str(exc)})
                continue
            result.append({**metadata, 'path': str(path.parent), 'member': member,
                           'label': f'{metadata["patient_id"]} / {metadata["studyset"]} / '
                                    f'{metadata["name"]} [{path.parent}]', 'error': None})
    return result


def load_red_mapping(path):
    """Read exact structure names and finite REDs from a CSV/TSV preset.

    Duplicate names are rejected rather than silently taking the final value.
    """
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        sample = stream.read(4096)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',\t;')
        except csv.Error:
            dialect = csv.excel_tab if Path(path).suffix.lower() == '.tsv' else csv.excel
        reader = csv.DictReader(stream, dialect=dialect)
        headers = {h.strip().lower().replace('_', ' '): h for h in reader.fieldnames or []}
        name_column = next((headers[h] for h in ('structure', 'structure name', 'name', 'roi') if h in headers), None)
        red_column = next((headers[h] for h in ('red', 'relative electron density', 'electron density') if h in headers), None)
        if name_column is None or red_column is None:
            raise ValueError('Preset needs a header row: structure,red')
        mapping = {}
        for number, row in enumerate(reader, 2):
            if not any(row.values()):
                continue
            name, raw = (row.get(name_column) or '').strip(), (row.get(red_column) or '').strip()
            if not name or not raw:
                raise ValueError(f'Preset row {number}: structure and RED are required')
            if name in mapping:
                raise ValueError(f'Duplicate preset structure: {name}')
            value = float(raw)
            _positive_ed(value)
            mapping[name] = value
    if not mapping:
        raise ValueError('Preset has no structure mappings')
    return mapping


def apply_red_mapping(data, mapping):
    """Return edited bytes, a preview of changes, and unmatched preset names.

    Matched structures receive mode 2 (forced) and the preset uniform RED.
    Unmatched structures, fill values and layer settings are retained verbatim.
    """
    for value in mapping.values():
        _positive_ed(value)
    records = plan_metadata(data, '<selected-plan>')['density_overrides']
    names = [record['name'] for record in records]
    if len(names) != len(set(names)):
        raise FormatError('Duplicate structure names in plan density table')
    edited, changes = data, []
    for record in records:
        name = record['name']
        if name not in mapping:
            continue
        edited = edit_plan_density(edited, name, mode=2, uniform_ed=mapping[name])
        changes.append({'structure': name, 'old_mode': record['mode'],
                        'old_red': record['uniform_ed'], 'new_mode': 'forced', 'new_red': mapping[name]})
    return edited, changes, sorted(set(mapping) - set(names))


def save_plan_copy(data, source_path, destination):
    """Write a new file exclusively, refusing the source and existing files."""
    destination = Path(destination)
    if destination.resolve() == Path(source_path).resolve():
        raise ValueError('Choose a new output file; the source plan must be preserved')
    with destination.open('xb') as stream:
        stream.write(data)
