"""Saved optimisation and DVH configuration readers.

These readers preserve native values and provenance and do not calculate dose.
Named records are independent of patient, plan and structure names.

Observed layouts:
- .hyp 000610b6: VOIDEF > COSTFUNCTION > SHRINKMARGINTARGET blocks, with
  key=value properties and an !END for each level.
- dvhparam.xml version 1: XmlFileIo/Data/DvhParams.
- isodosesettings.xml version 5: per-structure index settings, reference-dose
  requests and DoseGoal records under DoseStructureParametersList.

Native objective doses are Gy, XML goal doses are cGy, and native objective
margins are mm. These conventions are kept separate from display conversions.
See docs/format-notes.md for evidence and the limits of each mapping.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from .core import BLOCKS, Field, FormatError


# Names/units from PlanCheck's format mapping; qp/o_q/se/pa additionally have
# screenshot evidence in reports/vmat-2026-10-29.md. Unknown types stay literal.
OBJECTIVES = {
    'po': ('Target EUD', 'cGy'), 'qp': ('Target Penalty', 'cGy'),
    'o_q': ('Quadratic Overdose', 'cGy'), 'pa': ('Parallel', '%'),
    'se': ('Serial', 'cGy'), 'o_v': ('Overdose DVH', '%'),
    'u_v': ('Underdose DVH', '%'), 'mxd': ('Maximum Dose', 'cGy'),
    'u_q': ('Quadratic Underdose', 'cGy'), 'conf': ('Conformality', None),
}
# Saved optimizer output can contain Windows C-runtime spellings as well as
# XML's INF. Keep the spelling and its meaning without emitting NaN/Infinity
# into JSON or treating an uncalculated effect as a zero dose.
SPECIAL_NUMBERS = {
    'INF': 'positive_infinity', '+INF': 'positive_infinity', '-INF': 'negative_infinity',
    '1.#INF': 'positive_infinity', '-1.#INF': 'negative_infinity',
    'NAN': 'not_a_number', '-NAN': 'not_a_number',
    '1.#IND': 'not_a_number', '-1.#IND': 'not_a_number',
    '1.#QNAN': 'not_a_number', '-1.#QNAN': 'not_a_number',
    '1.#SNAN': 'not_a_number', '-1.#SNAN': 'not_a_number',
}


def _number(raw, context, *, special=False):
    """Return a finite value or an explicit unknown, preserving raw text outside."""
    if raw is None:
        return None
    if special and raw.upper() in SPECIAL_NUMBERS:
        return None
    try:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError('nonfinite value')
        return value
    except ValueError as exc:
        raise FormatError(f'{context}: invalid finite number {raw!r}') from exc


def _boolean(raw, context):
    if raw is None:
        return None
    if raw not in ('0', '1', 'true', 'false'):
        raise FormatError(f'{context}: invalid boolean {raw!r}')
    return raw in ('1', 'true')


def _impact_symbols(relative_impact):
    """Map a saved impact to the four UI bands used in PlanCheck's report."""
    if relative_impact is None:
        return None
    if relative_impact <= 0:
        return ''
    for symbol_count, upper_bound in enumerate((.25, .5, .75), 1):
        if relative_impact < upper_bound:
            return '+' * symbol_count
    return '++++'


