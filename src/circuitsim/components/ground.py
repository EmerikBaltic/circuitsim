"""Ground reference component."""

from __future__ import annotations

from circuitsim.components.base import Component


class Ground(Component):
    """Reference node component (0 V potential).

    Any node connected to a Ground component is treated as being at 0 V
    reference potential in Modified Nodal Analysis.
    """

    def __init__(self, name: str = "GND", node: str = "0") -> None:
        super().__init__(name=name, nodes=(node,))

    @property
    def node(self) -> str:
        """Return the node name tied to ground."""
        return self.nodes[0]

    @property
    def component_type(self) -> str:
        return "ground"
