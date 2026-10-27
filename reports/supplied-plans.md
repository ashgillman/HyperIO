# Supplied phantom archive: initial observations

Generated from the supplied local archive by `scripts/research_baseline.py`.
These are saved settings interpreted using the initial format profile; UI confirmation is pending.
The independent source hashes are in [provenance.json](provenance.json).

The archive contains 5,735 files and 2,162,402,099 uncompressed bytes.
It contains 6 plans and 6 studysets.

| Plan | Primary studyset | Grid, raw | MCVARIANCE | MCSEGMENTVARIANCE | Insert uniform ED | Beams |
|---|---|---:|---:|---:|---:|---:|
| HDHeteroSq6F | PinpointBone | 1.0 | 0.005 | 0.005 | 1.606 | 3 |
| HDHeteroSq6X | SemiflexBone | 1.0 | 0.01 | 0.01 | 1.606 | 3 |
| LDHeteroSq6F | PoinpointLung | 1.0 | 0.005 | 0.005 | 0.283 | 3 |
| LDHeteroSq6X | SemiflexLung | 1.0 | 0.01 | 0.01 | 0.283 | 3 |
| RefHeteroSq6F | PinpointWater | 1.0 | 0.005 | 0.005 | 1 | 3 |
| RefHeteroSq6X | SemiflexWater | 1.0 | 0.01 | 0.01 | 1 | 3 |

All six plans store DOSETOMEDIUM=1, FORCEWATER=0, STORECOUCHCOILDOSE=0, and ISPHANTOMMATERIAL=0.
MCVARPERPLAN is absent in all six .hyp files; uncertainty mode remains unknown.
All linked studysets name RoutineSep21 as their CT-to-ED selection; the conversion table itself is absent.
Each plan has beam descriptions 3x3, 5x5, and 10x10, with algorithm code 6.
Beam names are labels; aperture dimensions, energy, control points, MU, and dose are not independently established.
The 6F machine identifier is Agility6MVFFF; the 6X identifier is Agility6MV2017.
The supplied studyset spelling PoinpointLung is preserved literally.

Grid values are interpreted as mm by PlanCheck; the help displays cm.
The two MC values are provisionally interpreted as uncertainty fractions, not squared variances.
Confirm both interpretations with controlled UI captures before relying on unit conversions.

The plan density table can override studyset defaults and uses a different field order.
For example, RefHeteroSq6X stores Insert at layer 9, while the other five plans store it at layer 2.
All plans store forced uniform ED 1.0 for Patient; the Insert values are shown above.
Layer precedence and the resulting voxel density map still require independent confirmation.

Calculation logs contain mcStdDev values, labelled per-segment and entire-calculation uncertainties, and completion messages.
For RefHeteroSq6X, the log records mcStdDev 0.01, each-segment uncertainty 1 percent, and entire-calculation uncertainty 0.69 percent.
These log observations are separate from saved settings and have not been proven to describe the current dose payload.

The existing plans differ in several respects and are observational examples, not isolated experiments.
Presence of native dose files is not proof that their dose reflects these settings.
See [the controlled capture protocol](../docs/experiments.md) for the next evidence to collect.
