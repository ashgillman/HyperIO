# Sources and reproducibility

The investigation used the two supplied files under `reference/` and the adjacent PlanCheck.jl checkout.
No external format specification or web source was needed for this initial map.
No runtime dependency on PlanCheck.jl was introduced.
The Python implementation was written separately around observed records and the mappings described below.

## Supplied plan archive

`reference/1~ZZZELEKTAONEHETERO.zip` is the immutable starting evidence.
The reader accesses selected text members directly.
During the first investigation, small copies of `plan`, `tel.1`, `.hyp`, `contournames`, and `info` were also placed under ignored `work/metadata/` for line-by-line inspection.
The original archive was not modified.

[reports/provenance.json](../reports/provenance.json) records the archive hash, inspected member hashes, input sizes, suffix counts, and the Python parser source hashes.
[reports/supplied-plans.json](../reports/supplied-plans.json) contains source filenames, raw values, line numbers, and diagnostics.
[reports/common-settings-check.json](../reports/common-settings-check.json) is an exercised saved-setting comparison against the explicitly observational example profile.

## Supplied help

`reference/Monaco.chm` was extracted with the Nix `p7zip` utility into ignored `work/help/`.
There are 1,784 extracted files, including 1,246 `.htm` topics indexed into `work/help-text/`.
Selected calculation logs, the reference checksum/normalization/comment records, and 256-byte native dose prefixes were also inspected directly.
The provenance report includes full log/checksum hashes and explicitly labelled dose-prefix hashes.
The HTML pages were read as local documentation; their scripts were not executed.
The text index omits figures and equations represented by images, so it is not a substitute for the original HTML when those matter.
The indexed topics were selected by searching calculation controls, uncertainty, electron density, layering, dose deposition, and saved-dose behavior, then reading the relevant full text.
Particle-specific and adaptive-only topics were not used as the general photon file specification.

| Topic | Exact CHM member | Why it matters |
|---|---|---|
| Calculation Properties dialog box | `usm1506019008231.htm` | UI grid units, deposition medium, force-water, uncertainty modes, couch dose, material lookup and Rx scope |
| Monte Carlo uncertainty formula | `usm1493663129001.htm` | Requested uncertainty and per-plan versus control-point behavior; no direct file-key mapping |
| Dose to Water versus Dose to Medium | `usm1493663145497.htm` | Separates transport medium from dose scoring and whole-patient force-water |
| Assign Densities dialog box | `usm1506018979724.htm` | Uniform density, fill and layering in QA plans |
| Structures Control: Layers Tab | `jap1518315983721.htm` | Overlap ownership, force/fill behavior, relative ED and original CT-derived values |
| Frozen Dose | `usm1493663137867.htm` | Why saved settings can differ from settings responsible for saved dose |
| About CT-to-ED Conversion Files | `usy1504705192560.htm` | Distinguishes table selection from conversion contents |
| Grid Volume group | `usm1506018963596.htm` | Potential independent UI checks of ED and dose/uncertainty grids |

Each of these original HTML members has a SHA-256 in the provenance report.
The help describes user-visible behavior and constraints, not the internal serialization keys.
The help package's relationship to the installed Monaco build remains unverified.

Rebuild the local help index with:

```sh
nix shell nixpkgs#p7zip --command 7z x -y -o./work/help reference/Monaco.chm
python3 scripts/index_help.py work/help work/help-text
rg -n -i 'uncertainty|dose grid|electron density|force.*water' work/help-text
```

Open the original extracted topic to inspect screenshots, diagrams, or equations.
Do not redistribute the vendor help or private source captures as part of a public package without establishing permission.

## PlanCheck.jl

The adjacent checkout is `/Users/gil/src/PlanCheck.jl` with remote `git@github.com:Townsville-Cancer-Centre/PlanCheck.jl.git`.
The independently checked HEAD was `6c6c00b8973430e5ab645c8191951db7cd8161a1` on `codex/structured-results-export`.
A narrow read-only Git subagent checked provenance and local state; the main session verified HEAD and the relevant diff state.
`src/monaco/` had no local changes relative to HEAD.
`src/checks/ROMP/5.3.jl` had local changes, so working-file hashes are recorded and HEAD alone is insufficient to reproduce all inspected report code.
The checkout had unrelated existing changes and was not edited.
No tracked LICENSE/COPYING file was found; this investigation does not assign a licence to that work.

