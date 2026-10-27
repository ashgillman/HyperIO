# Partial TPS review: findings and next experiments

This analysis was recorded on 26 October 2026 from Ashley Gillman's partial worksheet for Monaco 6.2.3.0.
The objective is to prioritise the remaining work for information gained per tester session.
The current patient and worksheet should be continued rather than replaced with another set of imports.

## Evidence and accounting

- Run: `hyperio-tps-8ccb9f90b45ee0d9`; installed patient: `zzzInputOutputAGsuite`.
- Original editable review: `validation/generated/REVIEW.md`.
- Exact checkpoint: `validation/results/history/partial-review-bed8eca15603.md`.
- Checkpoint SHA256: `bed8eca15603d22b959e373ae7be7dc9f47ec8e27807424780ed4dbeeda1a980`.
- Structured transcription: [partial-review-checkpoint.json](../validation/results/partial-review-checkpoint.json).
- Fifteen completed worksheet observations were appended to [the event register](../validation/results/events.jsonl); an identical reimport added zero events.

The worksheet has 53 rows: 11 marked pass, four marked observation, and 38 still marked not_reviewed.
These are worksheet counts, not independent experiments or a software validation percentage.
Several Reference rows already describe A/B or aperture checks whose duplicate rows later remain blank.
Those duplicates do not require a new experiment merely to fill the sheet.
The structured checkpoint preserves the original row statuses, sections and literal notes, with scope qualifications in messages.
It does not silently transfer passes between plans.

The worksheet's observed-at field is literally `20260226 17:30`, whereas the pasted logs are dated 26 October 2026.
The observation date and timezone remain unresolved; the structured observation date is null.
Blank actual cells marked pass are retained as human attestations without invented measurements.
The current editable worksheet, generated native patient and import ZIP were not changed.

## What the review establishes

### Native loading, images and structures

The new native restoration, CT geometry and zero values are marked pass.
The transferred contours are also marked pass.
This removes the earlier failed native imports as the immediate development blocker for this specific generated patient.
It does not identify which earlier defect caused those failures or establish a general native writer.

The apparently different centres are expected for the supplied geometry:

| Quantity | Independent file calculation | User observation | Interpretation |
|---|---|---|---|
| Image-volume centre | DICOM mm `(-0.0635, -0.0638, -599.5)`; candidate native HFS display cm `(x, z, -y)/10 = (-0.00635, -59.95, +0.00638)` | `(-0.01, -59.95, +0.01)` | Matches at displayed precision; the volume retained the source position rather than being centred on world zero. |
| Patient contour centroid | Area-weighted polygon centroid, equal 5 mm slice weighting, cm `(0.1899994, -59.9500196, -2.4999960)` | `(0.19, -59.95, -2.50)` | Matches at displayed precision; this is the contoured body rather than the image cube. |
| Beam isocentre | `.hyp` and `tel.1` native mm `(1, -598.5, -2)` → cm `(0.1, -59.85, -0.2)` | `(0.1, -59.85, -0.20)` | Matches the retained source plan; distinct from either centre above. |

The centroid calculation uses structure index 8 (Patient), shoelace polygon areas/centroids and the longitudinal coordinate in each `.WC` filename.
This independently explains the Patient centre without using the bounding-box midpoint as a substitute.
The HFS image-axis interpretation is consistent with this fixture and its UI result; nonzero rotations and other patient orientations remain separate work.

The observed SSD of 93.65 cm is also consistent with the retained zero-angle geometry.
The source beam record contains SAD 1000 mm and SSD 936.5 mm, with surface point `(1, -598.5, 61.5)` mm and isocentre vertical coordinate -2 mm.
Thus the surface-to-isocentre depth is 63.5 mm and `1000 - 63.5 = 936.5 mm`.
This does not resolve the separate oblique-plan PDF/UI discrepancy.

### Calculation settings