def cost_functions(data: bytes, source: str = '<memory>') -> list[dict]:
    """Read all .hyp VOIDEF/COSTFUNCTION records with individual target margins.

    Output doses are cGy and convenience shrink margins are cm.
    ``fields`` retains native Gy/mm values, tokens and one-based source lines.
    Missing values stay None; unknown types are retained with diagnostics.
    """
    lines = data.decode('cp1252', errors='surrogateescape').splitlines()
    if not lines or lines[0] != '000610b6':
        raise FormatError(f'{source}: unsupported .hyp header')
    # Keep the parent block until the complete structure is read. A structure
    # name is a property, not an implicit association with a previous row.
    block_stack, objective_blocks = [], []
    for line_number, raw in enumerate(lines[1:], 2):
        line = raw.strip()
        if line == '!END':
            if not block_stack:
                raise FormatError(f'{source}:{line_number}: unbalanced block end')
            block = block_stack.pop()
            if block['kind'] == 'COSTFUNCTION':
                objective_blocks.append((block_stack[-1], block))
        elif line.startswith('!') and line[1:] in BLOCKS:
            # Only the known grammar declares blocks. A valueless scalar such
            # as !PROTON_RBE_MODEL_ID must not consume a future !END.
            block_kind = line[1:]
            expected_parent = {'VOIDEF': None, 'COSTFUNCTION': 'VOIDEF', 'SHRINKMARGINTARGET': 'COSTFUNCTION'}
            if block_kind in expected_parent and (block_stack[-1]['kind'] if block_stack else None) != expected_parent[block_kind]:
                raise FormatError(f'{source}:{line_number}: invalid {block_kind} scope')
            block = {'kind': block_kind, 'line': line_number, 'fields': {}, 'children': []}
            if block_stack:
                block_stack[-1]['children'].append(block)
            block_stack.append(block)
        elif '=' in line and block_stack and block_stack[-1]['kind'] in ('VOIDEF', 'COSTFUNCTION', 'SHRINKMARGINTARGET'):
            key, value = (s.strip() for s in line.split('=', 1))
            fields = block_stack[-1]['fields']
            if key in fields:
                raise FormatError(f'{source}:{line_number}: duplicate {key}')
            fields[key] = Field(value, source, line_number, value, interpretation='literal .hyp record').as_dict()
    if block_stack:
        raise FormatError(f'{source}: incomplete .hyp blocks')
    results = []
    for structure_block, block in objective_blocks:
        if not structure_block['fields'].get('name', {}).get('value'):
            raise FormatError(f'{source}:{structure_block["line"]}: structure name missing')
        # Keep a typed native-field view alongside the original key/value text.
        # UI-unit conversion below must not overwrite these original values.
        fields = {key: field.copy() for key, field in block['fields'].items()}
        raw = {key: field['raw'] for key, field in fields.items()}
        objective_type = raw.get('type')
        objective_name, effect_unit = OBJECTIVES.get(objective_type, (None, None))
        diagnostics = [] if objective_type in OBJECTIVES else [f'unsupported objective type {objective_type!r}; native fields retained']
        for key, field in fields.items():
            if key in ('manual', 'multicriterial'):
                field['value'] = _boolean(field['raw'], f'{source}:{field["line"]}')
            elif key in ('weight', 'status', 'refdose', 'thresholddose', 'exponent',
                         'isoconstraint', 'isoeffect', 'relativeimpact', 'refvolume'):
                field['value'] = _number(field['raw'], f'{source}:{field["line"]}', special=True)
                if field['raw'].upper() in SPECIAL_NUMBERS:
                    field['special_value'] = SPECIAL_NUMBERS[field['raw'].upper()]
            if key in ('refdose', 'thresholddose') or key in ('isoconstraint', 'isoeffect') and effect_unit == 'cGy':
                field['unit'] = 'Gy'
            elif key in ('isoconstraint', 'isoeffect') and effect_unit == '%':
                field['unit'] = '%'
        def field_value(field_name):
            return fields.get(field_name, {}).get('value')

        status = field_value('status')
        if status is not None and status not in (0, 1, 2, 3):
            diagnostics.append(f'unsupported objective status {status!r}')
        # Each shrink record names its own target. Unequal margins are valid;
        # reducing them to a single number would lose optimization geometry.
        margins = []
        for child in block['children']:
            if child['kind'] != 'SHRINKMARGINTARGET':
                continue
            margin_fields = {key: field.copy() for key, field in child['fields'].items()}
            target = margin_fields.get('shrinkmargintarget', {}).get('raw')
            margin = _number(margin_fields.get('targetmargin', {}).get('raw'), f'{source}:{child["line"]}: targetmargin')
            if not target or margin is None:
                raise FormatError(f'{source}:{child["line"]}: incomplete shrink margin target')
            margin_fields['targetmargin'].update(value=margin, unit='mm')
            margins.append({'structure': target, 'margin_mm': margin, 'fields': margin_fields})
        unique_margin_values = {m['margin_mm'] for m in margins}
        # Parallel's reference dose is refdose, not thresholddose. This differs
        # from quadratic overdose and is independently visible in the VMAT GT.
        reference_dose_key = {
            'pa': 'refdose', 'o_q': 'thresholddose', 'o_v': 'thresholddose',
            'u_v': 'thresholddose', 'u_q': 'thresholddose',
        }.get(objective_type)
        reference_dose_gy = field_value(reference_dose_key)
        effect_scale = 100 if effect_unit == 'cGy' else 1

        def display_effect(field_name):
            native_effect = field_value(field_name)
            if objective_type not in OBJECTIVES or native_effect is None:
                return None
            return native_effect * effect_scale

        relative_impact = field_value('relativeimpact')
        results.append({
            'structure': structure_block['fields']['name']['raw'], 'type_code': objective_type, 'cost_function': objective_name,
            'status': {0: 'Off', 1: 'On', 2: 'Infeasible', 3: 'Offending'}.get(status),
            'manual': field_value('manual'), 'multicriterial': field_value('multicriterial'),
            'weight': field_value('weight'),
            'reference_dose_cgy': reference_dose_gy * 100 if reference_dose_gy is not None else None,
            'exponent': field_value('exponent') if objective_type in ('se', 'pa') else None,
            'shrink_margin_targets': margins,
            'shrink_margin_cm': next(iter(unique_margin_values)) / 10 if len(unique_margin_values) == 1 else None,
            'isoconstraint': display_effect('isoconstraint'),
            'isoeffect': display_effect('isoeffect'), 'effect_unit': effect_unit,
            'relative_impact_value': relative_impact,
            'relative_impact': _impact_symbols(relative_impact),
            'fields': fields, 'raw': raw, 'source_line': block['line'],
            'source': {'file': source, 'line': block['line']}, 'diagnostics': diagnostics,
        })
    return results


