# HyperIO

HyperIO is an initial Python library for reading Monaco TPS files, inspecting saved calculation settings, and comparing controlled plan saves.
The first application is checking whether commissioning plans contain the settings requested by an explicit test specification.

The supplied phantom archive is now readable without extracting its CT and dose payloads.
The current report covers six plans, their six linked studysets, eighteen beam headers, and plan-specific density settings.
See [the observed results](reports/supplied-plans.md), [the field map](docs/format-notes.md), and [the proposed Monaco experiments](docs/experiments.md).

## Current scope

- Read a Monaco patient directory or ZIP archive without changing it.
- Read named `.hyp` calculation settings with file, line, literal value, and interpretation attached.
- Read plan identity, primary studyset, the observed five-value plan density records, studyset density defaults, and selected CT-to-ED name.
- Read the observed beam-header layout, keeping native coordinate values and machine identifiers.
- Read saved optimisation cost functions with source tokens, native units, saved isoeffects and individual shrink-margin targets.
- Read DVH sampling settings, structure HI/CI reference settings, reference-dose requests and dosimetric goal definitions.
- Read beam DRP descriptions, coordinates and saved beam-dose entries from supported beam headers.
- Read labelled calculation-log uncertainty values and completion messages as separate observations.
- Compare selected saved settings against an explicit JSON expectation profile.
- Preserve `.hyp` bytes and produce an edited in-memory copy of an existing supported scalar setting.
- Hash and compare complete exports to support controlled save experiments, including binary files.

The interpreted layouts are limited to the supplied header identifiers: `.hyp` `000610b6`, `plan` `00d5101a`, `tel.1` `00d5101d`, `contournames` `00131027`, and `info` `00271016`.
These identifiers are literal file headers; their relationship to Monaco release numbers is not established.
The library reports diagnostics for missing, ambiguous, unsupported, and malformed settings instead of supplying presumed Monaco defaults.
The current perpetual-suite UI review identifies Monaco 6.2.3.0; mappings remain scoped to the supplied fixtures and recorded observations.

Saved settings describe the files being read.
They do not establish which settings generated a saved dose distribution or whether that dose is current.
An optional experimental path now decodes one observed native full-grid dose profile and calculates sampled DVHs; its remaining numerical differences are recorded in [the VMAT comparison](reports/vmat-2026-10-29.md).
Other native dose profiles, effective voxel density maps, complete control-point/MU semantics, checksum algorithms and multi-prescription associations remain uninterpreted.
The zero-CT generator and round-trip checks read cached DICOM pixels; native compressed CT pixels remain uninterpreted.
The current implementation is a research and commissioning development tool with fixture-specific UI and native calculation evidence; independent exported-dose validation remains pending.
A fixture-specific generator produces combined native plan candidates for that review; it does not establish general native write-back support.

## Run locally

Python 3.10 or newer is required.
Metadata readers use the Python standard library; tests use pytest.
Optional dose/DVH analysis uses NumPy, SciPy, Shapely and unlzw3 through the `analysis` extra.
No Julia environment is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/hyperio inspect 'reference/1~ZZZELEKTAONEHETERO.zip' > work/inspection.json
.venv/bin/hyperio check 'reference/1~ZZZELEKTAONEHETERO.zip' examples/common-settings.json
```

From the source checkout, commands also work with `PYTHONPATH=src python3 -m hyperio`.
The existing local Python environment was used to exercise that entry point and the test suite.
An editable installation and its installed `hyperio` command were also exercised in a local virtual environment using the existing setuptools build tools.
Python versions other than the available 3.13.12 environment have not yet been exercised.

`check` returns 0 when every requested setting matches for every discovered plan and there are no plan diagnostics.
It returns 1 for a mismatch, unavailable value, empty plan collection, or plan diagnostic, and 2 for invalid input.
`match` means equality to the requested saved-value expectation, not a clinical suitability decision.
The example profiles reproduce observations of the supplied fixture; they are not independently approved commissioning criteria.
`common-settings.json` matches all six supplied plans.
`uncertainty-6x.json` deliberately matches only the three `6X` plans if applied to the full archive.
Add `"MCVARPERPLAN": false` only when that is your actual expected value; its absence in these files produces `unknown`.
No default uncertainty tolerance or clinically recommended settings are built in.
Numeric comparisons allow only an absolute `1e-12` representation tolerance.

## Python API

```python
from hyperio import HypDocument, compare_settings, inspect_export

report = inspect_export("reference/1~ZZZELEKTAONEHETERO.zip")
for plan in report["plans"]:
    results = compare_settings(plan["settings"], {
        "DOSEGRIDSIZE": 1,
        "DOSETOMEDIUM": True,
        "FORCEWATER": False,
    })
    print(plan["name"], results)

# Review metadata is available through the same API and `hyperio inspect`.
for plan in report["plans"]:
    print(plan["dvh_parameters"])  # resolution_mm and bin_width_cgy, or None
    for objective in plan["cost_functions"] or []:
        print(objective["structure"], objective["cost_function"],
              objective["isoconstraint"], objective["isoeffect"], objective["effect_unit"])
        print(objective["shrink_margin_targets"])  # each target and its margin_mm
    if plan["isodose_settings"]:
        print(plan["isodose_settings"]["dose_goals"])
    print(plan["dose_reference_points"])

