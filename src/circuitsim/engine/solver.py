"""Modified Nodal Analysis (MNA) solver using NumPy and SciPy LU factorization."""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
from scipy.linalg import lu_factor, lu_solve

from circuitsim.components.ground import Ground
from circuitsim.components.lightbulb import Lightbulb
from circuitsim.components.meters import Ammeter, Voltmeter
from circuitsim.components.resistor import Resistor
from circuitsim.components.sources import DCCurrentSource, DCVoltageSource
from circuitsim.components.switch import Switch
from circuitsim.engine.errors import CircuitWarning, SingularMatrixError
from circuitsim.engine.netlist import Circuit


@dataclass
class SolveResult:
    """Result of a single DC operating point or transient step solve.

    Attributes:
        node_voltages: Mapping from every node name (including grounded nodes)
            to its solved electric potential in Volts.
        branch_currents: Mapping from component name to its solved branch current
            in Amperes (passive sign convention: positive from node[0] to node[1]).
        condition_number: 2-norm condition number of the MNA matrix A, if computed.
        warnings: Non-fatal circuit warnings detected during this solve.
        rebuilt_matrix: True if the MNA matrix A was assembled and LU-factorized
            on this call; False if a cached LU factorization was reused.
    """

    node_voltages: dict[str, float]
    branch_currents: dict[str, float]
    condition_number: float | None = None
    warnings: list[CircuitWarning] = field(default_factory=list)
    rebuilt_matrix: bool = True


