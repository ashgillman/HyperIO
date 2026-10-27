# Native suite return, 27 October 2026

The returned patient provides native calculation evidence for the four non-Reference Phantom plans.
The user explicitly confirms that neither Density plan was calculated.
Reference was also left uncalculated.
This capture can be analysed despite incidental beam-visibility changes; the saved states identify where those changes occurred.

## Source and comparison

- Supplied ZIP: `/Users/gil/Downloads/1~zzzInputOutputAGsuite.zip`.
- Retained exact copy: `reference/native-suite-return/1~zzzInputOutputAGsuite.zip`.
- SHA256: `48e1b57417eeb8bb3017691ec062b8e97a6c1f9f9e70d77b91fd088454fad615`.
- Generated run: `hyperio-tps-8ccb9f90b45ee0d9`.
- Baseline: the existing `validation/generated/native/1~zzzInputOutputAGsuite` tree.
- Baseline manifest SHA256: `1a5a4437e05e15826eb2c4c28e7be1b0d38301af530f996e5ba5950f6123211f`.
- [Machine-readable comparison](native-suite-return-2026-10-27.json) retains all member hashes, textual plan differences, named settings, numeric aperture records and labelled calculation-log observations.

All archive members passed ZIP CRC checking.
Matching member names case-insensitively gives 964 unchanged files, 19 changed files and 29 additions, with no removed files.
There are four additional case-only filename changes, tracked separately from content changes.
No supplied files were modified and no generated patient/package was replaced.

All 304 pre-existing files in each of CT1, Phantom and Density are byte-identical to the generated baseline.
This includes native images, cached DICOM images, contour records, info and structure tables.
The additional studyset files concern display state or bolus display metadata.
Reference and both Density plans retain all ten original plan-folder files byte-for-byte, without new calculation logs or dose files.
That establishes returned-file equality; it does not imply those three plans were explicitly saved/reopened during this session.

## What was calculated

| Plan | New native dose files | Own completion log, literal local time | Beam 2 visible in return |
|---|---|---|---|
| Reference | None | None | No |
| Calculation-A | Plan dose and three beam-dose files | 27 Oct 2026 11:50:46.974 | No |
| Calculation-B | Plan dose and three beam-dose files | 27 Oct 2026 15:54:25.666 | No |
| Aperture-Headers | Plan dose and three beam-dose files | 26 Oct 2026 18:07:26.531 | Yes |
| Aperture-Leaves | Plan dose and three beam-dose files | 27 Oct 2026 08:58:17.504 | Yes |
| Density-Conflict | None | None | No |
| Density-Aligned | None | None | No |

The generated baseline omitted both dose files and calculation logs, so these are new additions rather than inherited source dose.
Each of the four logs reports calculating three segments and ends with Dose Calculation Completed.
Native completion and file association are now supported for those four specific cases.
This does not establish absolute dose accuracy, native dose scaling/axes or current-dose freshness after every later edit.
The log timestamps have no timezone; the earlier review identifies Monaco 6.2.3.0, but the return alone does not independently establish the application build.

Beam 2 visibility was enabled in the two aperture plans only.
A and B still have it disabled, yet both have three segment calculations and three beam-dose payloads.
That supports treating this particular visibility flag as a display preference rather than a calculation-exclusion flag in these cases.
There is no need to repeat the calculations merely to restore visibility preferences.

## Uncertainty normalization and calculation evidence

| Plan | Generated MCVARIANCE / MCSEGMENTVARIANCE | Returned values | Generated → returned MCVARPERPLAN | Log mcStdDev | Log whole-calculation / per-control-point uncertainty |
|---|---|---|---|---|---|
| Calculation-A | .02 / .03 | .02 / .02 | Explicit 0 → absent | .02 for all three segments | 1.4% / 2.0% |
| Calculation-B | .04 / .05 | .04 / .04 | 1 → 1 | .04 for all three segments | 3.3% / 4.9% |
| Aperture-Headers | .01 / .01 | .01 / .01 | Absent → absent | .01 for all three segments | .69% / 1.0% |
| Aperture-Leaves | .01 / .01 | .01 / .01 | Absent → absent | .01 for all three segments | .69% / 1.0% |

Together with the earlier initial UI review, this shows the deliberately unequal segment values were not preserved through the calculation/save session.
They were brought into agreement with MCVARIANCE.
A's explicit false mode key was omitted, while B's true key remained.
For this build/fixture, a writer should keep the two uncertainty values consistent unless intentionally testing their interaction.
The reader should still retain absent mode keys as absent; this capture does not justify a universal implicit-false rule.
The exact stage that normalized the values cannot be isolated because there is no intermediate pre-calculation saved capture.

The logs now provide evidence that the chosen main uncertainty value reached the calculation setup, beyond merely changing the displayed UI value.
The reported achieved whole-calculation and per-control-point percentages are distinct quantities and need not equal the requested setting.
In particular, B's displayed 4% Per Calculation is accompanied by reported 3.3% whole-calculation and 4.9% per-control-point values; do not relabel either as a failed setting or an exact 4% measured result.

