"""Extract the FIR registration time for the first case-diary entry."""
import re
from typing import Any


def extract_fir_entry_time(value: Any) -> str:
    """Return a visible FIR time as HH:MM, or an empty string when unavailable."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    patterns = (
        (r"\b(\d{1,2})[:.](\d{2})\s*(AM|PM)\b", True),
        (r"\b(\d{1,2})[:.](\d{2})\s*(?:HRS?|HOURS?)?\b", False),
    )
    for pattern, has_meridiem in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if not match:
            continue
        hour, minute = int(match.group(1)), int(match.group(2))
        if minute > 59 or hour > (12 if has_meridiem else 23) or (hour == 0 and has_meridiem):
            continue
        if has_meridiem:
            hour = hour % 12 + (12 if match.group(3).upper() == "PM" else 0)
        return f"{hour:02d}:{minute:02d}"
    return ""


def fir_entry_time_from_sources(metadata: Any, source_text: Any = "") -> str:
    """Use only the explicit Date and Time of FIR / FIR-registration field.

    Information-received time and Point 12 narrative times are deliberately
    excluded: they describe different events and must not become the diary
    entry time by fallback.
    """
    metadata = metadata if isinstance(metadata, dict) else {}
    registration_value = next((metadata.get(key) for key in (
        "fir_registration_time",
        "fir_registration_datetime",
        "date_time_of_fir",
        "fir_date_time",
    ) if metadata.get(key)), None)
    registration_time = extract_fir_entry_time(registration_value)
    if registration_time:
        return registration_time

    # Allow a text fallback only when the source explicitly labels the value as
    # the FIR's date and time. Never search general prose or an unlabelled time.
    text = str(source_text or "")
    labelled = re.search(
        r"(?im)^\s*(?:date\s*(?:and|&)\s*time\s*of\s*FIR|FIR\s*(?:registration|registered)\s*(?:date\s*(?:and|&)\s*time)?)\s*[-:–]\s*(.*?)\s*$",
        text,
    )
    return extract_fir_entry_time(labelled.group(1)) if labelled else ""
