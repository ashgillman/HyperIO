"""Small, evidence-preserving readers for the supplied Monaco text layouts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any
import zipfile


class FormatError(ValueError):
    """A layout or value cannot be interpreted without guessing."""


@dataclass(frozen=True)
class Field:
    value: Any
    file: str
    line: int
    raw: str
    unit: str | None = None
    interpretation: str = "PlanCheck mapping; controlled UI confirmation pending"

    def as_dict(self):
        return asdict(self)


# Store both MC values separately. No default for absent MCVARPERPLAN.
SPECS = {
    "DOSEGRIDSIZE": (float, "mm (inferred)"),
    "MCVARIANCE": (float, "fraction (inferred)"),
    "MCSEGMENTVARIANCE": (float, "fraction (inferred)"),
    "MCVARPERPLAN": (bool, None),
    "DOSETOMEDIUM": (bool, None),
    "FORCEWATER": (bool, None),
    "STORECOUCHCOILDOSE": (bool, None),
    "ISPHANTOMMATERIAL": (bool, None),
    "FRACTIONS": (int, "count"),
    "PRESCRIPTION": (float, "Gy (inferred)"),
}
BLOCKS = {"LAYERING", "VOIDEF", "DOSE_ENGINES", "MOD_EQUIPMENT", "BEAMS", "BEAMDEF",
          "COSTFUNCTION", "SHRINKMARGINTARGET"}
DIRECTIVE = re.compile(rb"^([ \t]*!)([A-Z][A-Z0-9_]*)([ \t]*)([^\r\n]*)(\r\n|\n|\r)?$")


def typed_value(key: str, raw: str):
    kind = SPECS[key][0]
    try:
        if kind is bool:
            if raw not in ("0", "1"):
                raise ValueError("expected 0 or 1")
            return raw == "1"
        if kind is int:
            return int(raw)
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("nonfinite number")
        return value
    except ValueError as exc:
        raise FormatError(f"{key}: invalid value {raw!r}") from exc


class HypDocument:
    """Retain original bytes; expose unique named settings and copy-only edits.

    Editing a setting does not recalculate a plan or establish saved-dose validity.
    """

    def __init__(self, data: bytes, source: str = "<memory>"):
        self._data = data
        self.source = source
        self._lines = data.splitlines(keepends=True)
        self.version = self._lines[0].strip().decode("ascii", errors="replace") if self._lines else ""
        self.directives: dict[str, list[Field]] = {}
        self._scopes = {}
        scope = []
        for number, line in enumerate(self._lines, 1):
            match = DIRECTIVE.fullmatch(line)
            if match:
                key = match[2].decode("ascii")
                raw = match[4].decode("cp1252", errors="surrogateescape").strip()
                field = Field(raw, source, number, raw, interpretation="literal directive")
                self.directives.setdefault(key, []).append(field)
                self._scopes[number] = tuple(scope)
                if key == "END":
                    if scope:
                        scope.pop()
                elif key in BLOCKS and not raw:
                    scope.append(key)

    @classmethod
    def read(cls, path: str | Path):
        return cls(Path(path).read_bytes(), str(path))

    def to_bytes(self) -> bytes:
        return self._data

    def get(self, key: str) -> Field | None:
        if key not in SPECS:
            raise KeyError(key)
        if self.version != "000610b6":
            raise FormatError(f"unsupported .hyp version {self.version!r}")
        entries = self.directives.get(key, [])
        if not entries:
            return None
        if len(entries) != 1:
            raise FormatError(f"{key}: multiple directives; scope is ambiguous")
        field = entries[0]
        if self._scopes[field.line]:
            raise FormatError(f"{key}: directive is inside a block; scope is unsupported")
        kind, unit = SPECS[key]
        interpretation = "literal boolean; UI mapping pending" if kind is bool else Field.interpretation
        return Field(typed_value(key, field.raw), self.source, field.line, field.raw, unit, interpretation)

    def settings(self) -> dict[str, dict | None]:
        return {key: field.as_dict() if (field := self.get(key)) else None for key in SPECS}

    def with_value(self, key: str, value: float | int | bool) -> HypDocument:
        if key not in SPECS:
            raise FormatError(f"editing unsupported directive {key!r}")
        field = self.get(key)
        if field is None:
            raise FormatError(f"cannot edit absent directive {key}")
        kind = SPECS[key][0]
        if kind is bool:
            if type(value) is not bool:
                raise ValueError(f"{key} expects a boolean")
            raw = str(int(value))
        elif kind is int:
            if type(value) is not int:
                raise ValueError(f"{key} expects an integer")
            raw = str(value)
        else:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{key} expects a finite number")
            raw = format(value, ".17g")
        typed_value(key, raw)
        lines = self._lines.copy()
        match = DIRECTIVE.fullmatch(lines[field.line - 1])
        assert match is not None
        # Retain indentation, key spacing, trailing whitespace, and newline bytes.
        trailing = match[4][len(match[4].rstrip(b" \t")):]
        lines[field.line - 1] = match[1] + match[2] + match[3] + raw.encode("ascii") + trailing + (match[5] or b"")
        return HypDocument(b"".join(lines), self.source)


class Export:
    """Read a directory or ZIP without unpacking or modifying the source."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path) if self.path.is_file() else None
        try:
            if self.zip:
                items = [(i.filename, i.file_size) for i in self.zip.infolist() if not i.is_dir()]
            else:
                if not self.path.is_dir():
                    raise FileNotFoundError(self.path)
                paths = sorted(self.path.rglob("*"))
                if any(p.is_symlink() for p in paths):
                    raise FormatError("directory exports must not contain symbolic links")
                items = [(p.relative_to(self.path).as_posix(), p.stat().st_size) for p in paths if p.is_file()]
            self.sizes: dict[str, int] = {}
            for name, size in items:
                parts = PurePosixPath(name).parts
                if not parts or name.startswith("/") or ".." in parts or "\\" in name or ":" in parts[0]:
                    raise FormatError(f"unsafe export member {name!r}")
                if name in self.sizes:
                    raise FormatError(f"duplicate export member {name!r}")
                self.sizes[name] = size
        except Exception:
            if self.zip:
                self.zip.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.zip:
            self.zip.close()

    def open(self, name: str):
        if name not in self.sizes:
            raise KeyError(name)
        return self.zip.open(name) if self.zip else (self.path / name).open("rb")

    def read(self, name: str, limit: int = 8_000_000) -> bytes:
        if self.sizes[name] > limit:
            raise FormatError(f"metadata member too large: {name}")
        with self.open(name) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise FormatError(f"metadata member exceeds limit: {name}")
        return data


