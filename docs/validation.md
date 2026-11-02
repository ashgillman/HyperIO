# Initial validation record

For the additional 23 October 2026 selected-plan comparison, see [TPS PDF comparison](../reports/tps-pdf-comparison.md).
It records 208 matching values across 19 beams in three 6X plans, with explicit unit conversions and limitations.
The historical initial-validation record predates that evidence and the subsequent partial UI/native-return reviews.
Current boundaries are stated below; one native full-grid profile now has fixture-specific numerical evidence, while independent export validation remains pending.

## Native dose sampling and calculated DVHs, 30 October 2026

The optional `analysis` extra supplies NumPy, SciPy, Shapely and unlzw3.
The native reader delegates all decompression to unlzw3 after restoring a standard `.Z` wrapper.
GNU gzip independently decoded the plan payload to identical bytes during investigation.
The supplied fixture's grid-centre dose matches its DRP, and its array maximum matches screenshot rounding.
Synthetic tests cover a noncubic independently compressed array, byte order, physical axes/spacing/origin, affine-field trilinear interpolation, explicit out-of-grid behavior, WC polygon counts/tails, and separate raw versus binned statistics.

Calculated GT tests match all six extrema, all three HI values, both PTV volumes and means, all ten criterion values at displayed precision, and all ten criterion indicators.
The OAR volume is 0.015 cm³ high and its mean about 0.326 cGy high.
The independent interval-midpoint histogram revision brings both PTV D50 values and OAR D1% within 0.1 cGy; all supplied dose quantiles now have a separate tolerance-level regression gate.
The subsequent shared-policy reference-plan library below replaces the original per-metric residual allowances.
The nearest-slice contour rule, exact boundary and bin/inversion conventions, and Monaco CI formula remain provisional or unresolved.
Paddick CI can be requested as a separately labelled candidate, but is not asserted as the native Monaco CI.
At the initial calculation checkpoint, the full suite with analysis dependencies and the private VMAT archive enabled passed with 119 tests and 3 skips.
At that checkpoint, the metadata-only environment passed with 97 tests and 5 skips, including explicit skips for the two optional analysis test modules.
Analysis was exercised with NumPy 2.3.4, SciPy 1.16.3, Shapely 2.2.0 / GEOS 3.14.1, and unlzw3 0.2.3.

### Shared-policy reference-plan library

`tests/plan_library/cases.json` registers the independent GT, plan identity, local source locator and calculation options for each case.
The generic integration example discovers all registered cases, while the public `hyperio.comparison` API compares numerical outputs without changing the calculation.
No per-case threshold overrides or residual waivers are supported.
The user-specified dose policy is absolute difference ≤0.1 cGy for pass, >0.1 and <1.0 cGy for review, and ≥1.0 cGy for action_required.
The action gate fails missing dose outputs and action-level results; review findings are retained as warnings and in comparison records.
Values are compared unrounded against the supplied GT, with only a 1e-12 representation allowance at exact boundaries.
Other physical units are not evaluated until their own explicit policies are supplied.
This fixture now yields 15 dose comparisons within tolerance and one at review level, with none reaching the action level.
The remaining review difference is OAR mean +0.325789 cGy.
The independent histogram/boundary review passed with 126 tests, 3 skips and one warning retaining that review-level result.
New synthetic coverage checks half-open dose intervals, midpoint coordinates, wide-bin extrema bounds, and the separate effect of contour-edge sampling on raw volume and mean.
Without analysis extras, 117 tests passed and 5 skipped.
The local archive fallback was copied under ignored reference/plan-library and verified byte-for-byte by SHA-256; the plan-library tests also passed without an archive environment variable.

## Saved optimisation and DVH configuration readers, 29 October 2026

The public library now reads optimisation objectives, individual shrink-margin targets, DVH sampling settings, structure index references, reference-dose requests, dosimetric goal definitions and DRP records.
The existing inspection API and CLI expose these records for all discovered plans.
The screenshot GT lives under tests/fixtures, and documented integration tests compare public inspection results directly with each expected record.

