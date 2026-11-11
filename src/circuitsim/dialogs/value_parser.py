"""Engineering-notation value parser and formatter.

Follows Section 4 of circuit_simulator_specification.txt:
Inside the app, prefixes are:
    p = pico (1e-12)
    n = nano (1e-9)
    u or µ = micro (1e-6)
    m = milli (1e-3)      [case-sensitive: 'm' is milli, 'M' is mega]
    k or K = kilo (1e3)
    M or meg = mega (1e6)
    G = giga (1e9)
    ('P' is rejected because it is ambiguous between pico and peta.)

Supports a single decimal comma when no dot is present (e.g. "5,65 G" -> 5.65e9)
and optional whitespace between the number, prefix, and unit (e.g. "4.7 k", "5,65 G").

Standard SPICE is case-insensitive, where 'm' and 'M' both mean milli (1e-3)
and mega is written 'meg'. Use `parse_spice_value` when importing SPICE files.
"""

from __future__ import annotations

import math
import re

# Case-sensitive multipliers used across the application UI and netlists.
# Note: Both 'k' and 'K' are accepted for kilo (1e3), whereas 'm' (1e-3) and
# 'M'/'meg' (1e6) remain strictly case-sensitive and 'P' is rejected.
APP_PREFIX_MULTIPLIERS: dict[str, float] = {
    "": 1.0,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "\u00b5": 1e-6,  # MICRO SIGN (µ)
    "\u03bc": 1e-6,  # GREEK SMALL LETTER MU (μ)
    "m": 1e-3,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "meg": 1e6,
    "Meg": 1e6,
    "MEG": 1e6,
    "G": 1e9,
}

# Allowed optional physical unit names that may trail the multiplier prefix.
_KNOWN_UNITS: tuple[str, ...] = (
    "ohms",
    "ohm",
    "Ohm",
    "OHM",
    "\u03a9",  # GREEK CAPITAL LETTER OMEGA (Ω)
    "\u2126",  # OHM SIGN (Ω)
    "Hz",
    "hz",
    "HZ",
    "V",
    "v",
    "A",
    "a",
    "W",
    "w",
    "F",
    "f",
    "H",
    "h",
    "S",
    "s",
)

# Regex matching:
#   group('number'): signed decimal or scientific-notation float
#   group('suffix'): optional trailing prefix + unit characters (with optional internal space)
_VALUE_PATTERN = re.compile(
    r"^\s*(?P<number>[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?)"
    r"\s*(?P<suffix>[a-zA-Z\u00b5\u03bc\u03a9\u2126\s]*?)\s*$"
)

_READABLE_HELP_HINT = (
    "Try 4.7k or 5.65G (use a dot or single comma for decimals; prefixes: p n u m k M G)."
)


def _strip_optional_unit(suffix: str, allowed_prefixes: set[str]) -> str:
    """Strip a trailing physical unit (e.g. 'Ohm', 'V', 'Hz') if present."""
    compact = re.sub(r"\s+", "", suffix)
    if compact in allowed_prefixes:
        return compact

    # Sort longest unit first so 'ohms' matches before 's'.
    for unit in sorted(_KNOWN_UNITS, key=len, reverse=True):
        if compact.endswith(unit):
            candidate_prefix = compact[: -len(unit)]
            if candidate_prefix in allowed_prefixes:
                return candidate_prefix

    return compact


def parse_engineering_value(text: str | float | int) -> float:
    """Parse an application engineering-notation string into a float.

    Examples:
        "4.7k"    -> 4700.0
        "4,7k"    -> 4700.0
        "5,65 G"  -> 5.65e9
        "5.65 G"  -> 5.65e9
        "10K"     -> 10000.0
        "100n"    -> 1e-7
        "2.2u"    -> 2.2e-6
        "1M"      -> 1e6
        "10meg"   -> 1e7
        "15m"     -> 0.015

    Raises:
        ValueError: With a plain-language message if `text` is empty, has
            ambiguous commas/dots, is non-finite, or uses an unknown prefix.
    """
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        val = float(text)
        if not math.isfinite(val):
            raise ValueError(
                f"Couldn't read '{text}'. Please enter a finite number ({_READABLE_HELP_HINT})"
            )
        return val

    if not isinstance(text, str):
        raise ValueError(
            f"Couldn't read value of type {type(text).__name__}. {_READABLE_HELP_HINT}"
        )

    cleaned = text.strip()
    if not cleaned:
        raise ValueError(
            f"Couldn't read empty value. {_READABLE_HELP_HINT}"
        )

    # Check for decimal comma vs. ambiguous comma usage
    comma_count = cleaned.count(",")
    dot_count = cleaned.count(".")
    if comma_count > 1 or (comma_count >= 1 and dot_count >= 1):
        raise ValueError(
            f"Couldn't read '{cleaned}'. Do not mix commas and dots or use thousands "
            f"separators. {_READABLE_HELP_HINT}"
        )

    normalized = cleaned.replace(",", ".", 1) if comma_count == 1 else cleaned

    match = _VALUE_PATTERN.match(normalized)
    if match is None:
        raise ValueError(f"Couldn't read '{cleaned}'. {_READABLE_HELP_HINT}")

    number_str = match.group("number")
    raw_suffix = re.sub(r"\s+", "", match.group("suffix"))

    try:
        base_value = float(number_str)
    except ValueError as exc:
        raise ValueError(
            f"Couldn't read '{cleaned}'. {_READABLE_HELP_HINT}"
        ) from exc

    if not math.isfinite(base_value):
        raise ValueError(f"Couldn't read '{cleaned}'. {_READABLE_HELP_HINT}")

    prefix = _strip_optional_unit(raw_suffix, set(APP_PREFIX_MULTIPLIERS.keys()))
    if prefix not in APP_PREFIX_MULTIPLIERS:
        raise ValueError(
            f"Couldn't read '{cleaned}' (unrecognized prefix '{raw_suffix}'). "
            f"{_READABLE_HELP_HINT}"
        )

    return base_value * APP_PREFIX_MULTIPLIERS[prefix]


