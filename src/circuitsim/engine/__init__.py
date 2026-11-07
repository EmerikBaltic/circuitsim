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
from circuitsim.engine.solver import (
    IntegrationMethod,
    MNASolver,
    SolveResult,
    TransientResult,
)

__all__ = [
    "Circuit",
    "CircuitError",
    "CircuitWarning",
    "FloatingNodeError",
    "IntegrationMethod",
    "MNASolver",
    "NoGroundError",
    "SingularMatrixError",
    "SolveResult",
    "TransientResult",
    "VoltageSourceLoopError",
]
