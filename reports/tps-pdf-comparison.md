# Selected 6X TPS PDF comparison

On 23 October 2026, the current reader was compared against three independently supplied TPS PDF exports from Monaco 6.2.3.0.
The PDFs identify patient `zzzElektaONE_6X` and studyset `WaterPhantomL`.
Each was matched to the corresponding full path under `1~zzzElektaONE_6X/plan/` in the supplied archive.
Document content was used as evidence, not as instructions to perform clinical or administrative actions.

| Plan | PDF pages | Beams | Beam-value comparisons | Setting comparisons | Mismatches |
| --- | ---: | ---: | ---: | ---: | ---: |
| 05OI10x10S090 | 31 | 13 | 130 | 6 | 0 |
| 06ASYMMS100 | 448 | 4 | 40 | 6 | 0 |
| 07SHAPEDGroin | 444 | 2 | 20 | 6 | 0 |

All 208 comparisons matched within the stated display precision.
These are selected field comparisons, not 208 independent experiments or a complete plan validation.
Beam summary rows were extracted using Poppler layout text and matched by one-based beam order, with field ID and description checked as values.
Exact equality was used for strings.
Numeric beam comparisons allowed half the last displayed decimal unit plus floating-point slack.
Setting comparisons used explicit unit conversion with a 1e-10 numerical tolerance.
Disposable negative controls changed one extracted gantry value and one PDF patient identity.
The comparison detected exactly one mismatch for the altered gantry and rejected the wrong-patient text; the retained baseline still has 208 matches.
First beam-summary pages from all three PDFs, the oblique plan/settings pages, and the first groin segment-details page were rendered and visually inspected.
The remaining extracted tables were not individually visually reviewed.

## Supported observations

For each of the 19 beams, field ID, description, treatment unit, machine ID, gantry, couch, collimator, and all three isocentre coordinates agree.
The native isocentre coordinates divided by 10 agree with the printed Monaco coordinates in centimetres.
This supports a millimetre interpretation for these native coordinate fields in these fixtures, without establishing a DICOM or patient-coordinate transformation.
The oblique gantry series is 330, 335, 340, 345, 350, 355, 0, 5, 10, 15, 20, 25, and 30 degrees.
All couch and collimator angles are zero; these cases cannot distinguish competing positional mappings or validate nonzero rotations.

Plan Report pages are 18–19 for oblique, 9–10 for asymmetric, and 7–8 for groin.
In each plan, raw DOSEGRIDSIZE 2 agrees with printed grid spacing 0.20 cm, supporting millimetres for this saved setting.
DOSETOMEDIUM=true agrees with Medium; FORCEWATER=false agrees with No; STORECOUCHCOILDOSE=false agrees with No.
Both MCVARIANCE and MCSEGMENTVARIANCE are 0.005 and numerically agree with printed Statistical Uncertainty (%) per Control Point 0.50.
Because the native uncertainty directives are equal, this does not establish which directive controls that display or how the absent MCVARPERPLAN flag determines calculation mode.
The printed per-control-point label is evidence of the reported mode; the reader still cannot recover that mode independently from these native records.

## Matching and representation details

The user confirmed on 23 October 2026 that the oblique plan should use 100 cm SAD and 90 cm SSD, checked in the Monaco interface.
This is the user-confirmed intended setup for the oblique plan.
The PDF Beam Summary nevertheless prints Setup SSD and SSD 100.00 cm for every beam.
That printed value is an unresolved discrepancy against the confirmed setup, not authoritative evidence that the intended SSD is 100 cm.
SSD was outside the 208 comparisons and is not validated by their agreement.
The additional screenshot `image (5).png` visibly shows Setup SSD and SSD 90.00 cm for the displayed beams.
Its visible descriptions are square fields (1x1, 2x2, etc.), and no patient/plan name or SAD value is visible; it does not independently identify the oblique plan or display its 100 cm SAD.
Keep the user's oblique-plan confirmation, screenshot observations, and conflicting PDF value distinct until the corresponding beam records and report generation behavior have been checked.
The first two oblique beams both have Field ID 2 in the PDF and native records.
Field IDs must not be treated as unique beam identifiers.

Groin Beam Summary page 1 reports positive jaw magnitudes, including Width1 2.10 / X1 and Length2 20.00 / Y1 for beam 1.
Segment Details page 9 reports the corresponding signed values -2.10 / X1 and -20.00 / Y1.
Labels, signs, and report type must be retained when using these as geometry expectations.
Groin Segment Details pages 9–11 contain 80 indexed leaf rows for each of the two beams, with Y/X1/X2 columns.
This provides useful independent evidence for later aperture and leaf-position reader work.
Beam Summary reports zero segments while Segment Details presents a static segment labelled 1; preserve the distinct report meanings rather than assuming either is a parser error.

## Provenance and reproducibility

Original source PDFs are in `/Users/gil/Downloads/`, with filenames supplied in the chat.
They were not changed.
Full extracted text, representative rendered pages, and the fixture-specific comparison helper are retained under ignored `work/mppg9b-pdfs/`.
`work/mppg9b-pdfs/comparison.json` records PDF paths and SHA-256 hashes, native plan/tel/hyp member hashes, current reader/helper hashes, source member/line references, PDF page references, literal values, conversions, tolerances, and per-value results.
The comparison helper calls the current inspect_export implementation rather than relying on the earlier cached inspection JSON.
Run from the project root with `PYTHONPATH=src python3 work/mppg9b-pdfs/compare.py` after regenerating layout text with `pdftotext -layout` if source PDFs change.
The original 8 GB ZIP was not fully hashed or CRC-tested in this comparison; selected metadata members were hashed.

## Remaining validation boundary

This comparison exercises the existing reader API; it does not add jaw, MLC, MU, SSD, or dose-array interpretation.
The PDF-reported jaw/MLC/MU values have not yet been compared with parsed native values.
Density overrides, CT-to-ED table contents, dose scaling/axes, saved-dose freshness, nonzero couch/collimator transforms, and native writing remain unresolved.
PDF approval labels describe source document state and do not establish human review or approval of HyperIO.
The 6FFF plans have no corresponding independently compared PDF here.
No native files were edited or recalculated, and no clinical acceptance or MPPG protocol coverage was inferred.