# Byte-preserving edits return a new document and do not touch the source file.
doc = HypDocument.read("work/metadata/1~ZZZELEKTAONEHETERO/plan/RefHeteroSq6X/zzzelektaonehetero.hyp")
grid = doc.get("DOSEGRIDSIZE")
print(grid.value, grid.unit, grid.file, grid.line, grid.raw)
edited = doc.with_value("DOSEGRIDSIZE", 2)
assert doc.to_bytes() != edited.to_bytes()
```

The last example uses a small metadata file extracted during the initial investigation.
For another export, pass the corresponding local `.hyp` file instead.
`with_value` changes one unique, existing supported scalar directive and preserves other bytes, whitespace, unknown records, and line endings.
It rejects missing settings, duplicate directives, known nested block settings, unsupported headers, and nonfinite values.
Selected generated edits now have Monaco UI and returned calculation evidence, with normalization and remaining limits recorded in [the native-return report](reports/native-suite-return-2026-10-27.md).
That evidence does not validate arbitrary edits or every combination of supported scalar settings.
Changing a text setting alone does not recalculate dose or update related files and checksums.
Supported native plan write-back is a later milestone in [TODO.org](TODO.org).
For TPS validation, [validation/](validation/README.md) contains the perpetual component catalogue, combined native import package and append-only result ledger.

### Saved optimisation and DVH review metadata

`cost_functions`, `dvh_parameters`, `isodose_settings`, and `dose_reference_points` are also public byte-reader functions accepting an optional source filename.
`HypDocument.cost_functions()` reads objectives from the document's unchanged bytes.
These functions use named records and supported format profiles without requiring particular patient, plan or structure names.
Inspection adds their results to every discovered plan, and the existing CLI includes them automatically.
Absent optional XML files produce `None`; malformed or unsupported records produce plan diagnostics while other readable components remain available.

Objective display quantities are cGy or percent according to type, with the unit stated explicitly.
The `fields` dictionary retains native values, units, raw tokens, filename and one-based line numbers.
Every shrink-margin target remains separate in mm; `shrink_margin_cm` is a convenience value only when all targets have the same margin.
Unknown objective/goal types retain their raw fields and diagnostics; missing values and explicit unknown sentinels do not acquire defaults.
XML records retain filename and element paths.
Goal definitions cover the 14 mapped types, including absolute-volume conversion from native mm³ to cm³ and separate HI/CI `Index` values.

The [VMAT screenshot comparison](reports/vmat-2026-10-29.md) validates library output against the supplied GT.
The documented examples in [test_vmat_evidence.py](tests/test_vmat_evidence.py) compare inspected plans directly with the [GT fixture](tests/fixtures/vmat-2026-10-29-ground-truth.json).
The independent examples in [test_plan_review.py](tests/test_plan_review.py) demonstrate byte-reader usage without private files.
Saved optimizer isoeffects and DRP values are not independently recalculated dose or DVH statistics.
Exact Monaco contour-boundary and histogram conventions remain open work.

### Calculate an experimental DVH from saved native dose

Install the optional analysis dependencies with `python3 -m pip install -e '.[analysis]'`.
The library delegates compression decoding to unlzw3, interpolation to SciPy and polygon geometry to Shapely.
It does not implement its own compression algorithm.

```python
from hyperio import calculate_plan_dvh

result = calculate_plan_dvh(archive_path, plan_name="D291026AG")
print(result["sampling"])  # the actual lattice, contour and histogram policies
for structure in result["structures"]:
    print(structure["structure"], structure["volume_cm3"],
          structure["min_dose_cgy"], structure["max_dose_cgy"],
          structure["mean_dose_cgy"], structure["heterogeneity_index"])
    print(structure["criterion_results"])
