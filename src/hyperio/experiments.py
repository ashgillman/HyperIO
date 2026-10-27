"""Generate isolated native-file candidates for user review in Monaco.

This profile targets the supplied RefHeteroSq6X static-beam fixture.
Generation and read-back are not evidence that Monaco accepts an edit.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil

from .core import Export, FormatError, HypDocument, beam_headers, inspect_export, plan_metadata


PLAN_NAME = "RefHeteroSq6X"


def _positive_ed(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0.01 <= value <= 15:
        raise ValueError("experimental relative ED must be finite and between 0.01 and 15")
    return format(value, ".17g").encode("ascii")


def _patch_token(data: bytes, line: int, token: int, replacement: bytes) -> bytes:
    """Patch a single comma-delimited token, retaining surrounding whitespace."""
    rows = data.splitlines(keepends=True)
    raw = rows[line - 1]
    ending = b"\r\n" if raw.endswith(b"\r\n") else b"\n" if raw.endswith(b"\n") else b"\r" if raw.endswith(b"\r") else b""
    body = raw[:-len(ending)] if ending else raw
    fields = body.split(b",")
    if not 0 <= token < len(fields):
        raise FormatError("token index outside record")
    match = re.fullmatch(rb"([ \t]*)(.*?)([ \t]*)", fields[token])
    assert match is not None
    fields[token] = match[1] + replacement + match[3]
    rows[line - 1] = b",".join(fields) + ending
    return b"".join(rows)


def edit_plan_density(data: bytes, structure: str, *, uniform_ed=None, mode=None, fill_ed=None) -> bytes:
    """Edit the observed five-value plan table only; studyset defaults are separate."""
    records = plan_metadata(data, "<candidate-plan>")["density_overrides"]
    matches = [r for r in records if r["name"] == structure]
    if len(matches) != 1:
        raise FormatError(f"expected one plan density record for {structure!r}")
    line = matches[0]["source"]["line"]
    edited = data
    for index, value in ((2, uniform_ed), (3, fill_ed)):
        if value is not None:
            edited = _patch_token(edited, line, index, _positive_ed(value))
    if mode is not None:
        if type(mode) is not int or mode not in (1, 2, 3):
            raise ValueError("density mode must be 1, 2, or 3")
        edited = _patch_token(edited, line, 0, str(mode).encode("ascii"))
    return edited


def _edit_study_density(data: bytes, line: int, value) -> bytes:
    rows = data.splitlines()
    if not rows or rows[0] != b"00131027" or len(rows[line - 1].split(b",")) != 8:
        raise FormatError("unsupported studyset density record")
    return _patch_token(data, line, 1, _positive_ed(value))


def edit_static_aperture(data: bytes, field_id: str, probe: str) -> bytes:
    """Two deliberately isolated probes of competing static aperture records.

    Header rows and leaf positions are not claimed to be a complete beam writer.
    The other compact shape representation is left intact to test precedence.
    """
    beams = beam_headers(data, "<candidate-tel>")
    matches = [b for b in beams if b["field_id"] == field_id]
    if len(matches) != 1 or matches[0]["description"] != "10x10":
        raise FormatError("aperture probes require the unique labelled 10x10 beam")
    start = matches[0]["source"]["line"] - 1
    rows = data.splitlines()
    boundaries = [b["source"]["line"] - 1 for b in beams if b["source"]["line"] - 1 > start]
    end = min(boundaries, default=len(rows))
    if start + 167 >= end:
        raise FormatError("static aperture block is truncated")
    for offset in (16, 18):
        try:
            numbers = [float(v) for v in rows[start + offset].split(b",")]
        except ValueError as exc:
            raise FormatError("invalid static aperture header") from exc
        if numbers != [100, 100, 0, 0]:
            raise FormatError("aperture probe expects both original 100,100,0,0 headers")
    try:
        leaf_rows = [r.split(b",") for r in rows[start + 151:start + 167]]
        if len(leaf_rows) != 16 or any(len(r) != 10 for r in leaf_rows):
            raise FormatError("expected sixteen rows of ten leaf values")
        values = [float(v) for row in leaf_rows for v in row]
    except ValueError as exc:
        raise FormatError("invalid leaf-position table") from exc
    expected = [n for i in range(80) for n in ((-50, 50) if 28 <= i <= 51 else (-20, 20))]
    if values != expected:
        raise FormatError("leaf table differs from the supplied static 10x10 profile")
    edited = data
    if probe == "rectangle-header":
        for offset in (16, 18):
            edited = _patch_token(edited, start + offset + 1, 0, b"80")
            edited = _patch_token(edited, start + offset + 1, 1, b"60")
    elif probe == "leaf-notch":
        # One-based leaf pairs 37..44, bank represented by each pair's second value.
        for leaf in range(36, 44):
            index = leaf * 2 + 1
            edited = _patch_token(edited, start + 151 + index // 10 + 1, index % 10, b"10")
    else:
        raise ValueError(f"unknown aperture probe {probe!r}")
    return edited


def _case(case_id, title, operation, expected, checks):
    return {"id": case_id, "title": title, "operation": operation, "expected_observation": expected,
            "review_checks": checks, "validation_status": "generated_candidate_not_reviewed_in_Monaco"}


CASES = [
    _case("V00-original", "Original plan control", "original",
          "Original phantom plan, three square beams and its original saved dose. No file contents changed.",
          ["The original RefHeteroSq6X plan opens normally.", "Record Monaco version/build and baseline Calculation Properties."]),
    _case("V01-no-dose-control", "Control with saved dose and historical log omitted", "no-dose",
          "Same settings and geometry as V00; no native dose payloads or historical calculation log are supplied.",
          ["Record whether Monaco accepts missing dose files, and any message or displayed dose state.",
           "All three beam shapes, uncertainty controls, and density settings should otherwise match V00."]),
    _case("V02-mcvariance-only", "MCVARIANCE only to 0.02", "mcvariance",
          "Only MCVARIANCE changes from 0.01 to 0.02; MCSEGMENTVARIANCE stays 0.01. UI response is an open question.",
          ["Record displayed uncertainty and mode before making any UI edit.", "Does it show 1%, 2%, another value, or reject the plan?"]),
    _case("V03-mcsegment-only", "MCSEGMENTVARIANCE only to 0.02", "mcsegment",
          "Only MCSEGMENTVARIANCE changes from 0.01 to 0.02; MCVARIANCE stays 0.01. UI response is an open question.",
          ["Record displayed uncertainty and mode before making any UI edit.", "Compare directly with V02."]),
    _case("V04-uncertainty-both", "Both uncertainty values to 0.02", "mc-both",
          "Both stored uncertainty values are 0.02; candidate UI expectation is 2.00%. No mode flag is inserted.",
          ["Record uncertainty value and mode.", "After initial review, save/reopen and retain the resulting native files."]),
    _case("V05-grid", "Stored dose-grid value 1 to 2", "grid",
          "Candidate expected grid spacing is 0.20 cm / 2 mm; all uncertainty settings stay at baseline.",
          ["Record exact displayed grid value and units.", "Record whether Monaco requests or performs recalculation."]),
    _case("V06-ed-plan-only", "Insert plan override to 1.100", "ed-plan",
          "Plan-specific Insert forced ED is 1.100; studyset default stays 1.000. This tests source precedence.",
          ["Record the plan density override and studyset Layers value separately.", "Record any reconciliation or warning on load/save."]),
    _case("V07-ed-studyset-only", "Insert studyset default to 1.200", "ed-study",
          "Studyset Insert forced ED is 1.200; plan-specific Insert stays 1.000. Which value Monaco presents is an open question.",
          ["Record both density views, active override flags, and any frozen-dose indication.", "Do not copy this studyset file into a shared baseline between cases."]),
    _case("V08-ed-both", "Insert plan and studyset ED to 1.100", "ed-both",
          "Both Insert density representations contain forced ED 1.100.",
          ["Check the displayed value in both views.", "Compare acceptance and displayed values with V06 and V07."]),
    _case("V09-ed-disabled", "Disable Insert plan density override", "ed-disabled",
          "Plan Insert mode changes from forced (2) to none (1); stored values remain 1.000. Studyset defaults remain forced.",
          ["Record which override checkbox/value Monaco shows.", "This tests the plan mode and precedence; no voxel-density result is assumed."]),
    _case("V10-ed-fill", "Plan Insert fill mode at 0.800", "ed-fill",
          "Plan Insert mode is filled (3), minimum/fill ED is 0.800, and the inactive uniform value remains 1.000.",
          ["Check Force/Fill flags and exact displayed value/units.", "Record whether Monaco retains, rejects, or normalizes the combination."]),
    _case("V11-dose-to-water", "Dose deposition medium to water", "dose-water",
          "DOSETOMEDIUM changes to 0 with FORCEWATER still 0; candidate UI expectation is dose deposition to water.",
          ["Check deposition selection and force-water checkbox separately.", "Record any automatic change to companion settings."]),
    _case("V12-rectangle-header", "10x10 beam aperture-header probe: 80 by 60", "rectangle-header",
          "For field ID 2 (still labelled 10x10), both four-value aperture headers change from 100,100,0,0 to 80,60,0,0. Leaf and compact shape records stay original.",
          ["Candidate field-dimension expectation is 8 by 6 cm; record actual dimensions and BEV appearance.",
           "Does Monaco use these headers, normalize them, or keep a 10 by 10 cm aperture? The unchanged label is intentional."]),
    _case("V13-leaf-notch", "10x10 beam leaf-position notch probe", "leaf-notch",
          "For field ID 2, second-bank tips of leaf pairs 37 through 44 change from +50 to +10 mm. Aperture headers and compact shape records stay original.",
          ["Candidate expectation is a notch over eight central leaf pairs on the corresponding bank side; record BEV and leaf positions.",
           "A 5 mm pitch would make the notch 40 mm tall and 40 mm deep; orientation and use of this table need confirmation.",
           "If the BEV stays square, retain the saved native plan so the competing shape representation can be investigated."]),
]


CASES += [
    _case("V14-force-water", "Force-water flag enabled", "force-water",
          "FORCEWATER changes from 0 to 1; DOSETOMEDIUM remains 1. Record any coupled UI change.",
          ["Record force-water checkbox, dose deposition setting and effective density display.",
           "Retain separate saved and recalculated captures if accepted."]),
    _case("V15-mode-zero", "Insert MCVARPERPLAN=0", "mode-zero",
          "Insert the previously absent MCVARPERPLAN directive with value 0; both uncertainty values remain 0.01.",
          ["Record Per Control Point / Per Calculation mode and uncertainty value.",
           "Compare against absent-flag V01 and value-1 V16; record rejection or normalization."]),
    _case("V16-mode-one", "Insert MCVARPERPLAN=1", "mode-one",
          "Insert the previously absent MCVARPERPLAN directive with value 1; both uncertainty values remain 0.01.",
          ["Record Per Control Point / Per Calculation mode and uncertainty value.",
           "Retain the saved .hyp to establish flag polarity and persistence."]),
]


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _hash_path(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _patches(operation, original, plan_file, hyp_file, tel_file, contour_file, contour_line):
    changes = {}
    hyp_changes = {"mcvariance": {"MCVARIANCE": 0.02}, "mcsegment": {"MCSEGMENTVARIANCE": 0.02},
                   "mc-both": {"MCVARIANCE": 0.02, "MCSEGMENTVARIANCE": 0.02},
                   "grid": {"DOSEGRIDSIZE": 2}, "dose-water": {"DOSETOMEDIUM": False},
                   "force-water": {"FORCEWATER": True}}
    if operation in hyp_changes:
        doc = HypDocument(original[hyp_file], hyp_file)
        for key, value in hyp_changes[operation].items():
            doc = doc.with_value(key, value)
        changes[hyp_file] = doc.to_bytes()
    if operation in ("mode-zero", "mode-one"):
        doc = HypDocument(original[hyp_file], hyp_file)
        if doc.get("MCVARPERPLAN") is not None:
            raise FormatError("mode probes require absent baseline MCVARPERPLAN")
        anchor = doc.get("MCSEGMENTVARIANCE")
        rows = original[hyp_file].splitlines(keepends=True)
        newline = b"\r\n" if rows[anchor.line - 1].endswith(b"\r\n") else b"\n"
        rows.insert(anchor.line, b"!MCVARPERPLAN    " + (b"0" if operation == "mode-zero" else b"1") + newline)
        changes[hyp_file] = b"".join(rows)
    if operation in ("ed-plan", "ed-both"):
        changes[plan_file] = edit_plan_density(original[plan_file], "Insert", uniform_ed=1.1)
    if operation in ("ed-study", "ed-both"):
        changes[contour_file] = _edit_study_density(original[contour_file], contour_line, 1.2 if operation == "ed-study" else 1.1)
    if operation == "ed-disabled":
        changes[plan_file] = edit_plan_density(original[plan_file], "Insert", mode=1)
    if operation == "ed-fill":
        changes[plan_file] = edit_plan_density(original[plan_file], "Insert", mode=3, fill_ed=0.8)
    if operation in ("rectangle-header", "leaf-notch"):
        changes[tel_file] = edit_static_aperture(original[tel_file], "2", operation)
    return changes


def build_validation_batch(source: str | Path, destination: str | Path) -> dict:
    """Write fresh review cases; never overwrite captures or a previous review sheet.

    Payloads replace one plan folder and one contournames file in an independent
    copy of the original phantom patient. They are not complete patient imports.
    """
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite an existing validation batch: {destination}")
    # Prevent generation inside a directory input and accidental recursion/content capture.
    if source.is_dir() and (destination.resolve() == source.resolve() or source.resolve() in destination.resolve().parents):
        raise ValueError("validation output must be outside the source export")
    report = inspect_export(source)
    matches = [p for p in report["plans"] if p["name"] == PLAN_NAME]
    if len(matches) != 1 or matches[0]["diagnostics"]:
        raise FormatError("validation profile requires one supported RefHeteroSq6X plan with no reader diagnostics")
    plan = matches[0]
    studies = [s for s in report["studysets"] if s["name"] == plan["studyset"]
               and PurePosixPath(s["path"]).parent == PurePosixPath(plan["path"]).parent.parent]
    if len(studies) != 1 or studies[0]["diagnostics"] or plan["studyset"] != "SemiflexWater":
        raise FormatError("validation profile requires the linked SemiflexWater studyset")
    study = studies[0]
    inserts = [r for r in study["structures"] if r["name"] == "Insert"]
    plan_inserts = [r for r in plan["density_overrides"] if r["name"] == "Insert"]
    if len(inserts) != 1 or len(plan_inserts) != 1 or any(r["uniform_ed"] != 1 or r["mode"] != "forced" for r in inserts + plan_inserts):
        raise FormatError("validation profile expects original forced Insert ED 1.0 in both representations")
    for key, value in {"DOSEGRIDSIZE": 1, "MCVARIANCE": 0.01, "MCSEGMENTVARIANCE": 0.01,
                       "DOSETOMEDIUM": True, "FORCEWATER": False}.items():
        if not plan["settings"].get(key) or plan["settings"][key]["value"] != value:
            raise FormatError(f"validation profile baseline differs at {key}")
    plan_file, tel_file = plan["path"] + "/plan", plan["path"] + "/tel.1"
    contour_file = study["path"] + "/contournames"
    with Export(source) as export:
        hyp_files = [n for n in export.sizes if PurePosixPath(n).parent.as_posix() == plan["path"] and n.lower().endswith(".hyp")]
        if len(hyp_files) != 1:
            raise FormatError("expected one baseline .hyp")
        hyp_file = hyp_files[0]
        original = {n: export.read(n) for n in (plan_file, hyp_file, tel_file, contour_file)}
        source_names = sorted([n for n in export.sizes if PurePosixPath(n).parent.as_posix() == plan["path"]] + [contour_file])
        omitted_names = [n for n in source_names if PurePosixPath(n).name == "dose.1" or ".dose." in PurePosixPath(n).name or n.lower().endswith(".xlog")]
        if len(omitted_names) != 5:
            raise FormatError("expected four saved dose payloads and one historical log in the source plan")
        # Preflight every proposed edit before writing output.
        mutations = {c["id"]: _patches(c["operation"], original, plan_file, hyp_file, tel_file,
                                        contour_file, inserts[0]["source"]["line"]) for c in CASES}
        source_digest = _hash_path(source) if source.is_file() else None
        destination.mkdir(parents=True, exist_ok=False)
        result = {"schema_version": 1, "profile": "supplied-static-RefHeteroSq6X-v1",
                  "source": str(source), "source_archive_sha256": source_digest,
                  "patient_id": plan["patient_id"], "plan_name": plan["name"], "studyset": plan["studyset"],
                  "payload_plan_path": plan["path"], "payload_contournames_path": contour_file,
                  "identity_policy": "original identities retained; one case at a time in an independent copy",
                  "generator_source_sha256": {str(p): _hash_path(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
                  "cases": CASES}
        original_hashes = {}
        for case in CASES:
            case_dir = destination / "cases" / case["id"]
            payload = case_dir / "payload"
            case_dir.mkdir(parents=True)
            changes = mutations[case["id"]]
            omitted = [] if case["operation"] == "original" else omitted_names
            files = {}
            for name in source_names:
                if name in omitted:
                    continue
                target = payload / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if name in changes:
                    target.write_bytes(changes[name])
                else:
                    with export.open(name) as stream, target.open("wb") as output:
                        shutil.copyfileobj(stream, output, length=1024 * 1024)
                digest = _hash_path(target)
                if name not in changes:
                    original_hashes[name] = digest
                files[name] = {"size": target.stat().st_size, "sha256": digest,
                               "content": "modified" if name in changes else "source-identical"}
            diff_parts = []
            records = {}
            for name, data in changes.items():
                diff = "".join(difflib.unified_diff(original[name].decode("cp1252").splitlines(keepends=True),
                                                  data.decode("cp1252").splitlines(keepends=True),
                                                  fromfile="source/" + name, tofile="candidate/" + name))
                diff_parts.append(diff)
                records[name] = {"before_sha256": _sha(original[name]), "after_sha256": _sha(data)}
            manifest = {"schema_version": 1, "case": case, "comparison_base": "source" if case["operation"] in ("original", "no-dose") else "V01-no-dose-control",
                        "source_archive_sha256": source_digest, "files": files, "changed_files": records,
                        "omitted_files": {n: {"reason": "original saved dose or historical log; not evidence for the edited candidate",
                                               "source_sha256": original_hashes[n]} for n in omitted},
                        "monaco_validation": "not_reviewed"}
            _save_json(case_dir / "manifest.json", manifest)
            (case_dir / "changes.diff").write_text("\n".join(diff_parts), encoding="utf-8")
            checks = "\n".join("- [ ] " + check for check in case["review_checks"])
            (case_dir / "INSTRUCTIONS.md").write_text(
                f'# {case["id"]}: {case["title"]}\n\n{case["expected_observation"]}\n\n'
                'Follow the batch README to replace the plan folder and restore the accompanying studyset contournames file.\n'
                'Review this case independently; do not combine it with another case.\n'
                'Monaco load acceptance and visual representation are pending your review.\n\n'
                f'{checks}\n\nRecord the result in the batch REVIEW.md or review-results.json.\n'
                'After observing the initial load, save/reopen if accepted and retain the resulting native files under roundtrips/<case-id>/.\n'
                'The initial aperture probes intentionally leave competing shape records unchanged; inspect the measured geometry and leaf positions rather than the beam description.\n', encoding="utf-8")
        _save_json(destination / "batch.json", result)
    _write_review_material(destination, result)
    return result


def _write_review_material(destination, result):
    readme = f'''# Monaco validation batch: {result["profile"]}

This batch contains {len(result["cases"])} independent cases for the supplied phantom plan.
Each payload supplies the complete selected plan folder, plus the studyset contournames file needed to reset density defaults between tests.
CT images and the rest of the patient are supplied by your independent copy of the original archive.
These are native Monaco file candidates, not DICOM imports or complete patient-import archives.
All original patient, studyset, plan and document identities are retained so that renaming does not become an additional untested variable.
Use one case at a time in an independent copy of the phantom patient, using your normal native-data restoration workflow.

## Loading each case

1. Restore the original supplied phantom patient into an independent validation location.
   Record the Monaco version/build and how that location is opened or restored.
2. Close the plan/patient in Monaco before replacing native files.
   Preserve your baseline and any completed review outside the patient directory Monaco reads.
3. Replace the entire `{result["payload_plan_path"]}` folder with the corresponding folder from the selected case's `payload/`.
   Replace the folder, rather than merging files: most cases intentionally omit the original dose payloads and calculation log.
4. Copy `{result["payload_contournames_path"]}` from the same payload to the matching studyset in that validation patient.
   Do this for every case, including cases without an ED change, so studyset changes do not carry into the next case.
5. Open patient `{result["patient_id"]}`, studyset `{result["studyset"]}`, plan `{result["plan_name"]}`.
   Record initial values and messages before changing anything in the UI.
6. Follow the case INSTRUCTIONS.md and record findings in REVIEW.md or review-results.json.
   For accepted cases, capture screenshots and save/reopen; put returned native files in `roundtrips/<case-id>/`.
7. Reset using the next complete case payload for the next test.
   Do not install the case-ID folders as additional Monaco plan folders; the internal plan identity is the same in every case.

Start with V00-original, then V01-no-dose-control.
V00 contains source-identical plan files and the original saved dose/log; its studyset contournames file is also source-identical.
V01 omits four original dose payloads and the old calculation log, with every supplied remaining file source-identical.
All edited cases use the same omissions as V01, so compare their load behavior with V01.
If V00 fails, resolve baseline restoration first.
If V01 fails, record the exact response and stop the edited-case load sequence until the no-dose representation is understood.
Do not treat missing payloads as proof that Monaco has cleared every stored dose-state flag: those unassigned flags are deliberately not rewritten.
Original checksum and status records are retained; no checksum or calculation-completion claim has been fabricated.

The beam-shape cases are isolated representation probes.
V12 changes two aperture-header rows while retaining the leaf and compact shape records.
V13 changes eight second-bank leaf tips while retaining the aperture headers and compact shape records.
The beam description remains 10x10 in both; a label change would not validate geometry.
Monaco may use, reject, normalize or overwrite one representation, which is precisely what these cases test.

## Result capture

REVIEW.md is a human-editable review sheet; review-results.json contains the same case identifiers with structured empty fields.
All reviews start as not_reviewed, and no result is inferred from a Python read-back.
For every reviewed case, record loading acceptance, initial displayed values, warnings, screenshots, save/reopen behavior, and returned file paths.
A rejection or silent normalization is a useful result.
If recalculating, do so after the initial display and save/reopen observations, and keep that separate returned capture.

Each case has manifest.json with original/modified content hashes and omitted-file records, plus changes.diff for every changed text file.
The generator refuses to overwrite an existing batch, protecting results you fill in.
'''
    (destination / "README.md").write_text(readme, encoding="utf-8")
    lines = ["# Monaco validation review sheet", "", "Fill this file or review-results.json; both use the same case IDs.",
             "All results below are blank and have not been reviewed in Monaco.", "", "Reviewer: ", "Date/time and timezone: ",
             "Monaco version/build: ", "Validation location / restoration method: ", "Original archive hash verified: ", "",
             "| Case | Load result | Matches hypothesis? | Save/reopen | Screenshot / returned files | Notes |",
             "|---|---|---|---|---|---|"]
    for case in result["cases"]:
        lines.append(f'| {case["id"]} | not reviewed | | | | |')
    rows = []
    for case in result["cases"]:
        lines += ["", f'## {case["id"]}: {case["title"]}', "", case["expected_observation"], "",
                  "Review status: not_reviewed", "Load result / exact message: ", "Initial observed value(s) and units: ",
                  "Uncertainty mode / Force-Fill flags / geometry as applicable: ", "Observed dose state: ",
                  "Screenshot path(s): ", "Saved and reopened result: ", "Returned native files path: ",
                  "Optional recalculation result and separate capture path: ", "Interpretation / discrepancy / notes: "]
        rows.append({"case_id": case["id"], "expected_observation": case["expected_observation"],
                     "review_status": "not_reviewed", "load_result": None, "initial_observation": None,
                     "exact_messages": [], "dose_state": None, "matches_hypothesis": None,
                     "screenshots": [], "save_reopen_result": None, "returned_native_files": None,
                     "recalculation_result": None, "recalculation_capture": None, "notes": ""})
    (destination / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _save_json(destination / "review-results.json", {"schema_version": 1, "profile": result["profile"],
               "source_archive_sha256": result["source_archive_sha256"], "reviewer": None, "review_date": None,
               "monaco_version_build": None, "validation_location": None, "restoration_method": None, "cases": rows})
    (destination / "roundtrips").mkdir()
    (destination / "roundtrips" / "README.md").write_text(
        "# Returned Monaco captures\n\nCreate a directory per case ID with the native files saved by Monaco after initial review.\n"
        "Keep initial load, save/reopen, and recalculated captures separate.\n"
        "Include plan, tel.1, .hyp, changed studyset files, and any status/log/checksum records.\n"
        "Record screenshots and exact displayed values in the review sheet.\n", encoding="utf-8")


NAMED_PATIENT_ID = 'zzzInputOutputAG'
NAMED_PATIENT_NAME = 'zzPHYS^Ash'
SOURCE_PATIENT_ID = 'ZZZELEKTAONEHETERO'


def named_patient_path(name: str) -> str:
    """Rename only the fixture's patient directory and demographic filename."""
    parts = list(PurePosixPath(name).parts)
    if not parts or parts[0] != '1~' + SOURCE_PATIENT_ID:
        raise FormatError('unexpected patient root in named validation profile')
    parts[0] = '1~' + NAMED_PATIENT_ID
    if parts[-1] == 'demographic.' + SOURCE_PATIENT_ID:
        parts[-1] = 'demographic.' + NAMED_PATIENT_ID
    return PurePosixPath(*parts).as_posix()


