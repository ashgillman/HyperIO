# Reference-plan test library

[cases.json](cases.json) registers the plans and shared numerical comparison policies.
Adding a plan is a data change; [test_plan_library.py](../test_plan_library.py) discovers and calculates every registered case.
The public comparison API is in `hyperio.comparison` and is independent of this registry and of the dose-calculation code.

## Current dose policy

The user requested 0.1 cGy tolerance and a 1.0 cGy action level.
These are software-reproduction thresholds, separate from the clinical dose goals saved in a plan.
Comparisons use the unrounded calculated value and the independently supplied GT number.
They do not round the calculation to make it pass or add an allowance for screenshot rounding.
A 1e-12 numerical-representation allowance is used only when deciding exact threshold boundaries.

| Absolute difference | Status | Test behavior |
|---|---|---|
| ≤ 0.1 cGy | `pass` | Within tolerance |
| > 0.1 and < 1.0 cGy | `review` | Reported as a warning, retaining the signed difference |
| ≥ 1.0 cGy | `action_required` | Fails the action-gate test |
| Missing/nonfinite calculated dose | `not_evaluated` | Fails the action gate; never silently passes |

Volume, relative-volume and dimensionless comparisons retain their differences but remain `not_evaluated` until an explicit policy for their unit is supplied.
The cGy thresholds are never applied to cm³, percentages or HI/CI.
A Paddick candidate is not substituted for an unresolved Monaco CI.
Policies are shared by the registry; cases have no individual numeric waivers.

## Run the library

Install the optional analysis packages, then provide the private native archive:

```sh
python3 -m pip install -e '.[test,analysis]'
export HYPERIO_VMAT_ARCHIVE='/absolute/path/to/returned-plan.zip'
python3 -m pytest tests/test_plan_library.py -v
```

A case can also resolve its ignored fallback path under `reference/plan-library/`.
The first case's archive has been copied there byte-for-byte and verified against the source SHA-256, so it can run locally without setting an environment variable.
An unavailable private archive skips that case; an explicitly configured but nonexistent source is an error.
The current registry uses `HYPERIO_VMAT_ARCHIVE` for backward compatibility with the saved-metadata examples.
Raw archives and screenshots remain local and are not added to Git.
Registering another case does not broaden native file-format support; an unsupported dose or contour profile fails explicitly rather than being treated as a successful comparison.

The test warning summary reports review-level findings and the number of non-dose quantities not evaluated.
The JUnit `plan_comparisons` property retains every comparison when a compatible JUnit report is requested with `--junitxml=... -o junit_family=xunit1`.
An action-gate test passing does not mean every quantity passed the tighter tolerance; inspect the retained statuses.

## Add another plan

1. Keep its native archive under an ignored local directory or provide a dedicated environment variable.
2. Add an independently established GT JSON file under `tests/fixtures/`, preserving source provenance and units.
3. Add one entry to `cases.json` with a unique case ID, saved plan name, source locator, GT path and calculation options.
4. Run the same generic test; no plan-specific Python test or numeric exception is needed.

Example registry entry:

```json
{
  "id": "another-independent-plan",
  "plan_name": "SavedPlanName",
  "source": {
    "environment": "HYPERIO_OTHER_ARCHIVE",
    "path": "../../reference/plan-library/other-plan.zip"
  },
  "ground_truth": "../fixtures/other-plan-ground-truth.json",
  "calculation_options": {"boundary": "include"}
}
```

The GT schema can contain `dvh_statistics`, `dose_goals`, `dose_reference_points` and `dvh_reference_rows`, as illustrated by the first fixture.
Criterion quantities should state their output `unit` explicitly: `cGy`, `%`, `cm3`, or `dimensionless`.
This is especially important for Vdose goals, whose label alone cannot distinguish an absolute volume from a percentage.
An explicit GT unit conflicting with the calculated goal's unit is an error; no conversion or reinterpretation is guessed.
For a free reference-dose request, annotate the reference row with `origin: "request"` and a `query` specifying the input quantity and value.
This distinguishes an independently calculated output from an echoed input and avoids double-counting criterion-linked reference rows.
For example, a relative-volume query uses `{"quantity": "relative_volume", "value": 1.0}` and checks the calculated D1% dose.
Rows without a free-request annotation can remain as transcribed table evidence; criterion values are compared through `dose_goals`.

## Use comparisons directly

```python
from hyperio import ComparisonPolicy, calculate_plan_dvh, compare_dvh_results

policies = {"cGy": ComparisonPolicy("cGy", tolerance=0.1, action_level=1.0)}
calculated = calculate_plan_dvh(archive_path, plan_name)
comparisons = compare_dvh_results(calculated, ground_truth, policies)

for comparison in comparisons:
    print(comparison["id"], comparison["difference"],
          comparison["unit"], comparison["status"])
```

The calculation never receives GT data or comparison thresholds.
The [comparison examples](../test_comparison.py) demonstrate boundaries, both difference signs, missing results, unit isolation and identity-based record matching without private plans or analysis dependencies.
