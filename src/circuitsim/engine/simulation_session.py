"""Pure-Python simulation session controller and process-ready worker interface (no Qt imports).

This module provides `SimulationSession` and `SimulationBackendProtocol`, keeping all
simulation control (building the circuit from schematic data, Run/Pause/Stop,
chunked transient stepping, live switch toggling, live parameter editing, meter
readouts, lightbulb brightness, and canvas problem diagnostics) 100% independent
of PySide6 / Qt.

Because all inputs and outputs (`SimulationFrame`, `ComponentTelemetry`,
`ProblemDiagnostic`) are plain, picklable Python dataclasses, the session can run:
    - Directly in unit tests without opening a window,
    - Inside a background `QThread` worker (`circuitsim.app.sim_worker`), or
    - Inside a separate `multiprocessing.Process` if ever needed in the future.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import TYPE_CHECKING, Iterable, Protocol, Sequence

if TYPE_CHECKING:
    from circuitsim.canvas.connectivity import (
        ConnectivityResult,
        PlacedComponentSpec,
        PointPx,
        WireSpec,
    )
from circuitsim.components.base import Component
from circuitsim.components.lightbulb import Lightbulb
from circuitsim.components.meters import Ammeter, Voltmeter
from circuitsim.components.resistor import Resistor
from circuitsim.components.sources import (
    ACVoltageSource,
    DCCurrentSource,
    DCVoltageSource,
)
from circuitsim.components.switch import Switch
from circuitsim.dialogs.value_parser import format_engineering_value
from circuitsim.engine.errors import (
    CircuitError,
    CircuitWarning,
    FloatingNodeError,
    NoGroundError,
    SingularMatrixError,
    VoltageSourceLoopError,
)
from circuitsim.engine.netlist import Circuit
from circuitsim.engine.solver import MNASolver


class SimulationState(str, Enum):
    """Lifecycle state of a `SimulationSession`."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass(frozen=True)
class TransportControlsViewState:
    """Pure-Python specification of Run / Pause / Stop toolbar & status bar visual states."""

    sim_state: SimulationState
    run_enabled: bool
    run_label: str
    run_icon_text: str
    run_tooltip: str
    run_visual_role: str  # "normal", "active_green", or "error_red"
    pause_enabled: bool
    pause_label: str
    pause_icon_text: str
    pause_tooltip: str
    pause_visual_role: str  # "disabled", "normal", or "active_amber"
    stop_enabled: bool
    stop_label: str
    stop_icon_text: str
    stop_tooltip: str
    status_indicator_text: str  # "● Running", "❚❚ Paused", or "■ Stopped"
    status_indicator_role: str  # "running", "paused", "stopped", or "error"


