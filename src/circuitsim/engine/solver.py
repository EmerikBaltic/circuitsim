"""Modified Nodal Analysis (MNA) DC and Transient solver using NumPy and SciPy LU."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import numpy as np
from scipy.linalg import lu_factor, lu_solve

from circuitsim.components.capacitor import Capacitor
from circuitsim.components.ground import Ground
from circuitsim.components.inductor import Inductor
from circuitsim.components.led import LED
from circuitsim.components.lightbulb import Lightbulb
from circuitsim.components.meters import Ammeter, Voltmeter
from circuitsim.components.resistor import Resistor
from circuitsim.components.sources import (
    ACVoltageSource,
    DCCurrentSource,
    DCVoltageSource,
)
from circuitsim.components.switch import Switch
from circuitsim.engine.errors import CircuitWarning, SingularMatrixError
from circuitsim.engine.netlist import Circuit


class IntegrationMethod(str, Enum):
    """Numerical integration method for reactive companion models."""

    TRAPEZOIDAL = "trapezoidal"
    BACKWARD_EULER = "backward_euler"


@dataclass
class SolveResult:
    """Result of a single DC operating point or single transient step solve.

    Attributes:
        node_voltages: Mapping from every node name (including grounded nodes)
            to its solved electric potential in Volts.
        branch_currents: Mapping from component name to its solved branch current
            in Amperes (passive sign convention: positive from node[0] to node[1]).
        sim_time: Simulation timestamp in seconds (0.0 for DC operating point).
        dt: Step size used for this solve in seconds (0.0 for DC).
        integration_method: Integration method used for this step ('dc',
            'backward_euler', or 'trapezoidal').
        condition_number: 2-norm condition number of the MNA matrix A, if computed.
        warnings: Non-fatal circuit warnings detected during this solve.
        rebuilt_matrix: True if the MNA matrix A was assembled and LU-factorized
            on this call; False if a cached LU factorization was reused.
    """

    node_voltages: dict[str, float]
    branch_currents: dict[str, float]
    sim_time: float = 0.0
    dt: float = 0.0
    integration_method: str = "dc"
    condition_number: float | None = None
    warnings: list[CircuitWarning] = field(default_factory=list)
    rebuilt_matrix: bool = True


@dataclass
class TransientResult:
    """Time-series results from a multi-step transient simulation run.

    Attributes:
        times: 1D NumPy array of simulation timestamps in seconds.
        node_voltages: Mapping from node name to 1D NumPy array of voltages (V).
        branch_currents: Mapping from component name to 1D NumPy array of currents (A).
        component_voltages: Mapping from component name to 1D NumPy array of terminal
            voltages V(node_a) - V(node_b) (V).
        warnings: Deduplicated list of all `CircuitWarning` objects raised during the run.
        matrix_rebuild_count: Number of times `lu_factor` was called across the run.
        step_count: Total number of transient steps executed.
    """

    times: np.ndarray
    node_voltages: dict[str, np.ndarray]
    branch_currents: dict[str, np.ndarray]
    component_voltages: dict[str, np.ndarray]
    warnings: list[CircuitWarning] = field(default_factory=list)
    matrix_rebuild_count: int = 0
    step_count: int = 0


class MNASolver:
    """Modified Nodal Analysis (MNA) solver for DC and Transient circuit analysis.

    Numerical design highlights:
        1. `GMIN` (default 1e-12 S) is placed from every non-ground node to ground
           to prevent singular matrices when nodes are isolated behind open switches
           or series capacitors.
        2. LU factorization caching (`scipy.linalg.lu_factor` / `lu_solve`):
           During fixed-step transient simulation, the MNA matrix A depends only on
           component conductances, `dt`, and the active integration method. Once
           assembled and factorized, `(lu, piv)` is reused across hundreds or
           thousands of time steps until a switch toggles, `dt` or the integration
           method changes, or a thermal filament updates.
        3. Backward Euler startup and switch-event damping:
           Trapezoidal integration is second-order accurate (O(dt^2)) and energy-
           conserving (no artificial damping on lossless LC tanks), but it is not
           L-stable: step discontinuities (such as t = 0 startup or a switch
           toggling) cause step-to-step alternating ringing in the companion history
           currents. Using Backward Euler on the first step and for 2 damping steps
           upon any switch toggle settles discontinuous jumps cleanly before
           resuming Trapezoidal integration.
    """

    DEFAULT_GMIN: float = 1e-12
    KICKBACK_VOLTAGE_WARNING_MIN: float = 100.0

    def __init__(self, circuit: Circuit, *, gmin: float = DEFAULT_GMIN) -> None:
        if gmin < 0.0:
            raise ValueError("gmin cannot be negative.")
        self.circuit: Circuit = circuit
        self.gmin: float = float(gmin)

        # Transient clock and damping counter
        self.sim_time: float = 0.0
        self._transient_step_index: int = 0
        # Number of upcoming transient steps that must use Backward Euler
        # (initialized to 1 for the very first transient step, and set to 2
        # whenever a switch toggles to settle the impulse derivative).
        self._be_steps_remaining: int = 1

        # Cached MNA system state
        self._cached_mode: str = ""
        self._cached_circuit_version: int = -1
        self._cached_conductance_signature: tuple[float, ...] = ()
        self._node_to_idx: dict[str, int] = {}
        self._vs_to_idx: dict[str, int] = {}
        self._matrix_a: np.ndarray | None = None
        self._lu_piv: tuple[np.ndarray, np.ndarray] | None = None
        self._topology_warnings: list[CircuitWarning] = []

    def invalidate_cache(self) -> None:
        """Force the solver to rebuild and re-factorize the MNA matrix on next solve."""
        self._lu_piv = None
        self._cached_circuit_version = -1
        self._cached_mode = ""

    def reset_transient(self) -> None:
        """Reset simulation time, component states, and solver cache."""
        self.sim_time = 0.0
        self._transient_step_index = 0
        self._be_steps_remaining = 1
        self.circuit.reset_state()
        self.invalidate_cache()

    @property
    def matrix_a(self) -> np.ndarray | None:
        """Return a copy of the most recently assembled MNA matrix A."""
        return None if self._matrix_a is None else self._matrix_a.copy()

    def compute_condition_number(self) -> float:
        """Return the 2-norm condition number of the active MNA matrix A."""
        if self._matrix_a is None:
            raise RuntimeError("MNA matrix has not been assembled yet.")
        return float(np.linalg.cond(self._matrix_a))

    def choose_default_dt(self, duration: float | None = None) -> float:
        """Choose a safe default transient time step `dt` based on circuit timescales.

        Default Time-Step Rule:
            1. AC sources: at least 100 steps per period of the highest frequency
               AC source (`dt <= 1 / (100 * f_max)`), matching Section 7.2.
            2. RL time constants: at least 50 steps per RL time constant
               (`dt <= tau_L / 50`) for active inductive branches.
            3. RC time constants: at least 50 steps per RC time constant
               (`dt <= R_th * C / 50`) when R_th * C > 0.
            4. LC resonant tanks: at least 100 steps per resonant period
               (`dt <= 2 * pi * sqrt(L * C) / 100`).
            5. Total duration: if `duration` is specified, at least 200 steps across
               the run (`dt <= duration / 200`).
            6. Fallback default for purely resistive DC circuits: `dt = 1e-4 s` (100 us).
        """
        candidates: list[float] = []
        if duration is not None and duration > 0.0:
            candidates.append(duration / 200.0)
        else:
            candidates.append(1e-4)

        inductances: list[float] = []
        capacitances: list[float] = []

        for comp in self.circuit.components:
            if isinstance(comp, ACVoltageSource) and comp.frequency > 0.0:
                candidates.append(1.0 / (100.0 * comp.frequency))
            elif isinstance(comp, Inductor):
                inductances.append(comp.inductance)
                tau_l = comp.time_constant(self.circuit)
                if math.isfinite(tau_l) and tau_l > 1e-9:
                    candidates.append(tau_l / 50.0)
            elif isinstance(comp, Capacitor):
                capacitances.append(comp.capacitance)
                r_th = self.circuit.thevenin_resistance(
                    comp.nodes[0], comp.nodes[1], exclude_component=comp.name
                )
                tau_c = r_th * comp.capacitance
                if math.isfinite(tau_c) and tau_c > 1e-9:
                    candidates.append(tau_c / 50.0)

        if inductances and capacitances:
            min_l = min(inductances)
            min_c = min(capacitances)
            t_lc = 2.0 * math.pi * math.sqrt(min_l * min_c)
            if t_lc > 0.0:
                candidates.append(t_lc / 100.0)

        chosen = min(candidates)
        return max(1e-12, chosen)

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

    def _voltage_sources(self) -> list[DCVoltageSource | ACVoltageSource]:
        return [
            comp
            for comp in self.circuit.components
            if isinstance(comp, (DCVoltageSource, ACVoltageSource))
        ]

    def _dc_conductance_signature(self) -> tuple[float, ...]:
        sig: list[float] = [self.gmin]
        for comp in self.circuit.components:
            if isinstance(comp, (Resistor, Switch, Lightbulb, Voltmeter, Ammeter, LED)):
                sig.append(comp.conductance)
            elif isinstance(comp, Inductor):
                sig.append(comp.dc_conductance)
            elif isinstance(comp, (DCVoltageSource, ACVoltageSource)):
                sig.append(comp.r_internal)
        return tuple(sig)

    def _transient_conductance_signature(
        self, dt: float, method_str: str
    ) -> tuple[float, ...]:
        method_code = 1.0 if method_str == "backward_euler" else 2.0
        sig: list[float] = [self.gmin, dt, method_code]
        for comp in self.circuit.components:
            if isinstance(comp, (Resistor, Lightbulb, Voltmeter, Ammeter)):
                sig.append(comp.conductance)
            elif isinstance(comp, LED):
                g_led, _ = comp.companion_model(dt, method_str)
                sig.append(g_led)
            elif isinstance(comp, Switch):
                g_sw, _ = comp.companion_model(dt, method_str)
                sig.append(g_sw)
            elif isinstance(comp, Capacitor):
                g_c, _ = comp.companion_model(dt, method_str)
                sig.append(g_c)
            elif isinstance(comp, Inductor):
                g_l, _ = comp.companion_model(dt, method_str)
                sig.append(g_l)
            elif isinstance(comp, (DCVoltageSource, ACVoltageSource)):
                sig.append(comp.r_internal)
        return tuple(sig)

    def _assemble_and_factorize(
        self,
        *,
        mode: str,
        dt: float = 0.0,
        method_str: str = "trapezoidal",
    ) -> None:
        """Assemble the MNA matrix A (for DC or transient) and compute its LU factors."""
        non_gnd_nodes = self.circuit.non_ground_nodes()
        self._node_to_idx = {node: idx for idx, node in enumerate(non_gnd_nodes)}

        voltage_sources = self._voltage_sources()
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

        # 2. Stamp conductive and companion two-terminal components.
        for comp in self.circuit.components:
            if isinstance(comp, Ground):
                continue
            if isinstance(comp, (Resistor, Lightbulb, Voltmeter, Ammeter)):
                self._stamp_conductance(
                    matrix_a, comp.nodes[0], comp.nodes[1], comp.conductance
                )
            elif isinstance(comp, LED):
                g_led, _ = comp.companion_model(dt if mode != "dc" else 0.0, method_str if mode != "dc" else "dc")
                self._stamp_conductance(matrix_a, comp.nodes[0], comp.nodes[1], g_led)
            elif isinstance(comp, Switch):
                if mode == "dc":
                    g_sw = comp.conductance
                else:
                    g_sw, _ = comp.companion_model(dt, method_str)
                self._stamp_conductance(matrix_a, comp.nodes[0], comp.nodes[1], g_sw)
            elif isinstance(comp, Capacitor):
                if mode != "dc":
                    g_eq, _ = comp.companion_model(dt, method_str)
                    self._stamp_conductance(
                        matrix_a, comp.nodes[0], comp.nodes[1], g_eq
                    )
            elif isinstance(comp, Inductor):
                if mode == "dc":
                    self._stamp_conductance(
                        matrix_a, comp.nodes[0], comp.nodes[1], comp.dc_conductance
                    )
                else:
                    g_eq, _ = comp.companion_model(dt, method_str)
                    self._stamp_conductance(
                        matrix_a, comp.nodes[0], comp.nodes[1], g_eq
                    )

        # 3. Stamp voltage sources (KCL incidence + branch KVL equation).
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
        if dim > 0:
            try:
                self._lu_piv = lu_factor(matrix_a, check_finite=True)
            except (ValueError, np.linalg.LinAlgError) as exc:
                raise SingularMatrixError(
                    f"MNA matrix is singular and could not be factorized: {exc}"
                ) from exc
        else:
            self._lu_piv = (
                np.zeros((0, 0), dtype=np.float64),
                np.zeros(0, dtype=np.int32),
            )

        self._cached_mode = mode
        self._cached_circuit_version = self.circuit.version
        if mode == "dc":
            self._cached_conductance_signature = self._dc_conductance_signature()
        else:
            self._cached_conductance_signature = self._transient_conductance_signature(
                dt, method_str
            )

    def _build_rhs_dc(self) -> np.ndarray:
        """Assemble the right-hand side excitation vector b for DC operating point."""
        dim = len(self._node_to_idx) + len(self._vs_to_idx)
        rhs_b = np.zeros(dim, dtype=np.float64)

        for comp in self.circuit.components:
            if isinstance(comp, DCCurrentSource):
                idx_pos = self._node_to_idx.get(comp.nodes[0])
                idx_neg = self._node_to_idx.get(comp.nodes[1])
                if idx_pos is not None:
                    rhs_b[idx_pos] += comp.dc_current
                if idx_neg is not None:
                    rhs_b[idx_neg] -= comp.dc_current
            elif isinstance(comp, DCVoltageSource):
                row_k = self._vs_to_idx[comp.name]
                rhs_b[row_k] = comp.dc_voltage
            elif isinstance(comp, ACVoltageSource):
                row_k = self._vs_to_idx[comp.name]
                rhs_b[row_k] = comp.voltage_at(0.0)
            elif isinstance(comp, LED):
                _, i_eq = comp.companion_model(0.0, "dc")
                idx_a = self._node_to_idx.get(comp.nodes[0])
                idx_k = self._node_to_idx.get(comp.nodes[1])
                if idx_a is not None:
                    rhs_b[idx_a] += i_eq
                if idx_k is not None:
                    rhs_b[idx_k] -= i_eq

        return rhs_b

    def _build_rhs_transient(
        self, sim_time: float, dt: float, method_str: str
    ) -> np.ndarray:
        """Assemble the right-hand side vector b for a transient step at `sim_time`."""
        dim = len(self._node_to_idx) + len(self._vs_to_idx)
        rhs_b = np.zeros(dim, dtype=np.float64)

        for comp in self.circuit.components:
            if isinstance(comp, DCCurrentSource):
                idx_pos = self._node_to_idx.get(comp.nodes[0])
                idx_neg = self._node_to_idx.get(comp.nodes[1])
                if idx_pos is not None:
                    rhs_b[idx_pos] += comp.dc_current
                if idx_neg is not None:
                    rhs_b[idx_neg] -= comp.dc_current
            elif isinstance(comp, (DCVoltageSource, ACVoltageSource)):
                row_k = self._vs_to_idx[comp.name]
                rhs_b[row_k] = comp.voltage_at(sim_time)
            elif isinstance(comp, LED):
                _, i_eq = comp.companion_model(dt, method_str)
                idx_a = self._node_to_idx.get(comp.nodes[0])
                idx_k = self._node_to_idx.get(comp.nodes[1])
                if idx_a is not None:
                    rhs_b[idx_a] += i_eq
                if idx_k is not None:
                    rhs_b[idx_k] -= i_eq
            elif isinstance(comp, Switch) and (comp.c_parasitic > 0.0 or comp.arcing):
                _, i_sw_eq = comp.companion_model(dt, method_str)
                idx_a = self._node_to_idx.get(comp.nodes[0])
                idx_b = self._node_to_idx.get(comp.nodes[1])
                if idx_a is not None:
                    rhs_b[idx_a] += i_sw_eq
                if idx_b is not None:
                    rhs_b[idx_b] -= i_sw_eq
            elif isinstance(comp, Capacitor):
                # i_ab(t_n) = G_eq * v_ab(t_n) - I_eq
                # KCL at node_a: +G_eq * v_ab - I_eq => move +I_eq to RHS at node_a
                _, i_eq = comp.companion_model(dt, method_str)
                idx_a = self._node_to_idx.get(comp.nodes[0])
                idx_b = self._node_to_idx.get(comp.nodes[1])
                if idx_a is not None:
                    rhs_b[idx_a] += i_eq
                if idx_b is not None:
                    rhs_b[idx_b] -= i_eq
            elif isinstance(comp, Inductor):
                # i_ab(t_n) = G_eq * v_ab(t_n) + I_hist
                # KCL at node_a: +G_eq * v_ab + I_hist => move -I_hist to RHS at node_a
                _, i_hist = comp.companion_model(dt, method_str)
                idx_a = self._node_to_idx.get(comp.nodes[0])
                idx_b = self._node_to_idx.get(comp.nodes[1])
                if idx_a is not None:
                    rhs_b[idx_a] -= i_hist
                if idx_b is not None:
                    rhs_b[idx_b] += i_hist

        return rhs_b

    def solve_dc(self, *, compute_cond: bool = False) -> SolveResult:
        """Solve the DC operating point of the circuit.

        Capacitors are treated as open circuits (keeping any configured initial
        voltage if isolated) and inductors are modeled using their winding
        resistance (`max(dcr, 1 mΩ)`).
        """
        warnings = self.circuit.validate_topology()
        self._topology_warnings = list(warnings)

        has_leds = any(isinstance(c, LED) for c in self.circuit.components)
        max_diode_iters = 10 if has_leds else 1

        for _d_iter in range(max_diode_iters):
            current_sig = self._dc_conductance_signature()
            needs_rebuild = (
                self._lu_piv is None
                or self._cached_mode != "dc"
                or self._cached_circuit_version != self.circuit.version
                or self._cached_conductance_signature != current_sig
            )

            if needs_rebuild:
                self._assemble_and_factorize(mode="dc")

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

            node_voltages: dict[str, float] = {}
            for gnd_node in self.circuit.grounded_nodes():
                node_voltages[gnd_node] = 0.0
            for node, idx in self._node_to_idx.items():
                node_voltages[node] = float(solution_x[idx])

            state_changed = False
            for comp in self.circuit.components:
                if isinstance(comp, LED) and not comp.burned_out:
                    v_ak = node_voltages.get(comp.nodes[0], 0.0) - node_voltages.get(comp.nodes[1], 0.0)
                    if comp.is_conducting:
                        i_ak = (v_ak - comp.forward_voltage) / comp.r_on
                        if i_ak < -1e-9 or v_ak < comp.forward_voltage - 1e-4:
                            comp.is_conducting = False
                            state_changed = True
                    else:
                        if v_ak > comp.forward_voltage + 1e-4:
                            comp.is_conducting = True
                            state_changed = True

            if not state_changed:
                break

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
            elif isinstance(comp, LED):
                if comp.burned_out:
                    i_ab = v_ab / comp.r_off
                    comp.is_conducting = False
                    comp.brightness = 0.0
                    comp.is_over_current = False
                elif comp.is_conducting:
                    i_ab = (v_ab - comp.forward_voltage) / comp.r_on
                else:
                    i_ab = v_ab / comp.r_off
                comp.current = i_ab
                comp.power = v_ab * i_ab
                if comp.burned_out or i_ab < 1e-5:
                    comp.brightness = 0.0
                else:
                    comp.brightness = math.sqrt(max(0.0, i_ab) / comp.rated_current)
                comp.is_over_current = (i_ab > comp.max_current and not comp.burned_out)
                if comp.burnout_enabled and i_ab >= comp.burnout_current:
                    comp.burned_out = True
                    comp.is_conducting = False
                    comp.brightness = 0.0
                    comp.is_over_current = False
            elif isinstance(comp, Capacitor):
                comp.current = 0.0
                comp.power = 0.0
                comp.cap_voltage = v_ab
                comp.cap_current = 0.0
                i_ab = 0.0
            elif isinstance(comp, Inductor):
                i_ab = v_ab * comp.dc_conductance
                comp.current = i_ab
                comp.power = v_ab * i_ab
                comp.ind_current = i_ab
                comp.ind_voltage = 0.0
            elif isinstance(comp, (DCVoltageSource, ACVoltageSource)):
                row_k = self._vs_to_idx[comp.name]
                i_ab = float(solution_x[row_k])
                comp.current = i_ab
                comp.power = v_ab * i_ab
            elif isinstance(comp, DCCurrentSource):
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
            sim_time=0.0,
            dt=0.0,
            integration_method="dc",
            condition_number=cond_num,
            warnings=warnings,
            rebuilt_matrix=needs_rebuild,
        )

    def _initialize_t0_derivatives(self) -> None:
        """Compute exact t = 0+ voltages/currents given initial capacitor V0 and inductor I0.

        Why this matters:
            At t = 0+, each capacitor acts as an exact voltage source `cap_voltage`
            (with series resistance `esr`) and each inductor acts as an exact current
            source `ind_current`. Solving the exact t = 0+ circuit gives `v_L(0+)` and
            `i_C(0+)` to full 64-bit machine precision without any finite-difference
            probe error, preserving exact energy conservation and 2nd-order convergence
            for Trapezoidal integration from step 0.
        """
        capacitors = [c for c in self.circuit.components if isinstance(c, Capacitor)]
        inductors = [c for c in self.circuit.components if isinstance(c, Inductor)]
        if not capacitors and not inductors:
            return

        non_gnd_nodes = self.circuit.non_ground_nodes()
        node_to_idx = {node: idx for idx, node in enumerate(non_gnd_nodes)}
        voltage_sources = self._voltage_sources()

        n_nodes = len(non_gnd_nodes)
        n_vs = len(voltage_sources)
        n_caps = len(capacitors)
        dim = n_nodes + n_vs + n_caps
        if dim == 0:
            return

        mat = np.zeros((dim, dim), dtype=np.float64)
        rhs = np.zeros(dim, dtype=np.float64)

        for idx in range(n_nodes):
            mat[idx, idx] += max(self.gmin, 1e-15)

        for comp in self.circuit.components:
            if isinstance(comp, (Resistor, Switch, Lightbulb, Voltmeter, Ammeter)):
                g = comp.conductance
                ia = node_to_idx.get(comp.nodes[0])
                ib = node_to_idx.get(comp.nodes[1])
                if ia is not None:
                    mat[ia, ia] += g
                if ib is not None:
                    mat[ib, ib] += g
                if ia is not None and ib is not None:
                    mat[ia, ib] -= g
                    mat[ib, ia] -= g
            elif isinstance(comp, DCCurrentSource):
                ia = node_to_idx.get(comp.nodes[0])
                ib = node_to_idx.get(comp.nodes[1])
                if ia is not None:
                    rhs[ia] += comp.dc_current
                if ib is not None:
                    rhs[ib] -= comp.dc_current
            elif isinstance(comp, Inductor):
                # At t = 0+, an inductor carries current `ind_current` from node_a to node_b
                ia = node_to_idx.get(comp.nodes[0])
                ib = node_to_idx.get(comp.nodes[1])
                if ia is not None:
                    rhs[ia] -= comp.ind_current
                if ib is not None:
                    rhs[ib] += comp.ind_current

        for k, vs in enumerate(voltage_sources):
            row_k = n_nodes + k
            ia = node_to_idx.get(vs.nodes[0])
            ib = node_to_idx.get(vs.nodes[1])
            if ia is not None:
                mat[ia, row_k] += 1.0
                mat[row_k, ia] += 1.0
            if ib is not None:
                mat[ib, row_k] -= 1.0
                mat[row_k, ib] -= 1.0
            if vs.r_internal > 0.0:
                mat[row_k, row_k] += vs.r_internal
            rhs[row_k] = vs.voltage_at(0.0)

        for k, cap in enumerate(capacitors):
            row_k = n_nodes + n_vs + k
            ia = node_to_idx.get(cap.nodes[0])
            ib = node_to_idx.get(cap.nodes[1])
            # Branch variable is i_C(0+) flowing from node_a to node_b:
            # V(node_a) - V(node_b) - esr * i_C(0+) = cap_voltage
            if ia is not None:
                mat[ia, row_k] += 1.0
                mat[row_k, ia] += 1.0
            if ib is not None:
                mat[ib, row_k] -= 1.0
                mat[row_k, ib] -= 1.0
            if cap.esr > 0.0:
                mat[row_k, row_k] -= cap.esr
            rhs[row_k] = cap.cap_voltage

        try:
            sol_x = np.linalg.solve(mat, rhs)
        except np.linalg.LinAlgError:
            return

        node_v: dict[str, float] = {g: 0.0 for g in self.circuit.grounded_nodes()}
        for node, idx in node_to_idx.items():
            node_v[node] = float(sol_x[idx])

        for k, cap in enumerate(capacitors):
            row_k = n_nodes + n_vs + k
            i_c0 = float(sol_x[row_k])
            v_ab = node_v.get(cap.nodes[0], 0.0) - node_v.get(cap.nodes[1], 0.0)
            cap.cap_current = i_c0
            cap.voltage = v_ab
            cap.current = i_c0
            cap.power = v_ab * i_c0

        for ind in inductors:
            v_ab = node_v.get(ind.nodes[0], 0.0) - node_v.get(ind.nodes[1], 0.0)
            ind.ind_voltage = v_ab - ind.dcr * ind.ind_current
            ind.voltage = v_ab
            ind.current = ind.ind_current
            ind.power = v_ab * ind.ind_current

        self.invalidate_cache()

    def step_transient(
        self,
        dt: float,
        *,
        method: IntegrationMethod | str = IntegrationMethod.TRAPEZOIDAL,
        use_be_on_first_step: bool = True,
        use_be_on_switch: bool = True,
        compute_cond: bool = False,
    ) -> SolveResult:
        """Advance the transient simulation by one time step `dt` (in seconds).

        Args:
            dt: Time step size in seconds (must be > 0).
            method: Base integration method (`TRAPEZOIDAL` by default, or
                `BACKWARD_EULER`).
            use_be_on_first_step: When True (default), uses Backward Euler on the
                very first step (`step_index == 0`), as specified in Milestone 1.
            use_be_on_switch: When True (default), automatically switches to
                Backward Euler when any `Switch` toggles so discontinuous jumps do
                not trigger Trapezoidal numerical ringing.
            compute_cond: Whether to compute the 2-norm condition number on this step.
        """
        if dt <= 0.0:
            raise ValueError(f"Transient step dt must be > 0, got {dt}.")

        if self._transient_step_index == 0:
            self._topology_warnings = self.circuit.validate_topology()
            if not use_be_on_first_step:
                self._initialize_t0_derivatives()
                self._be_steps_remaining = 0

        t_next = self.sim_time + dt

        # 1. Check timed switches and update thermal lightbulb states from previous step.
        switch_toggled = False
        switch_opened = False
        for comp in self.circuit.components:
            if isinstance(comp, Switch):
                was_closed = comp.closed
                if comp.check_timed_event(t_next):
                    switch_toggled = True
                    if was_closed and not comp.closed:
                        switch_opened = True
            elif isinstance(comp, Lightbulb) and self._transient_step_index > 0:
                comp.advance_thermal_state(dt)

        if switch_toggled and use_be_on_switch:
            # Use Backward Euler on the switching step and two settling steps after it
            # so stiff impulse currents decay before Trapezoidal integration resumes.
            self._be_steps_remaining = max(self._be_steps_remaining, 3)

        base_method = (
            IntegrationMethod(method)
            if not isinstance(method, IntegrationMethod)
            else method
        )
        if base_method == IntegrationMethod.BACKWARD_EULER:
            active_method = IntegrationMethod.BACKWARD_EULER
        elif self._be_steps_remaining > 0:
            active_method = IntegrationMethod.BACKWARD_EULER
            self._be_steps_remaining -= 1
        else:
            active_method = IntegrationMethod.TRAPEZOIDAL

        method_str = active_method.value

        # 2. Check if we can reuse the cached LU factorization or must rebuild A.
        current_sig = self._transient_conductance_signature(dt, method_str)
        needs_rebuild = (
            self._lu_piv is None
            or self._cached_mode != "transient"
            or self._cached_circuit_version != self.circuit.version
            or self._cached_conductance_signature != current_sig
        )

        if needs_rebuild:
            self._assemble_and_factorize(
                mode="transient", dt=dt, method_str=method_str
            )

        assert self._lu_piv is not None
        assert self._matrix_a is not None

        # 3. Assemble RHS vector b(t_next) and solve using cached LU factors.
        dim = self._matrix_a.shape[0]
        if dim > 0:
            rhs_b = self._build_rhs_transient(t_next, dt, method_str)
            solution_x = lu_solve(self._lu_piv, rhs_b, check_finite=True)
            if not np.all(np.isfinite(solution_x)):
                raise SingularMatrixError(
                    f"Transient solve did not converge at t = {t_next:.6g} s."
                )
        else:
            solution_x = np.zeros(0, dtype=np.float64)

        node_voltages: dict[str, float] = {}
        for gnd_node in self.circuit.grounded_nodes():
            node_voltages[gnd_node] = 0.0
        for node, idx in self._node_to_idx.items():
            node_voltages[node] = float(solution_x[idx])

        # 3b. Check for switch contact breakdown arc ignition or extinction.
        #     Treat arc start/stop like a switch event: refactorize and settle with
        #     Backward Euler on this step and the following two steps.
        arc_state_changed = False
        arc_ignited_switches: list[str] = []
        for comp in self.circuit.components:
            if isinstance(comp, Switch) and not comp.closed:
                v_sw = node_voltages.get(comp.nodes[0], 0.0) - node_voltages.get(
                    comp.nodes[1], 0.0
                )
                if not comp.arcing and comp.check_arc_ignition(v_sw):
                    arc_state_changed = True
                    arc_ignited_switches.append(comp.name)
                elif comp.arcing and comp.check_arc_extinction(v_sw):
                    arc_state_changed = True

        if arc_state_changed:
            if use_be_on_switch:
                active_method = IntegrationMethod.BACKWARD_EULER
                method_str = active_method.value
                self._be_steps_remaining = max(self._be_steps_remaining, 2)
            self._assemble_and_factorize(
                mode="transient", dt=dt, method_str=method_str
            )
            needs_rebuild = True
            assert self._lu_piv is not None
            if dim > 0:
                rhs_b = self._build_rhs_transient(t_next, dt, method_str)
                solution_x = lu_solve(self._lu_piv, rhs_b, check_finite=True)
                for node, idx in self._node_to_idx.items():
                    node_voltages[node] = float(solution_x[idx])

        # 3c. Check for LED conduction state transitions
        for _diode_iter in range(5):
            led_state_changed = False
            for comp in self.circuit.components:
                if isinstance(comp, LED) and not comp.burned_out:
                    v_ak = node_voltages.get(comp.nodes[0], 0.0) - node_voltages.get(comp.nodes[1], 0.0)
                    if comp.is_conducting:
                        i_ak = (v_ak - comp.forward_voltage) / comp.r_on
                        if i_ak < -1e-9 or v_ak < comp.forward_voltage - 1e-4:
                            comp.is_conducting = False
                            led_state_changed = True
                    else:
                        if v_ak > comp.forward_voltage + 1e-4:
                            comp.is_conducting = True
                            led_state_changed = True
            if not led_state_changed:
                break
            self._assemble_and_factorize(
                mode="transient", dt=dt, method_str=method_str
            )
            needs_rebuild = True
            assert self._lu_piv is not None
            if dim > 0:
                rhs_b = self._build_rhs_transient(t_next, dt, method_str)
                solution_x = lu_solve(self._lu_piv, rhs_b, check_finite=True)
                for node, idx in self._node_to_idx.items():
                    node_voltages[node] = float(solution_x[idx])

        # 4. Update component voltages, currents, companion states, and meter buffers.
        step_warnings: list[CircuitWarning] = list(self._topology_warnings)
        branch_currents: dict[str, float] = {}

        # Nominal source voltage scale for inductive kickback comparison
        max_source_v = max(
            (
                abs(c.dc_voltage)
                if isinstance(c, DCVoltageSource)
                else (abs(c.amplitude) + abs(c.dc_offset))
                if isinstance(c, ACVoltageSource)
                else 0.0
                for c in self.circuit.components
            ),
            default=10.0,
        )
        kickback_threshold = max(
            self.KICKBACK_VOLTAGE_WARNING_MIN, 5.0 * max_source_v
        )

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

            if isinstance(comp, (Resistor, Lightbulb, Voltmeter, Ammeter)):
                i_ab = v_ab * comp.conductance
                comp.voltage = v_ab
                comp.current = i_ab
                comp.power = v_ab * i_ab
                if isinstance(comp, Voltmeter):
                    comp.record_sample(t_next, comp.voltage, dt)
                elif isinstance(comp, Ammeter):
                    comp.record_sample(t_next, comp.current, dt)
            elif isinstance(comp, LED):
                comp.voltage = v_ab
                if comp.burned_out:
                    i_ab = v_ab / comp.r_off
                    comp.is_conducting = False
                    comp.brightness = 0.0
                    comp.is_over_current = False
                elif comp.is_conducting:
                    i_ab = (v_ab - comp.forward_voltage) / comp.r_on
                else:
                    i_ab = v_ab / comp.r_off
                comp.current = i_ab
                comp.power = v_ab * i_ab
                if comp.burned_out or i_ab < 1e-5:
                    comp.brightness = 0.0
                else:
                    comp.brightness = math.sqrt(max(0.0, i_ab) / comp.rated_current)
                comp.is_over_current = (i_ab > comp.max_current and not comp.burned_out)
                if comp.burnout_enabled and i_ab >= comp.burnout_current:
                    comp.burned_out = True
                    comp.is_conducting = False
                    comp.brightness = 0.0
                    comp.is_over_current = False
            elif isinstance(comp, Switch):
                comp.update_companion_state(v_ab, dt, method_str)
                i_ab = comp.current
            elif isinstance(comp, Capacitor):
                g_eq, i_eq = comp.companion_model(dt, method_str)
                i_ab = g_eq * v_ab - i_eq
                comp.update_companion_state(v_ab, i_ab)
            elif isinstance(comp, Inductor):
                g_eq, i_hist = comp.companion_model(dt, method_str)
                i_ab = g_eq * v_ab + i_hist
                comp.update_companion_state(v_ab, i_ab)
                if (
                    abs(comp.ind_voltage) >= kickback_threshold
                    or (switch_opened and abs(comp.ind_voltage) > 2.0 * max_source_v)
                    or bool(arc_ignited_switches)
                ):
                    step_warnings.append(
                        CircuitWarning(
                            code="inductive_kickback",
                            message="Inductive kickback, consider a flyback diode",
                            component_names=(comp.name,),
                        )
                    )
            elif isinstance(comp, (DCVoltageSource, ACVoltageSource)):
                row_k = self._vs_to_idx[comp.name]
                i_ab = float(solution_x[row_k])
                comp.voltage = v_ab
                comp.current = i_ab
                comp.power = v_ab * i_ab
            elif isinstance(comp, DCCurrentSource):
                i_ab = -comp.dc_current
                comp.voltage = v_ab
                comp.current = i_ab
                comp.power = v_ab * i_ab
            else:
                i_ab = 0.0

            branch_currents[comp.name] = i_ab

        self.sim_time = t_next
        self._transient_step_index += 1
        cond_num = self.compute_condition_number() if (compute_cond and dim > 0) else None

        return SolveResult(
            node_voltages=node_voltages,
            branch_currents=branch_currents,
            sim_time=t_next,
            dt=dt,
            integration_method=method_str,
            condition_number=cond_num,
            warnings=step_warnings,
            rebuilt_matrix=needs_rebuild,
        )

    def solve_transient(
        self,
        duration: float,
        dt: float | None = None,
        *,
        method: IntegrationMethod | str = IntegrationMethod.TRAPEZOIDAL,
        use_be_on_first_step: bool = True,
        use_be_on_switch: bool = True,
        reset_before_run: bool = True,
    ) -> TransientResult:
        """Run a transient simulation from `t = 0` (or current `sim_time`) for `duration` s.

        Returns a `TransientResult` with NumPy waveform arrays for every node and
        component, including the initial state at index 0 (`t = 0`).
        """
        if duration <= 0.0:
            raise ValueError(f"Transient duration must be > 0 s, got {duration}.")

        if reset_before_run:
            self.reset_transient()

        step_dt = dt if (dt is not None and dt > 0.0) else self.choose_default_dt(duration)
        n_steps = max(1, int(round(duration / step_dt)))

        # Validate topology and initialize t = 0+ voltages/currents for index 0 recording.
        all_warnings: list[CircuitWarning] = list(self.circuit.validate_topology())
        self._topology_warnings = list(all_warnings)
        self._initialize_t0_derivatives()
        if use_be_on_first_step:
            self._be_steps_remaining = 1
        else:
            self._be_steps_remaining = 0

        all_nodes = sorted(self.circuit.all_nodes())
        comp_names = [c.name for c in self.circuit.components]

        times = np.zeros(n_steps + 1, dtype=np.float64)
        node_history: dict[str, np.ndarray] = {
            n: np.zeros(n_steps + 1, dtype=np.float64) for n in all_nodes
        }
        curr_history: dict[str, np.ndarray] = {
            name: np.zeros(n_steps + 1, dtype=np.float64) for name in comp_names
        }
        volt_history: dict[str, np.ndarray] = {
            name: np.zeros(n_steps + 1, dtype=np.float64) for name in comp_names
        }

        # Record t = 0 state
        times[0] = self.sim_time
        gnd_nodes = self.circuit.grounded_nodes()
        for comp in self.circuit.components:
            curr_history[comp.name][0] = comp.current
            volt_history[comp.name][0] = comp.voltage
            if not isinstance(comp, Ground) and len(comp.nodes) >= 2:
                if comp.nodes[1] in gnd_nodes and comp.nodes[0] not in gnd_nodes:
                    node_history[comp.nodes[0]][0] = comp.voltage

        rebuild_count = 0
        seen_warning_keys: set[tuple[str, tuple[str, ...]]] = {
            (w.code, w.component_names) for w in all_warnings
        }

        for k in range(1, n_steps + 1):
            res = self.step_transient(
                step_dt,
                method=method,
                use_be_on_first_step=use_be_on_first_step,
                use_be_on_switch=use_be_on_switch,
            )
            if res.rebuilt_matrix:
                rebuild_count += 1
            times[k] = res.sim_time
            for n, v in res.node_voltages.items():
                node_history[n][k] = v
            for comp in self.circuit.components:
                curr_history[comp.name][k] = comp.current
                volt_history[comp.name][k] = comp.voltage
            for w in res.warnings:
                key = (w.code, w.component_names)
                if key not in seen_warning_keys:
                    seen_warning_keys.add(key)
                    all_warnings.append(w)

        return TransientResult(
            times=times,
            node_voltages=node_history,
            branch_currents=curr_history,
            component_voltages=volt_history,
            warnings=all_warnings,
            matrix_rebuild_count=rebuild_count,
            step_count=n_steps,
        )
