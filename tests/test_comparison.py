"""Examples: classify reconstruction differences using an explicit unit policy.

These tests need no private plans or optional analysis packages. Policies are
software-comparison thresholds, independent of a plan's clinical dose goals.
"""
import pytest

from hyperio import ComparisonPolicy, compare_numeric, compare_dvh_results


DOSE_POLICY = ComparisonPolicy(unit='cGy', tolerance=.1, action_level=1)


@pytest.mark.parametrize('actual,expected,status', [
    (10, 10, 'pass'), (10.1, 10, 'pass'), (9.9, 10, 'pass'),
    (10.1001, 10, 'review'), (10.999, 10, 'review'),
    (11, 10, 'action_required'), (9, 10, 'action_required'),
    (12, 10, 'action_required'),
])
def test_classify_absolute_differences_in_both_directions(actual, expected, status):
    """Tolerance is inclusive; the action level is reached at 1 cGy, not above it."""
    result = compare_numeric(actual, expected, 'cGy', {'cGy': DOSE_POLICY})
    assert result['status'] == status
    assert result['difference'] == pytest.approx(actual - expected)
    assert result['absolute_difference'] == pytest.approx(abs(actual - expected))


def test_compare_unrounded_values_without_borrowing_a_dose_policy_for_volume():
    """A mean-dose residual is review-level; cm³ needs its own explicit policy."""
    result = compare_numeric(2104.725789, 2104.4, 'cGy', {'cGy': DOSE_POLICY})
    assert result['status'] == 'review'
    assert result['difference'] == pytest.approx(.325789)
    volume = compare_numeric(32.750, 32.735, 'cm3', {'cGy': DOSE_POLICY})
    assert volume['status'] == 'not_evaluated'
    assert volume['difference'] == pytest.approx(.015)
    assert 'no policy' in volume['reason']


@pytest.mark.parametrize('actual', [None, float('nan'), float('inf')])
def test_unavailable_values_do_not_acquire_a_pass(actual):
    result = compare_numeric(actual, 20, 'cGy', {'cGy': DOSE_POLICY})
    assert result['status'] == 'not_evaluated'
    assert result['difference'] is None


@pytest.mark.parametrize('tolerance,action_level', [(-.1, 1), (.1, .1), (1, .1), (.1, float('inf'))])
def test_invalid_policy_is_rejected(tolerance, action_level):
    with pytest.raises(ValueError):
        ComparisonPolicy('cGy', tolerance, action_level)


def test_result_collection_uses_explicit_metrics_and_reports_missing_values():
    """Join results to GT by identity, so array order cannot select another organ."""
    reference = {'dvh_statistics': [
        {'structure': 'A', 'mean_dose_cgy': 10, 'volume_cm3': 2},
        {'structure': 'B', 'mean_dose_cgy': 30},
    ]}
    actual = {'structures': [
        {'structure': 'B', 'mean_dose_cgy': 31},
        {'structure': 'A', 'mean_dose_cgy': 10.2, 'volume_cm3': 2},
    ]}
    results = compare_dvh_results(actual, reference, {'cGy': DOSE_POLICY})
    keyed = {result['id']: result for result in results}
    assert keyed['statistics/A/mean_dose_cgy']['status'] == 'review'
    assert keyed['statistics/B/mean_dose_cgy']['status'] == 'action_required'
    assert keyed['statistics/A/volume_cm3']['status'] == 'not_evaluated'
    actual['structures'].pop()
    missing = compare_dvh_results(actual, reference, {'cGy': DOSE_POLICY})
    assert next(result for result in missing if result['id'] == 'statistics/A/mean_dose_cgy')['status'] == 'not_evaluated'


def test_duplicate_actual_identities_are_rejected_instead_of_using_the_first():
    with pytest.raises(ValueError, match='duplicate'):
        compare_dvh_results({'structures': [{'structure': 'A'}, {'structure': 'A'}]}, {}, {'cGy': DOSE_POLICY})


def test_absolute_volume_goals_keep_their_units_and_mismatched_gt_units_fail():
    """Vdose labels alone cannot distinguish an absolute volume from a percentage."""
    goal = {'metric': 'V500cGy', 'operator': '<=', 'limit': 3, 'limit_unit': 'cm3'}
    actual = {'structures': [{'structure': 'A', 'criterion_results': [
        {'metric': 'V500cGy', 'actual': 2.5, 'goal': goal},
    ]}]}
    expected = {'dose_goals': [{'structure': 'A', 'metric': 'V500cGy', 'operator': '<=',
                               'limit': 3, 'displayed_value': 2.5, 'unit': 'cm3'}]}
    result = compare_dvh_results(actual, expected, {'cGy': DOSE_POLICY})[0]
    assert result['unit'] == 'cm3'
    assert result['status'] == 'not_evaluated'
    expected['dose_goals'][0]['unit'] = '%'
    with pytest.raises(ValueError, match='units disagree'):
        compare_dvh_results(actual, expected, {'cGy': DOSE_POLICY})
