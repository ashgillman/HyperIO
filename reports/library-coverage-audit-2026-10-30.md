# Library coverage audit, 30 October 2026

Several useful capabilities demonstrated in previous investigations are not yet reusable through the ordinary inspection API.
The clearest gaps are static aperture reading, CT round-trip geometry inspection, and extraction of the structure-volume messages used in the native-return analysis.
Contour reading exists inside the library package but is private to a fixture-specific suite generator.
These should become reusable readers with explicit format scope and provenance.

This is an implementation-location audit, not a new validation of native semantics or a claim that every past request can be recovered from Git history.
The available history contains only `ca847c4` and `951a396`.
Both current source and retained investigation outputs were checked because later work is uncommitted.
The active saved-objective/goal/DRP/DVH-settings correction was inspected but left unchanged.
No runtime implementation was changed by this audit.

## What counts as inclusion in the library

A callable function in an installed `hyperio` submodule is already library code, even if `hyperio.__init__` does not re-export it.
A private parser embedded in a fixture generator is useful implementation work, but is not a supported reader for callers.
A value stored in a report proves that an investigation extracted or compared it; it does not by itself provide a repeatable implementation.
Tests should exercise public readers and comparison functions rather than carry the only implementation of those operations.

## Gaps and recommendations

| Priority | Capability previously demonstrated | Current implementation and evidence | Recommendation |
|---|---|---|---|
| High | Static aperture headers and individual MLC leaf positions | [Native-return JSON](native-suite-return-2026-10-27.json) contains `apertures_before` / `apertures_after`, source line numbers and 80 leaf pairs per supported static beam. [The return analysis](native-suite-return-2026-10-27.md) describes locating the shifted table. [`beam_headers`](../src/hyperio/core.py) exposes identity, angles and isocentre, but no aperture records. [`edit_static_aperture`](../src/hyperio/experiments.py) reads the fixture's original table internally to construct two probes. There is no reusable reader for the returned tables. | Implement a format-scoped aperture reader and include its records in inspection. Retain both headers, individual leaf values, raw records and source locations; reject ambiguous or truncated tables. Test the shifted returned layout and independent synthetic records. Keep physical bank/axis meaning, complete control-point coverage and compact-shape precedence explicitly limited until independently established. |
| High | Native studyset image geometry and comparison with cached DICOM | [The CT round-trip report](zero-ct-import-roundtrip.md) and [JSON](zero-ct-import-roundtrip.json) record matrix, spacing, positions, index ordering, UID agreement and cached-DICOM pixel/HU checks. [`study_metadata`](../src/hyperio/core.py) currently exposes only study identity/path, CT-to-ED name, structure defaults and diagnostics. No reusable native CT-header/index reader or round-trip comparison function was found. | Implement studyset image-index/header readers plus an optional cached-DICOM comparison path. Distinguish native header evidence, cached DICOM geometry/pixels and uninterpreted native pixel payloads. Preserve native and cached identities separately: the successful return contains a deliberate patient-ID difference. |
| High, coordinated with dose work | Native contour polygons | [`_wc_polygons`](../src/hyperio/validation_suite.py) reads leading `00091013` polygon records, and `_contours` uses it in a fixed 311-slice-to-100-slice transfer. [`test_validation_suite.py`](../tests/test_validation_suite.py) imports the private parser directly. This is package code, but there is no independent supported contour reader or inspection output. | Extract a reader independent of suite constants and transfer policy. Preserve structure IDs, slice geometry, polygon boundaries, source lines and unparsed marker/trailing records. Add explicit unsupported/truncated/nonfinite handling. Keep contour reading separate from interpolation, rasterisation and clinical volume semantics; coordinate ownership with the ongoing DVH work. |
| High | Structure total/free volumes and segment-calculation messages in logs | [The native-return analysis](native-suite-return-2026-10-27.md) uses the logged Insert total/free volume and three-segment calculations. [`calculation_log`](../src/hyperio/logs.py) currently returns only `mc_stddev`, whole-calculation uncertainty, per-segment uncertainty, completion events and event count. The structure-volume observations are not structured library output. | Extend the literal log reader with labelled structure-volume and segment-calculation events, retaining native labels, units, timestamps, file/line and all occurrences. Do not infer effective material, calculation inclusion or freshness from these messages alone. |
| Medium | Native dose-file inventory associated with each plan | [The native-return JSON](native-suite-return-2026-10-27.json) lists `dose_members` per plan. [`research_baseline.py`](../scripts/research_baseline.py) separately samples native dose headers and hashes; `inspect_export` exposes calculation logs but no dose-payload inventory. Generic snapshots can already provide file sizes/hashes. | Add plan-scoped dose-member observations and provenance, reusing existing export/snapshot mechanisms. Treat filename association and payload presence as separate evidence from dose meaning, absolute scaling and freshness. Native dose interpretation remains separate work unless the ongoing dose work supersedes this gap. |
| Medium | Case-only filename changes in returned exports | [The native-return report](native-suite-return-2026-10-27.md) separately records four case-only `.hyp` renames. [`diff_snapshots`](../src/hyperio/snapshots.py) matches exact paths, so it represents those as removal/addition rather than an associated rename. | Add an explicit optional correspondence mode/helper for unique case-insensitive path matching, preserve both original paths and any content change, and reject collisions. Preserve exact-path comparison as the default. This is distinct from patient-ID `.hyp` lookup, which already has a TODO. |
| Low | Beam visibility settings | [The native-return JSON](native-suite-return-2026-10-27.json) contains `BeamNumber`, `BeamVisibility` and `DoseVisibility` observations. No `planning_layout.xml` reader is present in the package. | Add a small optional display-metadata reader if callers need it. Keep the values named as visibility settings; the fixture does not support turning them into treatment-enabled or calculation-exclusion flags. This is lower priority than geometry and calculation evidence. |

