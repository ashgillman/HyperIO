#!/usr/bin/env python3
"""Reproduce the supplied-archive report and its content provenance."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath

from hyperio import inspect_export
from hyperio.core import Export

HELP_PAGES = {
    "usm1506019008231.htm": "Calculation Properties dialog box",
    "usm1493663129001.htm": "Monte Carlo uncertainty formula",
    "usm1493663145497.htm": "Dose to Water versus Dose to Medium",
    "usm1506018979724.htm": "Assign Densities dialog box",
    "jap1518315983721.htm": "Structures Control: Layers Tab",
    "usm1493663137867.htm": "Frozen Dose",
    "usy1504705192560.htm": "About CT-to-ED Conversion Files",
    "usm1506018963596.htm": "Grid Volume group",
}
PLAN_CHECK_FILES = ["src/monaco/raw.jl", "src/monaco/plan/plan.jl", "src/monaco/plan/hyperion.jl",
                    "src/monaco/plan/tel.jl", "src/monaco/studyset/contournames.jl",
                    "src/monaco/studyset/info.jl", "src/checks/ROMP/5.2.jl", "src/checks/ROMP/5.3.jl"]


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--help-chm", type=Path)
    parser.add_argument("--extracted-help", type=Path)
    parser.add_argument("--plancheck", type=Path)
    parser.add_argument("--plancheck-head", help="revision independently checked by the investigator")
    parser.add_argument("--out", type=Path, default=Path("reports"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = inspect_export(args.archive)
    save(args.out / "supplied-plans.json", report)
    with Export(args.archive) as source:
        metadata = {}
        for name in sorted(source.sizes):
            if PurePosixPath(name).name in ("plan", "tel.1", "info", "contournames") or name.lower().endswith((".hyp", ".xlog")) or PurePosixPath(name).name == "checksum.1":
                metadata[name] = {"size": source.sizes[name], "sha256": hashlib.sha256(source.read(name)).hexdigest()}
        dose_headers = {}
        for name in sorted(source.sizes):
            if PurePosixPath(name).name == "dose.1" or ".dose." in PurePosixPath(name).name:
                with source.open(name) as stream:
                    prefix = stream.read(256)
                dose_headers[name] = {"sample_bytes": len(prefix), "prefix_sha256": hashlib.sha256(prefix).hexdigest(),
                                      "first_line": prefix.split(b"\n", 1)[0].decode("ascii", errors="replace")}
        counts = dict(sorted(Counter(PurePosixPath(n).suffix or "<none>" for n in source.sizes).items()))
    provenance = {"archive": {"path": str(args.archive), "sha256": sha_file(args.archive),
                               "bytes": args.archive.stat().st_size},
                  "file_extensions": counts, "inspected_metadata": metadata,
                  "native_dose_header_samples": dose_headers,
                  "parser_source_sha256": {p.as_posix(): sha_file(p) for p in sorted([*Path("src/hyperio").glob("*.py"), *Path("scripts").glob("*.py")])}}
    if args.help_chm:
        provenance["help_chm"] = {"path": str(args.help_chm), "sha256": sha_file(args.help_chm)}
    if args.extracted_help:
        provenance["help_topics"] = {name: {"title": title, "sha256": sha_file(args.extracted_help / name)}
                                     for name, title in HELP_PAGES.items()}
    if args.plancheck:
        provenance["plancheck"] = {"path": str(args.plancheck), "investigator_checked_head": args.plancheck_head,
                                   "files": {name: sha_file(args.plancheck / name) for name in PLAN_CHECK_FILES},
                                   "note": "Working-tree hashes are authoritative; checks/ROMP/5.3.jl had local changes."}
    save(args.out / "provenance.json", provenance)
    rows = []
    for p in report["plans"]:
        insert = next((s for s in p["density_overrides"] if s["name"] == "Insert"), {})
        setting = lambda key: p["settings"].get(key)["value"] if p["settings"].get(key) else "unknown"
        rows.append(f'| {p["name"]} | {p["studyset"]} | {setting("DOSEGRIDSIZE")} | '
                    f'{setting("MCVARIANCE")} | {setting("MCSEGMENTVARIANCE")} | '
                    f'{insert.get("uniform_ed", "unknown"):g} | {len(p["beams"])} |')
    text = "\n".join([
        "# Supplied phantom archive: initial observations", "",
        "Generated from the supplied local archive by `scripts/research_baseline.py`.",
        "These are saved settings interpreted using the initial format profile; UI confirmation is pending.",
        "The independent source hashes are in [provenance.json](provenance.json).", "",
        f'The archive contains {report["file_count"]:,} files and {report["uncompressed_bytes"]:,} uncompressed bytes.',
        f'It contains {len(report["plans"])} plans and {len(report["studysets"])} studysets.', "",
        "| Plan | Primary studyset | Grid, raw | MCVARIANCE | MCSEGMENTVARIANCE | Insert uniform ED | Beams |",
        "|---|---|---:|---:|---:|---:|---:|", *rows, "",
        "All six plans store DOSETOMEDIUM=1, FORCEWATER=0, STORECOUCHCOILDOSE=0, and ISPHANTOMMATERIAL=0.",
        "MCVARPERPLAN is absent in all six .hyp files; uncertainty mode remains unknown.",
        "All linked studysets name RoutineSep21 as their CT-to-ED selection; the conversion table itself is absent.",
        "Each plan has beam descriptions 3x3, 5x5, and 10x10, with algorithm code 6.",
        "Beam names are labels; aperture dimensions, energy, control points, MU, and dose are not independently established.",
        "The 6F machine identifier is Agility6MVFFF; the 6X identifier is Agility6MV2017.",
        "The supplied studyset spelling PoinpointLung is preserved literally.", "",
        "Grid values are interpreted as mm by PlanCheck; the help displays cm.",
        "The two MC values are provisionally interpreted as uncertainty fractions, not squared variances.",
        "Confirm both interpretations with controlled UI captures before relying on unit conversions.", "",
        "The plan density table can override studyset defaults and uses a different field order.",
        "For example, RefHeteroSq6X stores Insert at layer 9, while the other five plans store it at layer 2.",
        "All plans store forced uniform ED 1.0 for Patient; the Insert values are shown above.",
        "Layer precedence and the resulting voxel density map still require independent confirmation.", "",
        "Calculation logs contain mcStdDev values, labelled per-segment and entire-calculation uncertainties, and completion messages.",
        "For RefHeteroSq6X, the log records mcStdDev 0.01, each-segment uncertainty 1 percent, and entire-calculation uncertainty 0.69 percent.",
        "These log observations are separate from saved settings and have not been proven to describe the current dose payload.", "",
        "The existing plans differ in several respects and are observational examples, not isolated experiments.",
        "Presence of native dose files is not proof that their dose reflects these settings.",
        "See [the controlled capture protocol](../docs/experiments.md) for the next evidence to collect.", ""])
    (args.out / "supplied-plans.md").write_text(text, encoding="utf-8")
    print(f'Wrote reports for {len(report["plans"])} plans to {args.out}')


if __name__ == "__main__":
    main()
