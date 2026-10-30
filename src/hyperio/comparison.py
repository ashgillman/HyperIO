"""Unit-specific software comparisons for a growing library of reference plans.

The policy compares calculated numbers with independent references. It is
separate from the clinical goal limits stored inside a treatment plan.
No fixture names or expected dose values belong in this module.
"""
from dataclasses import asdict, dataclass
import math
from numbers import Real


@dataclass(frozen=True)
class ComparisonPolicy:
    """Inclusive tolerance and action level in one explicit physical unit.

    |difference| <= tolerance: pass.
    tolerance < |difference| < action_level: review.
    |difference| >= action_level: action_required.
    """
    unit: str
    tolerance: float
    action_level: float

    def __post_init__(self):
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError('comparison unit must be a nonempty string')
        if not all(_finite(value) for value in (self.tolerance, self.action_level)):
            raise ValueError('comparison thresholds must be finite numbers')
        if not 0 <= self.tolerance < self.action_level:
            raise ValueError('require 0 <= tolerance < action_level')
        object.__setattr__(self, 'tolerance', float(self.tolerance))
        object.__setattr__(self, 'action_level', float(self.action_level))


def _finite(value):
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def compare_numeric(actual, expected, unit, policies):
    """Compare unrounded values and retain signed and absolute differences.

    No policy for the unit, missing results and nonfinite results remain
    not_evaluated. A cGy policy never becomes a cm³ or dimensionless policy.
    A 1e-12 representation allowance is used only at threshold boundaries.
    """
    if not _finite(expected):
        raise ValueError('reference value must be a finite number')
    policy = policies.get(unit)
    if policy is not None and policy.unit != unit:
        raise ValueError('policy unit disagrees with its mapping key')
    result = {'expected': float(expected), 'actual': float(actual) if _finite(actual) else None,
              'unit': unit, 'difference': None, 'absolute_difference': None,
              'status': 'not_evaluated', 'policy': asdict(policy) if policy else None,
              'reason': None}
    if not _finite(actual):
        result['reason'] = 'missing or nonfinite calculated value'
        return result
    difference = float(actual) - float(expected)
    absolute = abs(difference)
    result.update(difference=difference, absolute_difference=absolute)
    if policy is None:
        result['reason'] = f'no policy for unit {unit}'
    elif absolute <= policy.tolerance or math.isclose(absolute, policy.tolerance, rel_tol=0, abs_tol=1e-12):
        result['status'] = 'pass'
    elif absolute >= policy.action_level or math.isclose(absolute, policy.action_level, rel_tol=0, abs_tol=1e-12):
        result['status'] = 'action_required'
    else:
        result['status'] = 'review'
    return result


def _unique(rows, field, description):
    keyed = {}
    for row in rows:
        identity = row[field]
        if identity in keyed:
            raise ValueError(f'duplicate {description}: {identity!r}')
        keyed[identity] = row
    return keyed


def _one(matches, description):
    if len(matches) > 1:
        raise ValueError(f'duplicate {description}')
    return matches[0] if matches else {}


def compare_dvh_results(calculated, reference, policies):
    """Join calculated DVH records to independently transcribed reference data.

    The reference uses the documented plan-library GT schema: structure
    statistics, displayed goal quantities, DRPs, and optionally annotated free
    reference-dose requests. Only calculated outputs are compared; echoing a
    query's input dose/volume is not a successful numerical reconstruction.
    """
    structures = _unique(calculated.get('structures', []), 'structure', 'calculated structure')
    _unique(reference.get('dvh_statistics', []), 'structure', 'reference structure')
    results = []

    def add(identity, actual, expected, unit):
        if expected is not None:
            results.append({'id': identity, **compare_numeric(actual, expected, unit, policies)})

    units = {'volume_cm3': 'cm3', 'min_dose_cgy': 'cGy', 'max_dose_cgy': 'cGy',
             'mean_dose_cgy': 'cGy', 'heterogeneity_index': 'dimensionless',
             'conformity_index': 'dimensionless', 'percent_in_volume': '%'}
    for expected in reference.get('dvh_statistics', []):
        name = expected['structure']
        actual = structures.get(name, {})
        for metric, unit in units.items():
            if metric in expected:
                # A separately labelled Paddick candidate is intentionally not
                # substituted for an unestablished Monaco conformity index.
                add(f'statistics/{name}/{metric}', actual.get(metric), expected[metric], unit)

    for index, expected in enumerate(reference.get('dose_goals', [])):
        name, metric = expected['structure'], expected['metric']
        matches = []
        for candidate in structures.get(name, {}).get('criterion_results', []):
            goal = candidate.get('goal', {})
            same_operator = 'operator' not in expected or goal.get('operator') == expected['operator']
            same_limit = 'limit' not in expected or _finite(goal.get('limit')) and math.isclose(
                goal['limit'], expected['limit'], rel_tol=0, abs_tol=1e-12)
            if candidate['metric'] == metric and same_operator and same_limit:
                matches.append(candidate)
        actual = _one(matches, f'calculated goal {name}/{metric}')
        reference_unit = expected.get('unit') or expected.get('limit_unit')
        actual_unit = actual.get('goal', {}).get('limit_unit')
        if reference_unit and actual_unit and reference_unit != actual_unit:
            raise ValueError(f'goal units disagree for {name}/{metric}: {reference_unit} versus {actual_unit}')
        # Prefer explicit units: Vdose can be either cm³ or percent even though
        # its metric label is identical. The fallback supports older GT files.
        unit = reference_unit or actual_unit or (
            'cGy' if metric.startswith('D') else '%' if metric.startswith('V') else 'dimensionless')
        add(f'criteria/{name}/{metric}/{index}', actual.get('actual'), expected['displayed_value'], unit)

    points = _unique(calculated.get('dose_reference_point_samples', []), 'description', 'calculated DRP')
    for expected in reference.get('dose_reference_points', []):
        description = expected['description']
        add(f'drp/{description}/plan_dose_cgy', points.get(description, {}).get('sampled_dose_cgy'),
            expected['total_dose_cgy'], 'cGy')

    for expected in reference.get('dvh_reference_rows', []):
        if expected.get('origin') != 'request':
            continue
        name, query = expected['structure'], expected['query']
        matches = [candidate for candidate in structures.get(name, {}).get('reference_requests', [])
                   if candidate.get('query') == query]
        actual = _one(matches, f'calculated reference request {name}/{query}')
        outputs = {'volume_percent': ('ref_volume_percent', '%'), 'volume_cm3': ('ref_volume_cm3', 'cm3')}
        if query['quantity'] in ('relative_volume', 'absolute_volume'):
            outputs = {'dose_cgy': ('ref_dose_cgy', 'cGy'),
                       **({'volume_cm3': ('ref_volume_cm3', 'cm3')} if query['quantity'] == 'relative_volume' else {})}
        for metric, (reference_field, unit) in outputs.items():
            identity = f'reference/{name}/{query["quantity"]}={query["value"]:g}/{metric}'
            add(identity, actual.get(metric), expected[reference_field], unit)
    return results
