"""Polygon records from native WC slices, independently of sampling policy."""
import math
from pathlib import PurePosixPath
import re

from .core import FormatError


def contour_slice(data: bytes, source: str, *, y_mm: float | None = None) -> dict:
    """Read leading polygon records from a 00091013 WC slice.

    Each record starts with a point count and structure index on separate lines,
    then exactly that many x/z pairs in native mm. A structure can have several
    polygons. Their union/hole semantics are deliberately left to the caller.
    Marker and other trailing records are preserved, not mistaken for polygons.
    """
    rows = data.decode('cp1252', errors='surrogateescape').splitlines()
    if len(rows) < 7 or rows[0] != '00091013':
        raise FormatError(f'{source}: unsupported contour slice header')
    if y_mm is None:
        match = re.fullmatch(r'T\.([+-]?(?:\d+(?:\.\d*)?|\.\d+))\.WC', PurePosixPath(source).name)
        if match is None:
            raise FormatError(f'{source}: supply y_mm or a T.<position>.WC filename')
        y_mm = float(match[1])
    if not math.isfinite(y_mm):
        raise FormatError(f'{source}: nonfinite slice coordinate')
    cursor, polygons = 7, []
    while cursor + 1 < len(rows):
        try:
            count, structure_index = int(rows[cursor]), int(rows[cursor + 1])
        except ValueError:
            break
        if count <= 0 or structure_index <= 0:
            break
        if count > 100_000 or count < 3:
            raise FormatError(f'{source}:{cursor + 1}: unsupported polygon point count')
        first_line = cursor + 1
        cursor += 2
        coordinates = []
        while len(coordinates) < count * 2 and cursor < len(rows):
            try:
                coordinates.extend(float(value) for value in rows[cursor].split(','))
            except ValueError as exc:
                raise FormatError(f'{source}:{cursor + 1}: polygon point count mismatch') from exc
            cursor += 1
        if len(coordinates) != count * 2 or not all(math.isfinite(value) for value in coordinates):
            raise FormatError(f'{source}:{first_line}: polygon point count mismatch/nonfinite coordinate')
        polygons.append({'structure_index': structure_index,
                         'points_xz_mm': [coordinates[index:index + 2] for index in range(0, len(coordinates), 2)],
                         'source': {'file': source, 'line': first_line}})
    return {'y_mm': float(y_mm), 'polygons': polygons, 'raw_header': rows[:7],
            'unparsed_tail': rows[cursor:], 'source': {'file': source, 'line': 1}}
