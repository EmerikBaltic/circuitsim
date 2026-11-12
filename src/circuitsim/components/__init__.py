"""Component physics models for CircuitSim (no Qt dependencies)."""

from circuitsim.components.base import Component, ComponentParameter
from circuitsim.components.capacitor import Capacitor
from circuitsim.components.factory import (
    KNOWN_COMPONENT_TYPES,
    create_default_component_model,
)
from circuitsim.components.ground import Ground
from circuitsim.components.inductor import Inductor
from circuitsim.components.led import LED, LED_COLOUR_PRESETS
from circuitsim.components.lightbulb import Lightbulb
from circuitsim.components.meters import Ammeter, MeterMode, Voltmeter
from circuitsim.components.resistor import Resistor
from circuitsim.components.sources import (
    ACVoltageSource,
    DCCurrentSource,
    DCVoltageSource,
    WaveformType,
)
from circuitsim.components.switch import Switch

__all__ = [
    "ACVoltageSource",
    "Ammeter",
    "Capacitor",
    "Component",
    "ComponentParameter",
    "DCCurrentSource",
    "DCVoltageSource",
    "Ground",
    "Inductor",
    "KNOWN_COMPONENT_TYPES",
    "LED",
    "LED_COLOUR_PRESETS",
    "Lightbulb",
    "MeterMode",
    "Resistor",
    "Switch",
    "Voltmeter",
    "WaveformType",
    "create_default_component_model",
]
