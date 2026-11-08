"""Qt-free factory that creates default component models from a type id.

Used by the canvas (placing a part from the palette) and by the `.circ` file
loader (rebuilding a part from its saved type name).
"""

from __future__ import annotations

from circuitsim.components.base import Component
from circuitsim.components.capacitor import Capacitor
from circuitsim.components.ground import Ground
from circuitsim.components.inductor import Inductor
from circuitsim.components.lightbulb import Lightbulb
from circuitsim.components.meters import Ammeter, Voltmeter
from circuitsim.components.resistor import Resistor
from circuitsim.components.sources import (
    ACVoltageSource,
    DCCurrentSource,
    DCVoltageSource,
)
from circuitsim.components.switch import Switch

KNOWN_COMPONENT_TYPES: tuple[str, ...] = (
    "resistor",
    "capacitor",
    "inductor",
    "dc_voltage",
    "ac_voltage",
    "dc_current",
    "ground",
    "switch",
    "lightbulb",
    "voltmeter",
    "ammeter",
)


def create_default_component_model(component_id: str, name: str) -> Component:
    """Create a default physics `Component` instance for `component_id`."""
    n0, n1 = f"{name}_a", f"{name}_b"
    if component_id == "resistor":
        return Resistor(name, n0, n1, resistance=1000.0)
    if component_id == "capacitor":
        return Capacitor(name, n0, n1, capacitance=1e-6)
    if component_id == "inductor":
        return Inductor(name, n0, n1, inductance=10e-3, dcr=1.0)
    if component_id == "dc_voltage":
        return DCVoltageSource(name, n0, n1, voltage=12.0)
    if component_id == "ac_voltage":
        return ACVoltageSource(name, n0, n1, amplitude=10.0, frequency=1000.0)
    if component_id == "dc_current":
        return DCCurrentSource(name, n0, n1, current=0.01)
    if component_id == "ground":
        return Ground(name, "0")
    if component_id == "switch":
        return Switch(name, n0, n1, closed=False)
    if component_id == "lightbulb":
        return Lightbulb(name, n0, n1, rated_power=60.0, rated_voltage=120.0)
    if component_id == "voltmeter":
        return Voltmeter(name, n0, n1)
    if component_id == "ammeter":
        return Ammeter(name, n0, n1)
    raise ValueError(f"Unknown component_id {component_id!r}.")