```

`native_dose(bytes, source_name)` returns a `DoseGrid` with cGy values ordered `(y,z,x)` and native xyz geometry in mm.
`DoseGrid.sample(points_xyz_mm)` interpolates dose and rejects extrapolation by default.
`contour_slice(bytes, source_name)` reads polygon geometry and retains unparsed trailing records.
`DVH(samples_cgy, resolution_mm=1, bin_width_cgy=1)` exposes raw statistics and a separately binned cumulative curve with `dose_at_volume` and `volume_at_dose` queries.
Samples occupy half-open dose intervals, with cumulative counts placed at interval midpoints and linear interpolation for queries.
This convention reproduces the supplied Dx references within 0.1 cGy; its precise bin coordinates are inferred from this fixture rather than specified in the vendor help.
Dx results are bounded by the raw sampled dose range.
These APIs are documented by [synthetic examples](tests/test_dose_analysis.py) and [the reference-plan test library](tests/plan_library/README.md).

The native reader currently supports the observed `00d5301e` profile with four zero placeholder blocks and one complete uint32 dose grid.
Other block profiles and non-unit secondary scaling fields raise diagnostics rather than acquiring guessed interpretations.
The plan calculation requires axial WC slices and a sampling spacing commensurate with the isocentre-aligned native grid origin.
It unions same-structure polygons and holds each contour over a nearest-slice slab; those reconstruction choices remain provisional.
`boundary="include"` or `"exclude"` makes the boundary rule explicit.
The [generic plan-library test](tests/test_plan_library.py) discovers plans from [cases.json](tests/plan_library/cases.json) and compares their results under shared policies.
For dose quantities, the user-specified tolerance is 0.1 cGy and the action level is 1.0 cGy: differences up to 0.1 pass, differences between the levels require review, and differences reaching 1.0 fail the action gate.
Comparisons use unrounded values and retain review statuses and signed differences; an action gate passing does not mean every metric met tolerance.
No volume, percentage or dimensionless policies are inferred from dose thresholds.
The reusable API is `compare_dvh_results(calculated, ground_truth, policies)` with `ComparisonPolicy` values indexed by unit.
Optional `include_conformity=True` reports a Paddick CI candidate, explicitly separate from a verified Monaco conformity-index mapping.

## Review generated plan candidates in Monaco

The [perpetual TPS test list](validation/TESTS.org) has stable component IDs with expected observations.
The generated suite places seven independent plans and three studysets in one native patient, `zzzInputOutputAGsuite`.
Restore that patient once and collect several checks while each plan is open.
Use [validation/README.md](validation/README.md) for the plan matrix, regeneration command and result-recording workflow.
The current package is [HyperIO-TPS-tests.zip](validation/generated/HyperIO-TPS-tests.zip).
Old separate import packages have been removed; returned files and observations are retained separately as evidence.
The [partial UI review](reports/tps-partial-review-analysis.md) and [native calculation return](reports/native-suite-return-2026-10-27.md) record the current evidence.
Calculation-A/B and both aperture plans have their own completion logs and new native dose payloads; Reference and both Density plans were intentionally not calculated.
The next priorities are independent DICOM RT Plan/RT Dose exports and investigation of the Insert's logged zero free volume.

## Generate the zero CT DICOM import candidate

The example CT's DICOM metadata supplies the axial orientation and volume centre.
All pixel values are replaced with zero, using slope 1 / intercept 0 so every voxel is 0 HU.
The generated volume has 100 slices of 100x100 pixels at 5 mm spacing, giving 500 mm extent between outer voxel edges.
New Study, Series, Frame of Reference and per-slice SOP Instance UIDs are generated.
Patient identity is `zzzInputOutputAG` / `zzPHYS^Ash`.
This path requires the optional `dicom` dependencies from pyproject.toml.

```sh
PYTHONPATH=src python3 -m hyperio blank-ct \
  'reference/1~ZZZELEKTAONEHETERO.zip' work/zero-ct-demo
```

Import the resulting `DICOM/` folder through Monaco's DICOM importer, then retain the native studyset Monaco creates.
This CT-only candidate contains no structures or plan.
The successful CT import and returned native checks are documented in [the round-trip report](reports/zero-ct-import-roundtrip.md).
The original native return is retained under `reference/native-zero-ct/` as an immutable fixture.
The `index-ct SOURCE DESTINATION WORKING_DEPOT_ZIP` command reproduces a complete working depot's index relationships and raw DICOM encoding; a lone RTDIR.dir is insufficient.


## Capture and compare saves

```sh
PYTHONPATH=src python3 -m hyperio snapshot work/captures/C00-before > work/C00-before.json
PYTHONPATH=src python3 -m hyperio snapshot work/captures/C00-after > work/C00-after.json
PYTHONPATH=src python3 -m hyperio diff work/C00-before.json work/C00-after.json > work/C00-diff.json
```

Snapshots stream SHA-256 hashes over every file, including CT and dose payloads.
They include small readable UTF-8 text for unified diffs; they preserve hash differences for binary and other encodings.
Timestamps are excluded from comparison; no file content changes are silently discarded.
Use the same relative directory layout for before/after exports so renamed parent directories do not obscure file correspondence.
Snapshot JSON can contain identifying plan and patient text and belongs with the source research data.

## Evidence and development

[The controlled experiment protocol](docs/experiments.md) defines the next captures and acceptance criteria.
[Format notes](docs/format-notes.md) distinguish literal observations, PlanCheck-derived mappings, help-described behavior, and untested hypotheses.
[Source notes](docs/sources.md) identify help topics and PlanCheck files precisely.
[The validation record](docs/validation.md) lists exercised behavior and the remaining verification boundary.
[Provenance](reports/provenance.json) records the supplied archive, CHM, inspected members, source files, and parser hashes.
[TODO.org](TODO.org) contains remaining work; completed tasks are removed from it.

The input archive, CHM, extracted help, and working captures are excluded from version control by `.gitignore`.
The synthetic tests run without those assets; the local archive integration test is skipped when the archive is absent.
Raw archives, vendor help, generated patient packages and private captures remain local and are excluded from commits.
No project licence has been selected; no third-party licence is assumed for colleague code or vendor assets.
