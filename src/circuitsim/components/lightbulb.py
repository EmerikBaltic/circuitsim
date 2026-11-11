"""Incandescent lightbulb component model (Section 5.1 of specification)."""

from __future__ import annotations

from circuitsim.components.base import Component
from circuitsim.dialogs.value_parser import parse_engineering_value


class Lightbulb(Component):
    """Incandescent lightbulb with rated wattage/voltage and optional filament inertia.

    Physics model (Section 5.1):
        - Hot resistance: R_hot = V_rated^2 / P_rated
          (e.g., 60 W at 120 V -> R_hot = 14400 / 60 = 240 Ω).
        - Default mode (`use_filament_model=False`): constant resistance equal to R_hot.
        - Optional filament mode (`use_filament_model=True`):
          Cold resistance is `cold_resistance_ratio * R_hot` (default 0.1 * R_hot).
          A normalized filament temperature state `temperature` (0.0 = ambient cold,
          1.0 = steady-state hot at rated power) evolves once per time step from the
          previous step's dissipated power:
              dT/dt = ((P_prev / P_rated) - T) / thermal_time_constant
          Resistance interpolates linearly between R_cold and R_hot for T in [0, 1].
        - Brightness ratio = P_actual / P_rated (1.0 = 100% full glow).
    """

    OPEN_BURNOUT_RESISTANCE: float = 1e9

    def __init__(
        self,
        name: str,
        node_a: str,
        node_b: str,
        *,
        rated_power: float | str = 60.0,
        rated_voltage: float | str = 120.0,
        use_filament_model: bool = False,
        cold_resistance_ratio: float = 0.1,
        thermal_time_constant: float | str = 0.04,
        burnout_enabled: bool = False,
        burnout_power_ratio: float = 1.2,
        burnout_time: float | str = 0.5,
        label: str | None = None,
        show_value: bool = True,
        color: str = "#FFD54F",
    ) -> None:
        super().__init__(
            name=name,
            nodes=(node_a, node_b),
            label=label,
            show_value=show_value,
            color=color,
        )
        p_rated = parse_engineering_value(rated_power)
        v_rated = parse_engineering_value(rated_voltage)
        tau_th = parse_engineering_value(thermal_time_constant)
        t_burn = parse_engineering_value(burnout_time)

        if p_rated <= 0.0:
            raise ValueError(f"Lightbulb {name!r}: rated_power must be > 0 W.")
        if v_rated <= 0.0:
            raise ValueError(f"Lightbulb {name!r}: rated_voltage must be > 0 V.")
        if not (0.0 < cold_resistance_ratio <= 1.0):
            raise ValueError(
                f"Lightbulb {name!r}: cold_resistance_ratio must be in (0, 1]."
            )
        if tau_th <= 0.0:
            raise ValueError(
                f"Lightbulb {name!r}: thermal_time_constant must be > 0 s."
            )

        self.rated_power: float = p_rated
        self.rated_voltage: float = v_rated
        self.use_filament_model: bool = bool(use_filament_model)
        self.cold_resistance_ratio: float = float(cold_resistance_ratio)
        self.thermal_time_constant: float = tau_th
        self.burnout_enabled: bool = bool(burnout_enabled)
        self.burnout_power_ratio: float = float(burnout_power_ratio)
        self.burnout_time: float = t_burn

        # Filament state: 0.0 when cold at t=0 (if filament model active), 1.0 at rated hot.
        self.temperature: float = 0.0 if self.use_filament_model else 1.0
        self.burned_out: bool = False
        self._overload_duration: float = 0.0

    @property
    def component_type(self) -> str:
        return "lightbulb"

    @property
    def r_hot(self) -> float:
        """Hot filament resistance R_hot = V_rated^2 / P_rated in Ohms."""
        return (self.rated_voltage**2) / self.rated_power

    @property
    def r_cold(self) -> float:
        """Cold filament resistance in Ohms."""
        return self.r_hot * self.cold_resistance_ratio

    def effective_resistance(self) -> float:
        """Return the bulb's instantaneous resistance in Ohms for the current step."""
        if self.burned_out:
            return self.OPEN_BURNOUT_RESISTANCE
        if not self.use_filament_model:
            return self.r_hot

        clamped_temp = min(max(self.temperature, 0.0), 1.0)
        return self.r_cold + (self.r_hot - self.r_cold) * clamped_temp

    @property
    def conductance(self) -> float:
        """Return effective conductance G = 1 / R_eff in Siemens."""
        return 1.0 / self.effective_resistance()

    @property
    def brightness(self) -> float:
        """Unclamped brightness ratio (P_actual / P_rated). 1.0 = 100% rated glow."""
        if self.burned_out or self.rated_power <= 0.0:
            return 0.0
        return max(0.0, self.power / self.rated_power)

    @property
    def brightness_percent(self) -> float:
        """Brightness expressed as a percentage (e.g., 100.0 for rated power)."""
        return self.brightness * 100.0

    @property
    def clamped_brightness(self) -> float:
        """Brightness ratio clamped to [0.0, 1.0] for standard canvas glow rendering."""
        return min(max(self.brightness, 0.0), 1.0)

    @property
    def is_over_bright(self) -> bool:
        """Return True if power exceeds rated power (> 100% brightness)."""
        return self.brightness > 1.0 + 1e-6

    def advance_thermal_state(self, dt: float) -> bool:
        """Update filament temperature and burnout timer from the previous step's power.

        Called once per transient step (no Newton iteration in Milestone 1).

        Returns:
            True if the bulb's effective resistance changed significantly.
        """
        if dt <= 0.0:
            return False

        old_r = self.effective_resistance()

        if self.burnout_enabled and not self.burned_out:
            if self.power > self.rated_power * self.burnout_power_ratio:
                self._overload_duration += dt
                if self._overload_duration >= self.burnout_time:
                    self.burned_out = True
                    self.power = 0.0
                    self.current = 0.0
                    return True
            else:
                self._overload_duration = max(0.0, self._overload_duration - dt)

        if self.use_filament_model and not self.burned_out:
            target_temp = self.power / self.rated_power
            # Exact exponential step for first-order thermal ODE:
            # dT/dt = (target_temp - T) / tau
            alpha = min(1.0, dt / (self.thermal_time_constant + dt))
            self.temperature += alpha * (target_temp - self.temperature)

        new_r = self.effective_resistance()
        return abs(new_r - old_r) > 1e-9 * old_r

    def reset_burnout(self) -> None:
        """Repair a burned-out bulb and reset its overload timer."""
        self.burned_out = False
        self._overload_duration = 0.0

    def reset_state(self) -> None:
        """Reset filament temperature, burnout state, and electrical readings."""
        super().reset_state()
        self.temperature = 0.0 if self.use_filament_model else 1.0
        self.burned_out = False
        self._overload_duration = 0.0

    def get_parameter_value(self, key: str) -> float:
        """Return the numerical value of parameter `key`."""
        if key == "burnout_enabled":
            return 1.0 if self.burnout_enabled else 0.0
        if key in ("burnout_power_ratio", "burnout_time"):
            return float(getattr(self, key))
        return super().get_parameter_value(key)

    def set_parameter_value(self, key: str, raw_value: float | str) -> float:
        """Set parameter `key` to `raw_value` and return parsed float."""
        if key == "burnout_enabled":
            self.burnout_enabled = bool(raw_value)
            return 1.0 if self.burnout_enabled else 0.0
        if key == "burnout_power_ratio":
            val = float(raw_value)
            if val <= 1.0:
                raise ValueError(f"Lightbulb {self.name!r}: burnout_power_ratio must be > 1.0.")
            self.burnout_power_ratio = val
            return val
        if key == "burnout_time":
            val = parse_engineering_value(raw_value)
            if val <= 0.0:
                raise ValueError(f"Lightbulb {self.name!r}: burnout_time must be > 0 s.")
            self.burnout_time = val
            return val
        return super().set_parameter_value(key, raw_value)