| Candidate | Stored variance / segment variance | Observed uncertainty | Stored mode | Observed mode | Deposition | Force water |
|---|---|---|---|---|---|---|
| Reference | `.01 / .01` | 1.00% | absent | Per Control Point | Medium | Off |
| Calculation-A | `.02 / .03` | 2.00% | `0` | Per Control Point | Water | Off |
| Calculation-B | `.04 / .05` | 4.00% | `1` | Per Calculation | Medium | On |

The deliberately unequal numeric values distinguish `MCVARIANCE` as the displayed uncertainty in A and B.
The mode results support `0 → Per Control Point` and `1 → Per Calculation` in these candidates.
The absent Reference key displayed Per Control Point here; the reader should continue preserving absence rather than inventing a universal default.
Deposition and force-water selections can display independently: B shows Medium while force water is on.
The grouped grid check is marked pass, but no actual numbers or units were transcribed.
The predicted 0.10/0.20/0.30 cm values therefore remain expectations accompanied by a reviewer pass, not newly captured numeric observations.

These findings substantially reduce uncertainty about initial UI interpretation.
They do not establish the computational role of `MCSEGMENTVARIANCE`, effective transport materials, or persistence after Monaco rewrites the native files.
Rechecking the same displayed settings has lower value than collecting the corresponding saved files and a fresh calculation.

### Beam and aperture records

The baseline beam note explicitly identifies Density-Aligned despite appearing under Reference.
It records 3D delivery, Agility2017, 6 MV photons, Monte Carlo, 100 MU/fraction, SAD setup and zero gantry/collimator/couch angles.
Those observations must retain that plan scope.

The hidden 10×10 beam has a direct candidate explanation.
Every generated plan's copied `GUI.STATUS` lists BeamNumber 2 with `BeamVisibility=false` and `DoseVisibility=true`, whereas beams 3 and 1 have beam visibility enabled.
That matches the observed field IDs and hidden beam.
The first diagnostic should be toggling that beam's visibility; this finding does not prove it is excluded from calculation.
Future generation should set intentional initial visibility instead of inheriting source display preferences, after retaining this checkpoint as evidence.

The aperture-header result reports two 4 cm widths and two 3 cm lengths plus a rectangular BEV, consistent with the requested 8×6 cm rectangle.
The literal field label in the note is `20x10`, while the edited candidate targeted the 10×10-labelled beam.
The plan/field label should be resolved from one screenshot or returned file rather than silently corrected in the evidence.

The leaf result describes the intended C shape and second-bank tips at about one fifth of their outer extension.
This supports a visible effect of the leaf-table edit, but the review does not measure every leaf index, bank sign or physical position.
Both aperture observations were written in the Reference section without naming the observed aperture plan.
The intended profile association is an inference from the unique test purpose.
Headers and leaves each influence the display in their respective candidates, but the redundant compact-shape representation and calculated aperture still need investigation.

### Save/reopen, dose and logs

Save/reopen is marked pass without per-plan detail or an accompanying returned native archive for this run.
Keep that attestation; byte-level persistence and plan independence remain unverified.
The .hyp filename check belongs in automatic package/returned-file checks, since the reviewer cannot inspect it in Monaco.
All seven generated folders locally contain `zzzInputOutputAGsuite.hyp` with matching plan associations.

The reviewer explicitly reports no doses calculated.
CALC-EXECUTION and EXPORT-DOSE are still not reviewed.
There is consequently no new evidence for dose validity, current-dose association or computational effects of the settings.

The pasted log contains 564 parseable Log elements, including 45 Error and 22 Warn entries, spanning multiple processes and times.
It is not ordered strictly by time.
No log message names `zzzInputOutputAGsuite`, so errors cannot automatically be assigned to this patient.
Older entries include lock/service failures, GUI-status save warnings and DICOM export errors before 17:30.
Those may deserve investigation if reproduced during a clearly identified operation; their presence alone does not establish a current suite failure.
After 17:30 the parsed warning entries are three `VoiCombinationFactory::AWithoutB - ::RemoveEmptyVois` messages, with no Error entries in that interval.
The retained structure definitions contain derived-structure combinations, which makes inspecting empty/derived structures a useful hypothesis, not a proven warning cause.
There is no basis to override the reviewer's no-calculation statement using unrelated earlier dose/log activity.

