"""SPST Switch component model with contact capacitance and breakdown arc clamp."""

from __future__ import annotations

import math

from circuitsim.components.base import Component
from circuitsim.dialogs.value_parser import parse_engineering_value


class Switch(Component):
    """Single-Pole Single-Throw (SPST) switch with parasitic capacitance and arc clamp.

    Why finite ON and OFF resistances?
        In Modified Nodal Analysis, an ideal open switch (0 S) can leave nodes
        floating, while an ideal closed switch (infinite conductance) changes the
        number of independent nodes when toggled. Modeling ON as 1 milliohm and
        OFF as 1 gigaohm keeps the matrix topology constant and non-singular.

    Why a parasitic contact capacitance (10 pF default, Section 5.4)?
        When a switch opens in series with an inductive load, the 10 pF contact
        capacitance provides a realistic energy-transfer path across the contacts.

    Simplified Contact Breakdown / Arc Model:
        When `v_breakdown` is set (default 350 V, typical air-gap Paschen breakdown)
        and the switch is OPEN, if the contact voltage |v_ab| exceeds `v_breakdown`,
        an arc strikes across the contacts. While arcing, the switch conducts with
        a clamped voltage drop of `±v_breakdown` in series with a small dynamic arc
        resistance `r_arc` (default 1 Ω). When the arc current decays below the
        holding current threshold `i_hold` (default 1 mA) or reverses polarity,
        the arc extinguishes and the switch returns to its high-impedance OFF state.
        Setting `v_breakdown=None` (or `<= 0`) disables breakdown clamping (ideal
        open contact).

    Attributes:
        closed: True when the switch is ON (closed), False when OFF (open).
        r_on: Contact resistance when closed (default 1 mΩ).
        r_off: Isolation resistance when open (default 1 GΩ).
        c_parasitic: Small parasitic contact capacitance (default 10 pF).
        v_breakdown: Contact breakdown / arc clamp voltage in Volts (default 350 V,
            or None to disable clamping).
        r_arc: Dynamic resistance of the conducting arc in Ohms (default 1 Ω).
        i_hold: Minimum holding current in Amperes to sustain an arc (default 1 mA).
        toggle_time: Optional simulation time (in seconds) at which the switch
            automatically flips from its initial state.
        shortcut: Optional keyboard shortcut string for UI toggling.
    """

    def __init__(
        self,
        name: str,
        node_a: str,
        node_b: str,
        *,
        closed: bool = False,
        r_on: float | str = 1e-3,
        r_off: float | str = 1e9,
        c_parasitic: float | str = 10e-12,
        v_breakdown: float | str | None = 350.0,
        r_arc: float | str = 1.0,
        i_hold: float | str = 1e-3,
        toggle_time: float | str | None = None,
        shortcut: str = "",
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
        parsed_on = parse_engineering_value(r_on)
        parsed_off = parse_engineering_value(r_off)
        parsed_c = parse_engineering_value(c_parasitic)
        parsed_r_arc = parse_engineering_value(r_arc)
        parsed_i_hold = parse_engineering_value(i_hold)

        parsed_v_bd: float | None
        if v_breakdown is None:
            parsed_v_bd = None
        else:
            val_bd = parse_engineering_value(v_breakdown)
            parsed_v_bd = val_bd if (val_bd > 0.0 and math.isfinite(val_bd)) else None

        if parsed_on <= 0.0 or parsed_off <= 0.0:
            raise ValueError(f"Switch {name!r}: r_on and r_off must be > 0 Ω.")
        if parsed_on >= parsed_off:
            raise ValueError(
                f"Switch {name!r}: r_on ({parsed_on}) must be < r_off ({parsed_off})."
            )
        if parsed_c < 0.0:
            raise ValueError(f"Switch {name!r}: c_parasitic cannot be negative.")
        if parsed_r_arc <= 0.0:
            raise ValueError(f"Switch {name!r}: r_arc must be > 0 Ω.")
        if parsed_i_hold < 0.0:
            raise ValueError(f"Switch {name!r}: i_hold cannot be negative.")

        self.initial_closed: bool = bool(closed)
        self.closed: bool = bool(closed)
        self.r_on: float = parsed_on
        self.r_off: float = parsed_off
        self.c_parasitic: float = parsed_c
        self.v_breakdown: float | None = parsed_v_bd
        self.r_arc: float = parsed_r_arc
        self.i_hold: float = parsed_i_hold
        self.toggle_time: float | None = (
            parse_engineering_value(toggle_time) if toggle_time is not None else None
        )
        self.shortcut: str = shortcut
        self._timer_triggered: bool = False

        # Parasitic contact capacitor state and arc state
        self._cap_current: float = 0.0
        self.arcing: bool = False
        self._arc_polarity: float = 0.0

    @property
    def component_type(self) -> str:
        return "switch"

    @property
    def resistance(self) -> float:
        """Current effective DC contact resistance in Ohms (excluding arc source)."""
        return self.r_on if self.closed else self.r_off

    @property
    def conductance(self) -> float:
        """Current effective DC conductance G = 1 / R in Siemens."""
        return 1.0 / self.resistance

    def check_arc_ignition(self, v_terminal: float) -> bool:
        """Check whether an open switch should strike an arc at `v_terminal`.

        Returns:
            True if the switch transitioned from non-arcing to arcing.
        """
        if (
            self.closed
            or self.arcing
            or self.v_breakdown is None
            or abs(v_terminal) <= self.v_breakdown
        ):
            return False

        self.arcing = True
        self._arc_polarity = 1.0 if v_terminal >= 0.0 else -1.0
        return True

    def check_arc_extinction(self, v_terminal: float) -> bool:
        """Check whether an active contact arc should extinguish at `v_terminal`.

        The arc extinguishes when the arc current `i_arc = (v_ab - s * v_bd) / r_arc`
        falls at or below `i_hold` along the arc polarity `s`.

        Returns:
            True if the switch transitioned from arcing to non-arcing.
        """
        if not self.arcing or self.closed or self.v_breakdown is None:
            if self.arcing:
                self.arcing = False
                self._arc_polarity = 0.0
                return True
            return False

        signed_overvoltage = self._arc_polarity * v_terminal - self.v_breakdown
        i_arc_mag = signed_overvoltage / self.r_arc
        if i_arc_mag <= self.i_hold:
            self.arcing = False
            self._arc_polarity = 0.0
            return True
        return False

    def companion_model(self, dt: float, method: str = "trapezoidal") -> tuple[float, float]:
        """Return `(g_total, i_eq)` for the switch + `c_parasitic` + active arc at step `dt`.

        The total switch branch current from `node_a` to `node_b` is:
            i_ab(t_n) = g_total * v_ab(t_n) - i_eq
        So `+i_eq` is stamped into `node_a` on the MNA RHS vector b, and `-i_eq`
        into `node_b`.
        """
        g_total = self.conductance
        i_eq = 0.0

        if not self.closed and self.arcing and self.v_breakdown is not None:
            g_arc = 1.0 / self.r_arc
            g_total += g_arc
            # i_arc = g_arc * (v_ab - s * v_bd) = g_arc * v_ab - (s * g_arc * v_bd)
            i_eq += self._arc_polarity * g_arc * self.v_breakdown

        if self.c_parasitic > 0.0 and dt > 0.0:
            if method == "backward_euler":
                g_cap = self.c_parasitic / dt
                i_cap_eq = g_cap * self.voltage
            elif method == "trapezoidal":
                g_cap = (2.0 * self.c_parasitic) / dt
                i_cap_eq = g_cap * self.voltage + self._cap_current
            else:
                raise ValueError(f"Unknown integration method {method!r}.")
            g_total += g_cap
            i_eq += i_cap_eq

        return g_total, i_eq

    def update_companion_state(
        self, v_terminal: float, dt: float, method: str = "trapezoidal"
    ) -> None:
        """Update switch voltage, current, power, and contact capacitance current."""
        i_res = v_terminal * self.conductance
        i_arc = 0.0
        if not self.closed and self.arcing and self.v_breakdown is not None:
            i_arc = (v_terminal - self._arc_polarity * self.v_breakdown) / self.r_arc

        if self.c_parasitic > 0.0 and dt > 0.0:
            if method == "backward_euler":
                g_cap = self.c_parasitic / dt
                i_cap = g_cap * (v_terminal - self.voltage)
            else:
                g_cap = (2.0 * self.c_parasitic) / dt
                i_cap = g_cap * (v_terminal - self.voltage) - self._cap_current
        else:
            i_cap = 0.0

        self._cap_current = i_cap
        self.voltage = v_terminal
        self.current = i_res + i_arc + i_cap
        self.power = v_terminal * self.current

    def toggle(self) -> bool:
        """Flip the switch between ON and OFF and return the new state."""
        self.closed = not self.closed
        if self.closed:
            self.arcing = False
            self._arc_polarity = 0.0
        return self.closed

    def set_closed(self, closed: bool) -> bool:
        """Set the switch state explicitly. Returns True if the state changed."""
        new_state = bool(closed)
        changed = new_state != self.closed
        self.closed = new_state
        if self.closed:
            self.arcing = False
            self._arc_polarity = 0.0
        return changed

    def check_timed_event(self, sim_time: float) -> bool:
        """Check whether the switch should flip at `sim_time`.

        Returns:
            True if the switch toggled on this call, False otherwise.
        """
        if (
            self.toggle_time is not None
            and not self._timer_triggered
            and sim_time >= self.toggle_time - 1e-15
        ):
            self._timer_triggered = True
            self.closed = not self.initial_closed
            if self.closed:
                self.arcing = False
                self._arc_polarity = 0.0
            return True
        return False

    def reset_state(self) -> None:
        """Restore initial switch state and clear timer and arc states."""
        super().reset_state()
        self.closed = self.initial_closed
        self._timer_triggered = False
        self._cap_current = 0.0
        self.arcing = False
        self._arc_polarity = 0.0
