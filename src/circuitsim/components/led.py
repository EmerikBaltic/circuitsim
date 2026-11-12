"""Light Emitting Diode (LED) component model with forward voltage, colours, and burn-out."""

from __future__ import annotations

from circuitsim.components.base import Component
from circuitsim.dialogs.value_parser import parse_engineering_value

# Standard LED colour presets with typical datasheet forward voltages at 20 mA
# and recommended display hex colours
LED_COLOUR_PRESETS: dict[str, dict[str, object]] = {
    "Red": {
        "forward_voltage": 2.0,
        "hex": "#FF3B30",
        "datasheet_range": "1.8–2.4 V",
    },
    "Orange": {
        "forward_voltage": 2.0,
        "hex": "#FF9500",
        "datasheet_range": "1.9–2.4 V",
    },
    "Yellow": {
        "forward_voltage": 2.1,
        "hex": "#FFCC00",
        "datasheet_range": "2.0–2.5 V",
    },
    "Green": {
        "forward_voltage": 2.2,
        "hex": "#34C759",
        "datasheet_range": "2.0–2.6 V",
    },
    "Pure green": {
        "forward_voltage": 3.2,
        "hex": "#00E676",
        "datasheet_range": "3.0–3.6 V",
    },
    "Blue": {
        "forward_voltage": 3.2,
        "hex": "#007AFF",
        "datasheet_range": "3.0–3.6 V",
    },
    "White": {
        "forward_voltage": 3.2,
        "hex": "#F2F2F7",
        "datasheet_range": "3.0–3.6 V",
    },
    "Custom": {
        "forward_voltage": 2.0,
        "hex": "#FF3B30",
        "datasheet_range": "User defined",
    },
}


class LED(Component):
    """Light Emitting Diode (LED) model with forward voltage drop, colour presets, and burn-out.

    Physics model:
        - Terminals: Anode (node_a) and Cathode (node_k).
        - In forward bias (V_ak >= V_f): conducts with dynamic forward resistance
          r_on (default 1 mΩ) in series with forward voltage drop V_f.
        - In reverse bias (V_ak < V_f): high-impedance OFF state r_off (1 GΩ).
        - If burnout_enabled is True and current exceeds burnout_current (or max_current * 1.5)
          under sustained overload, the LED burns out permanently (open circuit r_off).
    """

    DEFAULT_R_ON: float = 1e-3  # 1 mΩ forward series resistance
    DEFAULT_R_OFF: float = 1e9  # 1 GΩ reverse isolation resistance

    def __init__(
        self,
        name: str,
        node_anode: str,
        node_cathode: str,
        *,
        forward_voltage: float | str = 2.0,
        rated_current: float | str = 0.02,
        max_current: float | str = 0.03,
        color_name: str = "Red",
        color: str | None = None,
        burnout_enabled: bool = False,
        burnout_current: float | str | None = None,
        label: str | None = None,
        show_value: bool = True,
    ) -> None:
        v_f = parse_engineering_value(forward_voltage)
        i_rated = parse_engineering_value(rated_current)
        i_max = parse_engineering_value(max_current)
        i_burn = (
            parse_engineering_value(burnout_current)
            if burnout_current is not None
            else i_max * 1.5
        )

        display_color = color
        if display_color is None:
            preset_info = LED_COLOUR_PRESETS.get(color_name, LED_COLOUR_PRESETS["Red"])
            display_color = str(preset_info["hex"])

        super().__init__(
            name=name,
            nodes=(node_anode, node_cathode),
            label=label,
            show_value=show_value,
            color=display_color,
        )

        if v_f <= 0.0:
            raise ValueError(f"LED {name!r}: forward_voltage must be > 0 V.")
        if i_rated <= 0.0:
            raise ValueError(f"LED {name!r}: rated_current must be > 0 A.")
        if i_max <= 0.0:
            raise ValueError(f"LED {name!r}: max_current must be > 0 A.")

        self.forward_voltage: float = v_f
        self.rated_current: float = i_rated
        self.max_current: float = i_max
        self.color_name: str = color_name
        self.burnout_enabled: bool = bool(burnout_enabled)
        self.burnout_current: float = i_burn
        self.burned_out: bool = False

        self.r_on: float = self.DEFAULT_R_ON
        self.r_off: float = self.DEFAULT_R_OFF

        # Operating state for rendering
        self.is_conducting: bool = False
        self.is_over_current: bool = False
        self.brightness: float = 0.0

    @property
    def component_type(self) -> str:
        return "led"

    @property
    def anode_node(self) -> str:
        return self.nodes[0]

    @property
    def cathode_node(self) -> str:
        return self.nodes[1]

    @property
    def conductance(self) -> float:
        """Effective DC conductance G in Siemens."""
        if self.burned_out:
            return 1.0 / self.r_off
        if self.is_conducting:
            return 1.0 / self.r_on
        return 1.0 / self.r_off

    def companion_model(self, dt: float = 0.0, method: str = "trapezoidal") -> tuple[float, float]:
        """Return `(g_eq, i_eq)` for MNA solver.

        Branch current from anode to cathode is:
            i_ak = g_eq * v_ak - i_eq
        When forward-biased and conducting:
            i_ak = (v_ak - V_f) / r_on = (1/r_on) * v_ak - (V_f / r_on)
            => g_eq = 1/r_on, i_eq = V_f / r_on
        When reverse-biased or burned out:
            i_ak = v_ak / r_off => g_eq = 1/r_off, i_eq = 0
        """
        _ = (dt, method)
        if self.burned_out or not self.is_conducting:
            return (1.0 / self.r_off, 0.0)

        g_on = 1.0 / self.r_on
        i_eq = self.forward_voltage * g_on
        return (g_on, i_eq)

    def set_color_preset(self, name: str) -> None:
        """Apply a named color preset, updating forward voltage and hex color."""
        if name not in LED_COLOUR_PRESETS:
            name = "Custom"
        self.color_name = name
        preset = LED_COLOUR_PRESETS[name]
        if name != "Custom":
            self.forward_voltage = float(preset["forward_voltage"])
            self.color = str(preset["hex"])

    def reset_state(self) -> None:
        super().reset_state()
        self.burned_out = False
        self.is_conducting = False
        self.is_over_current = False
        self.brightness = 0.0
