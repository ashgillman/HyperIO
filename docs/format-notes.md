# Initial Monaco format map

## Evidence levels

- **Observed:** exact values and record shapes present in the supplied archive.
- **Mapped:** a meaning suggested by PlanCheck.jl and compatible with these files.
- **Documented behavior:** a user-interface behavior described by the supplied Monaco help.
- **Controlled confirmation pending:** a mapping still needs a labelled one-variable edit, repeat capture, or independent export.

These are different kinds of evidence.
A documented UI control does not establish its file key, unit, active-state flag, or saved-dose provenance.
The initial Python outputs attach a source file, one-based line number, raw token, and interpretation to each named setting.
Positional records retain their complete raw line and explicitly mark the mapping as provisional.
The initial mappings below are supplemented by fixture-specific UI results from the partial perpetual-suite review described under Named calculation settings.
Saved-file normalization and calculation semantics remain separate evidence requirements.

## Archive organization

The ZIP contains 5,735 files and 2,162,402,099 uncompressed bytes.
Its patient root contains six studyset directories, six directories under `plan/`, demographics, locks, and DICOM mapping data.
There are 1,866 files each with `.DCM`, `.CT`, and `.WC` suffixes.
A CT file count does not by itself establish slice ordering or equivalence of the studysets.

| Record | Initial handling | Source of interpretation |
|---|---|---|
| `plan/<name>/plan` | Header, plan/patient/studyset identity, one observed density table | PlanCheck `plan.jl`, checked against all six supplied plans |
| `plan/<name>/*.hyp` | Literal directives, selected typed settings, byte-preserving copy edits | Named keys plus PlanCheck `hyperion.jl` |
| `plan/<name>/tel.1` | Three beam headers per supplied plan | PlanCheck `tel.jl` header pattern and offsets |
| `<studyset>/contournames` | Structure indices, density defaults, mode, type code, layer | PlanCheck `contournames.jl` |
| `<studyset>/info` | Selected CT-to-ED conversion name | PlanCheck `info.jl` |
| `DCMData/*.DCM` | Counted; pixels and tags not yet parsed | Future independent DICOM comparison |
| `T.*.CT` | Counted; data retained in the original ZIP | Native compressed image pixels remain uninterpreted |
| `T.*.WC` | Leading polygon records, coordinates, source lines and unparsed tail | Public contour reader; sampling policy is separate |
| `dose.1`, `tel.1.dose.*` | Optional full-grid decoding for one observed profile | 30 October VMAT array/DRP/statistic evidence below; other block profiles remain unsupported |
| `RxA.xlog` | Labelled uncertainty and calculation completion observations | Literal XML-fragment messages; dose association unverified |
| `dvhparam.xml` | DVH sample spacing and dose bin width | XML version 1; screenshot-associated sampling settings |
| `isodosesettings.xml` | Structure index references, reference-dose requests, 14 mapped goal types | XML version 5; PlanCheck goal mapping plus supplied VMAT screenshot |
| `checksum.1`, status files | Retained and compared by snapshots | Freshness semantics and checksum algorithms not yet mapped |

The library reads ZIP members directly and never extracts them as part of inspection.

### Unity phantom plan header

The supplied `1~cellIrrad.zip` inspected on 4 November 2026 contains five plans with header `00be101a`.
All five have the same identity positions (plan, patient and studyset on lines 3, 5 and 7), single-prescription marker on line 6, and one unambiguous five-value density table used by the existing `00d5101a` reader.
The RED workflow accepts these two explicit headers and preserves the original header on output.
Unknown headers, multiple prescriptions, malformed tables and ambiguous table matches remain rejected.
`CellTesting` contains two density records named `patient`; a name-based RED preset targeting that name is rejected as ambiguous.
Uniquely named structures can be edited while unrelated duplicate records are retained verbatim.
The observed layout supports reading and selective token edits; it does not identify the Monaco release number or validate other Unity records, native reloading, effective material assignment or recalculated dose.
The supplied-archive regression can be run with `HYPERIO_UNITY_EXAMPLE=/path/to/1~cellIrrad.zip python -m pytest tests/test_applications.py -k supplied_unity`.
A single-Rx plan must have exactly one `.hyp` in its directory to associate settings unambiguously.
The interpreter requires known headers and the observed record shapes and reports a diagnostic when those checks fail.
Version headers alone are not proof that every other file with that header has an identical layout.

