"""JSON command-line tools for local inspection and controlled captures."""
import argparse
import json
from pathlib import Path
import sys
import zipfile

from .core import FormatError, compare_settings, inspect_export
from .snapshots import diff_snapshots, snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect Monaco saved plan settings")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "snapshot"):
        sub = commands.add_parser(name)
        sub.add_argument("source", type=Path)
    sub = commands.add_parser("check", help="compare an explicit raw-setting profile against each plan")
    sub.add_argument("source", type=Path)
    sub.add_argument("profile", type=Path)
    sub = commands.add_parser("diff", help="compare two saved JSON snapshots")
    sub.add_argument("before", type=Path)
    sub.add_argument("after", type=Path)
    sub = commands.add_parser("validation-pack", help="retired legacy command; use validation-suite")
    sub.add_argument("source", type=Path)
    sub.add_argument("destination", type=Path)
    profile = sub.add_mutually_exclusive_group()
    profile.add_argument("--named-patient", action="store_true",
                     help="use zzzInputOutputAG / zzPHYS, Ash and include the selected CT baseline")
    profile.add_argument("--three-slice", action="store_true",
                         help="standalone named patient cases with three native CT slices each")
    sub = commands.add_parser("blank-ct", help="generate a zero-valued 500mm DICOM CT cube with 5mm voxels")
    sub.add_argument("source", type=Path)
    sub.add_argument("destination", type=Path)
    sub = commands.add_parser("index-ct", help="package CT using a complete working depot ZIP as layout evidence")
    sub.add_argument("source", type=Path)
    sub.add_argument("destination", type=Path)
    sub.add_argument("template", type=Path, help="complete working depot ZIP, including both indices and CT images")
    sub = commands.add_parser("validation-suite", help="generate one native patient with grouped tests from a perpetual catalogue")
    sub.add_argument("source", type=Path, help="supplied native plan/contour fixture")
    sub.add_argument("native_return", type=Path, help="TPS-created 100-slice CT1 native return")
    sub.add_argument("destination", type=Path)
    sub.add_argument("--catalogue", type=Path, default=Path("validation/catalogue.json"))
    sub = commands.add_parser("record-review", help="append completed run observations to the perpetual result ledger")
    sub.add_argument("review", type=Path)
    sub.add_argument("catalogue", type=Path)
    sub.add_argument("events", type=Path)
    args = parser.parse_args(argv)
    exit_code = 0
    try:
        if args.command == "inspect":
            output = inspect_export(args.source)
            exit_code = int(not output["plans"] or any(p["diagnostics"] for p in output["plans"])
                            or any(s["diagnostics"] for s in output["studysets"]))
        elif args.command == "snapshot":
            output = snapshot(args.source)
        elif args.command == "diff":
            output = diff_snapshots(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
        elif args.command == "validation-suite":
            from .validation_suite import build_suite
            output = build_suite(args.source, args.native_return, args.destination, args.catalogue)
        elif args.command == "record-review":
            from .validation_suite import record_review
            output = {"events_appended": record_review(args.review, args.catalogue, args.events)}
        elif args.command == "index-ct":
            from .depot_index import package_indexed_ct
            output = package_indexed_ct(args.source, args.destination, args.template)
        elif args.command == "blank-ct":
            from .blank_ct import build_blank_ct
            output = build_blank_ct(args.source, args.destination)
        elif args.command == "validation-pack":
            raise ValueError("validation-pack is retired; use validation-suite with the returned native CT1 and validation/catalogue.json")
        else:
            expected = json.loads(args.profile.read_text())
            if not isinstance(expected, dict):
                raise ValueError("profile must be a JSON object of raw setting names and expected values")
            report = inspect_export(args.source)
            plans = []
            # Validate even when no plan was discovered.
            compare_settings({}, expected)
            for plan in report["plans"]:
                checks = compare_settings(plan["settings"], expected)
                plans.append({"name": plan["name"], "path": plan["path"], "checks": checks,
                              "diagnostics": plan["diagnostics"]})
            output = {"source": str(args.source), "profile": str(args.profile), "plans": plans,
                      "limitations": report["limitations"]}
            exit_code = int(not plans or any(p["diagnostics"] or any(c["status"] != "match" for c in p["checks"])
                                             for p in plans))
        json.dump(output, sys.stdout, indent=2, allow_nan=False)
        print()
        return exit_code
    except (OSError, ImportError, FormatError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(f"hyperio: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
