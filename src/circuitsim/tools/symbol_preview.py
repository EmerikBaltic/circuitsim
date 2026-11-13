"""Symbol Preview Tool: renders every IEC symbol in Dark and Light themes.

Usage:
    # Open interactive preview window:
    python -m circuitsim.tools.symbol_preview

    # Export a high-resolution PNG reference sheet without opening a window:
    python -m circuitsim.tools.symbol_preview --export symbol_sheet.png
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from circuitsim.app.themes import DARK_PALETTE, LIGHT_PALETTE, ThemePalette
from circuitsim.app_info import APP_NAME
from circuitsim.canvas.symbol_geometry import GRID_PITCH_PX
from circuitsim.canvas.symbol_renderer import SymbolLibrary


def render_symbol_preview_image(
    symbol_library: SymbolLibrary | None = None,
) -> QImage:
    """Render a side-by-side Dark & Light theme reference sheet of all IEC symbols.

    Each row displays one symbol (plus both 'open' and 'closed' states for Switch):
        - Left column: Dark Theme with 20 px grid, bounding box, center crosshair,
          and terminal dots overlaid.
        - Right column: Light Theme with 20 px grid, bounding box, center crosshair,
          and terminal dots overlaid.
    """
    lib = symbol_library or SymbolLibrary()
    catalog = lib.metadata_catalog

    # Build list of (component_id, state, title) rows to render
    rows: list[tuple[str, str | None, str]] = []
    for comp_id, meta in catalog.items():
        if meta.states:
            for state_name in meta.states:
                rows.append(
                    (comp_id, state_name, f"{meta.display_name} [{state_name}]")
                )
        else:
            rows.append((comp_id, None, meta.display_name))

    row_height = 104
    header_height = 48
    col_width = 380
    total_width = col_width * 2
    total_height = header_height + len(rows) * row_height + 20

    image = QImage(total_width, total_height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#161B22"))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    # Draw column backgrounds
    painter.fillRect(
        QRectF(0, 0, col_width, total_height), QColor(DARK_PALETTE.canvas_bg)
    )
    painter.fillRect(
        QRectF(col_width, 0, col_width, total_height),
        QColor(LIGHT_PALETTE.canvas_bg),
    )

    # Headers
    title_font = QFont("Segoe UI", 11)
    title_font.setBold(True)
    painter.setFont(title_font)

    painter.setPen(QColor(DARK_PALETTE.symbol_stroke))
    painter.drawText(
        QRectF(0, 10, col_width, 30),
        Qt.AlignmentFlag.AlignCenter,
        "DARK THEME (Grid 20 px + Terminal Dots)",
    )
    painter.setPen(QColor(LIGHT_PALETTE.symbol_stroke))
    painter.drawText(
        QRectF(col_width, 10, col_width, 30),
        Qt.AlignmentFlag.AlignCenter,
        "LIGHT THEME (Grid 20 px + Terminal Dots)",
    )

    for row_idx, (comp_id, state_name, title) in enumerate(rows):
        y_top = header_height + row_idx * row_height
        _draw_preview_cell(
            painter,
            lib,
            comp_id,
            state_name,
            title,
            QRectF(12, y_top + 6, col_width - 24, row_height - 12),
            DARK_PALETTE,
        )
        _draw_preview_cell(
            painter,
            lib,
            comp_id,
            state_name,
            title,
            QRectF(col_width + 12, y_top + 6, col_width - 24, row_height - 12),
            LIGHT_PALETTE,
        )

    painter.end()
    return image


def _draw_preview_cell(
    painter: QPainter,
    lib: SymbolLibrary,
    comp_id: str,
    state_name: str | None,
    title: str,
    cell_rect: QRectF,
    palette: ThemePalette,
) -> None:
    meta = lib.get_metadata(comp_id)
    w_px, h_px = meta.pixel_size

    painter.save()
    painter.setPen(QPen(QColor(palette.border_color), 1.0))
    painter.drawRoundedRect(cell_rect, 6.0, 6.0)

    # Symbol drawing center on the right side of the cell
    cx = cell_rect.right() - 100.0
    cy = cell_rect.center().y()

    # Draw 20 px grid inside the symbol preview area
    grid_area = QRectF(cx - 60.0, cy - 40.0, 120.0, 80.0)
    painter.setPen(QPen(QColor(palette.grid_major), 1.0))
    for gx in range(-60, 61, GRID_PITCH_PX):
        painter.drawLine(
            QLineF(cx + gx, grid_area.top(), cx + gx, grid_area.bottom())
        )
    for gy in range(-40, 41, GRID_PITCH_PX):
        painter.drawLine(
            QLineF(grid_area.left(), cy + gy, grid_area.right(), cy + gy)
        )

    # Draw dashed footprint box (80x40 or 40x40)
    painter.setPen(QPen(QColor(palette.selection_accent), 1.0, Qt.PenStyle.DashLine))
    painter.drawRect(QRectF(cx - w_px / 2.0, cy - h_px / 2.0, float(w_px), float(h_px)))

    # Draw center origin crosshair at (cx, cy)
    painter.setPen(QPen(QColor(palette.grid_origin), 1.0))
    painter.drawLine(QLineF(cx - 5.0, cy, cx + 5.0, cy))
    painter.drawLine(QLineF(cx, cy - 5.0, cx, cy + 5.0))

    # Paint the symbol and terminal dots
    painter.save()
    painter.translate(cx, cy)
    used_svg = lib.paint_symbol(
        painter,
        comp_id,
        state=state_name,
        stroke_color=palette.symbol_stroke,
        show_terminals=True,
        terminal_color=palette.terminal_hover,
    )
    painter.restore()

    # Text summary on the left side of the cell
    label_font = QFont("Segoe UI", 9)
    label_font.setBold(True)
    painter.setFont(label_font)
    painter.setPen(QColor(palette.symbol_stroke))
    text_rect = QRectF(
        cell_rect.left() + 10.0,
        cell_rect.top() + 8.0,
        cell_rect.width() - 190.0,
        cell_rect.height() - 16.0,
    )
    src_tag = "SVG" if used_svg else "Procedural IEC"
    term_coords = ", ".join(
        f"{t.name}:{list(t.grid_pos)}" for t in meta.terminals
    )
    info_text = (
        f"{title}\n"
        f"id: {comp_id} ({meta.grid_size[0]}x{meta.grid_size[1]} grid = {w_px}x{h_px} px)\n"
        f"terminals: {term_coords}\n"
        f"source: {src_tag}"
    )
    label_font.setBold(False)
    painter.setFont(label_font)
    painter.drawText(
        text_rect,
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        info_text,
    )
    painter.restore()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"Preview all {APP_NAME} IEC symbols in Dark and Light themes."
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=None,
        help="Optional path to save the rendered symbol preview PNG and exit.",
    )
    args = parser.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv)
    lib = SymbolLibrary()
    image = render_symbol_preview_image(lib)

    if lib.warnings:
        for w in lib.warnings:
            print(f"[Symbol Warning] {w}")

    if args.export is not None:
        args.export.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(args.export))
        print(f"Saved symbol preview sheet to {args.export}")
        return 0

    win = QMainWindow()
    win.setWindowTitle(f"{APP_NAME} — IEC Symbol Preview (Dark & Light Themes)")
    win.resize(800, 760)

    scroll = QScrollArea()
    container = QWidget()
    vbox = QVBoxLayout(container)
    lbl = QLabel()
    lbl.setPixmap(QPixmap.fromImage(image))
    vbox.addWidget(lbl)
    scroll.setWidget(container)
    win.setCentralWidget(scroll)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
