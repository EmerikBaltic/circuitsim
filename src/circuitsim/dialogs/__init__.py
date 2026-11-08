"""Dialogs and engineering-notation value parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from circuitsim.dialogs.value_parser import (
    format_engineering_value,
    parse_engineering_value,
    parse_spice_value,
)

if TYPE_CHECKING:
    from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog

__all__ = [
    "QuickValueDialog",
    "format_engineering_value",
    "parse_engineering_value",
    "parse_spice_value",
]


def __getattr__(name: str) -> object:
    if name == "QuickValueDialog":
        from circuitsim.dialogs.quick_edit_dialog import QuickValueDialog

        return QuickValueDialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
