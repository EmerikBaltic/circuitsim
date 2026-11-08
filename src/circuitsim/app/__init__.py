"""Application window, docks, menus, and themes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from circuitsim.app.themes import ThemeMode, ThemePalette, get_theme_palette

if TYPE_CHECKING:
    from circuitsim.app.main_window import MainWindow

__all__ = [
    "MainWindow",
    "ThemeMode",
    "ThemePalette",
    "get_theme_palette",
]


def __getattr__(name: str) -> object:
    if name == "MainWindow":
        from circuitsim.app.main_window import MainWindow

        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