class MNASolver:
    """Modified Nodal Analysis (MNA) solver with SciPy LU factorization caching.

    Why GMIN (1e-12 S)?
        In circuits with open switches (1 GΩ), series capacitors, or subcircuits
        with high impedance, a tiny conductance GMIN = 1e-12 S (1 TΩ) from every
        non-ground node to ground guarantees that the nodal conductance submatrix
        G is strictly diagonally dominant / non-singular without measurably
        perturbing normal circuit voltages.

    Why cache the LU factorization (`scipy.linalg.lu_factor`)?
        Factorizing an n x n matrix takes O(n^3) work, whereas forward/backward
        substitution (`lu_solve`) takes O(n^2). When stepping a linear circuit
        with a fixed time step or varying only source excitations, the system
        matrix A does not change—only the right-hand side vector b changes.
        We therefore cache `(lu, piv)` and only re-factorize when the circuit
        topology or a component conductance changes.
    """

    DEFAULT_GMIN: float = 1e-12

    def __init__(self, circuit: Circuit, *, gmin: float = DEFAULT_GMIN) -> None:
        if gmin < 0.0:
            raise ValueError("gmin cannot be negative.")
        self.circuit: Circuit = circuit
        self.gmin: float = float(gmin)

        # Cached MNA system state
        self._cached_circuit_version: int = -1
        self._cached_conductance_signature: tuple[float, ...] = ()
        self._node_to_idx: dict[str, int] = {}
        self._vs_to_idx: dict[str, int] = {}
        self._matrix_a: np.ndarray | None = None
        self._lu_piv: tuple[np.ndarray, np.ndarray] | None = None

    def invalidate_cache(self) -> None:
        """Force the solver to rebuild and re-factorize the MNA matrix on next solve."""
        self._lu_piv = None
        self._cached_circuit_version = -1

    @property
    def matrix_a(self) -> np.ndarray | None:
        """Return a copy of the most recently assembled MNA matrix A."""
        return None if self._matrix_a is None else self._matrix_a.copy()

    def compute_condition_number(self) -> float:
        """Return the 2-norm condition number of the active MNA matrix A."""
        if self._matrix_a is None:
            raise RuntimeError("MNA matrix has not been assembled yet. Call solve_dc() first.")
        return float(np.linalg.cond(self._matrix_a))

    def _conductance_signature(self) -> tuple[float, ...]:
        """Build a lightweight tuple of conductance-determining component parameters.

        If any switch toggles, resistor value changes, or lightbulb filament
        temperature updates, this signature changes and triggers LU re-factorization.
        """
        sig: list[float] = [self.gmin]
        for comp in self.circuit.components:
            if isinstance(comp, Resistor):
                sig.append(comp.conductance)
            elif isinstance(comp, Switch):
                sig.append(comp.conductance)
            elif isinstance(comp, Lightbulb):
                sig.append(comp.conductance)
            elif isinstance(comp, (Voltmeter, Ammeter)):
                sig.append(comp.conductance)
            elif isinstance(comp, DCVoltageSource):
                sig.append(comp.r_internal)
        return tuple(sig)

    def _stamp_conductance(
        self,
        matrix_a: np.ndarray,
        node_a: str,
        node_b: str,
        g: float,
    ) -> None:
        """Stamp a two-terminal conductance `g` between `node_a` and `node_b`."""
        idx_a = self._node_to_idx.get(node_a)
        idx_b = self._node_to_idx.get(node_b)
        if idx_a is not None:
            matrix_a[idx_a, idx_a] += g
        if idx_b is not None:
            matrix_a[idx_b, idx_b] += g
        if idx_a is not None and idx_b is not None:
            matrix_a[idx_a, idx_b] -= g
            matrix_a[idx_b, idx_a] -= g

    def _assemble_and_factorize_dc(self) -> None:
        """Assemble the DC MNA matrix A and compute its SciPy LU factorization."""
        non_gnd_nodes = self.circuit.non_ground_nodes()
        self._node_to_idx = {node: idx for idx, node in enumerate(non_gnd_nodes)}

        voltage_sources = [
            comp
            for comp in self.circuit.components
            if isinstance(comp, DCVoltageSource)
        ]
        n_nodes = len(non_gnd_nodes)
        n_vs = len(voltage_sources)
        self._vs_to_idx = {
            comp.name: n_nodes + k for k, comp in enumerate(voltage_sources)
        }

        dim = n_nodes + n_vs
        matrix_a = np.zeros((dim, dim), dtype=np.float64)

        # 1. Stamp GMIN from every non-ground node to ground.
        for idx in range(n_nodes):
            matrix_a[idx, idx] += self.gmin

        # 2. Stamp conductive two-terminal components.
        for comp in self.circuit.components:
            if isinstance(comp, Ground):
                continue
            if isinstance(comp, (Resistor, Switch, Lightbulb, Voltmeter, Ammeter)):
                self._stamp_conductance(
                    matrix_a, comp.nodes[0], comp.nodes[1], comp.conductance
                )

        # 3. Stamp voltage sources (KCL incidence + branch KVL equation).
        #    Branch variable I_k is defined as current flowing INTO node_pos and
        #    OUT OF node_neg (passive convention), so delivered current is -I_k.
        #    Branch equation: V(node_pos) - V(node_neg) + r_internal * I_k = V_source
        for comp in voltage_sources:
            row_k = self._vs_to_idx[comp.name]
            idx_pos = self._node_to_idx.get(comp.nodes[0])
            idx_neg = self._node_to_idx.get(comp.nodes[1])

            if idx_pos is not None:
                matrix_a[idx_pos, row_k] += 1.0
                matrix_a[row_k, idx_pos] += 1.0
            if idx_neg is not None:
                matrix_a[idx_neg, row_k] -= 1.0
                matrix_a[row_k, idx_neg] -= 1.0

            if comp.r_internal > 0.0:
                matrix_a[row_k, row_k] += comp.r_internal

        self._matrix_a = matrix_a
        try:
            self._lu_piv = lu_factor(matrix_a, check_finite=True)
        except (ValueError, np.linalg.LinAlgError) as exc:
            raise SingularMatrixError(
                f"MNA matrix is singular and could not be factorized: {exc}"
            ) from exc

        self._cached_circuit_version = self.circuit.version
        self._cached_conductance_signature = self._conductance_signature()

    def _build_rhs_dc(self) -> np.ndarray:
        """Assemble the right-hand side excitation vector b for DC analysis."""
        dim = len(self._node_to_idx) + len(self._vs_to_idx)
        rhs_b = np.zeros(dim, dtype=np.float64)

        for comp in self.circuit.components:
            if isinstance(comp, DCCurrentSource):
                # Current source injects `dc_current` into `node_pos` and draws
                # `dc_current` from `node_neg`.
                idx_pos = self._node_to_idx.get(comp.nodes[0])
                idx_neg = self._node_to_idx.get(comp.nodes[1])
                if idx_pos is not None:
                    rhs_b[idx_pos] += comp.dc_current
                if idx_neg is not None:
                    rhs_b[idx_neg] -= comp.dc_current
            elif isinstance(comp, DCVoltageSource):
                row_k = self._vs_to_idx[comp.name]
                rhs_b[row_k] = comp.dc_voltage

        return rhs_b

    def solve_dc(self, *, compute_cond: bool = False) -> SolveResult:
        """Solve the DC operating point of the circuit.

        Validates circuit topology first, reuses the cached SciPy LU factorization
        if no conductances or connections have changed, and updates live voltage,
        current, and power attributes on every component.
        """
        warnings = self.circuit.validate_topology()

        current_sig = self._conductance_signature()
        needs_rebuild = (
            self._lu_piv is None
            or self._cached_circuit_version != self.circuit.version
            or self._cached_conductance_signature != current_sig
        )

        if needs_rebuild:
            self._assemble_and_factorize_dc()

        assert self._lu_piv is not None
        assert self._matrix_a is not None

        dim = self._matrix_a.shape[0]
        if dim > 0:
            rhs_b = self._build_rhs_dc()
            solution_x = lu_solve(self._lu_piv, rhs_b, check_finite=True)
            if not np.all(np.isfinite(solution_x)):
                raise SingularMatrixError("MNA solve produced non-finite values.")
        else:
            solution_x = np.zeros(0, dtype=np.float64)

        # Extract node voltages (grounded nodes are 0.0 V).
        node_voltages: dict[str, float] = {}
        for gnd_node in self.circuit.grounded_nodes():
            node_voltages[gnd_node] = 0.0
        for node, idx in self._node_to_idx.items():
            node_voltages[node] = float(solution_x[idx])

        # Update every component's voltage, current, and power.
        branch_currents: dict[str, float] = {}
        for comp in self.circuit.components:
            if isinstance(comp, Ground):
                comp.voltage = 0.0
                comp.current = 0.0
                comp.power = 0.0
                branch_currents[comp.name] = 0.0
                continue

            v_a = node_voltages.get(comp.nodes[0], 0.0)
            v_b = node_voltages.get(comp.nodes[1], 0.0)
            v_ab = v_a - v_b
            comp.voltage = v_ab

            if isinstance(comp, (Resistor, Switch, Lightbulb, Voltmeter, Ammeter)):
                i_ab = v_ab * comp.conductance
                comp.current = i_ab
                comp.power = v_ab * i_ab
                if isinstance(comp, Voltmeter):
                    comp.record_sample(0.0, comp.voltage, 0.0)
                elif isinstance(comp, Ammeter):
                    comp.record_sample(0.0, comp.current, 0.0)
            elif isinstance(comp, DCVoltageSource):
                row_k = self._vs_to_idx[comp.name]
                i_ab = float(solution_x[row_k])
                comp.current = i_ab
                comp.power = v_ab * i_ab
            elif isinstance(comp, DCCurrentSource):
                # Passive convention from node_pos to node_neg is -dc_current.
                i_ab = -comp.dc_current
                comp.current = i_ab
                comp.power = v_ab * i_ab
            else:
                i_ab = 0.0

            branch_currents[comp.name] = i_ab

        cond_num = self.compute_condition_number() if (compute_cond and dim > 0) else None
        return SolveResult(
            node_voltages=node_voltages,
            branch_currents=branch_currents,
            condition_number=cond_num,
            warnings=warnings,
            rebuilt_matrix=needs_rebuild,
        )