def compute_transport_controls_state(
    state: SimulationState,
    *,
    error_reason: str = "",
) -> TransportControlsViewState:
    """Pure-Python mapping from `SimulationState` to Run/Pause/Stop UI controls."""
    if state == SimulationState.RUNNING:
        return TransportControlsViewState(
            sim_state=state,
            run_enabled=True,
            run_label="▶ &Run",
            run_icon_text="▶ Run",
            run_tooltip="Simulation is running (Shortcut: F5)",
            run_visual_role="active_green",
            pause_enabled=True,
            pause_label="⏸ &Pause",
            pause_icon_text="⏸ Pause",
            pause_tooltip="Pause circuit simulation (Shortcut: F6)",
            pause_visual_role="normal",
            stop_enabled=True,
            stop_label="⏹ &Stop",
            stop_icon_text="⏹ Stop",
            stop_tooltip="Stop simulation and reset meters/states (Shortcut: F7)",
            status_indicator_text="● Running",
            status_indicator_role="running",
        )
    if state == SimulationState.PAUSED:
        return TransportControlsViewState(
            sim_state=state,
            run_enabled=True,
            run_label="▶ &Resume",
            run_icon_text="▶ Resume",
            run_tooltip="Resume paused circuit simulation (Shortcut: F5)",
            run_visual_role="normal",
            pause_enabled=True,
            pause_label="⏸ &Pause",
            pause_icon_text="⏸ Pause",
            pause_tooltip="Simulation is paused (Shortcut: F6)",
            pause_visual_role="active_amber",
            stop_enabled=True,
            stop_label="⏹ &Stop",
            stop_icon_text="⏹ Stop",
            stop_tooltip="Stop simulation and reset meters/states (Shortcut: F7)",
            status_indicator_text="❚❚ Paused",
            status_indicator_role="paused",
        )
    if state == SimulationState.ERROR:
        tip = (
            f"Cannot run ({error_reason}) — click to retry (Shortcut: F5)"
            if error_reason
            else "Cannot run due to circuit error — click to retry (Shortcut: F5)"
        )
        return TransportControlsViewState(
            sim_state=state,
            run_enabled=True,
            run_label="▶ &Run",
            run_icon_text="▶ Run",
            run_tooltip=tip,
            run_visual_role="error_red",
            pause_enabled=False,
            pause_label="⏸ &Pause",
            pause_icon_text="⏸ Pause",
            pause_tooltip="Pause circuit simulation (Shortcut: F6)",
            pause_visual_role="disabled",
            stop_enabled=False,
            stop_label="⏹ &Stop",
            stop_icon_text="⏹ Stop",
            stop_tooltip="Stop simulation and reset meters/states (Shortcut: F7)",
            status_indicator_text="■ Stopped",
            status_indicator_role="error",
        )
    # Default: SimulationState.STOPPED
    return TransportControlsViewState(
        sim_state=SimulationState.STOPPED,
        run_enabled=True,
        run_label="▶ &Run",
        run_icon_text="▶ Run",
        run_tooltip="Start circuit simulation (Shortcut: F5)",
        run_visual_role="normal",
        pause_enabled=False,
        pause_label="⏸ &Pause",
        pause_icon_text="⏸ Pause",
        pause_tooltip="Pause circuit simulation (Shortcut: F6)",
        pause_visual_role="disabled",
        stop_enabled=False,
        stop_label="⏹ &Stop",
        stop_icon_text="⏹ Stop",
        stop_tooltip="Stop simulation and reset meters/states (Shortcut: F7)",
        status_indicator_text="■ Stopped",
        status_indicator_role="stopped",
    )


class SimulationSpeed(str, Enum):
    """Target simulation speed relative to wall-clock time."""

    REAL_TIME = "1x"
    SLOW_MOTION = "0.1x"
    FAST = "10x"

    @property
    def multiplier(self) -> float:
        if self == SimulationSpeed.SLOW_MOTION:
            return 0.1
        if self == SimulationSpeed.FAST:
            return 10.0
        return 1.0


@dataclass(frozen=True)
class ComponentTelemetry:
    """Immutable snapshot of a single component's live operating state for the UI."""

    name: str
    component_type: str
    voltage: float
    current: float
    power: float
    display_value: str
    brightness: float = 0.0
    is_over_bright: bool = False
    burned_out: bool = False
    switch_closed: bool = False
    switch_arcing: bool = False


@dataclass(frozen=True)
class ProblemDiagnostic:
    """Structured error or warning for canvas problem highlighting and status bar."""

    code: str
    severity: str  # "error" or "warning"
    message: str
    component_names: tuple[str, ...] = ()
    wire_ids: tuple[str, ...] = ()
    nodes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimulationFrame:
    """Immutable, picklable snapshot emitted after each solver chunk or state transition."""

    state: SimulationState
    sim_time: float
    dt: float
    speed_ratio: float
    node_voltages: dict[str, float] = field(default_factory=dict)
    components: dict[str, ComponentTelemetry] = field(default_factory=dict)
    diagnostics: tuple[ProblemDiagnostic, ...] = ()


def format_component_canvas_text(comp: Component) -> str:
    """Return the value/readout string shown beneath a component on the schematic."""
    if isinstance(comp, Resistor):
        return format_engineering_value(comp.resistance, "Ω")
    if isinstance(comp, DCVoltageSource):
        return format_engineering_value(comp.dc_voltage, "V")
    if isinstance(comp, ACVoltageSource):
        v_str = format_engineering_value(comp.amplitude, "V")
        f_str = format_engineering_value(comp.frequency, "Hz")
        return f"{v_str} {f_str}"
    if isinstance(comp, DCCurrentSource):
        return format_engineering_value(comp.dc_current, "A")
    if isinstance(comp, Switch):
        if comp.arcing and not comp.closed:
            return "ARC!"
        return "ON" if comp.closed else "OFF"
    if isinstance(comp, Lightbulb):
        if comp.burned_out:
            return "BURNED OUT"
        return f"{comp.rated_power:g}W / {comp.rated_voltage:g}V"
    if isinstance(comp, (Voltmeter, Ammeter)):
        return comp.format_reading()
    # Capacitor / Inductor fallback via attribute check to avoid circular import
    if hasattr(comp, "capacitance"):
        return format_engineering_value(float(getattr(comp, "capacitance")), "F")
    if hasattr(comp, "inductance"):
        return format_engineering_value(float(getattr(comp, "inductance")), "H")
    return ""