def _lines(data: bytes):
    return data.decode("cp1252", errors="surrogateescape").splitlines()


def _numbers(line: str, width: int | None = None):
    parts = line.split(",")
    if width is not None and len(parts) != width:
        return None
    try:
        numbers = [float(p.strip()) for p in parts]
        return numbers if all(math.isfinite(n) for n in numbers) else None
    except ValueError:
        return None


def _shape(lines, start, widths):
    return start + len(widths) <= len(lines) and all(
        _numbers(lines[start + j], width) is not None for j, width in enumerate(widths) if width
    ) and all(
        len(lines[start + j].split(",")) == 1 for j, width in enumerate(widths) if width is None
    )


def plan_metadata(data: bytes, source: str):
    lines = _lines(data)
    if len(lines) < 7 or lines[0] != "00d5101a" or lines[5] != "1":
        raise FormatError("unsupported plan header or prescription layout")
    result = {"name": lines[2], "patient_id": lines[4], "studyset": lines[6],
              "identity_source": {"file": source, "lines": [3, 5, 7]}, "density_overrides": []}
    candidates = []
    for start, line in enumerate(lines):
        if not line.isdecimal() or not 1 <= int(line) <= 10000:
            continue
        count = int(line)
        if start + 2 * count >= len(lines):
            continue
        rows = []
        for i in range(count):
            n = start + 1 + i * 2
            name = lines[n]
            values = _numbers(lines[n + 1], 5)
            if not name.strip() or _numbers(name) is not None or values is None:
                break
            if values[0] not in (1, 2, 3) or values[4] != int(values[4]):
                break
            mode = {1: "none", 2: "forced", 3: "filled"}[int(values[0])]
            rows.append({"name": name, "mode": mode, "mode_code": int(values[0]),
                         "uniform_ed": values[2], "fill_ed": values[3], "layer": int(values[4]),
                         "source": {"file": source, "line": n + 2, "raw": lines[n + 1]},
                         "interpretation": "PlanCheck five-value mapping; UI confirmation pending"})
        if len(rows) == count:
            candidates.append(rows)
    if len(candidates) != 1:
        raise FormatError(f"expected one plan density table, found {len(candidates)}")
    result["density_overrides"] = candidates[0]
    return result


