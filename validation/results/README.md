# Observation history

`events.jsonl` is the perpetual append-only results register.
Each line records a scoped observation, not a global declaration that the software is validated.
Several components can use the same patient archive, screenshots and test session.
The phase distinguishes initial load, returned-file checks, save/reopen and calculation.
Unknown and unreviewed states are never converted to pass.

Historical CT import success under `zzzInputOutputAG2` is recorded alongside the failed earlier depot attempt.
It does not pass a fresh generated suite's native restoration or plan-association tests.
Historical worksheets, logs and returned captures are preserved under ignored `history/`.
The canonical native CT return is retained at `reference/native-zero-ct/1~zzzInputOutputAG2.zip`.

Use `hyperio record-review` to append completed structured observations without duplicating unchanged rows.
Record corrections as new observations; keep earlier evidence intact.

`partial-review-checkpoint.json` transcribes Ashley Gillman's partial Monaco 6.2.3.0 Markdown review for run `hyperio-tps-8ccb9f90b45ee0d9`.
It preserves all 53 worksheet rows, including 38 not_reviewed rows; only the 15 completed observations were appended to the register.
The original row profile is retained even where a note explicitly describes other plans, with scope qualifications in messages and the analysis report.
Blank actual cells marked pass remain human attestations, and the unresolved observed-at date is not silently corrected.
The exact Markdown snapshot and SHA256 are identified in the checkpoint; the original generated worksheet remains editable for continued review.
See [the analysis and information-value priorities](../../reports/tps-partial-review-analysis.md) before counting duplicate grouped rows as remaining experiments.

`native-return-2026-10-27.json` records the subsequent native-file comparison of the four calculated Phantom candidates.
Reference and both Density plans were intentionally not calculated and receive no inferred calculation result.
The source ZIP and all member hashes are identified in [the return analysis](../../reports/native-suite-return-2026-10-27.md).
Catalogue revision 2 adds CALC-RETURN to record completion/payload evidence without equating it with numerical dose validation, and extends EXPORT-DOSE revision 2 to named calculated profiles.
The current generated worksheet/package remains at its original revision; no human review has been overwritten.
