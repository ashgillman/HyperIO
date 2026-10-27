"""Literal observations from Monaco calculation logs, not a dose-freshness verdict."""
import math
import re
import xml.etree.ElementTree as ET

from .core import Field, FormatError


PATTERNS = {
    "mc_stddev": (r"mcStdDev:\s*([0-9.eE+-]+)", "fraction (log label mcStdDev)"),
    "entire_calculation_percent": (r"For the entire calculation:\s*([0-9.eE+-]+)\s*percent", "percent (log label)"),
    "per_segment_percent": (r"For each segment \(control point\):\s*([0-9.eE+-]+)\s*percent", "percent (log label)"),
}


def calculation_log(data: bytes, source: str) -> dict:
    try:
        text = data.decode("utf-8-sig")
        root = ET.fromstring("<Events>" + text + "</Events>")
    except (UnicodeDecodeError, ET.ParseError) as exc:
        raise FormatError(f"cannot parse calculation log {source}: {exc}") from exc
    matches = list(re.finditer(r"<Message(?:\s[^>]*)?>", text))
    events = list(root.findall("Log"))
    if len(matches) != len(events):
        raise FormatError(f"expected one message per log event in {source}")
    result = {key: [] for key in PATTERNS}
    result.update({"completion_events": [], "event_count": len(events),
                   "interpretation": "Log observations only; association to current settings/dose is unverified"})
    for event, match in zip(events, matches):
        message = event.findtext("Message") or ""
        line = text.count("\n", 0, match.start()) + 1
        for key, (pattern, unit) in PATTERNS.items():
            found = re.search(pattern, message)
            if found:
                value = float(found[1])
                if not math.isfinite(value):
                    raise FormatError(f"nonfinite log value in {source}:{line}")
                field = Field(value, source, line, message, unit, "literal labelled log observation").as_dict()
                field["time_raw"] = event.findtext("Time")
                result[key].append(field)
        if message.strip() == "Dose Calculation Completed":
            field = Field(message, source, line, message, interpretation="literal log event; dose freshness unverified").as_dict()
            field["time_raw"] = event.findtext("Time")
            result["completion_events"].append(field)
    return result
