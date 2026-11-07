"""SPST Switch component model (Section 5.2 and 5.4 of specification)."""

from __future__ import annotations

from circuitsim.components.base import Component
from circuitsim.dialogs.value_parser import parse_engineering_value


class Switch(Component):
    """Single-Pole Single-Throw (SPST) switch modeled as a two-state resistance.

    Why finite ON and OFF resistances?
        In Modified Nodal Analysis, an ideal open switch (0 S) can leave nodes
        floating, while an ideal closed switch (infinite conductance) changes the
        number of independent nodes when toggled. Modeling ON as 1 milliohm and
        OFF as 1 gigaohm keeps the matrix topology constant and non-singular.

    Attributes:
        closed: True when the switch is ON (closed), False when OFF (open).
        r_on: Contact resistance when closed (default 1 mΩ).
        r_off: Isolation resistance when open (default 1 GΩ).
        c_parasitic: Small parasitic contact capacitance (default 10 pF, Section 5.4).
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
        if parsed_on <= 0.0 or parsed_off <= 0.0:
            raise ValueError(f"Switch {name!r}: r_on and r_off must be > 0 Ω.")
        if parsed_on >= parsed_off:
            raise ValueError(f"Switch {name!r}: r_on ({parsed_on}) must be < r_off ({parsed_off}).")
        if parsed_c < 0.0:
            raise ValueError(f"Switch {name!r}: c_parasitic cannot be negative.")

        self.initial_closed: bool = bool(closed)
        self.closed: bool = bool(closed)
        self.r_on: float = parsed_on
        self.r_off: float = parsed_off
        self.c_parasitic: float = parsed_c
        self.toggle_time: float | None = (
            parse_engineering_value(toggle_time) if toggle_time is not None else None
        )
        self.shortcut: str = shortcut
        self._timer_triggered: bool = False

    @property
    def component_type(self) -> str:
        return "switch"

    @property
    def resistance(self) -> float:
        """Current effective resistance of the switch contacts in Ohms."""
        return self.r_on if self.closed else self.r_off

    @property
    def conductance(self) -> float:
        """Current effective conductance G = 1 / R in Siemens."""
        return 1.0 / self.resistance

    def toggle(self) -> bool:
        """Flip the switch between ON and OFF and return the new state."""
        self.closed = not self.closed
        return self.closed

    def set_closed(self, closed: bool) -> bool:
        """Set the switch state explicitly. Returns True if the state changed."""
        new_state = bool(closed)
        changed = new_state != self.closed
        self.closed = new_state
        return changed

    def check_timed_event(self, sim_time: float) -> bool:
        """Check whether the switch should flip at `sim_time`.

        Returns:
            True if the switch toggled on this call, False otherwise.
        """
        if (
            self.toggle_time is not None
            and not self._timer_triggered
            and sim_time >= self.toggle_time
        ):
            self._timer_triggered = True
            self.closed = not self.initial_closed
            return True
        return False

    def reset_state(self) -> None:
        """Restore initial switch state and clear timer trigger."""
        super().reset_state()
        self.closed = self.initial_closed
        self._timer_triggered = False
