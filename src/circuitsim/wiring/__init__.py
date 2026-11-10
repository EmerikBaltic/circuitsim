"""Explicit wiring model: attachments, junctions, netlist and routing (no Qt)."""

from circuitsim.wiring.model import (
    Attachment,
    FreeEnd,
    Junction,
    JunctionRef,
    SplitResult,
    TerminalRef,
    Wire,
    WireGraph,
    WireGraphError,
)
from circuitsim.wiring.netlist import GROUND_NODE, WiringNetlist, build_circuit
from circuitsim.wiring.router import route

__all__ = [
    "Attachment",
    "FreeEnd",
    "GROUND_NODE",
    "Junction",
    "JunctionRef",
    "SplitResult",
    "TerminalRef",
    "Wire",
    "WireGraph",
    "WireGraphError",
    "WiringNetlist",
    "build_circuit",
    "route",
]
