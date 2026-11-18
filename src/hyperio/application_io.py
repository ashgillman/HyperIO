"""Headless RED editing and complete patient export workflows.

Density edits target only the observed plan table, preserving all other bytes.
They remain experimental native edits; they do not update dose or study defaults.
"""
from __future__ import annotations

import csv
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .core import Export, FormatError, plan_metadata, study_metadata
from .ct_red import linked_study_path
from .experiments import _positive_ed, edit_plan_density
from .plan_discovery import discover_plans as discover_plans


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

    Numeric values set forced mode and uniform RED; dictionaries may independently
    set mode and uniform RED using the keys "mode" and "red".
    Unmatched structures, fill values and layer settings are retained verbatim.
    A preset may only target names with exactly one density record.
    """
    for value in mapping.values():
        if isinstance(value, dict):
            if value.get("red") is not None:
                _positive_ed(value["red"])
            if value.get("mode") not in (None, "none", "forced", "filled"):
                raise ValueError("density mode must be none, forced, or filled")
        else:
            _positive_ed(value)
    records = plan_metadata(data, '<selected-plan>')['density_overrides']
    names = [record['name'] for record in records]
    duplicates = sorted(name for name in mapping if names.count(name) > 1)
    if duplicates:
        raise FormatError(f'Duplicate structure names in plan density table: {", ".join(duplicates)}')
    edited, changes = data, []
    for record in records:
        name = record['name']
        if name not in mapping:
            continue
        value = mapping[name]
        mode = value.get('mode') if isinstance(value, dict) else 'forced'
        red = value.get('red') if isinstance(value, dict) else value
        mode_code = {'none': 1, 'forced': 2, 'filled': 3}.get(mode)
        edited = edit_plan_density(edited, name, mode=mode_code, uniform_ed=red)
        changes.append({'structure': name, 'old_mode': record['mode'],
                        'old_red': record['uniform_ed'], 'new_mode': mode or record['mode'],
                        'new_red': red if red is not None else record['uniform_ed']})
    return edited, changes, sorted(set(mapping) - set(names))


def save_plan_copy(data, source_path, destination):
    """Write a new file exclusively, refusing the source and existing files."""
    destination = Path(destination)
    if destination.resolve() == Path(source_path).resolve():
        raise ValueError('Choose a new output file; the source plan must be preserved')
    with destination.open('xb') as stream:
        stream.write(data)


def validate_output_name(name):
    """Require a single native header line usable as a Windows/macOS folder."""
    if (not name or not name.strip() or name != name.strip() or
            any(ord(c) < 32 or ord(c) == 127 for c in name) or
            any(c in '<>:"/\\|?*' for c in name) or name.endswith('.') or
            re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name)):
        raise ValueError('Plan name must be a nonempty valid folder name without control characters or surrounding spaces')
    try:
        return name.encode('cp1252')
    except UnicodeEncodeError as exc:
        raise ValueError('Plan name must use characters supported by the native Windows encoding') from exc


def prepare_red_output(data, mapping, name):
    """Apply one independent preset and replace only the native plan-name line."""
    encoded = validate_output_name(name)
    edited, changes, missing = apply_red_mapping(data, mapping)
    rows = edited.splitlines(keepends=True)
    old = rows[2]
    ending = b'\r\n' if old.endswith(b'\r\n') else old[-1:] if old.endswith((b'\r', b'\n')) else b''
    rows[2] = encoded + ending
    return b''.join(rows), changes, missing


def load_red_plans(source):
    """Load per-plan preview bytes in the application's scanning worker."""
    plans = discover_plans(source)
    with Export(source) as export:
        selections = {}
        for plan in plans:
            if not plan.get('error'):
                plan['data'] = export.read(plan['member'])
                try:
                    study_path = linked_study_path(export, plan)
                    if study_path not in selections:
                        selection = study_metadata(export, study_path)['ct_to_ed_name']
                        selections[study_path] = selection['value'] if selection else None
                    plan['ct_to_ed_name'] = selections[study_path]
                except (FormatError, ValueError, UnicodeError, OSError):
                    plan['ct_to_ed_name'] = None
    return plans


