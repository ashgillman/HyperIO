"""Examples: compare a returned Monaco plan with independently supplied UI values.

Run these integration examples with the private native archive::

    export HYPERIO_VMAT_ARCHIVE='/absolute/path/to/returned-plan.zip'
    python3 -m pytest tests/test_vmat_evidence.py -v

The archive is read through the public ``inspect_export`` API, which accepts
either a ZIP or an extracted patient directory. Inspect once, choose a plan
from ``report['plans']``, and use its review records directly.

The JSON under tests/fixtures is a manual transcription of the user's GT
screenshots. Values are rounded here only to the precision visible in those
screenshots. The library retains unrounded native values and provenance.

These examples verify saved definitions, optimizer results and DRP entries.
The fixture also retains DVH statistics, reference-dose result rows and UI
indicators for future dose-analysis tests; this module does not claim to
recalculate those quantities. Tests skip if the private archive is not supplied.
"""
import json
import os
from pathlib import Path

import pytest

from hyperio import inspect_export


GROUND_TRUTH = json.loads(
    (Path(__file__).parent / 'fixtures/vmat-2026-10-29-ground-truth.json').read_text()
)


@pytest.fixture(scope='module')
def returned_plan():
    """Inspect an export and select one unambiguous plan by its saved identity.

    Typical application code follows the same three steps: inspect the source,
    select from ``report['plans']``, then check diagnostics before using data.
    The expected plan identity belongs to this fixture, not to the reader.
    """
    archive = os.environ.get('HYPERIO_VMAT_ARCHIVE')
    if not archive:
        pytest.skip('set HYPERIO_VMAT_ARCHIVE to run the documented private-archive examples')

    report = inspect_export(archive)
    expected_name = GROUND_TRUTH['plan']['name']
    matches = [plan for plan in report['plans'] if plan['name'] == expected_name]
    assert len(matches) == 1, f'Expected one plan named {expected_name!r}'
    plan = matches[0]
    assert not plan['diagnostics'], plan['diagnostics']
    return plan


def test_read_dvh_sampling_and_record_collections(returned_plan):
    """Read DVH sampling settings independently of the dose calculation grid.

    ``dvh_parameters`` exposes spacing in mm and bin width in cGy.
    These two expected settings were observed in the supplied dvhparam.xml;
    they are not values visible in the three GT screenshots.
    Missing optional documents produce None, rather than assumed defaults.
    """
    assert returned_plan['studyset'] == GROUND_TRUTH['plan']['studyset']
    sampling = returned_plan['dvh_parameters']
    assert sampling is not None
    assert sampling['resolution_mm'] == 1
    assert sampling['bin_width_cgy'] == 1

    # Check entire collections too: extra or omitted records must not be hidden
    # by successful comparisons of the other rows.
    assert len(returned_plan['isodose_settings']['dose_goals']) == len(GROUND_TRUTH['dose_goals'])
    assert len(returned_plan['cost_functions']) == len(GROUND_TRUTH['imrt_constraints'])
    assert len(returned_plan['dose_reference_points']) == len(GROUND_TRUTH['dose_reference_points'])


@pytest.mark.parametrize(
    'expected', GROUND_TRUTH['dose_goals'],
    ids=[f"{goal['structure']} {goal['metric']}" for goal in GROUND_TRUTH['dose_goals']],
)
def test_read_dosimetric_goal_definitions(returned_plan, expected):
    """Find a criterion by structure and metric, then read its bound and tolerance.

    ``isodose_settings['dose_goals']`` contains definitions, not evaluated
    results. Each record exposes metric, comparison operator, limit, units and
    tolerance. Its source gives the XML filename and element path.
    In this fixture each (structure, metric) pair identifies one definition.
    """
    goals = returned_plan['isodose_settings']['dose_goals']
    matches = [goal for goal in goals
               if (goal['structure'], goal['metric']) == (expected['structure'], expected['metric'])]
    assert len(matches) == 1
    actual = matches[0]
    assert actual['operator'] == expected['operator']
    # This tight tolerance allows binary representation of the XML's 1.15;
    # it is not a dose acceptance tolerance or clinical criterion.
    assert actual['limit'] == pytest.approx(expected['limit'], rel=0, abs=1e-12)
    assert actual['tolerance'] == pytest.approx(expected['tolerance'], rel=0, abs=1e-12)
    assert actual['source']['file'].endswith('/isodosesettings.xml')
    assert '/DoseGoal[' in actual['source']['path']


@pytest.mark.parametrize(
    'row_index,expected', enumerate(GROUND_TRUTH['imrt_constraints']),
    ids=[f"{index + 1}: {row['structure']} {row['cost_function']}"
         for index, row in enumerate(GROUND_TRUTH['imrt_constraints'])],
)
def test_read_optimisation_objectives_at_ui_precision(returned_plan, row_index, expected):
    """Read objectives in saved order, preserving full native precision in fields.

    Dose-valued effects are exposed in cGy; Parallel effects are percentages.
    ``reference_dose_cgy`` is explicitly cGy and ``shrink_margin_cm`` is a
    convenience display value. Individual target margins remain available in
    mm under ``shrink_margin_targets``. The ``fields`` dictionary preserves
    native values, units, original tokens and one-based source lines.
    """
    actual = returned_plan['cost_functions'][row_index]
    for key in ('structure', 'cost_function', 'status', 'manual', 'multicriterial',
                'relative_impact', 'effect_unit'):
        assert actual[key] == expected[key], key

    display_precision = {
        'weight': 3, 'reference_dose_cgy': 1, 'exponent': 2, 'shrink_margin_cm': 2,
        'isoconstraint': 2 if expected['effect_unit'] == '%' else 1,
        'isoeffect': 2 if expected['effect_unit'] == '%' else 1,
    }
    for key, decimal_places in display_precision.items():
        if expected[key] is None:
            assert actual[key] is None, key
        else:
            assert actual[key] is not None, key
            assert round(actual[key], decimal_places) == expected[key], key

    # Enabled has no separately established native mapping here. Keep the
    # checkbox in the GT without claiming this reader independently reads it.
    assert actual['fields']['isoeffect']['file'].endswith('.hyp')
    assert actual['fields']['isoeffect']['line'] > 0


@pytest.mark.parametrize(
    'expected', GROUND_TRUTH['dose_reference_points'],
    ids=[row['description'] for row in GROUND_TRUTH['dose_reference_points']],
)
def test_read_saved_dose_reference_points(returned_plan, expected):
    """Read DRP coordinates and saved beam dose without sampling a dose array.

    ``xyz_cm`` exposes coordinates in cm; ``coordinates`` preserves native mm
    and line provenance. A zero saved beam dose remains numeric zero even when
    Monaco displays a dash. Location dropdown labels and Total Dose are not
    inferred by this reader and are therefore not asserted as parsed values.
    """
    matches = [point for point in returned_plan['dose_reference_points']
               if point['description'] == expected['description']]
    assert len(matches) == 1
    actual = matches[0]
    assert actual['point_description'] == expected['point_description']
    assert actual['xyz_cm'] == expected['xyz_cm']
    if expected['beam_dose_cgy'] is None:
        assert actual['saved_beam_dose_cgy'] == 0
    else:
        assert round(actual['saved_beam_dose_cgy'], 1) == expected['beam_dose_cgy']
    assert actual['coordinates']['unit'] == 'mm'
    assert actual['saved_beam_dose']['file'].endswith('/tel.1')
