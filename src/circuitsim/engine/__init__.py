"""Simulation engine: MNA matrix builder, solvers, session controller, and topology diagnostics."""

from circuitsim.engine.errors import (
    CircuitError,
    CircuitWarning,
    FloatingNodeError,
    NoGroundError,
    SingularMatrixError,
    VoltageSourceLoopError,
)
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.simulation_session import (
    ComponentTelemetry,
    ProblemDiagnostic,
    SimulationBackendProtocol,
    SimulationFrame,
    SimulationSession,
    SimulationSpeed,
    SimulationState,
)
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
    "ComponentTelemetry",
    "FloatingNodeError",
    "IntegrationMethod",
    "MNASolver",
    "NoGroundError",
    "ProblemDiagnostic",
    "SimulationBackendProtocol",
    "SimulationFrame",
    "SimulationSession",
    "SimulationSpeed",
    "SimulationState",
    "SingularMatrixError",
    "SolveResult",
    "TransientResult",
    "VoltageSourceLoopError",
]
