"""Source-independent DVH goal libraries, matching and plot coordinates."""
from fnmatch import fnmatchcase
import json
import math
from pathlib import Path
import re

DATA_DIRECTORY = Path(__file__).parent / 'data' / 'dvh'
NUMBER = r'(?:\d+(?:\.\d*)?|\.\d+)'
UNIT = r'(?:%|cc|cm3|cm³)'
OP = r'(?:<=|>=|<|>|=)'


def clean(text):
    return ' '.join(text.replace('\u200b', '').split())


def library_paths():
    return sorted(DATA_DIRECTORY.glob('*.json'), key=lambda p: p.name.casefold())


def regimens(page):
    return list(dict.fromkeys(group['regimen'] for group in page['groups']))


def matching_groups(page, regimen, structure):
    return [g for g in page['groups'] if g['regimen'] == regimen
            and any(fnmatchcase(structure.casefold(), p.casefold())
                    for p in g.get('structure_patterns', [g['organ']]))]


def goal_colour(point):
    """Colour only explicitly labelled goal levels; other limits stay black."""
    qualifier = point.get('qualifier', '').strip().casefold()
    if qualifier in ('ideal', 'tolerance'):
        return '#ff7f0e'
    if qualifier in ('acceptable', 'action'):
        return '#d62728'
    return 'black'


def marker(point):
    if point['operator'] == '=':
        return 'o'
    lower = point['operator'].startswith('<')
    return ('v' if lower else '^') if point['metric'] == 'V' else ('<' if lower else '>')


def parse_point(text):
    """Return a threshold coordinate, never an interpretation of clinical suitability."""
    text = clean(text).replace('≤', '<=').replace('≥', '>=').rstrip('.')
    v = re.fullmatch(rf'V\s*({NUMBER})\s*(cGy|Gy|%)\s*({OP})\s*({NUMBER})\s*({UNIT})', text, re.I)
    d = re.fullmatch(rf'D\s*({NUMBER})\s*({UNIT})\s*({OP})\s*({NUMBER})\s*(cGy|Gy|%)', text, re.I)
    if v:
        dose, dose_unit, operator, volume, volume_unit = v.groups()
        metric = 'V'
    elif d:
        volume, volume_unit, operator, dose, dose_unit = d.groups()
        metric = 'D'
    else:
        return None
    dose, volume = float(dose), float(volume)
    dose *= 100 if dose_unit.lower() == 'gy' else 1
    unit = '%' if volume_unit == '%' else 'cm3'
    if not math.isfinite(dose) or not math.isfinite(volume) or (unit == '%' and volume > 100):
        return None
    return dict(metric=metric, **{('dose_percent' if dose_unit == '%' else 'dose_cgy'): dose}, volume=volume, volume_unit=unit, operator=operator)


def overlay_points(group, volume_cm3, volume_unit, prescription_cgy=None):
    """Convert thresholds for the explicitly selected plan structure and volume axis."""
    if not math.isfinite(volume_cm3) or volume_cm3 <= 0:
        return []
    points = []
    for record in group['recommendations']:
        point = record.get('point')
        if point is None:
            continue
        point = dict(point)
        if 'dose_percent' in point:
            if prescription_cgy is None or not math.isfinite(prescription_cgy) or prescription_cgy <= 0:
                continue
            point['dose_cgy'] = point['dose_percent'] / 100 * prescription_cgy
        volume = point['volume']
        if point['volume_unit'] == 'cm3' and volume_unit == '%':
            volume = volume / volume_cm3 * 100
        elif point['volume_unit'] == '%' and volume_unit != '%':
            volume = volume / 100 * volume_cm3
        points.append(dict(point, volume=volume, text=record.get('point_expression', record['text']),
                           qualifier=record.get('qualifier', '')))
    return points


def load_catalogue(path):
    catalogue = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(catalogue, dict) or catalogue.get('schema_version') != 1 or not isinstance(catalogue.get('protocols'), list):
        raise ValueError('Unsupported DVH goal catalogue format')
    for page in catalogue['protocols']:
        for group in page['groups']:
            for record in group['recommendations']:
                point = record.get('point')
                if point is not None and (not isinstance(point, dict) or not point
                                          or point != parse_point(record.get('point_expression', record['text']))):
                    raise ValueError('Catalogue point differs from its recommendation text')
    return catalogue