## Remaining work ranked by information value

| Priority | Experiment or work | Why it is informative | Minimum evidence / next decision |
|---|---|---|---|
| 1 | Return the current saved native patient, identify the opened plans, and enable beam 2 visibility once. | One capture tests persistence, silent normalization, file association, redundant aperture records and the visibility explanation together, without a new import. | Saved patient ZIP plus one clearly labelled beam/BEV capture; compare against the exact generated manifest. Separate source metadata from Monaco rewrites. |
| 2 | Inspect the existing Density-Conflict / Density-Aligned pair, then force/fill/disabled cases. | Effective density and precedence are still wholly open and affect the meaning of later dose differences. The pair holds other numerical plan/beam inputs equal. | Record studyset and plan values, effective/displayed mode and layer behavior; use effective-density evidence where available. UI settings alone must not be labelled computational precedence. |
| 3 | Calculate Reference once, save/reopen and return native data plus DICOM RT Plan/RT Dose. | This distinguishes a loadable/displayable template from a working calculation path and provides independent geometry, scaling and association evidence. | Calculation completion/state, machine/model and normalization, associated RT Plan/RT Dose, and source/returned hashes. Stop to diagnose a failure rather than expanding the matrix. |
| 4 | Compare saved/exported aperture geometry for the two existing probes. | Resolves which records Monaco preserves or regenerates and whether the requested aperture survives beyond display. | Explicit plan and beam IDs, saved leaf/jaw/compact-shape diffs and exported geometry; calculate modified apertures only after establishing a working Reference control. |
| 5 | Resolve residual uncertainty-mode/segment-value behavior with one targeted native capture. | Initial numeric display and Boolean polarity now have useful evidence; the remaining question is the second field's role and saved/calculation behavior. | Native files before/after a single UI uncertainty/mode edit, with the other displayed controls fixed. Avoid another broad collection of parameter imports. |
| 6 | Broaden coordinates, geometry, materials and supported models only after the above. | Nonzero angles, oblique surfaces, asymmetric fields, other energies and models are valuable held-out tests but add confounders before the baseline is understood. | Explicitly labelled held-out cases and independent geometry/dose checks; retain fixture/version scope. |

Priority 2 needs only review of the already installed plans; its computational part can follow the successful Reference calculation from priority 3.
There is no need to complete every remaining UI row before attempting that control calculation once its geometry and materials are understood.
The next reviewer session can consist of one saved-patient return, a short density comparison, and one Reference calculation/export if practical.
Do not repeat already documented A/B settings simply because duplicate rows are blank.

## Useful work while TPS review is paused

1. Compare the returned saved native patient when supplied; this currently has the highest evidence yield per reviewer action.
2. Implement independently tested DICOM RT Dose geometry/scaling and sampling as the first calculated-dose return path.
   Use analytic arrays with known physical coordinates, orientation, frame offsets and absolute values before reading the first TPS dose.
3. Separate automatic filename/linkage/package checks from human UI questions, and make grouped results explicitly name their observed profiles.
   Preserve stable test IDs and this run's original worksheet/revision.
4. Prepare a comparison that reports changed/normalized native settings and unknown dose freshness explicitly.
5. Defer native compressed-dose interpretation, algorithm switching, multiple prescriptions and broad protocol matrices until a useful static-field round trip works.

The immediate milestone is one traceable generated field that calculates, returns through DICOM and yields independently checked physical dose samples.
Measurement comparison and protocol coverage remain subsequent requirements; successful loading or a completed calculation does not complete commissioning validation.
