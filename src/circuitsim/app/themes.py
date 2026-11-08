"""Dark and Light visual themes and color tokens for CircuitSim."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ThemeMode(str, Enum):
    """Supported application visual themes."""

    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True)
class ThemePalette:
    """Color tokens used by the canvas, symbol renderer, and dock widgets."""

    mode: ThemeMode
    window_bg: str
    panel_bg: str
    canvas_bg: str
    grid_minor: str
    grid_major: str
    grid_origin: str
    symbol_stroke: str
    symbol_text: str
    terminal_dot: str
    terminal_hover: str
    selection_accent: str
    ghost_tint: str
    border_color: str


DARK_PALETTE = ThemePalette(
    mode=ThemeMode.DARK,
    window_bg="#161B22",
    panel_bg="#1E242C",
    canvas_bg="#0D1117",
    grid_minor="#21262D",
    grid_major="#30363D",
    grid_origin="#388BFD",
    symbol_stroke="#E6EDF3",
    symbol_text="#C9D1D9",
    terminal_dot="#58A6FF",
    terminal_hover="#FF7B72",
    selection_accent="#388BFD",
    ghost_tint="#58A6FF",
    border_color="#30363D",
)

LIGHT_PALETTE = ThemePalette(
    mode=ThemeMode.LIGHT,
    window_bg="#F6F8FA",
    panel_bg="#FFFFFF",
    canvas_bg="#FFFFFF",
    grid_minor="#EAEEF2",
    grid_major="#D0D7DE",
    grid_origin="#0969DA",
    symbol_stroke="#1F2328",
    symbol_text="#24292F",
    terminal_dot="#0969DA",
    terminal_hover="#CF222E",
    selection_accent="#0969DA",
    ghost_tint="#0969DA",
    border_color="#D0D7DE",
)


def get_theme_palette(mode: ThemeMode | str) -> ThemePalette:
    """Return the `ThemePalette` for `'dark'` or `'light'`."""
    theme = ThemeMode(mode) if not isinstance(mode, ThemeMode) else mode
    return DARK_PALETTE if theme == ThemeMode.DARK else LIGHT_PALETTE


def build_stylesheet(palette: ThemePalette) -> str:
    """Build a Qt Style Sheet (QSS) for the main window and dock panels."""
    return f"""
    QMainWindow, QWidget {{
        background-color: {palette.window_bg};
        color: {palette.symbol_stroke};
        font-family: "Segoe UI", sans-serif;
        font-size: 13px;
    }}
    QMenuBar {{
        background-color: {palette.panel_bg};
        border-bottom: 1px solid {palette.border_color};
    }}
    QMenuBar::item:selected {{
        background-color: {palette.selection_accent};
        color: #FFFFFF;
    }}
    QMenu {{
        background-color: {palette.panel_bg};
        border: 1px solid {palette.border_color};
    }}
    QMenu::item:selected {{
        background-color: {palette.selection_accent};
        color: #FFFFFF;
    }}
    QToolBar {{
        background-color: {palette.panel_bg};
        border-bottom: 1px solid {palette.border_color};
        spacing: 6px;
        padding: 4px;
    }}
    QToolButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QToolButton:hover {{
        border: 1px solid {palette.selection_accent};
    }}
    QDockWidget {{
        titlebar-close-icon: url(none);
        font-weight: 600;
    }}
    QDockWidget::title {{
        background-color: {palette.panel_bg};
        padding: 6px 10px;
        border: 1px solid {palette.border_color};
    }}
    QLineEdit, QTreeWidget, QListWidget, QTextEdit {{
        background-color: {palette.panel_bg};
        border: 1px solid {palette.border_color};
        border-radius: 4px;
        padding: 4px;
    }}
    QPushButton {{
        background-color: {palette.panel_bg};
        border: 1px solid {palette.border_color};
        border-radius: 4px;
        padding: 4px 10px;
    }}
    QPushButton:hover {{
        border: 1px solid {palette.selection_accent};
    }}
    QStatusBar {{
        background-color: {palette.panel_bg};
        border-top: 1px solid {palette.border_color};
    }}
    """
