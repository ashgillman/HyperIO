# Controlled Monaco capture protocol

The next evidence should come from deliberate edits to copies of the supplied phantom cases.
Start with the reference `6X` plan and keep a separate baseline for `6F` where its behavior differs.
Record the installed Monaco version/build, calculation algorithm, plan type/mode, prescription ID, and machine identifier before testing.
The supplied file headers and the help package do not establish the installed application version.

## Generated candidate files

The [perpetual validation suite](../validation/README.md) tests Python-generated native files in Monaco.
Its stable component list is [TESTS.org](../validation/TESTS.org), and compatible checks share one patient and a small set of plans.
Restore one native patient, inspect the CT1 image control, then check Reference before interpreting the other profiles.
Generated contour transfer and plan-to-studyset associations require explicit review before calculation.
Collect initial settings together by plan, then collect persistence after saving/closing/reopening the patient once.

The catalogue retains individual test IDs even where one profile tests grid, uncertainty, deposition and density settings together.
Record companion changes and interactions; if a combined profile fails or attribution is ambiguous, add a focused follow-up without replacing the existing IDs or evidence.
Keep initial-load, save/reopen and calculated returns separate.
The ledger appends scoped observations rather than resetting each time imports are regenerated.

The C-series below is a reference protocol for optional targeted UI captures, not a demand for a separate import per component.
Use it when a grouped suite result leaves a specific mapping unresolved.

## Capture procedure

1. Create an independent phantom patient/studyset copy for the experiment when a studyset-level change could affect sibling plans.
   Keep a stable exported relative directory layout between before/after captures.
2. Save and close the baseline plan so the captured files are stable.
   Export or copy the complete patient directory; preserve the exact original export.
3. Record the exact UI value, units, checkbox state, active prescription, calculation state, and relevant structure list in a screenshot and capture log.
4. Change one control only, record its old and new values, and note whether Monaco automatically recalculates, removes dose, or freezes another plan.
5. If available, capture a saved state before recalculation and a separate state after calculation completes and the plan is saved/closed again.
   If Monaco combines the actions, record that limitation explicitly.
6. Make content snapshots and compare every changed file, including hashes for binary files.
   Repeat an unchanged save control and reverse the setting to its original value to distinguish the setting from incidental save effects.
7. Reopen the changed plan and verify the UI value persisted.
   For geometry/dose work, also retain DICOM RT Plan, RT Structure Set, RT Dose, CT exports, and a plan/calculation report when available.

Do not discard timestamp, log, UUID, checksum, or dose changes until unchanged-save controls show which changes occur independently of the edited setting.
The snapshot tool ignores filesystem timestamps but retains timestamp text inside file contents.
A binary hash difference shows that bytes changed; it does not explain their meaning.
The existing six plans have several simultaneous differences and cannot substitute for this procedure.

## Experiment matrix

| ID | Priority | One change / paired capture | What to inspect | Acceptance evidence |
|---|---|---|---|---|
| C00 | First | No edit: reopen/save; separately recalculate/save with identical settings | Every file, especially plan dates, `.xlog`, checksums, status, dose payloads | Repeated controls characterize incidental changes and stochastic dose differences |
| C01 | First | Grid spacing `0.10 cm → 0.20 cm`, same algorithm and uncertainty | `DOSEGRIDSIZE`, plan grid metadata, dose sizes; compare exported dose grid spacing | UI, stored value, and independent dose-grid spacing establish units and scale; reverse restores setting |
| C02 | First | Hold uncertainty mode fixed; displayed `1.00% → 2.00%` for `6X` | Both MCVARIANCE and MCSEGMENTVARIANCE, other directives, logs/status | Distinguish fraction from squared variance by measured stored response; repeat in `6F` after baseline |
| C03 | First | Per Control Point ↔ Per Calculation; record displayed value before/after switching | Presence/value of MCVARPERPLAN and both MC values; save before/after calculation | Mode mapping and default/absence behavior observed; both modes must be captured, not inferred from missing key |
| C04 | First | Dose deposition Medium ↔ Water with force-water off | DOSETOMEDIUM, FORCEWATER, status/checksum/dose changes | Isolated deposition flag mapping; distinguish setting save from automatic recalculation |
| C05 | First | Force entire patient to water off ↔ on, where permitted by selected algorithm/mode | FORCEWATER, DOSETOMEDIUM, density UI and dose state | Establish flag behavior and dependencies; record any disabled control or automatic companion change |
| C06 | Next | Insert forced relative ED `1.000 → 1.100`; separately override disabled ↔ enabled | Plan five-value rows, studyset eight-value rows, `.WC`, timestamps, saved siblings | Locate value and activation code; determine whether UI action edits plan, studyset, or both |
| C07 | Next | Force ED ↔ Fill ED, then change only the minimum/fill value | Mode code, both density slots, overlaps and ED display | Distinguish inactive stored values, force, and minimum-fill semantics; screenshot the exact labels/units |
| C08 | Next | Move Insert by one layer; use two overlapping structures with distinct forced values | Layer fields in both representations, order, ED cursor values in overlap | Verify numeric layer direction and voxel ownership independently of record order |
| C09 | Next | Select a second known CT-to-ED table without altering its contents | `info` selection, table path/content/hash, saved-dose state of active and sibling plans | Resolve selection-to-table linkage; obtain both actual clinic tables and establish freshness effects |
| C10 | Later | Change algorithm for a separate valid simple-beam copy; record any coupled machine change | `tel.1` algorithm code, `.hyp` engine references, relevant UI/report | Confirm code mapping, per-beam/per-Rx scope and invalid combinations; no inference from engine availability |
| C11 | Next | Save calculated baseline; change one relevant studyset property; capture retained/frozen dose and then recalculate | GUI.STATUS, checksum.1, `.xlog`, `plan`, dose files, UI frozen-dose indication | Identify reliable current/frozen/missing/calculation-complete evidence and false-positive cases |
| C12 | Later | Add a second prescription with distinct labelled settings | `rx*plan`, `rx*tel.1`, `*_rx*.hyp`, comments, active prescription, beam isocentres | Associate each file with the correct Rx and expose shared versus per-Rx settings without ambiguity |
| C13 | Later | Store/display couch dose off ↔ on; separate couch inclusion change | STORECOUCHCOILDOSE, beam treatment-aid records, dose extents | Keep dose-storage behavior distinct from couch attenuation/inclusion |
| C14 | Later | QA material lookup Patient ↔ Phantom where available | ISPHANTOMMATERIAL and other changed records, algorithm and plan mode | Test candidate lookup key without relying on its name; document unavailable combinations |

