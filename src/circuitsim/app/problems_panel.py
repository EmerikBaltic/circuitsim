"""Problems Panel widget displaying structured circuit diagnostics (what, why, how-to-fix)."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from circuitsim.engine.simulation_session import ProblemDiagnostic


def make_severity_icon(severity: str) -> QIcon:
    """Render a crisp 16x16 icon for diagnostic severity (red error, amber warning, blue info)."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    sev = (severity or "info").lower()
    if sev == "error":
        p.setBrush(QBrush(QColor("#FF5252")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 14, 14)
        pen = QPen(QColor("#FFFFFF"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(4.5, 4.5), QPointF(11.5, 11.5))
        p.drawLine(QPointF(11.5, 4.5), QPointF(4.5, 11.5))
    elif sev == "warning":
        p.setBrush(QBrush(QColor("#FFA726")))
        p.setPen(Qt.PenStyle.NoPen)
        tri = QPolygonF([QPointF(8.0, 1.5), QPointF(15.0, 14.5), QPointF(1.0, 14.5)])
        p.drawPolygon(tri)
        p.setPen(QColor("#1A1A1A"))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRectF(1, 3, 14, 12), Qt.AlignmentFlag.AlignCenter, "!")
    else:  # info
        p.setBrush(QBrush(QColor("#2196F3")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 14, 14)
        p.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRectF(1, 1, 14, 14), Qt.AlignmentFlag.AlignCenter, "i")

    p.end()
    return QIcon(pixmap)


def make_close_icon(color: QColor | str = "#8B949E") -> QIcon:
    """Render a crisp 16x16 close cross icon in `color`."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(3.5, 3.5), QPointF(12.5, 12.5))
    p.drawLine(QPointF(12.5, 3.5), QPointF(3.5, 12.5))
    p.end()
    return QIcon(pixmap)


class ProblemsCloseButton(QPushButton):
    """Close button with '✕' text, accessible metadata, and crisp anti-aliased cross rendering."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("✕", parent)
        self.setObjectName("ProblemsCloseBtn")
        self.setMinimumSize(24, 24)
        self.setFixedSize(24, 24)
        self.setToolTip("Close (F8)")
        self.setAccessibleName("Close (F8)")
        self.setAccessibleDescription("Close Problems Panel")
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont("Segoe UI Symbol", 10, QFont.Weight.Bold))
        self._color = QColor("#8B949E")
        self._hover_bg = QColor("#30363D")
        self._hover_color = QColor("#F0F6FC")
        self.setIcon(make_close_icon(self._color))

    def set_theme_colors(
        self,
        fg: QColor | str,
        hover_bg: QColor | str,
        hover_fg: QColor | str,
    ) -> None:
        self._color = QColor(fg)
        self._hover_bg = QColor(hover_bg)
        self._hover_color = QColor(hover_fg)
        self.setIcon(make_close_icon(self._color))
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        is_hover = self.underMouse()
        if is_hover:
            p.setBrush(QBrush(self._hover_bg))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(1.0, 1.0, 22.0, 22.0), 4.0, 4.0)

        color = self._hover_color if is_hover else self._color
        pen = QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        # Center crisp 10x10 cross in 24x24 button
        p.drawLine(QPointF(7.0, 7.0), QPointF(17.0, 17.0))
        p.drawLine(QPointF(17.0, 7.0), QPointF(7.0, 17.0))
        p.end()


class ProblemsPanel(QWidget):
    """Problems panel content widget displaying diagnostics with close button and click navigation."""

    close_requested = Signal()
    problem_activated = Signal(str)  # Emits primary component name to select and center

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(60)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # Header bar with title, problem count, and 'X' close button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(2, 0, 2, 0)

        self.title_label = QLabel("Problems")
        title_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        self.title_label.setFont(title_font)
        header_layout.addWidget(self.title_label)

        self.count_label = QLabel("(0)")
        self.count_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        header_layout.addWidget(self.count_label)

        header_layout.addStretch()

        self.close_btn = ProblemsCloseButton(self)
        self.close_btn.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(self.close_btn)

        layout.addLayout(header_layout)

        # Tree widget listing diagnostics
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Severity", "Explanation", "Part"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

    def update_diagnostics(self, diagnostics: Sequence[ProblemDiagnostic]) -> None:
        """Populate the tree with active problem diagnostics."""
        self.tree.clear()
        n = len(diagnostics)
        self.count_label.setText(f"({n})")

        icons = {
            "error": make_severity_icon("error"),
            "warning": make_severity_icon("warning"),
            "info": make_severity_icon("info"),
        }

        for diag in diagnostics:
            sev_word = diag.severity.capitalize()
            parts_str = ", ".join(diag.component_names) if diag.component_names else "--"
            icon = icons.get(diag.severity.lower(), icons["info"])

            item = QTreeWidgetItem([sev_word, diag.message, parts_str])
            item.setIcon(0, icon)
            item.setData(0, Qt.ItemDataRole.UserRole, diag)
            self.tree.addTopLevelItem(item)

    def set_theme(self, theme: object) -> None:
        """Update colors of panel elements to match theme."""
        from circuitsim.app.themes import ThemeMode, get_theme_palette

        if isinstance(theme, ThemeMode):
            palette = get_theme_palette(theme)
            is_dark = theme == ThemeMode.DARK
        else:
            palette = getattr(theme, "palette", theme)
            bg = str(getattr(palette, "window_bg", "#0d1117")).lower()
            is_dark = bg in ("#0d1117", "#000000", "#161b22")

        if is_dark:
            self.close_btn.set_theme_colors("#8B949E", "#30363D", "#F0F6FC")
            self.count_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        else:
            self.close_btn.set_theme_colors("#57606A", "#E1E4E8", "#24292F")
            self.count_label.setStyleSheet("color: #57606A; font-size: 11px;")

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        _ = column
        diag = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(diag, ProblemDiagnostic) and diag.component_names:
            self.problem_activated.emit(diag.component_names[0])


class ProblemsDock(QDockWidget):
    """Bottom dock widget hosting the ProblemsPanel with default height ~120 px."""

    user_closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Problems", parent)
        self.setObjectName("ProblemsDock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.panel = ProblemsPanel(self)
        self.setWidget(self.panel)
        self.panel.close_requested.connect(self.close)

    def closeEvent(self, event) -> None:
        self.user_closed.emit()
        super().closeEvent(event)
