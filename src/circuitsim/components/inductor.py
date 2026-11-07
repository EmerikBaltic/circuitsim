"""Inductor component model with series winding resistance (DCR) and helpers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from circuitsim.components.base import Component
from circuitsim.dialogs.value_parser import parse_engineering_value

if TYPE_CHECKING:
    from circuitsim.engine.netlist import Circuit


class Inductor(Component):
    """Two-terminal inductor with series winding resistance (DCR) inside its branch.

    Physics & Companion Model (Section 5.3):
        - Winding resistance `dcr` is folded directly into the inductor's two-terminal
          branch equation (no extra internal node is added):
              v_ab(t) = dcr * i(t) + v_L(t),   where v_L(t) = L * di/dt
        - At DC operating point (`solve_dc`), an ideal inductor is a short circuit;
          to keep the nodal conductance matrix non-singular without adding an extra
          current row, a minimum DC resistance `MIN_DC_RESISTANCE = 1e-3 Ω` (1 mΩ)
          is used whenever `dcr < 1e-3 Ω`.
        - In transient analysis, the exact `dcr` (including `0.0 Ω` for lossless LC
          circuits) is used:
            * Backward Euler:
                R_eq = dcr + L / dt
                G_eq = 1 / R_eq
                I_hist = G_eq * (L / dt) * i(t_{n-1})
            * Trapezoidal:
                R_eq = dcr + 2 * L / dt
                G_eq = 1 / R_eq
                I_hist = G_eq * ((2 * L / dt) * i(t_{n-1}) + v_L(t_{n-1}))
          where i_ab(t_n) = G_eq * v_ab(t_n) + I_hist.
    """

    MIN_DC_RESISTANCE: float = 1e-3

    def __init__(
        self,
        name: str,
        node_a: str,
        node_b: str,
        inductance: float | str = 1e-3,
        *,
        dcr: float | str = 0.0,
        initial_current: float | str = 0.0,
        saturation_current: float | str | None = None,
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
        parsed_l = parse_engineering_value(inductance)
        parsed_dcr = parse_engineering_value(dcr)
        parsed_i0 = parse_engineering_value(initial_current)
        parsed_isat = (
            parse_engineering_value(saturation_current)
            if saturation_current is not None
            else None
        )

        if parsed_l <= 0.0:
            raise ValueError(
                f"Inductor {name!r}: inductance must be > 0 H, got {parsed_l}."
            )
        if parsed_dcr < 0.0:
            raise ValueError(
                f"Inductor {name!r}: winding resistance (dcr) cannot be negative."
            )
        if parsed_isat is not None and parsed_isat <= 0.0:
            raise ValueError(
                f"Inductor {name!r}: saturation_current must be > 0 A."
            )

        self.inductance: float = parsed_l
        self.dcr: float = parsed_dcr
        self.initial_current: float = parsed_i0
        self.saturation_current: float | None = parsed_isat

        # State of the pure inductive element
        self.ind_current: float = parsed_i0
        self.ind_voltage: float = 0.0
        self.current = parsed_i0

    @property
    def component_type(self) -> str:
        return "inductor"

    @property
    def dc_resistance(self) -> float:
        """Effective DC resistance (at least 1 mΩ so DC MNA matrix stays solvable)."""
        return max(self.dcr, self.MIN_DC_RESISTANCE)

    @property
    def dc_conductance(self) -> float:
        """Effective DC conductance for DC operating point solves."""
        return 1.0 / self.dc_resistance

    def reactance(self, frequency_hz: float | str) -> float:
        """Compute inductive reactance X_L = 2 * pi * f * L in Ohms."""
        f = parse_engineering_value(frequency_hz)
        if f < 0.0:
            raise ValueError(f"Frequency cannot be negative, got {f}.")
        return 2.0 * math.pi * f * self.inductance

    @staticmethod
    def calculate_inductance_from_reactance(
        desired_x_l: float | str,
        frequency_hz: float | str,
    ) -> float:
        """Helper (Section 5.3): calculate L = X_L / (2 * pi * f) in Henries."""
        x_l = parse_engineering_value(desired_x_l)
        f = parse_engineering_value(frequency_hz)
        if x_l <= 0.0:
            raise ValueError("Desired inductive reactance X_L must be > 0 Ω.")
        if f <= 0.0:
            raise ValueError("Frequency must be > 0 Hz.")
        return x_l / (2.0 * math.pi * f)

    def time_constant(self, circuit: Circuit | None = None, r_external: float = 0.0) -> float:
        """Compute RL time constant tau = L / (R_thevenin + DCR) in seconds.

        If `circuit` is provided, `R_thevenin` is computed automatically as the exact
        resistance seen between the inductor's terminals with all independent
        sources zeroed. Otherwise `r_external` is used.
        """
        if circuit is not None:
            r_th = circuit.thevenin_resistance(
                self.nodes[0], self.nodes[1], exclude_component=self.name
            )
        else:
            r_th = max(0.0, float(r_external))

        r_total = r_th + self.dcr
        if r_total <= 0.0:
            return float("inf")
        return self.inductance / r_total

    def companion_model(self, dt: float, method: str = "trapezoidal") -> tuple[float, float]:
        """Return `(g_eq, i_hist)` for the Norton companion model at time step `dt`.

        The branch relation from `node_a` to `node_b` is:
            i_ab(t_n) = g_eq * v_ab(t_n) + i_hist
        So in KCL:
            -i_hist enters `node_a` on the RHS vector b, and +i_hist enters `node_b`.
        """
        if dt <= 0.0:
            raise ValueError(f"Time step dt must be > 0, got {dt}.")

        if method == "backward_euler":
            l_over_dt = self.inductance / dt
            r_eq = self.dcr + l_over_dt
            g_eq = 1.0 / r_eq
            i_hist = g_eq * l_over_dt * self.ind_current
            return g_eq, i_hist

        if method == "trapezoidal":
            two_l_over_dt = (2.0 * self.inductance) / dt
            r_eq = self.dcr + two_l_over_dt
            g_eq = 1.0 / r_eq
            i_hist = g_eq * (two_l_over_dt * self.ind_current + self.ind_voltage)
            return g_eq, i_hist

        raise ValueError(f"Unknown integration method {method!r}.")

    def update_companion_state(self, v_terminal: float, i_branch: float) -> None:
        """Update internal inductor state after solving a transient step."""
        self.voltage = v_terminal
        self.current = i_branch
        self.power = v_terminal * i_branch
        self.ind_current = i_branch
        self.ind_voltage = v_terminal - self.dcr * i_branch

    def reset_state(self) -> None:
        """Reset inductor current to `initial_current` and pure voltage to 0."""
        super().reset_state()
        self.ind_current = self.initial_current
        self.ind_voltage = 0.0
        self.current = self.initial_current
