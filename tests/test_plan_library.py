"""Examples: run every registered plan under shared, unit-specific policies.

Run with ``python3 -m pytest tests/test_plan_library.py -v`` after installing
``.[analysis]`` and providing each case's private archive as documented in
tests/plan_library/README.md. Tests are parameterized by the registry, not by
hardcoded plan names. Inspect the warning summary for review-level results.

Only differences within tolerance have status 'pass'. Review-level findings
are reported as warnings, and action-level or unavailable dose results fail
the action-gate test. Non-dose quantities have no invented dose tolerance.
"""
from collections import Counter
import json
from pathlib import Path
import warnings

import pytest

from hyperio import calculate_plan_dvh, compare_dvh_results
from plan_cases import load_plan_library


LIBRARY = load_plan_library(Path(__file__).parent / 'plan_library/cases.json')


@pytest.fixture(scope='module', params=LIBRARY.cases, ids=lambda case: case.id)
def plan_comparisons(request):
    """Calculate each available case once; the library never sees its GT.

    Separate calculation from comparison so reference values cannot influence
    dose decoding, contour sampling or histogram construction.
    """
    for dependency in ('numpy', 'scipy', 'shapely', 'unlzw3'):
        pytest.importorskip(dependency)
    case = request.param
    source = case.resolve_source()
    if source is None:
        pytest.skip(f'{case.id}: supply {case.source_environment} or {case.source_fallback}')
    calculated = calculate_plan_dvh(source, case.plan_name, **case.calculation_options)
    comparisons = compare_dvh_results(calculated, case.reference, LIBRARY.policies)
    return case, comparisons


def test_no_missing_or_action_level_discrepancies(plan_comparisons, record_property):
    """Enforce the action gate and preserve every review result in test reports.

    A successful action gate does not mean every metric passed tolerance.
    The result objects and warning report preserve that distinction, including
    signed unrounded differences. JUnit XML can retain the full result records.
    """
    case, comparisons = plan_comparisons
    dose = [result for result in comparisons if result['unit'] == 'cGy']
    assert dose, f'{case.id}: no reference dose quantities were compared'
    assessed = [result for result in comparisons if result['unit'] in LIBRARY.policies]
    record_property('plan_comparisons', json.dumps(comparisons, allow_nan=False))
    missing = [result for result in assessed if result['status'] == 'not_evaluated']
    action = [result for result in assessed if result['status'] == 'action_required']
    reviews = [result for result in assessed if result['status'] == 'review']
    counts = Counter(result['status'] for result in dose)
    unassessed = sum(result['status'] == 'not_evaluated' for result in comparisons if result['unit'] not in LIBRARY.policies)
    if reviews or unassessed:
        details = '; '.join(f"{result['id']}: {result['difference']:+.6f} {result['unit']}" for result in reviews)
        warnings.warn(
            f"{case.id}: dose comparisons {dict(counts)}; "
            f"{unassessed} non-dose quantities not evaluated. Review: {details or 'none'}",
            UserWarning,
        )
    assert not missing, f'{case.id}: unavailable results with configured policies: {missing}'
    assert not action, f'{case.id}: action-level differences: {action}'


def test_registry_can_add_plans_without_changing_test_code(tmp_path):
    """Two data entries can locate distinct archives and independently named GT."""
    for name in ('First', 'Second'):
        (tmp_path / f'{name}.json').write_text(json.dumps({'plan': {'name': name}}))
    archive = tmp_path / 'first.zip'
    archive.write_bytes(b'local fixture placeholder')
    registry = {'schema_version': 1, 'comparison_policies': {'cGy': {'tolerance': .1, 'action_level': 1}},
                'cases': [
                    {'id': 'one', 'plan_name': 'First', 'source': {'environment': 'FIRST_ARCHIVE'}, 'ground_truth': 'First.json'},
                    {'id': 'two', 'plan_name': 'Second', 'source': {'path': 'absent.zip'}, 'ground_truth': 'Second.json'},
                ]}
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps(registry))
    library = load_plan_library(path)
    assert [case.plan_name for case in library.cases] == ['First', 'Second']
    assert library.cases[0].resolve_source({'FIRST_ARCHIVE': str(archive)}) == archive
    assert library.cases[1].resolve_source({}) is None
    with pytest.raises(FileNotFoundError):
        library.cases[0].resolve_source({'FIRST_ARCHIVE': str(tmp_path / 'missing.zip')})
    registry['cases'][1]['id'] = 'one'
    path.write_text(json.dumps(registry))
    with pytest.raises(ValueError, match='duplicate'):
        load_plan_library(path)
