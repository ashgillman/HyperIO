# CT-to-ED selection diagnostic investigation — 5 November 2026

## Status and scope

The CT-to-ED selection reader remains unresolved for the user's seven-plan batch.
Commit `5c7b55d` makes this diagnostic a WARN for reconstruction from saved dose, retaining the diagnostic while allowing export when required inputs are valid.
This change does not establish that the metadata was absent, fix the metadata parser, or establish the validity/freshness of the saved dose.
No source `info` file from the failing studyset was supplied in this investigation.

## Evidence supplied

The user supplied a schema-version-1 anonymised JSON support report from the original failure, before severity fields were added.
The report identifies Windows, Python 3.14.3 and HyperIO as `source checkout`; it does not identify the installed TPS release or exact HyperIO revision.
Its native file-version values are serialization identifiers, not evidence of a particular TPS release.
The original attachment is local to the Codex chat at `/Users/gil/.codex/attachments/18b90a6d-7cbc-4490-904f-f8bfacd1aba8/Pasted text.txt` and may not be available to a future agent.
The useful findings are preserved here without copying source identifiers or native records:

- The report inventories 223 relevant files, 34 studysets, 18 plans and seven attempted batch outcomes.
- All 34 studyset `info` files have version `00241016`; all corresponding `contournames` files have version `00121027`.
- Thirty-three studysets report `ct_to_ed_selection_absent_or_ambiguous`; `studyset_001` has no inspection diagnostics.
- Seventeen plans have only the CT-to-ED diagnostic.
- `plan_007` additionally reports `hyp_file_count_mismatch` and `no_supported_beam_headers`; it was not among the seven attempted outcomes.
- Attempted plans `plan_001` through `plan_006`, plus `plan_009`, all link to `studyset_002`.
- All seven outcomes failed with only `ct_to_ed_selection_absent_or_ambiguous` reported.
- These are metadata inspection/outcome findings, not proof that later dose/contour calculation checks would pass after the blocker is removed.

## What the reader actually expects

`study_metadata` in `src/hyperio/core.py` reads the selected conversion **name** from the studyset's `info` file.
It does not search for the numerical HU-to-electron-density conversion table in the plan.
For accepted `info` versions `00271016` and `00241016`, it searches for exactly one sequence matching:

1. One scalar numeric line.
2. Three non-empty, non-numeric, single-field text lines.
3. Thirteen scalar numeric lines.

The first of the three text lines is returned as `ct_to_ed_name`.
The surrounding identity fields are part of the recognition heuristic even though only the curve name is extracted.
Zero matches and multiple matches both produce the same diagnostic.
Consequently, the diagnostic does not distinguish absent selection, a different surrounding record layout, numeric/blank identity fields, or multiple candidate anchors.

## Reproduced parser limitation

A synthetic check using the actual `_shape` and `_numbers` helpers found one match with text identity fields, but zero matches when an adjacent field was changed to a numeric identifier while retaining the curve name.
This demonstrates a possible false negative; it does **not** establish that the user's failing files contain numeric identifiers.

```python
from hyperio.core import _shape, _numbers

lines = ["00241016", "0", "CalibrationName", "PHANTOM", "Study"] + ["0"] * 13

def matches(lines):
    return [i for i in range(len(lines))
            if _shape(lines, i, [1, None, None, None] + [1] * 13)
            and all(lines[i + j].strip() and _numbers(lines[i + j]) is None
                    for j in (1, 2, 3))]

assert len(matches(lines)) == 1
lines[3] = "123456"
assert len(matches(lines)) == 0
```

## Selected name versus conversion contents

The previously inspected archives stored a selected curve name in studyset `info`, while the conversion table itself was outside the patient archive; see `docs/format-notes.md`, CT-to-ED discussion.
The earlier CellIrrad investigation also successfully read CT-to-ED selection metadata with `info` version `00241016`; see `reports/unity-dvh-2026-11-05.md`.
The new report itself contains one diagnostic-free studyset with that same format version.
These observations argue against assuming that every file of this version omits the selected curve name.
They do not establish where this particular TPS installation stores the numerical table, or whether the failing studysets contain a selection.

## Next investigation

Obtain a de-identified `info` file from failing `studyset_002`, ideally alongside the passing `studyset_001` file.
Preserve line order, blank lines, delimiters, record lengths and whether each identity/name field is numeric or text when de-identifying.
Replacing a numeric identifier with an alphabetic placeholder could hide the demonstrated failure mode.
Compare candidate anchors and determine whether the actual failure is zero matches or multiple matches before adjusting the parser.
Use a failing regression based on the confirmed layout, then test numeric and blank identity fields, duplicate candidates, and truncated/malformed records.
Do not simply select the first candidate or infer an effective conversion curve from a name.
Keep the saved-dose DVH warning policy independent of whether CT-to-ED metadata extraction is subsequently fixed.