The help describes grid settings as shared across Rx IDs and uncertainty as prescription-specific in relevant modes.
C12 must verify how that behavior appears in saved files for the actual installed version.
Numeric values above are experiment labels, not recommended commissioning tolerances or clinical settings.
The fill dialog and Layers tab use potentially inconsistent density wording in the supplied help, so retain the actual UI label and units in the evidence.

## Minimal next capture set

For the highest-value next session, collect C00, C01, C02, and C03 from one independent phantom copy.
That means an unchanged save, an unchanged recalculation, a grid-only change, an uncertainty-value-only change, and an uncertainty-mode-only change.
Capture before/after exports and Calculation Properties screenshots, with the installed version/build recorded once.
This resolves the immediate grid and uncertainty audit ambiguities before expanding to other record types.

## Capture log template

Create one directory per experiment, for example `work/captures/C01-grid/`.
Keep `capture.json`, `before/`, `after-save/`, `after-calc/`, and screenshots together, using only stages that actually exist.

```json
{
  "experiment": "C01",
  "monaco_version_build": "record exact About dialog value",
  "plan_id": "record exact identifier",
  "studyset_id": "record exact identifier",
  "prescription_id": "record exact identifier",
  "plan_mode": "record Planning or QA",
  "algorithm": "record exact UI label",
  "machine_id": "record exact identifier",
  "control": "Calculation Properties / Grid Spacing",
  "before": {"value": 0.10, "unit": "cm"},
  "after": {"value": 0.20, "unit": "cm"},
  "actions": ["record the actual sequence, including automatic recalculation"],
  "dose_state_before": "record the observed state",
  "dose_state_after": "record the observed state",
  "screenshots": [],
  "independent_exports": [],
  "notes": "record other automatic changes or deviations"
}
```

Use `hyperio snapshot` and `hyperio diff` as shown in the README.
Keep the snapshot output outside the directory being snapshotted.
If the original archive contains an enclosing patient directory, preserve that same enclosing directory for both stages.
Snapshot files contain complete small text records and should be handled with the same access restrictions as the source exports.

## Promoting a mapping into supported behavior

A candidate mapping needs an isolated change with labelled UI evidence, an unchanged-save control, reversal or repetition, and a held-out capture.
Add synthetic tests for missing, malformed, duplicate, unsupported-version and conflicting-source cases.
Keep local source fixtures immutable and record SHA-256, version/build, experiment ID, UI truth, and scope.
Use a new saved plan or second studyset as the held-out case, not another value used to choose the mapping.
For a numeric conversion, confirm at least two distinct changed values as well as the baseline.
For booleans/modes, observe every supported state and explicitly test absence.

Independent DICOM exports should validate geometry, units, beam identities, dose grid axes, scaling, and relevant prescription associations.
A proposed native writer needs byte-preserving round trips plus Monaco load/save/recalculation and independent export comparisons before it can support a write-back claim.
A saved-setting match alone cannot validate calculation completion or dose freshness.

## Loading evidence, 2026-10-24

The supplied Monaco help topic `eww1554753273916.htm` states that studysets with fewer than five cross-sections do not open.
The earlier three-slice candidate was below that documented minimum and must not be used as a valid loading control.
The new 100-slice zero-CT candidate exceeds it, but the supplied log instead reports missing `.rtDir` depot metadata; CT pixel/geometry acceptance is still unverified.
See the retained log and interpretation in `validation/results/history/ct-001-zero-5mm/roundtrips/import-log-2026-10-24/`.
