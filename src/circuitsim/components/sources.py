"""Ideal and non-ideal DC voltage and current source models."""

from __future__ import annotations

from circuitsim.components.base import Component
from circuitsim.dialogs.value_parser import parse_engineering_value


class DCVoltageSource(Component):
    """DC voltage source maintaining V(node_pos) - V(node_neg) = voltage - I_load * r_internal.

    Sign conventions:
        - `node_pos` is the positive (+) terminal.
        - `node_neg` is the negative (-) terminal.
        - `self.voltage` is the terminal voltage V(node_pos) - V(node_neg).
        - `self.current` follows the passive convention used by MNA branch variables
          (positive when current flows into `node_pos` and out of `node_neg`, or
          negative when delivering power out of `node_pos`). `delivered_current`
          and `delivered_power` provide the source-convention values.
    """

    def __init__(
        self,
        name: str,
        node_pos: str,
        node_neg: str,
        voltage: float | str = 5.0,
        *,
        r_internal: float | str = 0.0,
        label: str | None = None,
        show_value: bool = True,
        color: str = "#FFFFFF",
    ) -> None:
        super().__init__(
            name=name,
            nodes=(node_pos, node_neg),
            label=label,
            show_value=show_value,
            color=color,
        )
        parsed_v = parse_engineering_value(voltage)
        parsed_r = parse_engineering_value(r_internal)
        if parsed_r < 0.0:
            raise ValueError(
                f"DCVoltageSource {name!r}: internal resistance cannot be negative ({parsed_r})."
            )
        self.dc_voltage: float = parsed_v
        self.r_internal: float = parsed_r

    @property
    def component_type(self) -> str:
        return "dc_voltage"

    @property
    def delivered_current(self) -> float:
        """Current flowing OUT of the positive terminal into the circuit (Amperes)."""
        return -self.current

    @property
    def delivered_power(self) -> float:
        """Power supplied by the source to the circuit (Watts)."""
        return -self.power


class DCCurrentSource(Component):
    """Ideal DC current source injecting `dc_current` from `node_neg` into `node_pos`.

    External circuit current leaves `node_pos` and returns to `node_neg`.
    """

    def __init__(
        self,
        name: str,
        node_pos: str,
        node_neg: str,
        current: float | str = 0.01,
        *,
        label: str | None = None,
        show_value: bool = True,
        color: str = "#FFFFFF",
    ) -> None:
        super().__init__(
            name=name,
            nodes=(node_pos, node_neg),
            label=label,
            show_value=show_value,
            color=color,
        )
        self.dc_current: float = parse_engineering_value(current)

    @property
    def component_type(self) -> str:
        return "dc_current"
