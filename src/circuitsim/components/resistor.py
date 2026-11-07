"""Linear resistor component model."""

from __future__ import annotations

from circuitsim.components.base import Component
from circuitsim.dialogs.value_parser import parse_engineering_value


class Resistor(Component):
    """Two-terminal linear resistor obeying Ohm's Law (V = I * R).

    Attributes:
        resistance: Resistance in Ohms (must be strictly positive).
        tolerance_pct: Manufacturing tolerance percentage (e.g., 1.0 for 1%).
        power_rating: Maximum continuous power rating in Watts (e.g., 0.25 W).
    """

    def __init__(
        self,
        name: str,
        node_a: str,
        node_b: str,
        resistance: float | str = 1000.0,
        *,
        tolerance_pct: float = 5.0,
        power_rating: float = 0.25,
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
        parsed_r = parse_engineering_value(resistance)
        if parsed_r <= 0.0:
            raise ValueError(f"Resistor {name!r}: resistance must be > 0 Ω, got {parsed_r}.")
        if power_rating <= 0.0:
            raise ValueError(f"Resistor {name!r}: power_rating must be > 0 W.")

        self.resistance: float = parsed_r
        self.tolerance_pct: float = float(tolerance_pct)
        self.power_rating: float = float(power_rating)

    @property
    def component_type(self) -> str:
        return "resistor"

    @property
    def conductance(self) -> float:
        """Return conductance G = 1 / R in Siemens."""
        return 1.0 / self.resistance

    @property
    def is_overloaded(self) -> bool:
        """Return True if dissipated power exceeds the resistor's power rating."""
        return self.power > self.power_rating