def beam_headers(data: bytes, source: str):
    lines = _lines(data)
    if not lines or lines[0] != "00d5101d":
        raise FormatError("unsupported tel.1 version")
    beams = []
    # Arity and numeric anchors from the PlanCheck beam-header approach.
    for i in range(len(lines)):
        if not _shape(lines, i, [None, 1, None, None, None, 3, 1, 11, None, 6, 2]):
            continue
        if i + 34 >= len(lines):
            continue
        algorithm = _numbers(lines[i + 13], 2)
        couch_collimator = _numbers(lines[i + 22], 9)
        iso = _numbers(lines[i + 26], 8)
        gantry = _numbers(lines[i + 32], 1)
        if any(v is None for v in (algorithm, couch_collimator, iso, gantry)):
            raise FormatError(f"beam header shape mismatch at {source}:{i + 1}")
        if algorithm[1] != int(algorithm[1]):
            raise FormatError("nonintegral beam algorithm code")
        code = int(algorithm[1])
        beams.append({"field_id": lines[i], "description": lines[i + 2],
                      "machine_id": lines[i + 3], "treatment_unit": lines[i + 4],
                      "algorithm_code": code,
                      "algorithm_label": {6: "Monte Carlo Photon (PlanCheck mapping)"}.get(code, "unknown"),
                      "gantry_raw": gantry[0], "couch_raw": couch_collimator[0],
                      "collimator_raw": couch_collimator[2], "isocentre_raw": iso[:3],
                      "source": {"file": source, "line": i + 1,
                                 "algorithm_line": i + 14, "isocentre_line": i + 27},
                      "interpretation": "positional mapping; native coordinates; no energy inference"})
    if not beams:
        raise FormatError("no supported beam headers found")
    return beams


def study_metadata(export: Export, prefix: str):
    result = {"name": PurePosixPath(prefix).name.split("~", 1)[-1],
              "path": prefix, "ct_to_ed_name": None, "structures": [], "diagnostics": []}
    info = prefix + "/info"
    if info in export.sizes:
        lines = _lines(export.read(info))
        if not lines or lines[0] != "00271016":
            result["diagnostics"].append("unsupported info version")
        else:
            hits = [i for i in range(len(lines)) if _shape(lines, i, [1, None, None, None] + [1] * 13)
                    and all(lines[i + j].strip() and _numbers(lines[i + j]) is None for j in (1, 2, 3))]
            if len(hits) == 1:
                i = hits[0] + 1
                result["ct_to_ed_name"] = Field(lines[i], info, i + 1, lines[i]).as_dict()
            else:
                result["diagnostics"].append("CT-to-ED selection absent or ambiguous")
    else:
        result["diagnostics"].append("missing info")
    contour = prefix + "/contournames"
    if contour not in export.sizes:
        result["diagnostics"].append("missing contournames")
        return result
    lines = _lines(export.read(contour))
    if not lines or lines[0] != "00131027":
        result["diagnostics"].append("unsupported contournames version")
        return result
    for i in range(len(lines) - 3):
        if not lines[i].strip() or _numbers(lines[i]) is not None or not _shape(lines, i, [None, 8, None, 6]):
            continue
        values = _numbers(lines[i + 1], 8)
        if values[2] not in (1, 2, 3) or any(values[j] != int(values[j]) for j in (0, 2, 3, 7)):
            result["diagnostics"].append(f"unrecognised structure record at line {i + 2}")
            continue
        result["structures"].append({"name": lines[i], "index": int(values[0]),
                                     "mode": {1: "none", 2: "forced", 3: "filled"}[int(values[2])],
                                     "type_code": int(values[3]), "uniform_ed": values[1],
                                     "fill_ed": values[6], "layer": int(values[7]),
                                     "source": {"file": contour, "line": i + 2, "raw": lines[i + 1]},
                                     "interpretation": "studyset defaults; use plan records for saved plan settings"})
    if len(lines) < 2 or not lines[1].isdecimal() or len(result["structures"]) != int(lines[1]):
        result["diagnostics"].append("structure count does not match contournames header")
    return result


