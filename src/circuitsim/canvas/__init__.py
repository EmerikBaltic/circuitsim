"""Interactive circuit schematic canvas, symbol geometry, and graphics items."""

from circuitsim.canvas.symbol_geometry import (
    DEFAULT_IEC_SYMBOLS_DIR,
    GRID_PITCH_PX,
    PreparedSvg,
    SymbolMetadata,
    TerminalSpec,
    grid_to_px,
    load_all_iec_metadata,
    load_symbol_metadata,
    parse_symbol_metadata_dict,
    prepare_svg_for_theme,
    px_to_grid,
    snap_to_grid,
    transform_terminal_position,
)

__all__ = [
    "DEFAULT_IEC_SYMBOLS_DIR",
    "GRID_PITCH_PX",
    "PreparedSvg",
    "SymbolMetadata",
    "TerminalSpec",
    "grid_to_px",
    "load_all_iec_metadata",
    "load_symbol_metadata",
    "parse_symbol_metadata_dict",
    "prepare_svg_for_theme",
    "px_to_grid",
    "snap_to_grid",
    "transform_terminal_position",
]
