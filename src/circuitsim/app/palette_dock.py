"""Left-side Component Palette dock with search filter, categories, and drag-and-drop."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from circuitsim.app.themes import ThemeMode
from circuitsim.canvas.symbol_renderer import SymbolLibrary
from circuitsim.canvas.view import MIME_COMPONENT_ID

CATEGORY_ORDER: tuple[str, ...] = (
    "Sources",
    "Passive",
    "Switches",
    "Semiconductors",
    "Loads",
    "Instruments",
)

# Explicit component ordering within each category (matching Section 3.1 of spec)
COMPONENT_ORDER_IN_CATEGORY: dict[str, tuple[str, ...]] = {
    "Sources": ("dc_voltage", "ac_voltage", "dc_current", "ground"),
    "Passive": ("resistor", "capacitor", "inductor"),
    "Switches": ("switch",),
    "Semiconductors": ("led",),
    "Loads": ("lightbulb",),
    "Instruments": ("voltmeter", "ammeter"),
}


class _PaletteTreeWidget(QTreeWidget):
    """Tree widget starting a `QDrag` with `MIME_COMPONENT_ID` when a part is dragged."""

    def __init__(self, symbol_library: SymbolLibrary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.symbol_library: SymbolLibrary = symbol_library
        self.theme: ThemeMode = ThemeMode.DARK
        self.setHeaderHidden(True)
        self.setIconSize(QSize(48, 22))
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAnimated(True)
        self.setIndentation(12)
        self.setUniformRowHeights(True)

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        _ = supported_actions
        item = self.currentItem()
        if item is None:
            return
        comp_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not comp_id:
            return

        mime = QMimeData()
        mime.setData(MIME_COMPONENT_ID, QByteArray(str(comp_id).encode("utf-8")))

        drag = QDrag(self)
        drag.setMimeData(mime)
        icon = self.symbol_library.create_palette_icon(
            str(comp_id), theme=self.theme, size=(80, 40)
        )
        pixmap = icon.pixmap(80, 40)
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        drag.exec(Qt.DropAction.CopyAction)


class ComponentPaletteWidget(QWidget):
    """Component palette containing a search bar and categorized draggable parts."""

    component_activated = Signal(str)  # Emits component_id on double-click

    def __init__(
        self,
        symbol_library: SymbolLibrary,
        *,
        theme: ThemeMode = ThemeMode.DARK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.symbol_library: SymbolLibrary = symbol_library
        self.theme: ThemeMode = theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search components (e.g. voltmeter, resistor)...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._apply_search_filter)
        layout.addWidget(self.search_input)

        self.tree = _PaletteTreeWidget(symbol_library, self)
        self.tree.theme = theme
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

        self._populate_tree()

    def set_theme(self, theme: ThemeMode) -> None:
        """Rebuild palette icons for the active theme."""
        self.theme = theme
        self.tree.theme = theme
        self._populate_tree()
        self._apply_search_filter(self.search_input.text())

    def _populate_tree(self) -> None:
        self.tree.clear()
        catalog = self.symbol_library.metadata_catalog

        grouped: dict[str, list[str]] = {cat: [] for cat in CATEGORY_ORDER}
        for comp_id, meta in catalog.items():
            grouped.setdefault(meta.category, []).append(comp_id)

        for category, comp_ids in grouped.items():
            if not comp_ids:
                continue
            preferred = COMPONENT_ORDER_IN_CATEGORY.get(category, ())
            comp_ids.sort(
                key=lambda cid: (
                    preferred.index(cid) if cid in preferred else 999,
                    cid,
                )
            )
            cat_item = QTreeWidgetItem(self.tree, [category])
            cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            cat_item.setExpanded(True)

            for comp_id in comp_ids:
                meta = catalog[comp_id]
                part_item = QTreeWidgetItem(cat_item, [meta.display_name])
                part_item.setData(0, Qt.ItemDataRole.UserRole, comp_id)
                part_item.setSizeHint(0, QSize(180, 26))
                part_item.setToolTip(
                    0,
                    f"{meta.display_name} ({comp_id})\n"
                    "Drag onto the canvas or double-click to place at center.",
                )
                part_item.setIcon(
                    0,
                    self.symbol_library.create_palette_icon(
                        comp_id, theme=self.theme, size=(48, 22)
                    ),
                )

        self.tree.expandAll()

    def _apply_search_filter(self, query: str) -> None:
        needle = query.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            cat_item = self.tree.topLevelItem(i)
            if cat_item is None:
                continue
            cat_name = cat_item.text(0).lower()
            visible_children = 0
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                if child is None:
                    continue
                comp_id = str(child.data(0, Qt.ItemDataRole.UserRole) or "").lower()
                label = child.text(0).lower()
                matches = (
                    not needle
                    or needle in label
                    or needle in comp_id
                    or needle in cat_name
                )
                child.setHidden(not matches)
                if matches:
                    visible_children += 1
            cat_item.setHidden(visible_children == 0)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        _ = column
        comp_id = item.data(0, Qt.ItemDataRole.UserRole)
        if comp_id:
            self.component_activated.emit(str(comp_id))
            _ = QPointF
