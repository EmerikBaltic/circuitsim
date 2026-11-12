"""Double-click Quick Value Editing Dialog built from `ComponentParameter` metadata."""

from __future__ import annotations

from typing import Callable
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from circuitsim.components.base import Component, ComponentParameter
from circuitsim.components.led import LED, LED_COLOUR_PRESETS
from circuitsim.components.lightbulb import Lightbulb
from circuitsim.components.meters import Ammeter, Voltmeter
from circuitsim.components.switch import Switch
from circuitsim.dialogs.value_parser import (
    format_engineering_value,
    parse_engineering_value,
)


class QuickValueDialog(QDialog):
    """Compact parameter editor opened when double-clicking a schematic component.

    Features:
        - Dynamically builds input rows from `component.get_editable_parameters()`
          so Milestone 3 can extend it into the full multi-tab properties dialog.
        - Validates all inputs using `parse_engineering_value` (case-sensitive
          engineering notation: `m` = milli, `M`/`meg` = mega, `u`/`µ` = micro).
        - Displays a readable inline error message when an entry is invalid
          without closing or crashing.
        - Supports live application (`Apply` or `OK`) while the simulation runs.
    """

    def __init__(
        self,
        component: Component,
        *,
        on_apply: Callable[[dict[str, float], bool], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.component: Component = component
        self._on_apply = on_apply
        self._param_specs: tuple[ComponentParameter, ...] = (
            component.get_editable_parameters()
        )
        self.inputs: dict[str, QLineEdit] = {}
        self.preview_labels: dict[str, QLabel] = {}
        self.applied_values: dict[str, float] = {}

        self.setWindowTitle(f"Edit {component.name} ({component.component_type})")
        self.setMinimumWidth(380)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        header = QLabel(
            f"<b>{component.name}</b> — Enter values using engineering prefixes "
            "(`p`, `n`, `u`, `m`, `k`/`K`, `M`/`meg`, `G`):"
        )
        header.setWordWrap(True)
        root_layout.addWidget(header)

        self.live_edit_note_label = QLabel(
            "Changes apply immediately while the simulation is running."
        )
        self.live_edit_note_label.setWordWrap(True)
        self.live_edit_note_label.setStyleSheet(
            "color: #58A6FF; font-size: 11px; font-style: italic;"
        )
        root_layout.addWidget(self.live_edit_note_label)

        self._updating_color: bool = False
        self._updating_vf: bool = False
        self._updating_meter: bool = False
        self.led_color_combo: QComboBox | None = None
        self.led_datasheet_lbl: QLabel | None = None
        self.led_datasheet_hint_lbl: QLabel | None = None
        self.led_burnout_cb: QCheckBox | None = None
        self.led_burnout_current_edit: QLineEdit | None = None
        self.meter_preset_combo: QComboBox | None = None
        self.meter_loading_notice_label: QLabel | None = None
        self.meter_ideal_hint_lbl: QLabel | None = None

        form = QFormLayout()
        form.setSpacing(8)

        if isinstance(component, (Voltmeter, Ammeter)):
            self.meter_preset_combo = QComboBox(self)
            self.meter_preset_combo.setObjectName("meter_preset_combo")
            if isinstance(component, Voltmeter):
                self.meter_preset_combo.addItem("Ideal", "ideal")
                self.meter_preset_combo.addItem("10 Mohm (typical multimeter)", "10M")
                self.meter_preset_combo.addItem("1 Mohm", "1M")
                self.meter_preset_combo.addItem("Custom", "custom")
                if component.is_ideal:
                    self.meter_preset_combo.setCurrentText("Ideal")
                elif math.isclose(component.r_internal, 10e6, rel_tol=1e-3):
                    self.meter_preset_combo.setCurrentText("10 Mohm (typical multimeter)")
                elif math.isclose(component.r_internal, 1e6, rel_tol=1e-3):
                    self.meter_preset_combo.setCurrentText("1 Mohm")
                else:
                    self.meter_preset_combo.setCurrentText("Custom")
            else:
                self.meter_preset_combo.addItem("Ideal (0 V branch)", "ideal")
                self.meter_preset_combo.addItem("1 mohm", "1m")
                self.meter_preset_combo.addItem("Custom", "custom")
                if component.is_ideal:
                    self.meter_preset_combo.setCurrentText("Ideal (0 V branch)")
                elif math.isclose(component.r_internal, 1e-3, rel_tol=1e-3):
                    self.meter_preset_combo.setCurrentText("1 mohm")
                else:
                    self.meter_preset_combo.setCurrentText("Custom")

            self.meter_preset_combo.currentTextChanged.connect(self._on_meter_preset_changed)

        if isinstance(component, LED):
            self.led_color_combo = QComboBox(self)
            self.led_color_combo.setObjectName("led_color_combo")
            for cname, cinfo in LED_COLOUR_PRESETS.items():
                pix = QPixmap(16, 16)
                pix.fill(QColor(str(cinfo["hex"])))
                self.led_color_combo.addItem(QIcon(pix), cname)

            self.led_color_combo.setCurrentText(component.color_name)
            self.led_color_combo.currentTextChanged.connect(self._on_led_color_changed)
            form.addRow("Colour:", self.led_color_combo)

        for spec in self._param_specs:
            field_container = QWidget(self)
            field_vbox = QVBoxLayout(field_container)
            field_vbox.setContentsMargins(0, 0, 0, 0)
            field_vbox.setSpacing(2)

            row_widget = QWidget(field_container)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            line_edit = QLineEdit(component.format_parameter_value(spec.key))
            line_edit.setPlaceholderText(f"e.g. 4.7k, 5,65 G ({spec.unit})")
            self.inputs[spec.key] = line_edit
            row_layout.addWidget(line_edit, stretch=1)

            unit_lbl = QLabel(spec.unit)
            unit_lbl.setMinimumWidth(24)
            row_layout.addWidget(unit_lbl)
            field_vbox.addWidget(row_widget)

            preview_lbl = QLabel("")
            preview_lbl.setStyleSheet("color: #8B949E; font-size: 11px;")
            self.preview_labels[spec.key] = preview_lbl
            field_vbox.addWidget(preview_lbl)

            if isinstance(component, Switch) and spec.key == "v_breakdown":
                arc_hint_lbl = QLabel(
                    "Contact arc is a simplified model: a switch with more "
                    "than this voltage across it can arc. Set to 0 for an ideal contact."
                )
                arc_hint_lbl.setObjectName("switch_arc_hint_label")
                arc_hint_lbl.setWordWrap(True)
                arc_hint_lbl.setStyleSheet(
                    "color: #8B949E; font-size: 11px; font-style: italic;"
                )
                field_vbox.addWidget(arc_hint_lbl)

            if isinstance(component, (Voltmeter, Ammeter)) and spec.key == "r_internal":
                if self.meter_preset_combo is not None:
                    field_vbox.insertWidget(0, self.meter_preset_combo)

                if isinstance(component, Voltmeter):
                    self.meter_ideal_hint_lbl = QLabel(
                        "Reads the voltage between its nets without loading the circuit.", self
                    )
                    self.meter_ideal_hint_lbl.setObjectName("meter_ideal_hint_lbl")
                    self.meter_ideal_hint_lbl.setWordWrap(True)
                    self.meter_ideal_hint_lbl.setStyleSheet("color: #58A6FF; font-size: 11px;")
                    self.meter_ideal_hint_lbl.setVisible(component.is_ideal)
                    field_vbox.addWidget(self.meter_ideal_hint_lbl)

                    if component.loading_error_message:
                        self.meter_loading_notice_label = QLabel(component.loading_error_message, self)
                        self.meter_loading_notice_label.setObjectName("meter_loading_notice_label")
                        self.meter_loading_notice_label.setWordWrap(True)
                        self.meter_loading_notice_label.setStyleSheet(
                            "color: #E3B341; font-size: 11px; font-weight: 500; padding: 4px; "
                            "background: rgba(227, 179, 65, 0.1); border: 1px solid #E3B341; border-radius: 4px;"
                        )
                        field_vbox.addWidget(self.meter_loading_notice_label)
                elif isinstance(component, Ammeter):
                    self.meter_ideal_hint_lbl = QLabel(
                        "0 V branch: keeps parallel and loop diagnostics.", self
                    )
                    self.meter_ideal_hint_lbl.setObjectName("meter_ideal_hint_lbl")
                    self.meter_ideal_hint_lbl.setWordWrap(True)
                    self.meter_ideal_hint_lbl.setStyleSheet("color: #58A6FF; font-size: 11px;")
                    self.meter_ideal_hint_lbl.setVisible(component.is_ideal)
                    field_vbox.addWidget(self.meter_ideal_hint_lbl)

                if component.is_ideal:
                    line_edit.setEnabled(False)
                    line_edit.setText("Ideal")
                    preview_lbl.setText(
                        "Ideal (no loading)" if isinstance(component, Voltmeter) else "Ideal (0 V branch)"
                    )

            if isinstance(component, LED) and spec.key == "forward_voltage":
                cname = component.color_name
                preset = LED_COLOUR_PRESETS.get(cname, LED_COLOUR_PRESETS["Red"])
                vf_val = preset["forward_voltage"]
                vf_text = (
                    f"Forward voltage at 20 mA: {vf_val:.1f} V "
                    f"(datasheet range {preset['datasheet_range']})"
                    if cname != "Custom"
                    else "Forward voltage: user defined (Custom)"
                )
                self.led_datasheet_lbl = QLabel(vf_text, self)
                self.led_datasheet_lbl.setObjectName("led_datasheet_lbl")
                self.led_datasheet_lbl.setWordWrap(True)
                self.led_datasheet_lbl.setStyleSheet("color: #58A6FF; font-size: 11px;")
                field_vbox.addWidget(self.led_datasheet_lbl)

                self.led_datasheet_hint_lbl = QLabel(
                    "typical datasheet values; real LEDs vary by about +-0.3 V", self
                )
                self.led_datasheet_hint_lbl.setObjectName("led_datasheet_hint_lbl")
                self.led_datasheet_hint_lbl.setWordWrap(True)
                self.led_datasheet_hint_lbl.setStyleSheet(
                    "color: #8B949E; font-size: 11px; font-style: italic;"
                )
                field_vbox.addWidget(self.led_datasheet_hint_lbl)

            line_edit.textChanged.connect(
                lambda _text, s=spec: self._on_field_text_changed(s)
            )
            self._update_field_preview(spec)

            if isinstance(component, Voltmeter) and spec.key == "r_internal":
                row_label = "Input resistance:"
            elif isinstance(component, Ammeter) and spec.key == "r_internal":
                row_label = "Series resistance:"
            else:
                row_label = f"{spec.label}:"
            form.addRow(row_label, field_container)

        self.switch_closed_cb: QCheckBox | None = None
        if isinstance(component, Switch):
            self.switch_closed_cb = QCheckBox("Switch Closed (ON)")
            self.switch_closed_cb.setChecked(component.closed)
            form.addRow("State:", self.switch_closed_cb)

        self.bulb_burnout_cb: QCheckBox | None = None
        self.burnout_ratio_edit: QLineEdit | None = None
        self.burnout_time_edit: QLineEdit | None = None
        if isinstance(component, Lightbulb):
            self.bulb_burnout_cb = QCheckBox("Enable burn-out on overload")
            self.bulb_burnout_cb.setObjectName("bulb_burnout_cb")
            self.bulb_burnout_cb.setChecked(component.burnout_enabled)
            form.addRow("Burn-out:", self.bulb_burnout_cb)

            burnout_hint_lbl = QLabel(
                "Simplified burn-out model: if dissipated power exceeds "
                "rated power by this ratio for the specified duration, "
                "the filament burns out and becomes an open circuit."
            )
            burnout_hint_lbl.setObjectName("bulb_burnout_hint_label")
            burnout_hint_lbl.setWordWrap(True)
            burnout_hint_lbl.setStyleSheet(
                "color: #8B949E; font-size: 11px; font-style: italic;"
            )
            form.addRow("", burnout_hint_lbl)

            self.burnout_ratio_edit = QLineEdit(str(component.burnout_power_ratio))
            self.burnout_ratio_edit.setObjectName("burnout_ratio_edit")
            form.addRow("Burn-out Power Ratio:", self.burnout_ratio_edit)

            self.burnout_time_edit = QLineEdit(
                format_engineering_value(component.burnout_time, "s")
            )
            self.burnout_time_edit.setObjectName("burnout_time_edit")
            form.addRow("Burn-out Duration:", self.burnout_time_edit)

        if isinstance(component, LED):
            self.led_burnout_cb = QCheckBox("Enable burn-out on overload")
            self.led_burnout_cb.setObjectName("led_burnout_cb")
            self.led_burnout_cb.setChecked(component.burnout_enabled)
            form.addRow("Burn-out:", self.led_burnout_cb)

            burnout_thresh = format_engineering_value(component.burnout_current, "A")
            self.led_burnout_current_edit = QLineEdit(burnout_thresh)
            self.led_burnout_current_edit.setObjectName("led_burnout_current_edit")
            form.addRow("Burn-out Current Threshold:", self.led_burnout_current_edit)

        self.show_value_cb = QCheckBox("Show value on schematic canvas")
        self.show_value_cb.setChecked(component.show_value)
        form.addRow("Display:", self.show_value_cb)

        root_layout.addLayout(form)

        # Readable error banner (hidden until an invalid input is entered)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            "color: #FF6B6B; font-weight: 600; padding: 4px;"
        )
        self.error_label.setVisible(False)
        root_layout.addWidget(self.error_label)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        btn_box.accepted.connect(self._on_ok_clicked)
        btn_box.rejected.connect(self.reject)
        apply_btn = btn_box.button(QDialogButtonBox.StandardButton.Apply)
        if apply_btn is not None:
            apply_btn.clicked.connect(self._on_apply_clicked)
        root_layout.addWidget(btn_box)

    def _clear_error(self) -> None:
        if self.error_label.isVisible():
            self.error_label.clear()
            self.error_label.setVisible(False)

    def _on_led_color_changed(self, color_name: str) -> None:
        if self._updating_color or not isinstance(self.component, LED):
            return
        if color_name in LED_COLOUR_PRESETS and color_name != "Custom":
            preset = LED_COLOUR_PRESETS[color_name]
            self._updating_vf = True
            vf_val = float(preset["forward_voltage"])
            if "forward_voltage" in self.inputs:
                self.inputs["forward_voltage"].setText(str(vf_val))
            if self.led_datasheet_lbl is not None:
                self.led_datasheet_lbl.setText(
                    f"Forward voltage at 20 mA: {vf_val:.1f} V "
                    f"(datasheet range {preset['datasheet_range']})"
                )
            self._updating_vf = False
        elif color_name == "Custom" and self.led_datasheet_lbl is not None:
            self.led_datasheet_lbl.setText("Forward voltage: user defined (Custom)")

    def _on_meter_preset_changed(self, text: str) -> None:
        if self._updating_meter or not isinstance(self.component, (Voltmeter, Ammeter)):
            return
        self._updating_meter = True
        low = text.lower()
        line_edit = self.inputs.get("r_internal")
        is_ideal = "ideal" in low

        if self.meter_ideal_hint_lbl is not None:
            self.meter_ideal_hint_lbl.setVisible(is_ideal)

        if line_edit is not None:
            if is_ideal:
                line_edit.setEnabled(False)
                line_edit.setText("Ideal")
            else:
                line_edit.setEnabled(True)
                if "10" in text:
                    line_edit.setText("10M")
                elif isinstance(self.component, Voltmeter) and ("1m" in low or "1 mohm" in low or "1 meg" in low):
                    line_edit.setText("1M")
                elif isinstance(self.component, Ammeter) and ("1m" in low or "1 mohm" in low):
                    line_edit.setText("1m")
                elif "custom" in low:
                    if line_edit.text() in ("Ideal", ""):
                        line_edit.setText(
                            self.component.format_parameter_value("r_internal")
                        )
            spec = next((s for s in self._param_specs if s.key == "r_internal"), None)
            if spec is not None:
                self._update_field_preview(spec)

        self._updating_meter = False

    def _on_field_text_changed(self, spec: ComponentParameter) -> None:
        self._clear_error()
        self._update_field_preview(spec)

        if (
            isinstance(self.component, (Voltmeter, Ammeter))
            and spec.key == "r_internal"
            and not self._updating_meter
            and self.meter_preset_combo is not None
        ):
            curr_text = self.inputs[spec.key].text().strip()
            curr_preset = self.meter_preset_combo.currentText().lower()
            if "ideal" not in curr_preset and curr_preset != "custom":
                try:
                    val = parse_engineering_value(curr_text)
                    if isinstance(self.component, Voltmeter):
                        if "10" in curr_preset and not math.isclose(val, 10e6, rel_tol=1e-3):
                            self._updating_meter = True
                            self.meter_preset_combo.setCurrentText("Custom")
                            self._updating_meter = False
                        elif "1 m" in curr_preset and not math.isclose(val, 1e6, rel_tol=1e-3):
                            self._updating_meter = True
                            self.meter_preset_combo.setCurrentText("Custom")
                            self._updating_meter = False
                    elif isinstance(self.component, Ammeter):
                        if "1 m" in curr_preset and not math.isclose(val, 1e-3, rel_tol=1e-3):
                            self._updating_meter = True
                            self.meter_preset_combo.setCurrentText("Custom")
                            self._updating_meter = False
                except Exception:
                    pass

        if (
            isinstance(self.component, LED)
            and spec.key == "forward_voltage"
            and not self._updating_vf
            and self.led_color_combo is not None
        ):
            try:
                typed_val = parse_engineering_value(self.inputs[spec.key].text().strip())
                curr_color = self.led_color_combo.currentText()
                if curr_color in LED_COLOUR_PRESETS and curr_color != "Custom":
                    expected_vf = float(LED_COLOUR_PRESETS[curr_color]["forward_voltage"])
                    if not math.isclose(typed_val, expected_vf, abs_tol=1e-3):
                        self._updating_color = True
                        self.led_color_combo.setCurrentText("Custom")
                        if self.led_datasheet_lbl is not None:
                            self.led_datasheet_lbl.setText("Forward voltage: user defined (Custom)")
                        self._updating_color = False
            except ValueError:
                pass

    def _update_field_preview(self, spec: ComponentParameter) -> None:
        lbl = self.preview_labels.get(spec.key)
        if lbl is None:
            return
        if isinstance(self.component, (Voltmeter, Ammeter)) and spec.key == "r_internal":
            if self.meter_preset_combo is not None and "ideal" in self.meter_preset_combo.currentText().lower():
                lbl.setText("Ideal (no loading)" if isinstance(self.component, Voltmeter) else "Ideal (0 V branch)")
                return
        raw_text = self.inputs[spec.key].text().strip()
        try:
            val = parse_engineering_value(raw_text)
        except ValueError as exc:
            lbl.setText(str(exc))
            return

        if not spec.allow_negative and not spec.allow_zero and val <= 0.0:
            lbl.setText(f"{spec.label} must be > 0 {spec.unit}")
            return
        if not spec.allow_negative and spec.allow_zero and val < 0.0:
            lbl.setText(f"{spec.label} cannot be negative")
            return

        preview_text = f"= {format_engineering_value(val, spec.unit)}"
        if not spec.live_editable:
            preview_text += " (applies at t = 0 after Stop + Run)"
        lbl.setText(preview_text)

    def validate_inputs(self) -> tuple[dict[str, object] | None, str | None]:
        """Validate all parameter fields and return `(parsed_dict, error_message)`."""
        parsed_map: dict[str, object] = {}
        for spec in self._param_specs:
            if isinstance(self.component, (Voltmeter, Ammeter)) and spec.key == "r_internal":
                if self.meter_preset_combo is not None and "ideal" in self.meter_preset_combo.currentText().lower():
                    parsed_map["is_ideal"] = True
                    parsed_map["r_internal"] = self.component.r_internal
                    continue
                else:
                    parsed_map["is_ideal"] = False

            raw_text = self.inputs[spec.key].text().strip()
            try:
                val = parse_engineering_value(raw_text)
            except ValueError as exc:
                return None, f"{spec.label}: {exc}"

            if not spec.allow_negative and not spec.allow_zero and val <= 0.0:
                return (
                    None,
                    f"{spec.label} must be greater than 0 {spec.unit} (got {raw_text!r}).",
                )
            if not spec.allow_negative and spec.allow_zero and val < 0.0:
                return (
                    None,
                    f"{spec.label} cannot be negative (got {raw_text!r}).",
                )
            parsed_map[spec.key] = val

        if isinstance(self.component, Lightbulb):
            if self.bulb_burnout_cb is not None:
                parsed_map["burnout_enabled"] = bool(self.bulb_burnout_cb.isChecked())
            if self.burnout_ratio_edit is not None:
                try:
                    ratio = float(self.burnout_ratio_edit.text().strip())
                    if ratio <= 1.0:
                        return None, "Burn-out power ratio must be greater than 1.0."
                    parsed_map["burnout_power_ratio"] = ratio
                except ValueError:
                    return None, f"Invalid burn-out power ratio: {self.burnout_ratio_edit.text()!r}"
            if self.burnout_time_edit is not None:
                try:
                    t_burn = parse_engineering_value(self.burnout_time_edit.text().strip())
                    if t_burn <= 0.0:
                        return None, "Burn-out duration must be greater than 0 s."
                    parsed_map["burnout_time"] = t_burn
                except ValueError as exc:
                    return None, f"Invalid burn-out duration: {exc}"

        if isinstance(self.component, LED):
            if self.led_burnout_cb is not None:
                parsed_map["burnout_enabled"] = self.led_burnout_cb.isChecked()
            if self.led_burnout_current_edit is not None:
                try:
                    i_b = parse_engineering_value(self.led_burnout_current_edit.text().strip())
                    if i_b <= 0.0:
                        return None, "Burn-out threshold must be greater than 0 A."
                    parsed_map["burnout_current"] = i_b
                except ValueError as exc:
                    return None, f"Invalid burn-out threshold: {exc}"
            if self.led_color_combo is not None:
                cname = self.led_color_combo.currentText()
                parsed_map["color_name"] = cname
                if cname in LED_COLOUR_PRESETS:
                    parsed_map["color"] = str(LED_COLOUR_PRESETS[cname]["hex"])

        return parsed_map, None

    def _apply_current_inputs(self) -> bool:
        parsed_map, err_msg = self.validate_inputs()
        if err_msg is not None or parsed_map is None:
            self.error_label.setText(err_msg or "Invalid input.")
            self.error_label.setVisible(True)
            return False

        self._clear_error()
        self.applied_values = dict(parsed_map)
        show_val = self.show_value_cb.isChecked()

        if self._on_apply is not None:
            self._on_apply(parsed_map, show_val)
        else:
            param_keys = {p.key for p in self.component.get_editable_parameters()}
            for k, v in parsed_map.items():
                if k in param_keys:
                    self.component.set_parameter_value(k, v)
                elif hasattr(self.component, k):
                    setattr(self.component, k, v)
            self.component.show_value = show_val

        if (
            self.switch_closed_cb is not None
            and isinstance(self.component, Switch)
        ):
            self.component.set_closed(self.switch_closed_cb.isChecked())

        return True

    def _on_apply_clicked(self) -> None:
        self._apply_current_inputs()

    def _on_ok_clicked(self) -> None:
        if self._apply_current_inputs():
            self.accept()