The first four items contain useful reading/checking work that should be promoted into reusable APIs.
The dose inventory and filename comparison items consolidate report logic around existing infrastructure.
Visibility is an optional completeness improvement.
Report-only operations should be reimplemented with independent tests rather than copied from an unavailable investigation session.

## Features already in the library

| Capability | Reusable entry point | Assessment |
|---|---|---|
| Saved scalar calculation settings, byte-preserving scalar edits | `HypDocument`, `HypDocument.with_value` | Already library functionality. |
| Explicit saved-setting expectation checks | `compare_settings`; CLI `check` calls it | The calculation/comparison is not trapped in the CLI. |
| Plan identity, linked studysets, plan/study density settings, selected CT-to-ED name, initial beam headers | `inspect_export`; readers in `hyperio.core` | Already library output, within its documented layout limits. |
| Labelled uncertainty and completion-log observations | `hyperio.logs.calculation_log`, also included in `inspect_export` | Already library functionality; the missing log categories above are an extension. |
| Complete content hashes and exact-path snapshot differences | `snapshot`, `diff_snapshots` | Already library functionality; case-aware correspondence is the additional gap. |
| Zero-CT generation | `hyperio.blank_ct.build_blank_ct`, CLI `blank-ct` | Already callable library functionality. Fixed geometry/identity is a generalisation limit, recorded in the existing commissioning backlog. |
| Working depot inspection and CT packaging | `hyperio.depot_layout.inspect_working_depot`, `package_working_layout`; `hyperio.depot_index.package_indexed_ct`, CLI `index-ct` | Already library functions with fixture/layout constraints. The lack of top-level re-exports is a discoverability issue. |
| Experimental density/aperture edits and validation-candidate generation | `hyperio.experiments` | Already library code, explicitly experimental and fixture-specific. It should not be promoted into a general writer merely because it is callable. |
| Combined validation-suite generation and append-only review recording | `hyperio.validation_suite.build_suite`, `record_review`; matching CLI commands | Already callable library functionality. Human review remains external evidence. |
| Saved optimisation objectives/isoeffects, dosimetric goal definitions, HI/CI settings, reference-dose requests, DRP saved entries, DVH sampling settings | `cost_functions`, `dose_reference_points`, `dvh_parameters`, `isodose_settings`, also included in `inspect_export` | Present in the active uncommitted correction, including direct API tests. This audit does not count them as completed historical omissions or duplicate their implementation. |

Top-level exports and Python examples for the supported generator/depot/suite functions would improve discoverability.
They do not require another implementation of those features.
Retired named/three-slice candidate helpers should remain explicitly legacy/experimental rather than becoming newly advertised supported APIs.

## Script-by-script follow-up