def inspect_export(path: str | Path) -> dict:
    from .logs import calculation_log

    with Export(path) as export:
        plans = []
        for name in sorted(export.sizes):
            p = PurePosixPath(name)
            if p.name != "plan" or p.parent.parent.name != "plan":
                continue
            prefix = str(p.parent)
            plan = {"name": p.parent.name, "path": prefix, "settings": {}, "beams": [],
                    "density_overrides": [], "diagnostics": [], "studyset": None}
            try:
                plan.update(plan_metadata(export.read(name), name))
            except FormatError as exc:
                plan["diagnostics"].append(str(exc))
            hyps = [n for n in export.sizes if PurePosixPath(n).parent == p.parent and n.lower().endswith(".hyp")]
            if len(hyps) == 1:
                hyp = HypDocument(export.read(hyps[0]), hyps[0])
                plan["hyp_version"] = hyp.version
                plan["hyp_beam_definition_count"] = len(hyp.directives.get("BEAMDEF", []))
                for key in SPECS:
                    try:
                        field = hyp.get(key)
                        plan["settings"][key] = field.as_dict() if field else None
                    except FormatError as exc:
                        plan["settings"][key] = None
                        plan["diagnostics"].append(str(exc))
            else:
                plan["diagnostics"].append(f"expected one .hyp for single-Rx plan, found {len(hyps)}")
            tel = prefix + "/tel.1"
            if tel in export.sizes:
                try:
                    plan["beams"] = beam_headers(export.read(tel), tel)
                except FormatError as exc:
                    plan["diagnostics"].append(str(exc))
                if plan.get("hyp_beam_definition_count") is not None and len(plan["beams"]) != plan["hyp_beam_definition_count"]:
                    plan["diagnostics"].append(".hyp beam definition count differs from parsed tel.1 beam count")
            else:
                plan["diagnostics"].append("missing tel.1")
            if any(PurePosixPath(n).parent == p.parent and re.fullmatch(r"rx.*plan", PurePosixPath(n).name, re.I)
                   for n in export.sizes):
                plan["diagnostics"].append("multiple prescription files present; association is unsupported")
            plan["calculation_logs"] = []
            for log_name in sorted(n for n in export.sizes if PurePosixPath(n).parent == p.parent and n.lower().endswith(".xlog")):
                try:
                    plan["calculation_logs"].append(calculation_log(export.read(log_name), log_name))
                except FormatError as exc:
                    plan["diagnostics"].append(str(exc))
            plans.append(plan)
        prefixes = sorted({str(PurePosixPath(n).parent) for n in export.sizes
                           if PurePosixPath(n).name == "contournames"})
        studies = [study_metadata(export, p) for p in prefixes]
        for plan in plans:
            matches = [s for s in studies if s["name"] == plan["studyset"]
                       and PurePosixPath(s["path"]).parent == PurePosixPath(plan["path"]).parent.parent]
            if len(matches) != 1:
                plan["diagnostics"].append(f"expected one linked studyset, found {len(matches)}")
            elif matches[0]["diagnostics"]:
                plan["diagnostics"].append("linked studyset has diagnostics")
        return {"schema_version": 1, "source": str(path), "file_count": len(export.sizes),
                "uncompressed_bytes": sum(export.sizes.values()), "plans": plans,
                "studysets": studies,
                "limitations": ["Saved settings do not establish which settings generated saved dose.",
                                "Only supplied single-Rx text layouts are interpreted.",
                                "Absent uncertainty mode is unknown; no Monaco defaults are assumed.",
                                "Native dose, voxel density, geometry, MU and checksums are not interpreted."]}


def compare_settings(settings: dict, expected: dict) -> list[dict]:
    """Compare explicit saved values; a match is not clinical approval."""
    results = []
    if not expected:
        raise ValueError("an expectation profile must contain at least one setting")
    for key, target in expected.items():
        if key not in SPECS:
            raise ValueError(f"unknown expectation key {key!r}")
        kind = SPECS[key][0]
        if kind is bool:
            valid = type(target) is bool
        elif kind is int:
            valid = type(target) is int
        else:
            valid = type(target) in (int, float) and math.isfinite(target)
        if not valid:
            raise ValueError(f"invalid expected value for {key}")
        field = settings.get(key)
        if field is None:
            status, actual, source = "unknown", None, None
        else:
            actual = field["value"]
            matches = (actual == target) if kind in (bool, int) else math.isclose(actual, target, rel_tol=0, abs_tol=1e-12)
            status = "match" if matches else "mismatch"
            source = {"file": field["file"], "line": field["line"], "raw": field["raw"]}
        results.append({"key": key, "expected": target, "actual": actual,
                        "status": status, "source": source})
    return results