def export_red_patient(source, edits, destination, *, zipped=False):
    """Copy the entire source, replacing or cloning plans from original inputs.

    Each edit supplies a source member, optional output name and RED mapping.
    A blank name replaces that source plan only in the exported patient copy.
    Clone all plan companion files without interpreting or recalculating them.
    """
    source, destination = Path(source), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Output already exists: {destination}')
    if source.is_dir() and (source.resolve() == destination.resolve() or
                            source.resolve() in destination.resolve().parents):
        raise ValueError('Output must be outside the source patient folder')
    with Export(source) as export:
        directories = ({info.filename.rstrip('/') for info in export.zip.infolist() if info.is_dir()}
                       if export.zip else
                       {path.relative_to(source).as_posix() for path in source.rglob('*') if path.is_dir()})
        for directory in directories:
            parts = PurePosixPath(directory).parts
            if not parts or directory.startswith('/') or '..' in parts or '\\' in directory or ':' in parts[0]:
                raise FormatError(f'Unsafe export directory: {directory}')
        source_directories = set(directories)
        # Map each output member to its original member and optional replacement.
        members = {member: (member, None) for member in export.sizes}
        existing = {str(PurePosixPath(member).parent).casefold()
                    for member in export.sizes if PurePosixPath(member).name == 'plan'}
        occupied = {str(parent).casefold() for member in export.sizes
                    for parent in PurePosixPath(member).parents}
        occupied.update(directory.casefold() for directory in directories)
        targets = set()
        for edit in edits:
            member = edit['member']
            if member not in export.sizes:
                raise ValueError(f'Input plan not found: {member}')
            path = PurePosixPath(member)
            if path.name != 'plan' or path.parent.parent.name != 'plan':
                raise ValueError(f'Not a native plan member: {member}')
            data = export.read(member)
            metadata = plan_metadata(data, member)
            name = edit.get('name') or metadata['name']
            validate_output_name(name)
            target = path.parent if not edit.get('name') else path.parent.parent / name
            key = str(target).casefold()
            if key in targets:
                raise ValueError(f'Multiple tabs target the same output plan: {target}')
            targets.add(key)
            if target != path.parent and (key in existing or key in occupied):
                raise ValueError(f'Output plan already exists in source: {target}')
            edited, _, _ = prepare_red_output(data, edit['mapping'], name)
            prefix = str(path.parent) + '/'
            for directory in source_directories:
                if directory == str(path.parent) or directory.startswith(prefix):
                    directories.add(str(target / PurePosixPath(directory).relative_to(path.parent)))
            for original in export.sizes:
                if original.startswith(prefix):
                    output = str(target / PurePosixPath(original).relative_to(path.parent))
                    members[output] = (original, edited if original == member else None)
        # Stage the complete export before publishing it under the selected name.
        with tempfile.TemporaryDirectory(prefix='.hyperio-red-', dir=destination.parent) as temporary:
            staged = Path(temporary) / 'patient'
            staged.mkdir()
            if zipped:
                archive_path = Path(temporary) / 'patient.zip'
                with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                    for directory in sorted(directories):
                        archive.writestr(directory + '/', b'')
                    for output, (original, replacement) in members.items():
                        with archive.open(output, 'w', force_zip64=True) as stream:
                            if replacement is not None:
                                stream.write(replacement)
                            else:
                                with export.open(original) as input_stream:
                                    shutil.copyfileobj(input_stream, stream)
                # Exclusive creation also works on volumes without hard-link support.
                output_stream = destination.open('xb')
                try:
                    with output_stream, archive_path.open('rb') as input_stream:
                        shutil.copyfileobj(input_stream, output_stream)
                except Exception:
                    destination.unlink()
                    raise
            else:
                for directory in directories:
                    (staged / directory).mkdir(parents=True, exist_ok=True)
                for output, (original, replacement) in members.items():
                    path = staged / output
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open('xb') as stream:
                        if replacement is not None:
                            stream.write(replacement)
                        else:
                            with export.open(original) as input_stream:
                                shutil.copyfileobj(input_stream, stream)
                destination.mkdir()
                try:
                    for child in staged.iterdir():
                        child.rename(destination / child.name)
                except Exception:
                    shutil.rmtree(destination)
                    raise
    return destination