## Saved optimisation and DVH review readers

`hyperio.review` reads `.hyp` objective blocks and the two review XML documents.
`inspect_export` exposes `cost_functions`, `dvh_parameters`, `isodose_settings`, and `dose_reference_points` per plan.
The public readers and `HypDocument.cost_functions()` do not depend on fixture patient, plan or structure names.

The `.hyp` reader uses the existing known-block grammar with explicit structure/objective/margin nesting and rejects duplicate keys or incomplete blocks.
It retains unknown objective types and extra properties, and exposes absent values as unknown.
Dose-valued objective effects are converted from Gy to cGy; percentage-valued types remain percent.
The underlying field records retain native units, original tokens and one-based line provenance.
Nonfinite saved optimizer results retain their literal/special representation and a JSON-safe null numerical value.
All per-target shrink margins remain available in mm, including unequal margins.
The Parallel reference-dose display uses `refdose`, supported by the supplied 3000 cGy screenshot row, rather than `thresholddose`.

The XML readers support namespaced and non-namespaced elements and validate the observed metadata versions when present.
DVH parameters are sample spacing in mm and bin width in cGy; they do not specify the exact sampling-grid phase or contour voxelization rules.
Structure settings retain enabled state, high/min dose reference percentages, prescribed dose of interest and reference-dose requests.
The observed `Enabled=-1`, `PrescribedDose=-1` and `RefValue=-1` sentinels retain their literal values and expose unknown interpreted values.
Reference request types 0 (dose in cGy) and 1 (relative volume in percent) have screenshot evidence; other types retain literal fields without guessed units.
Goal definitions preserve all raw XML fields, including finite or infinite mean-dose bounds, recovery tolerances and shift-recovery configuration.
The 14 mapped goal types include dose, relative/absolute volume, and HI/CI index goals.
Absolute-volume fields are mapped from mm³ to cm³; HI/CI limits use `Index`, not `Dose`.
Only the 10 goal definitions and four objective types represented in the supplied screenshot have that independent UI comparison; other type labels/units remain PlanCheck-derived mappings.

DRP parsing shares the `00d5101d` beam-header anchors and validates the six-value coordinate and eight-value saved-dose record shapes.
The coordinate/dose offsets are format-profile rules, not absolute line numbers or beam-name searches.
Coordinates retain native mm values and expose a cm convenience vector.
The saved dose entry is exposed in cGy with the complete raw record and line provenance.
A native zero stays zero; a UI dash, Location dropdown selection or total-dose value is not inferred.
Malformed DRP records produce a diagnostic independently of beam-header parsing.

The [29 October comparison](../reports/vmat-2026-10-29.md) uses the normal library output and records 25 matching saved records.
It does not establish native dose-array scaling, independent DRP dose sampling, DVH statistics, or general validity of all mapped objective/goal types.

## Named calculation settings

### Calculation Properties labels supplied on 23 October 2026

The user supplied two Calculation Properties screenshots and identified the controls corresponding to DOSEGRIDSIZE and MCVARPERPLAN.
These establish the display labels below; they are not a paired native-file toggle capture.

| Native key | Calculation Properties display | Evidence |
|---|---|---|
| `DOSEGRIDSIZE` | **Grid Spacing (cm):** | `image (4).png` shows 0.10 cm (1 mm); `image (3).png` shows 0.20 cm (2 mm) |
| `MCVARPERPLAN` | **Per Control Point** / **Per Calculation** | Both screenshots show Per Control Point selected; user identifies this selector with the native key |
| `MCVARIANCE` / `MCSEGMENTVARIANCE` | **Statistical Uncertainty (%):** | Both screenshots show 0.50; the screenshots do not distinguish the active native numeric directive |

