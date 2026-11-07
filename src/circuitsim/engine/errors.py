"""Plain-language simulation errors and warnings (Section 8 of specification)."""

from __future__ import annotations

from dataclasses import dataclass


class CircuitError(Exception):
    """Base exception for invalid circuit topologies or non-convergent solves."""


class NoGroundError(CircuitError):
    """Raised when the circuit has no Ground reference component connected."""


class FloatingNodeError(CircuitError):
    """Raised when a node is disconnected from ground or has a dangling terminal."""

    def __init__(self, node: str, message: str | None = None) -> None:
        self.node = node
        super().__init__(message or f"Node {node} is floating")


class VoltageSourceLoopError(CircuitError):
    """Raised when ideal voltage sources form a loop (parallel or cycle)."""

    def __init__(
        self,
        sources: tuple[str, ...] = (),
        message: str = "Voltage sources in a loop",
    ) -> None:
        self.sources = sources
        super().__init__(message)


class SingularMatrixError(CircuitError):
    """Raised when the MNA matrix is singular and cannot be solved."""


@dataclass(frozen=True)
class CircuitWarning:
    """Non-fatal circuit diagnostic warning (e.g. parallel ammeter, inductive kickback)."""

    code: str
    message: str
    component_names: tuple[str, ...] = ()