def parse_spice_value(text: str | float | int) -> float:
    """Parse a SPICE-notation value string (case-insensitive) into a float.

    In standard SPICE:
        - 'm' and 'M' both mean milli (1e-3)
        - 'meg' (any case) means mega (1e6)
    """
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return parse_engineering_value(text)

    if not isinstance(text, str) or not text.strip():
        raise ValueError("SPICE value string cannot be empty.")

    cleaned = text.strip()
    if cleaned.count(",") == 1 and "." not in cleaned:
        cleaned = cleaned.replace(",", ".", 1)

    match = _VALUE_PATTERN.match(cleaned)
    if match is None:
        raise ValueError(f"Couldn't read SPICE value '{text}'.")

    base_value = float(match.group("number"))
    raw_suffix = re.sub(r"\s+", "", match.group("suffix")).lower()
    if raw_suffix == "\u03bc":
        raw_suffix = "u"

    spice_multipliers: dict[str, float] = {
        "": 1.0,
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "\u00b5": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "meg": 1e6,
        "g": 1e9,
        "t": 1e12,
    }
    prefix = _strip_optional_unit(raw_suffix, set(spice_multipliers.keys()))
    if prefix not in spice_multipliers:
        raise ValueError(f"Unknown SPICE prefix {raw_suffix!r} in {text!r}.")

    return base_value * spice_multipliers[prefix]


_CURRENT_NUMBER_FORMAT: str = "dot"  # "dot", "comma", or "auto"


def set_global_number_format(mode: str) -> None:
    """Set the application-wide number format ('dot', 'comma', or 'auto')."""
    global _CURRENT_NUMBER_FORMAT
    if mode in ("dot", "comma", "auto"):
        _CURRENT_NUMBER_FORMAT = mode


def get_global_number_format() -> str:
    """Return the active application-wide number format setting."""
    return _CURRENT_NUMBER_FORMAT


def get_active_decimal_separator(override: str | None = None) -> str:
    """Return '.' or ',' depending on active number format setting."""
    fmt = override or _CURRENT_NUMBER_FORMAT
    if fmt == "comma":
        return ","
    if fmt == "dot":
        return "."
    # auto: check system locale
    import locale

    try:
        loc_sep = locale.localeconv().get("decimal_point", ".")
        return "," if loc_sep == "," else "."
    except Exception:
        return "."


def format_engineering_value(
    value: float,
    unit: str = "",
    sig_figs: int = 4,
    decimal_separator: str | None = None,
) -> str:
    """Format a floating-point number using readable engineering prefixes.

    Examples:
        format_engineering_value(4700.0, "Ω")  -> "4.7 kΩ" (or "4,7 kΩ")
        format_engineering_value(0.015, "A")   -> "15 mA"
        format_engineering_value(0.0, "V")     -> "0 V"
    """
    if not math.isfinite(value):
        return f"{value} {unit}".strip()

    if abs(value) < 1e-18:
        return f"0 {unit}".strip() if unit else "0"

    scale_table: list[tuple[float, str]] = [
        (1e9, "G"),
        (1e6, "M"),
        (1e3, "k"),
        (1.0, ""),
        (1e-3, "m"),
        (1e-6, "u"),
        (1e-9, "n"),
        (1e-12, "p"),
    ]

    abs_val = abs(value)
    chosen_scale = 1.0
    chosen_prefix = ""
    for scale, prefix in scale_table:
        if abs_val >= scale * 0.999999:
            chosen_scale = scale
            chosen_prefix = prefix
            break
    else:
        chosen_scale, chosen_prefix = scale_table[-1]

    scaled = value / chosen_scale
    formatted_num = f"{scaled:.{sig_figs}g}"

    sep = decimal_separator or get_active_decimal_separator()
    if sep == ",":
        formatted_num = formatted_num.replace(".", ",")

    unit_part = f"{chosen_prefix}{unit}"
    if unit_part:
        return f"{formatted_num} {unit_part}"
    return formatted_num