def named_patient_record(name: str, data: bytes) -> bytes:
    """Patch observed line records only, never search/replace image payloads."""
    base = PurePosixPath(name).name
    if base not in ('plan', 'info', 'demographic.' + SOURCE_PATIENT_ID):
        return data
    rows = data.splitlines(keepends=True)
    for i, row in enumerate(rows):
        value = row.rstrip(b'\r\n')
        if value == SOURCE_PATIENT_ID.encode():
            rows[i] = NAMED_PATIENT_ID.encode() + row[len(value):]
        elif base.startswith('demographic.') and value == b'ZZZElektaONEHetero^AG':
            rows[i] = NAMED_PATIENT_NAME.encode() + row[len(value):]
    return b''.join(rows)


def build_named_validation_batch(source: str | Path, destination: str | Path) -> dict:
    """Generate a separate named phantom baseline and isolated parameter overlays.

    Native demographic/reference edits are experimental too; validate identity first.
    Existing batches and returned reviews are never overwritten.
    """
    import tempfile
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f'refusing to overwrite an existing validation batch: {destination}')
    if Path(source).is_dir() and Path(source).resolve() in destination.resolve().parents:
        raise ValueError('validation output must be outside the source export')
    with tempfile.TemporaryDirectory(prefix='hyperio-named-') as temporary:
        staging = Path(temporary) / 'batch'
        result = build_validation_batch(source, staging)
        result['cases'] = json.loads(json.dumps(result['cases']).replace('No file contents changed.',
            'Only the shared identity records are changed.'))
        old_root = '1~' + SOURCE_PATIENT_ID
        demographic = old_root + '/demographic.' + SOURCE_PATIENT_ID
        info = old_root + '/1~SemiflexWater/info'
        with Export(source) as export:
            if demographic not in export.sizes or info not in export.sizes:
                raise FormatError('named profile requires demographic and studyset info records')
            if export.read(demographic).count(b'ZZZElektaONEHetero^AG') != 2:
                raise FormatError('unexpected source demographic name records')
            destination.mkdir(parents=True)
            baseline_records = {}
            # Include the selected studyset with its complete CT/WC/contour data.
            # Other studysets/plans and source editing locks are intentionally excluded.
            baseline_names = [n for n in export.sizes if n.startswith(old_root + '/1~SemiflexWater/')]
            baseline_names += [demographic, old_root + '/DcmMappingData.xml']
            baseline_payload = destination / 'baseline'
            for name in sorted(baseline_names):
                data = export.read(name, limit=export.sizes[name])
                edited = named_patient_record(name, data)
                target_name = named_patient_path(name)
                target = baseline_payload / target_name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(edited)
                baseline_records[target_name] = {'source_path': name, 'source_sha256': _sha(data),
                    'sha256': _sha(edited), 'size': len(edited),
                    'content': 'identity-edited' if edited != data else 'source-identical'}
            _save_json(destination / 'baseline-manifest.json', {'files': baseline_records,
                'monaco_validation': 'not_reviewed', 'source_archive_sha256': result['source_archive_sha256']})
            for case in result['cases']:
                case_dir = destination / 'cases' / case['id']
                payload = case_dir / 'payload'
                source_dir = staging / 'cases' / case['id']
                manifest = json.loads((source_dir / 'manifest.json').read_text())
                files, changes, diffs = {}, {}, []
                names = list(manifest['files']) + [demographic, info]
                for name in names:
                    raw = export.read(name, limit=export.sizes[name])
                    generated = (source_dir / 'payload' / name).read_bytes() if name in manifest['files'] else raw
                    data = named_patient_record(name, generated)
                    target_name = named_patient_path(name)
                    target = payload / target_name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    files[target_name] = {'source_path': name, 'sha256': _sha(data), 'size': len(data),
                        'content': 'modified' if raw != data else 'source-identical'}
                    if raw != data:
                        changes[target_name] = {'source_path': name, 'before_sha256': _sha(raw), 'after_sha256': _sha(data)}
                        diffs.append(''.join(difflib.unified_diff(raw.decode('cp1252').splitlines(keepends=True),
                            data.decode('cp1252').splitlines(keepends=True), fromfile='source/' + name,
                            tofile='candidate/' + target_name)))
                manifest.update(case=case, files=files, changed_files=changes,
                    identity_policy='requested identity edits shared by all cases; parameter changes relative to named V01',
                    comparison_base='source plus identity edits' if case['operation'] in ('original', 'no-dose') else 'named V01-no-dose-control')
                _save_json(case_dir / 'manifest.json', manifest)
                (case_dir / 'changes.diff').write_text('\n'.join(diffs), encoding='utf-8')
                (case_dir / 'INSTRUCTIONS.md').write_text(
                    '**CT DATA REQUIRED:** This payload is an overlay and contains no CT slices.\n'
                    'First restore the complete `baseline/1~zzzInputOutputAG/` patient from the batch root.\n'
                    'It already includes V00; load it directly for the first control.\n'
                    'Keep its studyset CT/WC files when applying subsequent case overlays.\n\n'
                    + (source_dir / 'INSTRUCTIONS.md').read_text().replace(
                    'No file contents changed.', 'Only the shared identity records are changed.'))
                with (case_dir / 'INSTRUCTIONS.md').open('a') as stream:
                    stream.write('\nUse the named batch README for installation and identity checks.\n'
                        'This control includes the shared patient identity edits; consult changes.diff.\n')
            # Seed baseline with V00 so it can be restored without combining sources.
            control = destination / 'cases/V00-original/payload'
            shutil.copytree(control, baseline_payload, dirs_exist_ok=True)
            control_manifest = json.loads((control.parent / 'manifest.json').read_text())
            for name, record in control_manifest['files'].items():
                baseline_records[name] = dict(record, source_sha256=_sha(export.read(record['source_path'], limit=export.sizes[record['source_path']])))
            _save_json(destination / 'baseline-manifest.json', {'files': baseline_records,
                'monaco_validation': 'not_reviewed', 'source_archive_sha256': result['source_archive_sha256']})
        result.update(profile='supplied-static-RefHeteroSq6X-named-v2',
            patient_id=NAMED_PATIENT_ID, patient_name='zzPHYS, Ash', native_patient_name=NAMED_PATIENT_NAME,
            payload_plan_path=named_patient_path(result['payload_plan_path']),
            payload_contournames_path=named_patient_path(result['payload_contournames_path']),
            identity_policy='named patient; shared original studyset/plan identities; one case at a time')
        _write_review_material(destination, result)
        readme = (destination / 'README.md').read_text()
        readme = readme.replace('All original patient, studyset, plan and document identities are retained so that renaming does not become an additional untested variable.',
            'Patient ID is `zzzInputOutputAG`; family/given name is `zzPHYS, Ash` (native spelling `zzPHYS^Ash`).\n'
            'Patient directory, demographic filename/records, plan patient ID, and studyset info patient ID are patched consistently.\n'
            'Studyset, plan and document identifiers remain shared across cases.\n'
            'Identity restoration is itself experimental: confirm the displayed ID/name before parameter testing.\n'
            'CT/WC binary payloads are source-identical; this is not a DICOM reidentification workflow.')
        readme = readme.replace('CT images and the rest of the patient are supplied by your independent copy of the original archive.',
            'The `baseline/1~zzzInputOutputAG/` directory supplies the selected studyset with CT/WC data, demographics and V00 plan.\n'
            'Other source studysets/plans and patient-root editing locks are excluded.')
        readme = readme.replace('1. Restore the original supplied phantom patient into an independent validation location.',
            '1. Restore `baseline/1~zzzInputOutputAG/` into an independent validation location using your native-data workflow.\n'
            '   Confirm Patient ID `zzzInputOutputAG` and Name `zzPHYS, Ash`; if rejected or displayed differently, retain the exact message and returned files before proceeding.')
        readme = readme.replace('No file contents changed.', 'Only the shared identity records are changed.')
        readme = readme.replace('V00 contains source-identical plan files and the original saved dose/log;',
            'V00 contains the shared identity edits and original saved dose/log;')
        readme = readme.replace('with every supplied remaining file source-identical.',
            'with the shared identity edits and no parameter changes.')
        (destination / 'README.md').write_text(readme)
        # Correct the original-control hypothesis everywhere, including review templates.
        for path in [destination / 'REVIEW.md', destination / 'review-results.json']:
            path.write_text(path.read_text().replace('No file contents changed.',
                'Only the shared identity records are changed.'))
        result['cases'] = json.loads(json.dumps(result['cases']).replace('No file contents changed.',
            'Only the shared identity records are changed.'))
        _save_json(destination / 'batch.json', result)
        return result