Retain **Per Calculation** as the user-facing wording for the second mode rather than deriving a label from the `PERPLAN` suffix.
The screenshots also show Algorithm: Monte Carlo Photon and Calculate Dose Deposition to: Medium.
Neither screenshot identifies its patient/plan, so the two displayed grid values are not assigned to particular native plans.
The matching 0.20 cm PDF/native-grid comparison is recorded separately in [the selected-plan comparison](../reports/tps-pdf-comparison.md).
MCVARPERPLAN's Boolean polarity and absent-key behavior still require native before/after captures with the selector changed.
The reader therefore continues to retain an absent MCVARPERPLAN as unknown.
Source copies and hashes are recorded in [source notes](sources.md#calculation-properties-screenshots).

### Initial archive observations

| Key | Observed values | Initial interpretation | Evidence gap / experiment |
|---|---|---|---|
| `DOSEGRIDSIZE` | `1` in all six plans | Grid size, provisionally mm | Help displays cm; confirm `0.10 cm → 0.20 cm` produces `1 → 2` (C01) |
| `MCVARIANCE` | `0.01` or `0.0050000000000000001` | Uncertainty fraction, provisionally 1% or 0.5% | Do not square or square-root based on the name; test C02/C03 |
| `MCSEGMENTVARIANCE` | Same as MCVARIANCE in every supplied plan | Separate stored uncertainty parameter | Active field / relationship unresolved; test C02/C03 |
| `MCVARPERPLAN` | Absent in all six `.hyp` files | Optional mode flag in PlanCheck | Absence is unknown; no default false; test C03 |
| `DOSETOMEDIUM` | `1` | Boolean associated with dose deposition medium | Toggle with transport unchanged (C04) |
| `FORCEWATER` | `0` | Boolean associated with treating the whole patient as water | Distinct from dose deposition selection; test C05 |
| `STORECOUCHCOILDOSE` | `0` | Store/display couch/coil dose | This is not the couch inclusion/attenuation flag; separate capture needed |
| `ISPHANTOMMATERIAL` | `0` | Literal Boolean; candidate material lookup selector | Name alone is insufficient; vary Patient/Phantom lookup in QA mode if available |
| `FRACTIONS` | `1` | Fraction count | Confirm against prescription UI/export |
| `PRESCRIPTION` | `2` | Prescription value, provisionally Gy | Confirm against prescription UI/export |

All literal directives remain available, including unknown directives and duplicate keys.
Typed access supports only unique known keys in the supplied `.hyp` header profile.
The typed API rejects nonfinite and malformed numbers; raw source bytes remain intact.
The parser recognizes known nested blocks so a directive in a structure/beam block is not treated as a global setting.
It is not a complete grammar for every possible `.hyp` block.

PlanCheck's check 5.3 explicitly questions which of `MCVARIANCE` and `MCSEGMENTVARIANCE` should be used.
Its report code defaults an absent `MCVARPERPLAN` to false in one expression.
HyperIO keeps the absence visible and does not adopt that default.
The existing fixtures cannot resolve this question because their two uncertainty values always agree.

### Partial perpetual-suite UI review, Monaco 6.2.3.0

Ashley Gillman's [partial review analysis](../reports/tps-partial-review-analysis.md) records the initial display of generated candidates with deliberately unequal uncertainty values.
Reference displays 1.00% Per Control Point for `.01/.01` with no mode key.
Calculation-A displays 2.00% Per Control Point for `MCVARIANCE=.02`, `MCSEGMENTVARIANCE=.03`, `MCVARPERPLAN=0`.
Calculation-B displays 4.00% Per Calculation for `.04/.05` and mode `1`.
These observations distinguish MCVARIANCE as the displayed numeric value and support the Boolean polarity in these candidates.
They do not establish the computational role of MCSEGMENTVARIANCE or a universal absent-key default.
The earlier screenshots and initial archive did not resolve these questions by themselves; the unequal-value candidates supply the additional UI evidence.

Reference/A/B display Medium/Water/Medium deposition respectively and off/off/on force-water states.
Medium deposition and force water can therefore coexist in the displayed B configuration.
Effective calculation material behavior and preservation after native save remain to be checked independently.
The grouped grid check was marked pass without transcribed actual numeric values/units.
The review's literal observation date conflicts with the pasted log date; no corrected timestamp has been inferred.

### Native calculation return supplied 27 October 2026

The [native-return comparison](../reports/native-suite-return-2026-10-27.md) covers the four calculated non-Reference Phantom plans.
A's returned MCSEGMENTVARIANCE is .02 instead of .03, and B's is .04 instead of .05, matching their MCVARIANCE values.
A's explicit MCVARPERPLAN=0 is omitted in the returned .hyp; B retains 1.
Their own calculation logs report mcStdDev .02 and .04 respectively for all three segments.
This adds calculation-setup and native-normalization evidence to the earlier UI observations, but does not isolate whether normalization occurred during opening, editing, saving or calculation.
Retain literal absent-key state in the reader and keep both uncertainty values consistent in future ordinary writers unless deliberately testing the interaction.

The aperture plans retain their numeric headers/leaves while the compact-shape records change in accordance with the different probes.
All four calculated plans have lower-case patient-ID .hyp basenames; uncalculated siblings retain mixed case.
All inherited checksum files remain unchanged despite added dose and changed plan/tel records, so their presence/equality must not be used as proof of current-dose freshness.
Insert overrides survive in the plan tables, but logs for A, B and Aperture-Headers give Insert free volume zero; effective material/layer precedence remains unresolved.

## Density records and precedence

The supplied `contournames` structure row has eight comma-separated values.
The mapped positions are:

| One-based position | Mapped meaning |
|---:|---|
| 1 | Structure index |
| 2 | Uniform/forced relative ED value |
| 3 | Density mode: 1 none, 2 forced, 3 filled |
| 4 | Structure type code |
| 5 | Timestamp-like value, retained raw |
| 6 | Unassigned in this reader |
| 7 | Fill relative ED value |
| 8 | Layer value |

The supplied plan-specific table has a structure name followed by five values.
The mapped positions are:

| One-based position | Mapped meaning |
|---:|---|
| 1 | Density mode: 1 none, 2 forced, 3 filled |
| 2 | Unassigned in this reader; retained raw |
| 3 | Uniform relative ED value |
| 4 | Fill relative ED value |
| 5 | Layer value |

PlanCheck also handles an older four-value plan layout; HyperIO has not implemented it without an appropriate labelled fixture.
The saved plan table must be distinguished from current studyset defaults.
The reader exposes both and links studysets by the actual saved studyset identifier within the same patient root.
It does not merge the two into a claimed effective voxel density map.
Stored density values in records with mode `none` are inactive configuration values, not an applied override.

The help says higher listed structures own overlapping voxels and that Fill ED considers original CT-derived relative ED.
Those rules mean a list of forced values alone cannot establish the effective density distribution.
The numeric direction of layer precedence and interaction with plan-specific overrides need C06-C08.
The selected CT-to-ED name is `RoutineSep21` in every linked studyset.
The clinic-level conversion table is outside this archive, so its contents cannot be reconstructed from its name.

## Beam records

The observed `tel.1` header pattern yields three beam records per plan.
The field IDs appear in native file order `3`, `1`, `2`, with descriptions `3x3`, `5x5`, and `10x10` respectively.
The reader preserves that order and does not sort beams by ID.
All eighteen records store algorithm code `6`, mapped by PlanCheck to Monte Carlo Photon.
This is not independently confirmed by a labelled algorithm switch or report export yet.
Machine IDs differ between `Agility6MVFFF` and `Agility6MV2017`.
The Python reader does not copy PlanCheck's clinic-specific machine-to-energy dictionary or infer nominal beam energy from those strings.

Native gantry, couch, collimator, and isocentre values are exposed as raw coordinates.
No DICOM coordinate conversion is applied.
Only beam headers are interpreted; description text is not proof of the aperture geometry.
PlanCheck warns that `.hyp` isocentres can be misleading with multiple prescriptions, so `.hyp` isocentre is not used as the authoritative beam coordinate here.

## Calculation logs

The `.xlog` files contain concatenated `<Log>` XML fragments with logger, process, counter, time, and message elements.
They are wrapped in a temporary root for parsing; source files are not changed.
The reader retains separate lists of labelled `mcStdDev` values, entire-calculation percentages, segment/control-point percentages, and calculation-completed messages with source lines and raw times.
It does not silently choose the last calculation or assume all events refer to the same saved dose.

| Plan | Log entire-calculation uncertainty (%) | Log each-segment/control-point uncertainty (%) |
|---|---:|---:|
| HDHeteroSq6F | 0.34 | 0.5 |
| HDHeteroSq6X | 0.67 | 1.0 |
| LDHeteroSq6F | 0.34 | 0.5 |
| LDHeteroSq6X | 0.69 | 1.0 |
| RefHeteroSq6F | 0.34 | 0.5 |
| RefHeteroSq6X | 0.69 | 1.0 |

Each supplied log also contains a `Dose Calculation Completed` message.
The logged `mcStdDev` values agree numerically with the saved MC directives.
This supports interpreting the numeric values as fractions and shows why an entire-calculation percentage should not be equated with the requested segment value.
It does not uniquely establish which of the two equal saved directives controls a given calculation, the missing mode default, or the log-to-current-dose association.

## Saved dose and binary payloads

Each supplied plan directory includes native dose payloads and checksum/status/log records.
All 24 sampled native dose files start with the ASCII header `00d5301e` and readable newline-delimited records before their payloads.
The provenance report records the first-line text and SHA-256 of a 256-byte prefix sample for each file; these are explicitly prefix hashes, not full dose-file hashes.
The inspected reference `checksum.1` is Boost-serialization XML with named physics, dynamics, leakage, cone-model, and global checksum entries.
Those names offer candidates for freshness experiments; their algorithms and validation behavior are not yet established.
PlanCheck reads exported DICOM dose rather than its native dose files, whose compression is unresolved in that implementation.
That is a useful boundary, not evidence for a specific compression algorithm.
The initial HyperIO implementation made no compression, byte-order, scaling, grid-shape, or axis-order claims for native dose.

### Full-grid VMAT dose profile, 30 October 2026

The D291026AG dose and beam-dose files have 39 ASCII header lines followed by five ASCII-length-prefixed compressed blocks and an uninterpreted `0,` trailer.
The first four blocks decode to four-byte zero placeholders; the fifth is a full array.
For this profile, adding the three-byte `.Z` header `1f 9d 90` makes the payload readable by the existing Unix-compress decoder in [unlzw3](https://github.com/scivision/unlzw3/blob/main/src/unlzw3/unlzw.py).
An independent GNU gzip invocation produced exactly the same 438,204 decoded bytes for the plan dose.
The library contains only this wrapper adapter, not an LZW or gzip implementation.

The tenth header line contains mode, x/z/y physical extents, x/z/y centre and x/z/y node counts.
For this case, counts are 53/53/39 and extents are 156/156/114 mm.
Array order is `(y,z,x)`, with x contiguous; each count is a big-endian uint32.
The first scalar on header line six scales counts to cGy; its value here is 1e-5.
The centre and extents define node-centre origin and spacing via `(extent / (node_count - 1))`.
The public DoseGrid converts geometry to xyz order and delegates trilinear interpolation to SciPy.
The remaining secondary scaling fields must equal the observed unit values; their general meaning is not inferred.
Non-placeholder preceding blocks, unsupported normalization/scaling profiles and decoded-size mismatches are rejected.

The sampled grid-centre dose is 2042.64831 cGy, matching the saved DRP's 2042.648315 cGy and screenshot 2042.6 cGy.
The array maximum is 6342.85086 cGy, matching screenshot rounding to 6342.9 cGy.
Both values are array-derived, not cached statistics read from review metadata.
Synthetic tests use an independently system-compressed noncubic grid to check byte order, all axes, origin, spacing and off-node interpolation.
These checks support this fixture's mapping; independent RT Dose export validation remains valuable before broadening support.

The public WC reader retains native x/z polygons at the filename's y coordinate and leaves marker/trailing records uninterpreted.
The existing validation generator now delegates its polygon reading to that public reader.
The experimental DVH calculation unions polygons belonging to one structure on each section, holds each section over a nearest-slice slab, samples a native-origin lattice commensurate with the first beam isocentre, and uses Shapely for point inclusion.
Only axial section orientation is supported.
Boundary inclusion is explicit because the rounded WC coordinates place sample points on polygon edges.
Histograms assign samples to half-open dose intervals `[k*w, (k+1)*w)` and place cumulative counts at their midpoints `(k+0.5)*w`, then linearly interpolate queries.
This replaces the initial nearest-integer assignment and brings all supplied Dx references within the shared 0.1 cGy tolerance.
The vendor help specifies dose intervals but not their precise bin coordinates; midpoint placement remains a fixture-supported inference pending held-out evidence.
Raw min/max/mean remain separate from binning, and interpolated Dx results are bounded by the raw extrema.
Optional conformity-volume sampling uses the same interval and cumulative-interpolation convention.
The [calculated-DVH comparison](../reports/vmat-2026-10-29.md) retains the unresolved OAR volume and raw-mean residuals and the independent boundary investigation.

The help's Frozen Dose topic describes saved dose becoming out of date after changes to patient models, CT-to-ED assignment, or relevant treatment-unit settings.
A commissioning audit must eventually distinguish requested settings, saved settings, calculation completion, and dose freshness.
Metadata checks compare saved settings; the experimental calculation separately samples the decoded saved dose.
Neither establishes current dose freshness.
C11 and independent exported RT Dose data remain required for stronger provenance and general mapping claims.