The raw named grid values remain 1/2/3 in the respective 1/2/3 mm candidate plans.
Dose deposition and force-water flags retain their requested combinations.
The plan grid metadata was regenerated in all four calculated plans, including different bounds, dimensions and centres for different grid settings.
Some positional SSD/depth-like records also changed after calculation, while the recognized beam isocentres, angles, aperture headers and numeric leaf positions remained unchanged.
Those derived records need independent export checks rather than being treated as unintended changes to requested beam placement.

## Aperture results

All three recognized beams in every returned plan retain the generated numeric aperture-header and leaf-table values.
The leaf-table location shifted by one line in the two aperture plans after a record was inserted, so the comparison locates its unique sixteen-row numeric table rather than assuming a fixed returned offset.

For field ID 2 in Aperture-Headers:

- Both aperture headers remain `80,60,0,0`.
- Numeric leaf values remain identical to the generated baseline, including the central +50 mm second-bank positions.
- The later compact-shape record changes from `3,20` / `50,50` / `30,40,30` to `3,12` / `40,30` / `20,40,20`, with corresponding list-length changes.

For field ID 2 in Aperture-Leaves:

- Both aperture headers remain `100,100,0,0`.
- One-based leaf pairs 37–44 retain the edited second-bank position +10 mm; their numeric values are unchanged despite formatting normalization to `10.0`.
- The later compact-shape record changes from `3,20` to `4,20`, and `30,40,30` to `30,30,10,30`, with additional zero-valued entries in its later arrays.

These paired results support the hypothesis that Monaco regenerates the compact-shape representation to reflect the edited aperture inputs during the calculation/save session.
The exact compact-shape grammar and full precedence rules remain unresolved.
The earlier BEV observations and new completed calculations are strong fixture-specific evidence, but exported RT Plan geometry and dose sampling are still needed before declaring a general coherent aperture writer validated.
The per-beam native dose files are not byte-identical between the two aperture plans, even where their sizes and logged history counts match; no numerical equality is inferred from matching size or history counts.

## Density: settings survive, effective precedence is still open

The stored plan overrides survive unchanged:

| Plan | Insert mode | Uniform ED | Fill ED | Calculation log observation |
|---|---|---|---|---|
| Calculation-A | Forced | 1.1 | 1.0 inactive | Total/free Insert volume 2663.3 / 0 ccm |
| Aperture-Headers | Filled | 1.0 inactive | .8 | Total/free Insert volume 2654.3 / 0 ccm |
| Aperture-Leaves | None | 1.0 stored | 1.0 stored | No Insert volume entry |
| Calculation-B | Forced | 1.0 | 1.0 inactive | Total/free Insert volume 2672.4 / 0 ccm |

The plan table also retains Patient forced ED 1.0 at layer 2 and Insert at layer 9.
The zero free volume is a specific reason to investigate overlap/layer behavior before interpreting a surviving Insert override as an effective material change.
It suggests the Insert may be masked in the effective volume assignment, but that interpretation is not proven by the log label alone.
CT-to-ED table contents and effective calculation material maps remain unavailable.
Do not promote these captures to validated forced/fill/disabled computational semantics.

Both uncalculated Density plans and their shared studyset are unchanged, preserving the original plan-versus-studyset conflict experiment for later review.
There is no failure or missing calculation to diagnose for those plans: the user intentionally did not calculate them.

## Filename and calculation-state observations

The four calculated plans have their `.hyp` basename changed from mixed-case `zzzInputOutputAGsuite.hyp` to lower-case `zzzinputoutputagsuite.hyp`.
Uncalculated plans retain the mixed-case filename.
The native patient ID and plan associations remain unchanged.
This is a fixture-specific reason for future patient-ID filename lookup to tolerate a unique case-insensitive match and reject ambiguous collisions, rather than assuming an exact case-sensitive filename.
It does not require renaming the supplied evidence or changing an otherwise successful Windows import.

The calculated plans' checksum files remain byte-identical to the generated inherited source files despite added dose and rewritten plan/tel records.
Thus these checksum files cannot be used here as an automatic proof that the current dose matches all current settings.
Their algorithm, scope and lifecycle remain unknown.
Calculation logs, payload presence, exact before/after hashes and later independent exports should remain separate evidence.

## Revised next work

1. Export DICOM RT Plan and RT Dose from the already calculated aperture plans first, with A/B useful for grid/uncertainty comparison.
   This can test saved versus exported jaws/leaves, case association, dose grids and physical sampling without another native import or another long calculation.
2. Investigate the Insert's zero free volume and effective layer/material assignment before spending time on Density-pair calculations.
   Keep the present pair intact; a future isolated follow-up should change only the layer/overlap or override condition needed to distinguish the alternatives.
3. Analyse the two regenerated compact-shape records against their exported geometries, then implement coherent aperture-writing support with fixture/version scope.
4. Calculate Reference later if a numerical unchanged-aperture control is needed.
   Its absence no longer blocks establishing that generated plans can calculate, because four other candidates have now done so.
5. Retain a targeted UI-save capture only if the exact timing of uncertainty normalization matters; a broad repeat of the uncertainty experiments is lower priority.

The immediate implementation priorities are an independent DICOM dose/geometry return path and comparison of the returned aperture representations.
Native compressed-dose interpretation is still a separate investigation; this analysis does not assign dose units or physical values to its payload bytes.
