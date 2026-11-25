# HyperIO code architecture

HyperIO reads saved Monaco patient folders and ZIPs, reconstructs selected dose and density quantities, and writes plan copies for review and commissioning.
The Python API, CLI, and desktop applications share the native file readers and workflow functions.

## Entry points

| Entry point | Where to start |
| --- | --- |
| Python API | [`hyperio/__init__.py`](../src/hyperio/__init__.py) re-exports the main readers, comparison functions, and analysis types. |
| `hyperio` and `python -m hyperio` | [`cli.py`](../src/hyperio/cli.py) parses arguments, dispatches inspection, settings checks, snapshots, and validation commands, and writes JSON results. |
| RED and DVH desktop apps | [`REDWindow`](../src/hyperio/desktop/red.py) and [`DVHWindow`](../src/hyperio/desktop/dvh.py) use [`PlanSourceWindow`](../src/hyperio/desktop/common.py) for source selection, background work, and diagnostic export. |
| Commissioning desktop app | [`CommissioningApp`](../src/hyperio/commissioning_gui.py) manages worksheet cases and native template selection. |

The scripts in [`applications/`](../applications/) launch the same desktop modules from a checkout.
See the [desktop guide](desktop-applications.md) for controls and workflows.

## Reading and inspecting an export

- [`core.py`](../src/hyperio/core.py) owns shared file access and metadata inspection.
  - `Export` opens members in a patient directory or ZIP.
  - `HypDocument` reads calculation settings from `.hyp` files and supports byte-preserving edits to recognised directives.
  - `inspect_export()` associates plans with studysets and assembles parsed records, source locations, and diagnostics.
    `compare_settings()` checks saved values against an explicit caller-supplied profile.
- [`review.py`](../src/hyperio/review.py) parses saved optimisation objectives, DVH settings, and isodose goals.
  [`logs.py`](../src/hyperio/logs.py) extracts observations from calculation logs.
- [`plan_discovery.py`](../src/hyperio/plan_discovery.py) builds plan selectors using relative member paths, which distinguish identically named plans in different patient sets.
  The DVH window uses its lazy mode to read identity headers before loading dose or full metadata.
- [`snapshots.py`](../src/hyperio/snapshots.py) hashes export members and compares two snapshots by relative path.
  [`diagnostics.py`](../src/hyperio/diagnostics.py) classifies issues for DVH processing and builds full or anonymised support reports.

## DVH reconstruction and export

[`dose.py`](../src/hyperio/dose.py) decodes supported saved full-grid dose layouts into `DoseGrid`, which interpolates cGy values in native coordinates.
[`contours.py`](../src/hyperio/contours.py) reads polygon records and structure indices from WC slices.
[`dvh.py`](../src/hyperio/dvh.py) combines those inputs in `calculate_plan_dvh()` and uses `DVH` to turn dose samples into cumulative curves and statistics.
A shared input or geometry failure stops the plan, while a structure-level sampling failure can leave other structures available.

[`dvh_export.py`](../src/hyperio/dvh_export.py) formats the result as a table and writes XLSX or CSV output with provenance.
[`DVHPlot`](../src/hyperio/dvh_plot.py) displays curves and cursor readouts.
[`dvh_goals.py`](../src/hyperio/dvh_goals.py) maps catalogue goals onto plot coordinates, and [`eviq.py`](../src/hyperio/eviq.py) refreshes the eviQ catalogue.
[`ComparisonPolicy`](../src/hyperio/comparison.py) supplies explicit unit-specific thresholds for numerical comparisons.

## RED editing and export

[`REDOutputs`](../src/hyperio/red_outputs.py) manages the editor's per-output tab state, previews, and RED mappings.
[`ct_red.py`](../src/hyperio/ct_red.py) optionally estimates mean CT-derived RED by sampling cached CT pixels inside saved contours using the studyset's selected calibration.

[`application_io.py`](../src/hyperio/application_io.py) owns the plan edits and writes.
Its `prepare_red_output()` applies a mapping to plan-level RED fields and sets the output plan name.
`export_red_patient()` stages a complete patient copy as a directory or ZIP and can replace plans within that copy.
`export_red_plan_copies()` adds named plan directories beside their originals and reuses the existing studysets.
The exporters can clear a supported saved approval flag and omit saved dose and calculation logs when callers request it.

## Commissioning and validation

| Module | Responsibility |
| --- | --- |
| [`commissioning.py`](../src/hyperio/commissioning.py) | Defines worksheet fields and validates, loads, and saves MPPG 5.b test cases. |
| [`commissioning_native.py`](../src/hyperio/commissioning_native.py) | `build_native_patient()` builds experimental plan copies from matching native templates, carrying forward template beam and prescription records and applying supported calculation settings. |
| [`validation_suite.py`](../src/hyperio/validation_suite.py) | `build_suite()` stages native test candidates from compatible plan, contour, and studyset inputs. `record_review()` appends completed observations to the review ledger. |
| [`blank_ct.py`](../src/hyperio/blank_ct.py), [`depot_index.py`](../src/hyperio/depot_index.py), [`depot_layout.py`](../src/hyperio/depot_layout.py) | `build_blank_ct()` prepares a fixed-geometry zero-HU DICOM candidate from a compatible axial template. `inspect_working_depot()` reads a supported depot ZIP; `package_indexed_ct()` delegates to `package_working_layout()` to package the candidate using that layout. |

Native readers and writers are scoped to observed layouts.
Saved settings, reconstructed quantities, and Monaco verification represent distinct evidence.
See the [native format notes](format-notes.md) for field mappings and the [validation workflow](../validation/README.md) for review procedures.