The user clarified that useful implementations may have appeared under `scripts/` rather than only in checks.
A second inventory included ignored/local files throughout this checkout, common script/notebook extensions and shebang-bearing files, excluding dependency environments and Git internals.
The current files contain two project scripts under `scripts/` and one investigation script under `work/`.
No additional standalone DVH script was found in this checkout at the time of this follow-up.
The vendor help's `common.js` is a help asset, not a HyperIO feature implementation.
This inventory cannot establish whether scripts exist in another checkout or were removed by the ongoing correction.

| Script | Logic outside the library | Should it move into the library? |
|---|---|---|
| [`scripts/research_baseline.py`](../scripts/research_baseline.py) | Identifies native plan/beam dose members by filename, reads the first 256 bytes, records the first text line and a hash of that prefix, selects metadata members for hashing, counts file extensions, and assembles source/code provenance and a fixture-specific Markdown report. Native plan/settings reading already delegates to `inspect_export`. | Move native dose-member classification and bounded header observations into the planned dose-inventory API, retaining path, scope, sampled-byte count and explicit prefix-versus-full-file hash meaning. Reuse snapshot hashing for full-file provenance where appropriate. Keep fixture assertions, selected help/PlanCheck source lists and report prose in the research script. Generic provenance composition is useful infrastructure, but is not another missing clinical reader. |
| [`scripts/index_help.py`](../scripts/index_help.py) | Converts extracted vendor HTML to text and builds a page/title index. It contains no patient, beam, structure or dose reader. | Keep as a research/documentation utility. Promote only if searchable vendor help becomes an intended library feature. |
| [`work/mppg9b-pdfs/compare.py`](../work/mppg9b-pdfs/compare.py) | Parses selected PDF text tables, verifies fixture identity, converts native coordinates/settings to PDF display units, compares at displayed precision, and records page/hash provenance. Native values already come from `inspect_export`. | Keep the fixture-specific parser and evidence checks in the harness. If PDF comparison is later generalised, introduce explicit report profiles and a reusable comparison layer rather than promoting the hard-coded patient/plan paths or silently adding those tolerances to ordinary setting checks. Display-unit conversions may become documented library conveniences once their supported geometry/unit scope is explicit. |

This script-specific pass adds detail to the dose-inventory recommendation; it does not reveal another completed DVH, dose-sampling or clinical-analysis implementation hidden in the currently available scripts.

## Work that should remain separate

The fixture-specific PDF extraction/comparison in [`work/mppg9b-pdfs/compare.py`](../work/mppg9b-pdfs/compare.py) checks 208 selected native/PDF values.
Its native beam/settings data already come from `inspect_export`.
The hard-coded PDF names, report layout and screenshot-precision tolerances belong to the evidence harness unless general PDF import is deliberately requested.
Their existence does not imply a missing native-settings feature.

Help indexing, source hashing and report presentation can remain research tooling.
Human UI answers and screenshot transcriptions should remain evidence fixtures rather than implementation defaults.
Unknown checkbox/location mappings should remain unknown until supported.

Absolute dose interpretation, DICOM RT Dose import/sampling, exact DVH statistics, PDD/profile/output-factor extraction, effective material maps, general coherent aperture writing, MU/control-point interpretation and multiple prescriptions are not otherwise complete features hidden in checks.
They remain implementation/validation work in the existing backlog or the current dose/DVH investigation.
The retained dose investigation files do not establish a supported, independently validated library implementation.

## Verification and follow-through

Read the package, CLI dispatch, tests, scripts, current README/TODO, retained CT/depot/native-return reports and the fixture-specific PDF comparison helper.
The delegated read-only Git audit reported two commits and unstaged active review work; the main session independently verified those facts.
Direct inspection of the retained native return found seven plans and three studysets, and confirmed that its public plan/beam/study/log records omit the categories identified above.
The ordinary local test run passed: **71 passed, 29 skipped** (`python3 -m pytest -q`).
The skips mean this run did not exercise every optional/private integration example; this audit does not supersede their recorded validation status.

The promotion tasks are recorded under “Promote investigated capabilities into reusable library APIs” in [TODO.org](../TODO.org).
Implement each reader/check in the package, add independent examples with varied names/values and failure cases, and make evidence checks call that API.
Document the Python import path and declared support boundary when each task is completed.
Remove its TODO entry only after the reusable behavior and relevant regression are in place.
