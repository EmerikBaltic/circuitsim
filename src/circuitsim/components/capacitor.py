"""Capacitor component model with initial voltage and optional series ESR."""

from __future__ import annotations

from circuitsim.components.base import Component
from circuitsim.dialogs.value_parser import parse_engineering_value


class Capacitor(Component):
    """Two-terminal linear capacitor with optional Equivalent Series Resistance (ESR).

    Companion model (no extra internal node for ESR):
        Let v_C(t) be the voltage across the ideal capacitance element alone, so the
        terminal voltage is v_ab(t) = v_C(t) + esr * i(t).

        - Backward Euler (step size dt):
            R_eq = esr + dt / C
            G_eq = 1 / R_eq
            I_eq = G_eq * v_C(t_{n-1})
            where i(t_n) = G_eq * v_ab(t_n) - I_eq

        - Trapezoidal rule (step size dt):
            R_eq = esr + dt / (2 * C)
            G_eq = 1 / R_eq
            V_hist = v_C(t_{n-1}) + (dt / (2 * C)) * i(t_{n-1})
            I_eq = G_eq * V_hist
            where i(t_n) = G_eq * v_ab(t_n) - I_eq
    """

    def __init__(
        self,
        name: str,
        node_a: str,
        node_b: str,
        capacitance: float | str = 1e-6,
        *,
        initial_voltage: float | str = 0.0,
        esr: float | str = 0.0,
        voltage_rating: float | str = 50.0,
        label: str | None = None,
        show_value: bool = True,
        color: str = "#FFFFFF",
    ) -> None:
        super().__init__(
            name=name,
            nodes=(node_a, node_b),
            label=label,
            show_value=show_value,
            color=color,
        )
        parsed_c = parse_engineering_value(capacitance)
        parsed_v0 = parse_engineering_value(initial_voltage)
        parsed_esr = parse_engineering_value(esr)
        parsed_v_max = parse_engineering_value(voltage_rating)

        if parsed_c <= 0.0:
            raise ValueError(
                f"Capacitor {name!r}: capacitance must be > 0 F, got {parsed_c}."
            )
        if parsed_esr < 0.0:
            raise ValueError(
                f"Capacitor {name!r}: ESR cannot be negative, got {parsed_esr}."
            )
        if parsed_v_max <= 0.0:
            raise ValueError(
                f"Capacitor {name!r}: voltage_rating must be > 0 V, got {parsed_v_max}."
            )

        self.capacitance: float = parsed_c
        self.initial_voltage: float = parsed_v0
        self.esr: float = parsed_esr
        self.voltage_rating: float = parsed_v_max

        # Internal state of the ideal capacitive element (excluding ESR drop).
        self.cap_voltage: float = parsed_v0
        self.cap_current: float = 0.0
        self.voltage = parsed_v0

    @property
    def component_type(self) -> str:
        return "capacitor"

    def companion_model(self, dt: float, method: str = "trapezoidal") -> tuple[float, float]:
        """Return `(g_eq, i_eq)` for the Norton companion model at time step `dt`.

        The branch relation from `node_a` to `node_b` is:
            i_ab(t_n) = g_eq * v_ab(t_n) - i_eq
        So in KCL:
            +i_eq enters `node_a` on the RHS vector b, and -i_eq enters `node_b`.
        """
        if dt <= 0.0:
            raise ValueError(f"Time step dt must be > 0, got {dt}.")

        if method == "backward_euler":
            r_eq = self.esr + (dt / self.capacitance)
            g_eq = 1.0 / r_eq
            i_eq = g_eq * self.cap_voltage
            return g_eq, i_eq

        if method == "trapezoidal":
            half_dt_over_c = dt / (2.0 * self.capacitance)
            r_eq = self.esr + half_dt_over_c
            g_eq = 1.0 / r_eq
            v_hist = self.cap_voltage + half_dt_over_c * self.cap_current
            i_eq = g_eq * v_hist
            return g_eq, i_eq

        raise ValueError(f"Unknown integration method {method!r}.")

    def update_companion_state(self, v_terminal: float, i_branch: float) -> None:
        """Update internal capacitor state after solving a transient step."""
        self.voltage = v_terminal
        self.current = i_branch
        self.power = v_terminal * i_branch
        self.cap_current = i_branch
        self.cap_voltage = v_terminal - self.esr * i_branch

    @property
    def is_overloaded(self) -> bool:
        """Return True if terminal voltage magnitude exceeds `voltage_rating`."""
        return abs(self.voltage) > self.voltage_rating

    def reset_state(self) -> None:
        """Reset capacitor voltage back to `initial_voltage` and current to 0."""
        super().reset_state()
        self.cap_voltage = self.initial_voltage
        self.cap_current = 0.0
        self.voltage = self.initial_voltage
