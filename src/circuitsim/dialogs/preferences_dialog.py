"""Preferences dialog for application-wide user settings (e.g. Number format)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from circuitsim.app.settings import AppSettings
from circuitsim.dialogs.value_parser import set_global_number_format


class PreferencesDialog(QDialog):
    """Preferences dialog managing number format and other app settings."""

    def __init__(
        self, settings: AppSettings, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.settings: AppSettings = settings
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(8)

        self.combo_number_format = QComboBox(self)
        self.combo_number_format.addItem("Automatic (System locale)", "auto")
        self.combo_number_format.addItem("Dot: 4.7 kΩ", "dot")
        self.combo_number_format.addItem("Comma: 4,7 kΩ", "comma")

        current_fmt = settings.get_number_format()
        idx = self.combo_number_format.findData(current_fmt)
        if idx >= 0:
            self.combo_number_format.setCurrentIndex(idx)

        form.addRow("Number format:", self.combo_number_format)

        self.combo_meters_mode = QComboBox(self)
        self.combo_meters_mode.setObjectName("combo_meters_mode")
        self.combo_meters_mode.addItem("Ideal", "ideal")
        self.combo_meters_mode.addItem("Realistic", "realistic")

        current_meter_mode = settings.get_new_meters_mode()
        idx_meter = self.combo_meters_mode.findData(current_meter_mode)
        if idx_meter >= 0:
            self.combo_meters_mode.setCurrentIndex(idx_meter)

        form.addRow("New meters are:", self.combo_meters_mode)
        layout.addLayout(form)

        hint = QLabel(
            "Controls display formatting across schematic labels, meter readouts, "
            "tooltips, and dialogs. Both dot and comma are always accepted when typing inputs."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8B949E; font-size: 11px;")
        layout.addWidget(hint)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_accept(self) -> None:
        fmt = str(self.combo_number_format.currentData())
        self.settings.set_number_format(fmt)
        set_global_number_format(fmt)
        meter_mode = str(self.combo_meters_mode.currentData())
        self.settings.set_new_meters_mode(meter_mode)
        self.accept()
