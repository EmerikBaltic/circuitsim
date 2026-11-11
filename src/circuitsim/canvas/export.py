"""Schematic export utilities for rendering to PNG images and SVG vector files."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from circuitsim.app.themes import ThemeMode, get_theme_palette
from circuitsim.canvas.scene import CircuitScene


def compute_schematic_bounds(
    scene: CircuitScene, margin_px: float = 20.0
) -> QRectF | None:
    """Compute the combined bounding rectangle of all placed components and wires plus margin."""
    has_content = False
    rect = QRectF()
    for item in scene.placed_items:
        rect = rect.united(item.sceneBoundingRect())
        has_content = True
    for wire in scene.placed_wires:
        rect = rect.united(wire.sceneBoundingRect())
        has_content = True

    if not has_content or rect.isEmpty():
        return None
    return rect.adjusted(-margin_px, -margin_px, margin_px, margin_px)


class _ExportSceneGuard:
    """Context manager to ensure clean schematic rendering without selection handles or hover dots."""

    def __init__(self, scene: CircuitScene, target_theme: ThemeMode) -> None:
        self.scene: CircuitScene = scene
        self.target_theme: ThemeMode = target_theme
        self.prev_selected: list = []
        self.prev_hover = None
        self.prev_ghost_visible: bool = False
        self.prev_theme: ThemeMode = scene.theme
        self.prev_grid: bool = scene.show_grid

    def __enter__(self) -> _ExportSceneGuard:
        self.prev_selected = list(self.scene.selectedItems())
        self.scene.clearSelection()
        self.prev_hover = self.scene._hovered_terminal_pt
        self.scene._hovered_terminal_pt = None
        if self.scene._ghost_item is not None:
            self.prev_ghost_visible = self.scene._ghost_item.isVisible()
            self.scene._ghost_item.setVisible(False)
        self.prev_grid = self.scene.show_grid
        self.scene.show_grid = False
        if self.target_theme != self.prev_theme:
            self.scene.set_theme(self.target_theme)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.target_theme != self.prev_theme:
            self.scene.set_theme(self.prev_theme)
        self.scene.show_grid = self.prev_grid
        self.scene._hovered_terminal_pt = self.prev_hover
        if self.scene._ghost_item is not None:
            self.scene._ghost_item.setVisible(self.prev_ghost_visible)
        for it in self.prev_selected:
            it.setSelected(True)


def export_schematic_to_image(
    scene: CircuitScene,
    *,
    margin_px: float = 20.0,
    theme_mode: ThemeMode = ThemeMode.LIGHT,
) -> QImage | None:
    """Render the schematic to a `QImage` tightly fitted to content plus margin."""
    bounds = compute_schematic_bounds(scene, margin_px=margin_px)
    if bounds is None:
        return None

    w = max(1, int(round(bounds.width())))
    h = max(1, int(round(bounds.height())))
    image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)

    with _ExportSceneGuard(scene, theme_mode):
        if theme_mode == ThemeMode.LIGHT:
            bg_color = Qt.GlobalColor.white
        else:
            palette = get_theme_palette(theme_mode)
            bg_color = QColor(palette.canvas_bg)
        image.fill(bg_color)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        scene.render(painter, target=QRectF(0, 0, w, h), source=bounds)
        painter.end()

    return image


def export_schematic_to_svg(
    scene: CircuitScene,
    output_path: str | Path,
    *,
    margin_px: float = 20.0,
    theme_mode: ThemeMode = ThemeMode.LIGHT,
) -> bool:
    """Render the schematic to an SVG file tightly fitted to content plus margin."""
    bounds = compute_schematic_bounds(scene, margin_px=margin_px)
    if bounds is None:
        return False

    w = max(1, int(round(bounds.width())))
    h = max(1, int(round(bounds.height())))
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with _ExportSceneGuard(scene, theme_mode):
        generator = QSvgGenerator()
        generator.setFileName(str(out_file))
        generator.setSize(QSize(w, h))
        generator.setViewBox(QRectF(0, 0, w, h))

        painter = QPainter(generator)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        if theme_mode == ThemeMode.LIGHT:
            bg_color = Qt.GlobalColor.white
        else:
            palette = get_theme_palette(theme_mode)
            bg_color = QColor(palette.canvas_bg)
        painter.fillRect(QRectF(0, 0, w, h), bg_color)
        scene.render(painter, target=QRectF(0, 0, w, h), source=bounds)
        painter.end()

    return True


class ExportOptionsDialog(QDialog):
    """Dialog allowing user to choose export appearance (White background vs Current theme)."""

    def __init__(
        self, current_theme: ThemeMode, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Schematic Appearance")
        self.setModal(True)
        layout = QVBoxLayout(self)

        lbl = QLabel("Choose schematic export appearance:", self)
        layout.addWidget(lbl)

        self.radio_white = QRadioButton(
            "White background with dark lines (recommended for printing & documents)",
            self,
        )
        self.radio_white.setChecked(True)
        layout.addWidget(self.radio_white)

        theme_name = current_theme.name.title()
        self.radio_current = QRadioButton(
            f"Current theme ({theme_name})", self
        )
        layout.addWidget(self.radio_current)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.current_theme: ThemeMode = current_theme

    def selected_theme_mode(self) -> ThemeMode:
        if self.radio_white.isChecked():
            return ThemeMode.LIGHT
        return self.current_theme