def _xml(data, source, tag):
    """Select one observed XML document payload and validate its own version."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise FormatError(f'{source}: invalid XML: {exc}') from exc
    # Monaco exports can declare a namespace only on the wrapper or on every
    # element. Match local names while keeping the same parent/child paths.
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    if root.tag != 'XmlFileIo':
        raise FormatError(f'{source}: unsupported XML root {root.tag!r}')
    versions = root.findall('./Metadata/Version')
    # Metadata versions belong to individual XML schemas, not a TPS release.
    supported_version = {'DvhParams': '1', 'IsodoseSettings': '5'}[tag]
    if len(versions) > 1 or versions and versions[0].text != supported_version:
        raise FormatError(f'{source}: unsupported XML metadata version')
    matches = root.findall(f'./Data/{tag}')
    if len(matches) != 1:
        raise FormatError(f'{source}: expected one {tag} element')
    return matches[0]


def _leaves(element, source, path):
    """Retain direct scalar children; nested lists are handled by their reader."""
    result = {}
    for child in element:
        if len(child):
            continue
        if child.tag in result:
            raise FormatError(f'{source}:{path}: duplicate {child.tag}')
        result[child.tag] = child.text
    return result


def dvh_parameters(data: bytes, source: str = '<memory>') -> dict:
    """Read saved DVH sampling spacing (mm) and dose bin width (cGy).

    Resolution describes the DVH sampling grid, independently of .hyp's dose
    calculation grid. Neither value defines the DVH sampling grid's phase.
    """
    element = _xml(data, source, 'DvhParams')
    raw = _leaves(element, source, '/XmlFileIo/Data/DvhParams')
    resolution = _number(raw.get('Resolution'), f'{source}: Resolution')
    width = _number(raw.get('BinWidth'), f'{source}: BinWidth')
    if resolution is not None and resolution <= 0 or width is not None and width <= 0:
        raise FormatError(f'{source}: DVH spacing and bin width must be positive')
    return {'resolution_mm': resolution, 'bin_width_cgy': width,
            'raw': raw, 'source': {'file': source, 'path': '/XmlFileIo/Data/DvhParams'}}


def isodose_settings(data: bytes, source: str = '<memory>') -> dict:
    """Read structure index settings, reference requests and all 14 goal types.

    Absolute volume goal values are native mm³, exposed as cm³.
    Unknown goal types and nonfinite optional bounds retain their raw XML text.
    No goal is evaluated and no histogram results are inferred from definitions.
    """
    element = _xml(data, source, 'IsodoseSettings')
    structures, goals = [], []
    for structure_index, structure in enumerate(element.findall('./DoseStructureParametersList/DoseStructureParameter'), 1):
        structure_path = f'/XmlFileIo/Data/IsodoseSettings/DoseStructureParametersList/DoseStructureParameter[{structure_index}]'
        structure_fields = _leaves(structure, source, structure_path)
        structure_name = structure_fields.get('StructureName')
        if not structure_name:
            raise FormatError(f'{source}:{structure_path}: missing StructureName')
        # RefDose entries are requested cursors/quantiles, not cached results.
        # Goal-linked rows are defined separately in DoseGoalList below.
        reference_doses = []
        for record_index, reference in enumerate(structure.findall('./RefDoseList/RefDose'), 1):
            reference_path = f'{structure_path}/RefDoseList/RefDose[{record_index}]'
            reference_fields = _leaves(reference, source, reference_path)
            try:
                reference_type = int(reference_fields['RefType'])
            except (KeyError, TypeError, ValueError) as exc:
                raise FormatError(f'{source}:{reference_path}: invalid RefType') from exc
            # Only 0 (dose) and 1 (relative volume) have screenshot evidence.
            quantity, reference_unit = {0: ('dose', 'cGy'), 1: ('relative_volume', '%')}.get(reference_type, (None, None))
            reference_value = None
            if reference_type in (0, 1) and reference_fields.get('RefValue') != '-1':
                reference_value = _number(reference_fields.get('RefValue'), f'{source}:{reference_path}')
            reference_doses.append({
                'type_code': reference_type, 'quantity': quantity, 'value': reference_value,
                'unit': reference_unit, 'raw': reference_fields,
                'source': {'file': source, 'path': reference_path},
            })
        # Older exports use -1 for unset fields. Preserve the token in raw;
        # do not turn the Enabled sentinel into True or a -1 cGy prescription.
        structures.append({
            'structure': structure_name, 'enabled': _boolean(structure_fields.get('Enabled'), f'{source}:{structure_path}') if structure_fields.get('Enabled') != '-1' else None,
            'high_dose_ref_percent': _number(structure_fields.get('HighDoseRef'), source),
            'min_dose_ref_percent': _number(structure_fields.get('MinDoseRef'), source),
            'prescribed_dose_cgy': _number(structure_fields.get('PrescribedDose'), source) if structure_fields.get('PrescribedDose') != '-1' else None,
            'reference_doses': reference_doses, 'raw': structure_fields, 'source': {'file': source, 'path': structure_path},
        })
        for record_index, goal in enumerate(structure.findall('./DoseGoalList/DoseGoal'), 1):
            goal_path = f'{structure_path}/DoseGoalList/DoseGoal[{record_index}]'
            goal_fields = _leaves(goal, source, goal_path)
            try:
                goal_type = int(goal_fields['GoalType'])
            except (KeyError, TypeError, ValueError) as exc:
                raise FormatError(f'{source}:{goal_path}: invalid GoalType') from exc
            metric = operator = limit = unit = None
            diagnostics = []
            tolerance = _number(goal_fields.get('Tolerance'), f'{source}:{goal_path}:Tolerance', special=True)
            if 1 <= goal_type <= 14:
                dose_cgy = _number(goal_fields.get('Dose'), f'{source}:{goal_path}:Dose', special=True)
                native_volume = _number(goal_fields.get('Volume'), f'{source}:{goal_path}:Volume', special=True)
                index_limit = _number(goal_fields.get('Index'), f'{source}:{goal_path}:Index', special=True)
                operator = '>=' if goal_type in (1, 3, 5, 6, 9, 10, 14) else '<='
                # GoalType selects which XML scalar is constrained:
                # 1-4: min/max/mean dose; 5-8: dose to a volume;
                # 9-12: volume receiving a dose; 13-14: HI/CI index.
                # Variants select lower/upper bounds and relative/absolute
                # volume; the numeric parity alone does not give direction.
                if goal_type <= 4:
                    metric, limit, unit = {1: 'Dmin', 2: 'Dmax', 3: 'Dmean', 4: 'Dmean'}[goal_type], dose_cgy, 'cGy'
                elif goal_type <= 8:
                    if native_volume is not None:
                        metric = f'D{native_volume:g}%' if goal_type in (5, 7) else f'D{native_volume / 1000:g}cm3'
                    limit, unit = dose_cgy, 'cGy'
                elif goal_type <= 12:
                    # Volume limits and their tolerances share native units.
                    # The absolute variants store mm³, unlike percent variants.
                    metric = f'V{dose_cgy:g}cGy' if dose_cgy is not None else None
                    absolute_volume = goal_type in (10, 12)
                    limit = native_volume / 1000 if absolute_volume and native_volume is not None else native_volume
                    unit = 'cm3' if absolute_volume else '%'
                    if absolute_volume and tolerance is not None:
                        tolerance /= 1000
                else:
                    # HI/CI use Index. Dose is often zero in these records.
                    metric, limit = ('HI' if goal_type == 13 else 'CI'), index_limit
                if metric is None or limit is None:
                    diagnostics.append('missing/nonfinite goal quantity; raw XML retained')
            else:
                diagnostics.append(f'unsupported goal type {goal_type}; raw XML retained')
            goals.append({'structure': structure_name, 'goal_type': goal_type, 'metric': metric, 'operator': operator,
                          'limit': limit, 'limit_unit': unit, 'tolerance': tolerance,
                          'raw': goal_fields, 'source': {'file': source, 'path': goal_path}, 'diagnostics': diagnostics})
    return {'structures': structures, 'dose_goals': goals,
            'source': {'file': source, 'path': '/XmlFileIo/Data/IsodoseSettings'}}
