"""Content snapshots for controlled save experiments; no timestamp filtering."""
import difflib
import hashlib
from pathlib import Path

from .core import Export


def snapshot(path: str | Path, text_limit: int = 128_000) -> dict:
    """Hash every member, streaming large images/dose; retain small UTF-8 text."""
    files = {}
    with Export(path) as export:
        for name, size in sorted(export.sizes.items()):
            digest = hashlib.sha256()
            chunks = []
            with export.open(name) as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                    if size <= text_limit:
                        chunks.append(chunk)
            record = {"size": size, "sha256": digest.hexdigest()}
            if size <= text_limit:
                data = b"".join(chunks)
                try:
                    text = data.decode("utf-8")
                    if all(ord(c) >= 32 or c in "\r\n\t" for c in text):
                        record["text"] = text
                except UnicodeDecodeError:
                    pass
            files[name] = record
    return {"schema_version": 1, "source": str(path), "files": files}


def diff_snapshots(before: dict, after: dict) -> list[dict]:
    changes = []
    for name in sorted(before["files"].keys() | after["files"].keys()):
        old = before["files"].get(name)
        new = after["files"].get(name)
        if old and new and old["sha256"] == new["sha256"]:
            continue
        change = {"path": name, "status": "added" if old is None else "removed" if new is None else "changed",
                  "before_sha256": old["sha256"] if old else None,
                  "after_sha256": new["sha256"] if new else None}
        if old and new and "text" in old and "text" in new:
            change["text_diff"] = "".join(difflib.unified_diff(old["text"].splitlines(keepends=True),
                                                            new["text"].splitlines(keepends=True),
                                                            fromfile="before/" + name, tofile="after/" + name))
        changes.append(change)
    return changes
