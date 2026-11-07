"""Unit tests for the engineering-notation value parser and formatter."""

from __future__ import annotations

import math
import pytest

from circuitsim.dialogs.value_parser import (
    format_engineering_value,
    parse_engineering_value,
    parse_spice_value,
)


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("4.7k", 4.7e3),
        ("100n", 100e-9),
        ("2.2u", 2.2e-6),
        ("2.2µ", 2.2e-6),
        ("2.2μ", 2.2e-6),
        ("1M", 1e6),
        ("10meg", 10e6),
        ("10MEG", 10e6),
        ("15m", 15e-3),
        ("10p", 10e-12),
        ("1G", 1e9),
        ("240", 240.0),
        ("-5.5k", -5500.0),
        ("  3.3kOhm ", 3300.0),
        ("100nF", 100e-9),
        ("120V", 120.0),
        ("50mA", 0.05),
        ("1.5e3", 1500.0),
    ],
)
def test_parse_engineering_value_valid(raw_text: str, expected: float) -> None:
    """Verify required specification strings and case-sensitive prefixes."""
    result = parse_engineering_value(raw_text)
    assert math.isclose(result, expected, rel_tol=1e-12, abs_tol=1e-18)


def test_case_sensitive_milli_vs_mega() -> None:
    """Ensure 'm' is milli (1e-3) and 'M' or 'meg' is mega (1e6) in app mode."""
    assert math.isclose(parse_engineering_value("1m"), 1e-3, rel_tol=1e-12)
    assert math.isclose(parse_engineering_value("1M"), 1e6, rel_tol=1e-12)
    assert math.isclose(parse_engineering_value("1meg"), 1e6, rel_tol=1e-12)
    assert math.isclose(
        parse_engineering_value("1M") / parse_engineering_value("1m"),
        1e9,
        rel_tol=1e-12,
    )


@pytest.mark.parametrize(
    "invalid_input",
    [
        "",
        "   ",
        "abc",
        "4.7Q",
        "10K",  # Uppercase 'K' is rejected in strict case-sensitive app mode
        "10P",
        "--5k",
        "4.7.2k",
        "k4.7",
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_parse_engineering_value_invalid(invalid_input: str | float) -> None:
    """Verify malformed or out-of-spec strings raise ValueError."""
    with pytest.raises(ValueError):
        parse_engineering_value(invalid_input)


def test_parse_spice_value_compatibility() -> None:
    """In SPICE, both 'm' and 'M' mean milli (1e-3), while 'meg' means mega (1e6)."""
    assert math.isclose(parse_spice_value("15m"), 15e-3, rel_tol=1e-12)
    assert math.isclose(parse_spice_value("15M"), 15e-3, rel_tol=1e-12)
    assert math.isclose(parse_spice_value("10meg"), 10e6, rel_tol=1e-12)
    assert math.isclose(parse_spice_value("10MEG"), 10e6, rel_tol=1e-12)
    assert math.isclose(parse_spice_value("4.7K"), 4700.0, rel_tol=1e-12)


def test_format_engineering_value() -> None:
    """Verify human-readable engineering formatting with auto-ranging prefixes."""
    assert format_engineering_value(4700.0, "Ω") == "4.7 kΩ"
    assert format_engineering_value(0.015, "A") == "15 mA"
    assert format_engineering_value(-0.0022, "V") == "-2.2 mV"
    assert format_engineering_value(0.0, "V") == "0 V"
