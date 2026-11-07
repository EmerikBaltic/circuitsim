"""Simulation engine: MNA matrix builder, solvers, and topology diagnostics."""

from circuitsim.engine.errors import (
    CircuitError,
    CircuitWarning,
    FloatingNodeError,
    NoGroundError,
    SingularMatrixError,
    VoltageSourceLoopError,
)
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.solver import MNASolver, SolveResult

__all__ = [
    "Circuit",
    "CircuitError",
    "CircuitWarning",
    "FloatingNodeError",
    "MNASolver",
    "NoGroundError",
    "SingularMatrixError",
    "SolveResult",
    "VoltageSourceLoopError",
]