| Source file | What informed this implementation |
|---|---|
| `src/monaco/raw.jl` | Row-width and numeric-shape matching approach; its false pattern entries are wildcards, not strict text-only requirements |
| `src/monaco/plan/hyperion.jl` | Named calculation directives, optional/missing values and multi-prescription isocentre caveat |
| `src/monaco/plan/plan.jl` | Patient/plan/studyset association, plan-specific density rows, old versus new density layouts, dose export boundary |
| `src/monaco/plan/tel.jl` | Beam-header anchors, offsets, algorithm-code mapping and machine identifiers |
| `src/monaco/studyset/contournames.jl` | Eight-value structure defaults, force/fill mode, layer and separate fill density |
| `src/monaco/studyset/info.jl` | CT-to-ED selection record |
| `src/checks/ROMP/5.2.jl` | Grid stored value interpreted in mm |
| `src/checks/ROMP/5.3.jl` | Uncertainty fraction interpretation and explicit unresolved choice of MC variance field |

The known uncertainty ambiguity was retained as an open question rather than converted into an assumed default.
Clinic-specific report thresholds and machine-to-energy dictionaries were not imported as generic library rules.

## Rebuild baseline reports

See also the Calculation Properties screenshot source record below for later UI-label evidence.

Run from the HyperIO project root:

```sh
PYTHONPATH=src python3 scripts/research_baseline.py 'reference/1~ZZZELEKTAONEHETERO.zip' \
  --help-chm reference/Monaco.chm --extracted-help work/help \
  --plancheck /Users/gil/src/PlanCheck.jl \
  --plancheck-head 6c6c00b8973430e5ab645c8191951db7cd8161a1
PYTHONPATH=src python3 -m hyperio check 'reference/1~ZZZELEKTAONEHETERO.zip' \
  examples/common-settings.json > reports/common-settings-check.json
python3 -m pytest -q
```

The revision argument records an investigator-checked value; the script does not itself verify Git state.
If the colleague checkout changes, verify and supply its actual current revision and retain the recorded working-file hashes.
Reports should be regenerated when parser source changes so source hashes continue to identify the code that produced the observations.

## Calculation Properties screenshots

On 23 October 2026, the user supplied `/Users/gil/Downloads/image (4).png` and `/Users/gil/Downloads/image (3).png` and explicitly identified their controls as the display names for DOSEGRIDSIZE and MCVARPERPLAN.
The screenshots show Grid Spacing (cm), Statistical Uncertainty (%), and the Per Control Point / Per Calculation mode selector.
Grid spacing is 0.10 cm in image (4) and 0.20 cm in image (3); both show uncertainty 0.50% and Per Control Point selected.
Patient, plan, and TPS build are not visible in these screenshots.
They establish UI wording and displayed state, without establishing native Boolean polarity or missing-key behavior.
Faithful copies are retained in ignored `reference/calculation-properties-2026-10-23/`.
`work/mppg9b-calculation-properties-provenance.json` records original paths, retained copy paths, and SHA-256 hashes.

| Source | SHA-256 |
|---|---|
| `image (4).png` | `451e67947ffbb76afe7fa5ebbf69384898a0abf044e323f1ec4125ac81eb0259` |
| `image (3).png` | `35a9a51dae5763c2b124099f3215942e8889e3861d671d152d7215282f47be78` |

## Beam setup screenshot and oblique-plan correction

On 23 October 2026, the user confirmed that the oblique plan should be 100 cm SAD and 90 cm SSD, checked in Monaco, and supplied `/Users/gil/Downloads/image (5).png`.
The screenshot shows the Beams table with Setup SSD and SSD 90.00 cm for the visible square-field rows.
It does not show the patient/plan name or SAD; the oblique-plan setup association and SAD come from the user's accompanying confirmation.
The conflicting oblique PDF SSD 100.00 cm is retained as a discrepancy in [the comparison report](../reports/tps-pdf-comparison.md).
A faithful copy is retained at `reference/calculation-properties-2026-10-23/image (5).png`.
SHA-256: `ae8e0853354f49acfe7f5fdb0dea495c1dd08c7d2c230c90a39943411fda19a6`.
`work/mppg9b-beam-setup-provenance.json` records the original and retained paths and hash.
