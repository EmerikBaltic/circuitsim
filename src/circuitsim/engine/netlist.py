"""Circuit container, topological validator, and Thévenin resistance calculator."""

from __future__ import annotations

from collections import defaultdict, deque
import numpy as np

from circuitsim.components.base import Component
from circuitsim.components.capacitor import Capacitor
from circuitsim.components.ground import Ground
from circuitsim.components.inductor import Inductor
from circuitsim.components.lightbulb import Lightbulb
from circuitsim.components.meters import Ammeter, Voltmeter
from circuitsim.components.resistor import Resistor
from circuitsim.components.sources import ACVoltageSource, DCVoltageSource
from circuitsim.components.switch import Switch
from circuitsim.engine.errors import (
    CircuitWarning,
    FloatingNodeError,
    NoGroundError,
    VoltageSourceLoopError,
)


class _DisjointSet:
    """Simple Union-Find data structure for cycle and connectivity checks."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        if item not in self._parent:
            self._parent[item] = item
            return item
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        curr = item
        while curr != root:
            nxt = self._parent[curr]
            self._parent[curr] = root
            curr = nxt
        return root

    def union(self, a: str, b: str) -> bool:
        """Merge sets containing `a` and `b`. Returns False if already in same set."""
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a == root_b:
            return False
        self._parent[root_b] = root_a
        return True


class Circuit:
    """Represents an electrical circuit composed of interconnected components.

    Responsibilities:
        - Stores components by unique name.
        - Tracks which nodes are grounded (0 V reference).
        - Validates circuit topology before solving (missing ground, floating
          nodes, ideal voltage-source loops, and ammeters in parallel with
          voltage sources).
        - Computes exact DC Thévenin resistance between any two nodes with all
          independent sources zeroed.
    """

    def __init__(self) -> None:
        self._components: dict[str, Component] = {}
        self.version: int = 0

    def add(self, component: Component) -> Component:
        """Add a component to the circuit and increment the topology version."""
        if component.name in self._components:
            raise ValueError(f"Duplicate component name {component.name!r} in circuit.")
        self._components[component.name] = component
        self.version += 1
        return component

    def remove(self, name: str) -> Component:
        """Remove and return a component by name."""
        if name not in self._components:
            raise KeyError(f"Component {name!r} not found in circuit.")
        comp = self._components.pop(name)
        self.version += 1
        return comp

    def get_component(self, name: str) -> Component:
        """Return a component by its unique name."""
        if name not in self._components:
            raise KeyError(f"Component {name!r} not found in circuit.")
        return self._components[name]

    @property
    def components(self) -> list[Component]:
        """Return all components in insertion order."""
        return list(self._components.values())

    def mark_modified(self) -> None:
        """Mark the circuit parameters as modified so the solver updates its matrix."""
        self.version += 1

    def reset_state(self) -> None:
        """Reset all component states (e.g. switches, thermal filaments, meters)."""
        for comp in self._components.values():
            comp.reset_state()
        self.version += 1

    def grounded_nodes(self) -> set[str]:
        """Return the set of node names explicitly connected to a Ground component."""
        return {
            comp.node
            for comp in self._components.values()
            if isinstance(comp, Ground)
        }

    def all_nodes(self) -> set[str]:
        """Return all node names referenced by any component in the circuit."""
        nodes: set[str] = set()
        for comp in self._components.values():
            nodes.update(comp.nodes)
        return nodes

    def non_ground_nodes(self) -> list[str]:
        """Return sorted list of independent (non-grounded) node names."""
        gnd = self.grounded_nodes()
        return sorted(n for n in self.all_nodes() if n not in gnd)

    def thevenin_resistance(
        self,
        node_a: str,
        node_b: str,
        *,
        exclude_component: str | None = None,
    ) -> float:
        """Compute the DC Thévenin resistance between `node_a` and `node_b`.

        All independent voltage sources are zeroed (replaced by their `r_internal`,
        or a short circuit if `r_internal == 0`), independent current sources are
        opened (0 A), and capacitors are treated as open circuits.

        Args:
            node_a: First terminal node name.
            node_b: Second terminal node name.
            exclude_component: Optional component name (such as the target inductor
                itself) to exclude when measuring the external network resistance.
        """
        gnd_nodes = self.grounded_nodes()
        if node_a == node_b or (node_a in gnd_nodes and node_b in gnd_nodes):
            return 0.0

        non_gnd = self.non_ground_nodes()
        node_to_idx = {n: i for i, n in enumerate(non_gnd)}

        # Voltage sources become 0 V constraints with series r_internal.
        # Any other inductor with dcr == 0 also acts as a 0 V DC short branch.
        zeroed_vs_branches: list[tuple[str, str, float]] = []
        for comp in self._components.values():
            if comp.name == exclude_component or isinstance(comp, (Ground, Capacitor)):
                continue
            if isinstance(comp, (DCVoltageSource, ACVoltageSource)):
                zeroed_vs_branches.append((comp.nodes[0], comp.nodes[1], comp.r_internal))
            elif isinstance(comp, Inductor) and comp.dcr == 0.0:
                zeroed_vs_branches.append((comp.nodes[0], comp.nodes[1], 0.0))

        n_nodes = len(non_gnd)
        n_vs = len(zeroed_vs_branches)
        dim = n_nodes + n_vs
        if dim == 0:
            return 0.0

        def build_matrix(gmin_val: float) -> np.ndarray:
            mat = np.zeros((dim, dim), dtype=np.float64)
            for idx in range(n_nodes):
                mat[idx, idx] += gmin_val

            for comp in self._components.values():
                if comp.name == exclude_component or isinstance(
                    comp, (Ground, Capacitor, DCVoltageSource, ACVoltageSource)
                ):
                    continue
                g = 0.0
                if isinstance(comp, (Resistor, Switch, Lightbulb, Voltmeter, Ammeter)):
                    g = comp.conductance
                elif isinstance(comp, Inductor) and comp.dcr > 0.0:
                    g = 1.0 / comp.dcr

                if g > 0.0:
                    ia = node_to_idx.get(comp.nodes[0])
                    ib = node_to_idx.get(comp.nodes[1])
                    if ia is not None:
                        mat[ia, ia] += g
                    if ib is not None:
                        mat[ib, ib] += g
                    if ia is not None and ib is not None:
                        mat[ia, ib] -= g
                        mat[ib, ia] -= g

            for k, (na, nb, r_int) in enumerate(zeroed_vs_branches):
                row_k = n_nodes + k
                ia = node_to_idx.get(na)
                ib = node_to_idx.get(nb)
                if ia is not None:
                    mat[ia, row_k] += 1.0
                    mat[row_k, ia] += 1.0
                if ib is not None:
                    mat[ib, row_k] -= 1.0
                    mat[row_k, ib] -= 1.0
                if r_int > 0.0:
                    mat[row_k, row_k] += r_int

            return mat

        rhs = np.zeros(dim, dtype=np.float64)
        idx_a = node_to_idx.get(node_a)
        idx_b = node_to_idx.get(node_b)
        if idx_a is not None:
            rhs[idx_a] += 1.0
        if idx_b is not None:
            rhs[idx_b] -= 1.0

        try:
            sol = np.linalg.solve(build_matrix(0.0), rhs)
        except np.linalg.LinAlgError:
            sol = np.linalg.solve(build_matrix(1e-12), rhs)

        va = float(sol[idx_a]) if idx_a is not None else 0.0
        vb = float(sol[idx_b]) if idx_b is not None else 0.0
        return max(0.0, va - vb)

    def validate_topology(self) -> list[CircuitWarning]:
        """Validate the circuit graph for fatal errors and non-fatal warnings.

        Checks performed:
            1. At least one `Ground` component is connected (`NoGroundError`).
            2. Every node has at least 2 terminal connections and a path to
               ground (`FloatingNodeError`).
            3. Ideal voltage sources do not form a cycle or short to ground
               (`VoltageSourceLoopError`).
            4. Ammeters are not connected directly in parallel across fixed
               voltage sources or shorted nodes (`CircuitWarning`).

        Returns:
            List of `CircuitWarning` objects discovered during inspection.
        """
        warnings: list[CircuitWarning] = []
        gnd_nodes = self.grounded_nodes()
        if not gnd_nodes:
            raise NoGroundError("No ground connected")

        non_ground_comps = [
            c for c in self._components.values() if not isinstance(c, Ground)
        ]
        if not non_ground_comps:
            return warnings

        CANONICAL_GND = "__GND__"

        def canonical(node: str) -> str:
            return CANONICAL_GND if node in gnd_nodes else node

        terminal_degree: dict[str, int] = defaultdict(int)
        adjacency: dict[str, set[str]] = defaultdict(set)

        for comp in non_ground_comps:
            if len(comp.nodes) < 2:
                continue
            n_a, n_b = comp.nodes[0], comp.nodes[1]
            c_a, c_b = canonical(n_a), canonical(n_b)
            terminal_degree[n_a] += 1
            terminal_degree[n_b] += 1
            adjacency[c_a].add(c_b)
            adjacency[c_b].add(c_a)

        # 1. Check for dangling nodes (only 1 connection on a non-ground node).
        for node in sorted(self.all_nodes() - gnd_nodes):
            if terminal_degree[node] < 2:
                raise FloatingNodeError(node, f"Node {node} is floating")

        # 2. Check that every node has a topological path to ground.
        visited: set[str] = {CANONICAL_GND}
        queue: deque[str] = deque([CANONICAL_GND])
        while queue:
            curr = queue.popleft()
            for neighbor in adjacency.get(curr, ()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        for node in sorted(self.all_nodes() - gnd_nodes):
            if canonical(node) not in visited:
                raise FloatingNodeError(node, f"Node {node} is floating")

        # 3. Check for ideal voltage-source loops using Union-Find.
        vs_dsu = _DisjointSet()
        seen_ideal_vs: list[tuple[str, str, str]] = []
        for comp in non_ground_comps:
            is_ideal_vs = isinstance(comp, (DCVoltageSource, ACVoltageSource)) and (
                comp.r_internal == 0.0
            )
            if is_ideal_vs:
                c_a = canonical(comp.nodes[0])
                c_b = canonical(comp.nodes[1])
                if not vs_dsu.union(c_a, c_b):
                    loop_root = vs_dsu.find(c_a)
                    loop_sources = [
                        name
                        for name, na, nb in seen_ideal_vs
                        if vs_dsu.find(na) == loop_root
                    ] + [comp.name]
                    raise VoltageSourceLoopError(
                        sources=tuple(loop_sources),
                        message="Voltage sources in a loop",
                    )
                seen_ideal_vs.append((comp.name, c_a, c_b))

        # 4. Check for ammeters connected directly across a rigid voltage difference.
        battery_dsu = _DisjointSet()
        for comp in non_ground_comps:
            if isinstance(comp, (DCVoltageSource, ACVoltageSource)):
                battery_dsu.union(canonical(comp.nodes[0]), canonical(comp.nodes[1]))

        for comp in non_ground_comps:
            if isinstance(comp, Ammeter):
                c_a = canonical(comp.nodes[0])
                c_b = canonical(comp.nodes[1])
                if c_a == c_b or battery_dsu.find(c_a) == battery_dsu.find(c_b):
                    warnings.append(
                        CircuitWarning(
                            code="ammeter_in_parallel",
                            message=(
                                f"Ammeter {comp.name} is connected in parallel across "
                                "a voltage source or short circuit."
                            ),
                            component_names=(comp.name,),
                        )
                    )

        return warnings