class SimulationBackendProtocol(Protocol):
    """Transport-agnostic interface for controlling the simulation session."""

    def start(self) -> SimulationFrame: ...

    def pause(self) -> SimulationFrame: ...

    def stop(self) -> SimulationFrame: ...

    def step_chunk(
        self, steps: int = 10, dt: float | None = None
    ) -> SimulationFrame: ...

    def toggle_switch(self, switch_name: str) -> SimulationFrame: ...

    def update_component_parameter(
        self, comp_name: str, param_key: str, raw_value: float | str
    ) -> SimulationFrame: ...


class SimulationSession:
    """Pure-Python controller managing a live `Circuit`, `MNASolver`, and telemetry."""

    def __init__(
        self,
        circuit: Circuit | None = None,
        *,
        connectivity: ConnectivityResult | None = None,
        default_dt: float | None = None,
    ) -> None:
        self._connectivity: ConnectivityResult | None = connectivity
        self.circuit: Circuit = (
            circuit
            if circuit is not None
            else (connectivity.circuit if connectivity is not None else Circuit())
        )
        self.solver: MNASolver = MNASolver(self.circuit)
        self.state: SimulationState = SimulationState.STOPPED
        self.speed: SimulationSpeed = SimulationSpeed.REAL_TIME
        self._dt: float = (
            default_dt
            if (default_dt is not None and default_dt > 0.0)
            else self._compute_step_dt()
        )
        self._last_speed_ratio: float = 0.0
        self._active_diagnostics: list[ProblemDiagnostic] = []
        self._latched_warnings: dict[tuple[str, tuple[str, ...]], CircuitWarning] = {}

    @classmethod
    def from_schematic(
        cls,
        placed_components: Sequence[PlacedComponentSpec],
        wires: Sequence[WireSpec],
        explicit_junctions: Iterable[tuple[float, float] | PointPx] = (),
    ) -> SimulationSession:
        """Create a `SimulationSession` directly from schematic placement and wire specs."""
        from circuitsim.canvas.connectivity import extract_connectivity

        conn = extract_connectivity(
            placed_components, wires, explicit_junctions
        )
        return cls(circuit=conn.circuit, connectivity=conn)

    def load_schematic(
        self,
        placed_components: Sequence[PlacedComponentSpec],
        wires: Sequence[WireSpec],
        explicit_junctions: Iterable[tuple[float, float] | PointPx] = (),
    ) -> SimulationFrame:
        """Rebuild the session's circuit from updated schematic data."""
        from circuitsim.canvas.connectivity import extract_connectivity

        was_running = self.state == SimulationState.RUNNING
        self._connectivity = extract_connectivity(
            placed_components, wires, explicit_junctions
        )
        self.circuit = self._connectivity.circuit
        self.solver = MNASolver(self.circuit)
        self._dt = self._compute_step_dt()
        self._latched_warnings.clear()
        self._active_diagnostics.clear()

        if was_running:
            return self.start()
        self.state = SimulationState.STOPPED
        return self.build_frame()

    @property
    def dt(self) -> float:
        return self._dt

    def _compute_step_dt(self) -> float:
        if not self.circuit.components:
            return 1e-4
        try:
            chosen = self.solver.choose_default_dt(0.02)
            # Clamp default real-time step between 1 us and 200 us for smooth interactive stepping
            return min(max(chosen, 1e-6), 2e-4)
        except Exception:
            return 5e-5

    def _components_and_wires_for_node(
        self, node: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        comp_names: list[str] = []
        for comp in self.circuit.components:
            if node in comp.nodes:
                comp_names.append(comp.name)
        wire_ids: list[str] = []
        if self._connectivity is not None:
            for wid, wnode in self._connectivity.wire_to_node.items():
                if wnode == node:
                    wire_ids.append(wid)
        return (tuple(comp_names), tuple(wire_ids))

    def _convert_error_to_diagnostic(self, exc: CircuitError) -> ProblemDiagnostic:
        if isinstance(exc, NoGroundError):
            all_comps = tuple(c.name for c in self.circuit.components)
            all_wires = (
                tuple(self._connectivity.wire_to_node.keys())
                if self._connectivity is not None
                else ()
            )
            return ProblemDiagnostic(
                code="no_ground",
                severity="error",
                message=str(exc) or "No ground connected",
                component_names=all_comps,
                wire_ids=all_wires,
            )
        if isinstance(exc, FloatingNodeError):
            c_names, w_ids = self._components_and_wires_for_node(exc.node)
            return ProblemDiagnostic(
                code="floating_node",
                severity="error",
                message=str(exc),
                component_names=c_names,
                wire_ids=w_ids,
                nodes=(exc.node,),
            )
        if isinstance(exc, VoltageSourceLoopError):
            return ProblemDiagnostic(
                code="voltage_source_loop",
                severity="error",
                message=str(exc),
                component_names=tuple(exc.sources),
            )
        if isinstance(exc, SingularMatrixError):
            return ProblemDiagnostic(
                code="singular_matrix",
                severity="error",
                message=str(exc),
                component_names=tuple(c.name for c in self.circuit.components),
            )
        return ProblemDiagnostic(
            code="circuit_error",
            severity="error",
            message=str(exc),
        )

    def _collect_warnings_diagnostics(
        self, step_warnings: Sequence[CircuitWarning]
    ) -> list[ProblemDiagnostic]:
        for w in step_warnings:
            key = (w.code, w.component_names)
            self._latched_warnings[key] = w

        diags: list[ProblemDiagnostic] = []
        for w in self._latched_warnings.values():
            diags.append(
                ProblemDiagnostic(
                    code=w.code,
                    severity="warning",
                    message=w.message,
                    component_names=w.component_names,
                )
            )

        # Also check lightbulb over-brightness (> 100% rated power)
        for comp in self.circuit.components:
            if isinstance(comp, Lightbulb) and comp.is_over_bright:
                diags.append(
                    ProblemDiagnostic(
                        code="over_bright",
                        severity="warning",
                        message=(
                            f"Lightbulb {comp.name} overloaded "
                            f"({comp.brightness_percent:.0f}% of rated {comp.rated_power:g} W)"
                        ),
                        component_names=(comp.name,),
                    )
                )
        return diags

    def start(self) -> SimulationFrame:
        """Validate topology, solve initial operating point, and enter `RUNNING` state."""
        if not self.circuit.components:
            self.state = SimulationState.STOPPED
            self._active_diagnostics = []
            return self.build_frame()

        self._dt = self._compute_step_dt()
        self._latched_warnings.clear()

        try:
            if self.solver.sim_time == 0.0:
                res = self.solver.solve_dc()
                # Also advance one tiny step if reactive/AC components exist so meters have samples
                res_step = self.solver.step_transient(self._dt)
                self._active_diagnostics = self._collect_warnings_diagnostics(
                    list(res.warnings) + list(res_step.warnings)
                )
                node_v = res_step.node_voltages
            else:
                res_step = self.solver.step_transient(self._dt)
                self._active_diagnostics = self._collect_warnings_diagnostics(
                    res_step.warnings
                )
                node_v = res_step.node_voltages
            self.state = SimulationState.RUNNING
            self._last_speed_ratio = self.speed.multiplier
            return self.build_frame(node_voltages=node_v)
        except CircuitError as exc:
            self.state = SimulationState.ERROR
            self._active_diagnostics = [self._convert_error_to_diagnostic(exc)]
            # Ensure meters show "-- V" / "-- A" on error
            self.circuit.reset_state()
            return self.build_frame()

    def pause(self) -> SimulationFrame:
        """Pause the running simulation without resetting component or meter states."""
        if self.state == SimulationState.RUNNING:
            self.state = SimulationState.PAUSED
        return self.build_frame()

    def stop(self) -> SimulationFrame:
        """Stop the simulation and reset all meters and reactive states to t = 0."""
        self.state = SimulationState.STOPPED
        self.solver.reset_transient()
        self.circuit.reset_state()
        self._last_speed_ratio = 0.0
        self._active_diagnostics.clear()
        self._latched_warnings.clear()
        return self.build_frame()

    def step_chunk(
        self,
        steps: int = 10,
        dt: float | None = None,
    ) -> SimulationFrame:
        """Advance the transient solver by `steps` time steps and return a `SimulationFrame`."""
        if self.state != SimulationState.RUNNING:
            frame = self.start()
            if self.state != SimulationState.RUNNING:
                return frame

        step_dt = dt if (dt is not None and dt > 0.0) else self._dt
        n_steps = max(1, int(steps))
        t_wall_start = time.perf_counter()

        last_node_voltages: dict[str, float] = {}
        collected_warnings: list[CircuitWarning] = []

        try:
            for _ in range(n_steps):
                res = self.solver.step_transient(step_dt)
                last_node_voltages = res.node_voltages
                if res.warnings:
                    collected_warnings.extend(res.warnings)
        except CircuitError as exc:
            self.state = SimulationState.ERROR
            self._active_diagnostics = [self._convert_error_to_diagnostic(exc)]
            return self.build_frame()

        t_wall_elapsed = max(1e-9, time.perf_counter() - t_wall_start)
        sim_advanced = n_steps * step_dt
        self._last_speed_ratio = sim_advanced / t_wall_elapsed
        self._active_diagnostics = self._collect_warnings_diagnostics(
            collected_warnings
        )
        return self.build_frame(node_voltages=last_node_voltages)

    def toggle_switch(self, switch_name: str) -> SimulationFrame:
        """Toggle a `Switch` by name and immediately update the simulation if active."""
        comp = self.circuit.get_component(switch_name)
        if not isinstance(comp, Switch):
            raise TypeError(f"Component {switch_name!r} is not a Switch.")
        comp.toggle()
        self.circuit.mark_modified()
        self.solver._be_steps_remaining = max(self.solver._be_steps_remaining, 3)

        if self.state == SimulationState.RUNNING:
            return self.step_chunk(steps=3)
        return self.build_frame()

    def update_component_parameter(
        self,
        comp_name: str,
        param_key: str,
        raw_value: float | str,
    ) -> SimulationFrame:
        """Validate and apply a parameter change to `comp_name` live."""
        comp = self.circuit.get_component(comp_name)
        comp.set_parameter_value(param_key, raw_value)
        self.circuit.mark_modified()
        self._dt = self._compute_step_dt()

        if self.state == SimulationState.RUNNING:
            return self.step_chunk(steps=3)
        return self.build_frame()

    def get_meter_reading_str(self, meter_name: str) -> str:
        """Return formatted reading string (e.g. '12 V', '12 mA', or '-- V') for `meter_name`."""
        comp = self.circuit.get_component(meter_name)
        if not isinstance(comp, (Voltmeter, Ammeter)):
            raise TypeError(f"Component {meter_name!r} is not a Voltmeter or Ammeter.")
        return comp.format_reading()

    def get_meter_reading_value(self, meter_name: str) -> float | None:
        """Return numerical meter reading, or `None` if no reading has been produced yet."""
        comp = self.circuit.get_component(meter_name)
        if not isinstance(comp, (Voltmeter, Ammeter)):
            raise TypeError(f"Component {meter_name!r} is not a Voltmeter or Ammeter.")
        if not comp.has_reading:
            return None
        return comp.reading

    def build_frame(
        self, node_voltages: dict[str, float] | None = None
    ) -> SimulationFrame:
        """Construct an immutable `SimulationFrame` from current component states."""
        comp_map: dict[str, ComponentTelemetry] = {}
        for comp in self.circuit.components:
            brightness = comp.brightness if isinstance(comp, Lightbulb) else 0.0
            over_bright = (
                comp.is_over_bright if isinstance(comp, Lightbulb) else False
            )
            burned_out = (
                comp.burned_out if isinstance(comp, Lightbulb) else False
            )
            sw_closed = comp.closed if isinstance(comp, Switch) else False
            sw_arcing = comp.arcing if isinstance(comp, Switch) else False

            comp_map[comp.name] = ComponentTelemetry(
                name=comp.name,
                component_type=comp.component_type,
                voltage=comp.voltage,
                current=comp.current,
                power=comp.power,
                display_value=format_component_canvas_text(comp),
                brightness=brightness,
                is_over_bright=over_bright,
                burned_out=burned_out,
                switch_closed=sw_closed,
                switch_arcing=sw_arcing,
            )

        return SimulationFrame(
            state=self.state,
            sim_time=self.solver.sim_time,
            dt=self._dt,
            speed_ratio=self._last_speed_ratio,
            node_voltages=dict(node_voltages) if node_voltages else {},
            components=comp_map,
            diagnostics=tuple(self._active_diagnostics),
        )