The complete suite with the returned VMAT archive enabled passed with 97 tests and 3 skips.
The 26 documented private-archive examples cover 25 screenshot records plus sampling settings and complete collection counts.
Without the archive environment variable, those examples skip explicitly; the synthetic byte-reader examples run independently.
Synthetic tests exercise arbitrary structure names and values, all mapped objective/goal types and units, unequal per-target margins, retained raw values and provenance, missing values, unknown types, nonfinite optimizer results, explicit unset sentinels, duplicate/incomplete records, XML namespace/version handling, and beam-anchored DRP parsing.
The original six-plan supplied-archive integration test remains passing.
The ordinary CLI inspected all eight plans in the new return without plan diagnostics; D291026AG exposes 13 objectives, 10 goal definitions and two DRPs.
The library output matches all 25 screenshot saved-record comparisons.

These tests validate parsing and regression behavior, not independent calculated-dose or DVH results.
The four objective types and 10 goal definitions in the screenshot have UI evidence; other mapped labels and types retain their PlanCheck-derived evidence level.
At this 29 October checkpoint, native dose decoding and Monaco's exact DVH sampling and histogram rules remained unimplemented.
Format comments in the readers describe the observed nesting, schema versions, units, sentinels, positional anchors and remaining unknown fields.

Validation was performed on 20 October 2026 using local Python 3.13.12.
The declared Python 3.10+ compatibility has not been exercised on other interpreters yet.

## Exercised behavior

- `python3 -m pytest -q`: 31 passed, including supplied-archive reader and generated-batch integration tests.
- An editable package was built and installed in `work/test-venv/` using the existing Nix-provided setuptools 80.9.0 build tools.
- The installed `hyperio` entry point successfully compared the common-settings profile against all six supplied plans.
- The common-settings CLI check returned 0 with every requested value matching.
- The `uncertainty-6x.json` profile returned 1, with the three `6X` plans matching and the three `6F` plans mismatching.
- An explicit `MCVARPERPLAN=false` profile returned 1 and reported `unknown` for all six plans.
- A complete archive snapshot streamed all 5,735 files, including binary CT/dose payloads, without an archive read error.
- Comparing the saved snapshot with itself returned an empty change list.
- Synthetic snapshot tests independently exercised changed, added, removed, binary, and line-ending changes.
- All six plans and all six studysets in the final report have empty parser diagnostics.
- The 24 sampled native dose prefixes all start with `00d5301e`.
- Recorded parser/script SHA-256 values were checked against the final source files.
- `compileall` completed for the Python source and investigation scripts.

Synthetic tests exercise byte-preserving edits, unknown bytes, missing final newlines, independent uncertainty fields, missing keys, nested settings, duplicate directives, unknown headers, nonfinite values, expectation validation, directory/ZIP equivalence, density-table ambiguity, missing studyset links, incomplete beam counts, malformed logs, empty-export failures, duplicate ZIP members, and unsafe member paths.
The local integration test checks plan count, studyset association, beam headers, raw calculation values, density overrides, CT-to-ED selection, and labelled log evidence across all six supplied plans.

## Perpetual TPS validation suite

The current catalogue is `validation/catalogue.json`, with readable checks in `validation/TESTS.org`.
One native patient contains seven grouped plan candidates, an intact CT1 image control and two structure/density studysets.
All three studysets retain the complete 100-slice CT geometry; no current candidate uses the retired three-slice studyset.
Transferred source contours, plan associations, patient-specific .hyp filenames, density settings and grouped calculation/geometry edits are explicit component tests.
Historical CT import success remains distinct from fresh native-patient restoration and native plan acceptance.

