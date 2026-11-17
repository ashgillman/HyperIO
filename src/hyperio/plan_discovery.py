"""Plan selection from native Monaco directories and ZIP archives."""
from pathlib import PurePosixPath

from .core import Export, FormatError, plan_identity, plan_metadata


def discover_plans(source, *, lazy=False):
    """List plans by full member path, keeping duplicate plan names distinct.

    Lazy discovery reads only identity headers; full validation waits for use.
    RED previews retain the default full density-table parsing.
    """
    result = []
    with Export(source) as export:
        for member in sorted(export.sizes):
            path = PurePosixPath(member)
            if path.name != 'plan' or path.parent.parent.name != 'plan':
                continue
            try:
                if lazy:
                    # Bound each line as well as the total header read.
                    with export.open(member) as stream:
                        rows = [stream.readline(4096) for _ in range(7)]
                    if any(len(row) == 4096 and not row.endswith(b'\n') for row in rows):
                        raise FormatError('plan identity header line exceeds limit')
                    header = b''.join(rows)
                    metadata = plan_identity(header, member)
                else:
                    metadata = plan_metadata(export.read(member), member)
            except FormatError as exc:
                result.append({'path': str(path.parent), 'member': member,
                               'label': f'{path.parent} [unreadable: {exc}]', 'error': str(exc)})
                continue
            result.append({**metadata, 'path': str(path.parent), 'member': member,
                           'label': f'{metadata["patient_id"]} / {metadata["studyset"]} / '
                                    f'{metadata["name"]} [{path.parent}]', 'error': None})
    return result
