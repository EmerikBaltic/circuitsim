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
        p.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRectF(1, 1, 14, 14), Qt.AlignmentFlag.AlignCenter, "✕")
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

        self.close_btn = QPushButton("✕")
        self.close_btn.setToolTip("Close Problems Panel (Shortcut: F8)")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setFlat(True)
        self.close_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 12px; font-weight: bold; color: #8B949E; border-radius: 3px; }"
            "QPushButton:hover { background-color: #30363D; color: #F0F6FC; }"
        )
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