Local tests verify coexisting plan names, patient/studyset references, exact image preservation, requested profile values, source/target contour provenance, no-dose omissions, reader diagnostics and generated file hashes.
The generated archive passes ZIP CRC checks.
Result-recording tests verify append-only history, observation phase/profile/revision scope, idempotence and rejection of unknown tests or unassigned profiles.
Run identities include catalogue, native output and generator hashes so observations can be tied to the software that generated them.
Generated worksheets start unreviewed without resetting historical results.

The old generated packages have been deleted at the user's request.
Historical reviews, metadata, logs and returned captures are preserved under `validation/results/history/`.
The canonical imported native CT is `reference/native-zero-ct/1~zzzInputOutputAG2.zip`.
Legacy format/packaging fixtures in the Python tests are not active TPS import candidates.

## Validation boundary

The generated zero CT has now been imported in Monaco and its returned native studyset compared with the generated DICOM data, as detailed below.
The partial review and 27 October native return establish fixture-specific UI effects, retained numeric aperture inputs and completed calculations for four generated Phantom plans.
The returned studyset files preserve the generated images/contours byte-for-byte, and the Patient centroid independently matches the reported UI value.
Explicit per-plan close/reopen steps were not independently demonstrated by the returned archive.
The later 30 October full-grid dose reader has fixture-specific array/DRP/screenshot evidence as described above.
Effective density voxel grids, checksum algorithms and complete saved-dose freshness remain unvalidated.
Initial UI observations distinguish the displayed uncertainty field and mode polarity; returned files show segment uncertainty normalization and omission of A's explicit false mode key.
These findings remain scoped to this fixture/build and do not establish all mappings or a universal absent-key default.
The package was exercised with available local build tools; an isolated dependency download/install workflow and a Python-version matrix remain untested.

The investigation created files only in HyperIO and temporary build locations, and left the PlanCheck source checkout and supplied reference archive/help unchanged.
The original investigation did not initialize Git or make commits; later implementation and evidence checkpoints are recorded in the repository history.

## Zero CT native return, 2026-10-24

The generated depot ct-003 was successfully imported under the user-selected native ID zzzInputOutputAG2.
The returned CT1 studyset has 100 native CT/WC pairs and 100 cached DICOM images, preserving 100x100x100 dimensions, 5 mm spacing and the 500 mm outer-voxel extent.
All cached DICOM dataset values agree with the source, including zero pixels, 0 HU scaling and entity identifiers.
Native CT headers and index agree with cached image geometry; native compressed pixels were not interpreted.
Cached DICOM retains source PatientID zzzInputOutputAG while native patient references use the selected AG2 suffix.
No plan or contoured body is present; explicit close/reopen, UI cursor readings, planning and calculation remain unverified.
See reports/zero-ct-import-roundtrip.md and its paired JSON report.

## Partial UI review and native calculation return

The [partial UI analysis](../reports/tps-partial-review-analysis.md) preserves 11 reviewer passes, four observations and 38 unreviewed worksheet rows without treating duplicate grouped rows as independent experiments.
The [27 October native-return analysis](../reports/native-suite-return-2026-10-27.md) records new plan/beam dose files and completion logs for Calculation-A/B and both aperture plans.
Reference and both Density plans were intentionally not calculated.
Numeric aperture edits persist while compact-shape records change; A/B segment uncertainty values become equal to their main uncertainty values.
Insert overrides survive as settings, but zero logged free volume leaves their effective material impact unresolved.
The original source ZIPs and editable worksheet remain unchanged, with exact hashes and scoped observations retained in the result register.

## Repository checkpoint verification, 28 October 2026

The complete local suite passed with 43 tests, including the available private-fixture integration checks.
A clean copy of the staged implementation without the ignored local assets passed with 33 tests and eight skips for unavailable optional dependencies or private fixtures.
The CLI help entry point and Python compilation checks also passed.
Candidate JSON/JSONL reports parse successfully, and the staged inventory excludes raw archives, images, generated patients, private capture history and Finder metadata.
These software checks do not broaden the TPS evidence boundary described above.
