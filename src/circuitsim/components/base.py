"""Base component abstractions for CircuitSim (pure Python, no Qt imports)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Component(ABC):
    """Abstract base class for all electrical components in a circuit.

    Attributes:
        name: Unique identifier in the circuit (e.g., "R1", "V1").
        nodes: Tuple of node names to which the component terminals connect.
        label: User-visible display label (defaults to `name`).
        show_value: Whether the component's value should be shown on the canvas.
        color: Optional display color string (e.g. hex code) for the UI.
        voltage: Latest solved voltage across the component (V_pos - V_neg), in Volts.
        current: Latest solved current through the component (from pos to neg), in Amperes.
        power: Latest solved power dissipated/absorbed by the component (V * I), in Watts.
    """

    def __init__(
        self,
        name: str,
        nodes: tuple[str, ...],
        *,
        label: str | None = None,
        show_value: bool = True,
        color: str = "#FFFFFF",
    ) -> None:
        if not name or not name.strip():
            raise ValueError("Component name must be a non-empty string.")
        self.name: str = name.strip()
        self.nodes: tuple[str, ...] = tuple(str(n).strip() for n in nodes)
        self.label: str = label if label is not None else self.name
        self.show_value: bool = show_value
        self.color: str = color

        # Live operating values updated by the solver after each solve/step.
        self.voltage: float = 0.0
        self.current: float = 0.0
        self.power: float = 0.0

    @property
    @abstractmethod
    def component_type(self) -> str:
        """Return a short canonical type identifier (e.g., 'resistor', 'dc_voltage')."""

    def reset_state(self) -> None:
        """Reset transient or thermal state back to initial conditions."""
        self.voltage = 0.0
        self.current = 0.0
        self.power = 0.0
