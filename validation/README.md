# HyperIO perpetual TPS validation

The test list lives in [TESTS.org](TESTS.org), with machine-readable definitions in [catalogue.json](catalogue.json).
Stable test IDs identify components of the software; they do not restart when packages are regenerated.
The current suite collects compatible checks in **one native patient, seven plans and three studysets**.
One native patient restoration replaces the old sequence of separate case imports.

## Current import package

[Download HyperIO-TPS-tests.zip](generated/HyperIO-TPS-tests.zip).
Extract it and restore `HyperIO-TPS-tests/native/1~zzzInputOutputAGsuite/` using the normal native Monaco patient-data workflow.
This native plan package is not for the DICOM import browser.
The suite patient is separate from `zzzInputOutputAG` and `zzzInputOutputAG2`.
If this suite identity is already in use, preserve its results before a fresh run and choose another suite identity in catalogue.json or through a supported TPS workflow.
Record the actual installed ID in the review.

Open the unchanged-image CT1 control first, then the Reference plan in Phantom.
If that opens, inspect the other plans and collect their combined settings/geometry checks while each plan is open.
The generated [review sheet](generated/REVIEW.md) is grouped by patient/plan, not by a separate import for every test.
Save/close/reopen the patient once to collect persistence checks together.
Calculation is a later optional gate on Reference, not a requirement to inspect every profile.
The [27 October native return](../reports/native-suite-return-2026-10-27.md) already supplies calculation evidence for the other four Phantom plans.
Continue with independent exports from those calculated plans; Reference and both Density plans were intentionally not calculated.
Catalogue revision 2 adds returned-calculation checks and broadens export checks without replacing the original generated worksheet or package.

| Plan | Studyset | Main combined checks |
|---|---|---|
| Reference | Phantom | Native association, source beam geometry, baseline calculation settings and no-dose state |
| Calculation-A | Phantom | 2 mm dose grid; MC fields 0.02/0.03; mode flag 0; water deposition; forced ED 1.1 |
| Calculation-B | Phantom | 3 mm dose grid; MC fields 0.04/0.05; mode flag 1; medium deposition and force-water |
| Aperture-Headers | Phantom | Candidate 8x6 cm aperture headers and Insert fill ED 0.8 |
| Aperture-Leaves | Phantom | Eight-leaf notch table and disabled Insert override |
| Density-Conflict | Density | Plan forced ED 1.1 versus studyset ED 1.2 |
| Density-Aligned | Density | Both density representations at ED 1.2 |

Every studyset includes all 100 native CT slices and cached DICOM images from the successful returned CT1.
CT1 retains its original empty contours.
Phantom and Density transfer source phantom contours by nearest physical slice, updating the target origin/orientation records.
That transfer and the transplanted plan associations are new candidates requiring TPS review.
The body/insert shapes are sampled from the supplied phantom; they are not a claim that the entire 500 mm CT cube is a contoured patient body.
Source dose files and historical calculation logs are omitted.
Plan grid/checksum/status/normalization/document metadata remain unverified for the new studyset and cloned plans.
These limits are recorded in the manifest and tested explicitly; local reader consistency is not TPS acceptance.

## Persistent results

[results/events.jsonl](results/events.jsonl) is the append-only observation ledger.
An observation identifies a test and revision, profile, run, phase, actual result and supporting evidence.
Initial-load, save/reopen, returned-file and calculation results remain distinct.
Historical successful zero-CT import and returned geometry checks are retained without pre-passing this new native restoration.
Earlier failed candidates and returned files are preserved as historical evidence outside the current generated package.

Fill `generated/review.json`, or return a filled Markdown sheet and one native patient ZIP with notes on which plans were saved/calculated.
The same returned patient can support several component checks.
Record a completed structured review with:

```sh
PYTHONPATH=src python3 -m hyperio record-review \
  validation/generated/review.json validation/catalogue.json validation/results/events.jsonl
```

Identical observations are not duplicated if a review is recorded again.
Further observations append; they do not erase previous passes, failures or unknowns.
`not_reviewed` records are not imported into the ledger as passes.
Use `observation` for unresolved field mappings, recording the displayed value/mode without declaring a mapping validated.
A failed patient/plan load blocks its dependent checks; record the exact failure rather than marking each numerical setting failed.

## Regeneration and extension

```sh
PYTHONPATH=src python3 -m hyperio validation-suite \
  'reference/1~ZZZELEKTAONEHETERO.zip' \
  'reference/native-zero-ct/1~zzzInputOutputAG2.zip' \
  validation/generated
```

The generator refuses to overwrite an existing generated directory or worksheet.
Retain any completed review and returned evidence before replacing generated material.
The generated directory contains the stable-name ZIP, catalogue snapshot, run worksheet, native patient, file manifests, source hashes, text diffs and per-slice contour-transfer provenance.

Add future tests to catalogue.json with new descriptive IDs, assign them to an existing compatible profile where possible, and update TESTS.org.
Never reuse an ID for a different check.
Increment a test's revision when its expected behavior changes, retaining old results and their recorded revisions.
Retain catalogue/profile identities needed to interpret older observations.
Use a focused follow-up only when a combined profile fails or settings interact enough to prevent attribution.
The catalogue and ledger persist independently of regenerated import packages.
