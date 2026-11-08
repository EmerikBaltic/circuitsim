"""Background QThread simulation worker wrapping the pure-Python `SimulationSession`."""

from __future__ import annotations

from typing import Iterable, Sequence

from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QThread,
    QTimer,
    Qt,
    Signal,
    Slot,
)

from circuitsim.canvas.connectivity import (
    PlacedComponentSpec,
    PointPx,
    WireSpec,
)
from circuitsim.engine.simulation_session import (
    SimulationFrame,
    SimulationSession,
    SimulationSpeed,
    SimulationState,
)


class _SessionThreadWorker(QObject):
    """Worker object living inside the background `QThread`."""

    frame_emitted = Signal(object)  # Emits immutable SimulationFrame

    def __init__(self) -> None:
        super().__init__()
        self.session: SimulationSession = SimulationSession()
        self._tick_timer: QTimer | None = None
        self.tick_interval_ms: int = 33  # ~30 FPS UI update rate

    def _ensure_timer(self) -> QTimer:
        if self._tick_timer is None:
            self._tick_timer = QTimer(self)
            self._tick_timer.setInterval(self.tick_interval_ms)
            self._tick_timer.timeout.connect(self._on_tick)
        return self._tick_timer

    @Slot(object, object, object)
    def handle_load_schematic(
        self,
        placed_specs: object,
        wire_specs: object,
        junctions: object,
    ) -> None:
        timer = self._ensure_timer()
        frame = self.session.load_schematic(
            placed_specs,  # type: ignore[arg-type]
            wire_specs,  # type: ignore[arg-type]
            junctions,  # type: ignore[arg-type]
        )
        if frame.state == SimulationState.RUNNING:
            timer.start()
        else:
            timer.stop()
        self.frame_emitted.emit(frame)

    @Slot()
    def handle_start(self) -> None:
        timer = self._ensure_timer()
        frame = self.session.start()
        if frame.state == SimulationState.RUNNING:
            timer.start()
        else:
            timer.stop()
        self.frame_emitted.emit(frame)

    @Slot()
    def handle_pause(self) -> None:
        timer = self._ensure_timer()
        timer.stop()
        frame = self.session.pause()
        self.frame_emitted.emit(frame)

    @Slot()
    def handle_stop(self) -> None:
        timer = self._ensure_timer()
        timer.stop()
        frame = self.session.stop()
        self.frame_emitted.emit(frame)

    @Slot(str)
    def handle_set_speed(self, speed_value: str) -> None:
        self.session.speed = SimulationSpeed(speed_value)

    @Slot(str)
    def handle_toggle_switch(self, switch_name: str) -> None:
        try:
            frame = self.session.toggle_switch(switch_name)
            self.frame_emitted.emit(frame)
        except Exception:
            pass

    @Slot(str, str, object)
    def handle_update_parameter(
        self, comp_name: str, param_key: str, raw_value: object
    ) -> None:
        try:
            frame = self.session.update_component_parameter(
                comp_name, param_key, raw_value  # type: ignore[arg-type]
            )
            self.frame_emitted.emit(frame)
        except Exception:
            pass

    @Slot()
    def _on_tick(self) -> None:
        if self.session.state != SimulationState.RUNNING:
            if self._tick_timer is not None:
                self._tick_timer.stop()
            return

        wall_dt = self.tick_interval_ms / 1000.0
        target_sim_advance = wall_dt * self.session.speed.multiplier
        dt = max(1e-9, self.session.dt)
        steps = max(1, min(350, int(round(target_sim_advance / dt))))
        frame = self.session.step_chunk(steps=steps, dt=dt)
        if frame.state != SimulationState.RUNNING and self._tick_timer is not None:
            self._tick_timer.stop()
        self.frame_emitted.emit(frame)


class SimulationWorkerController(QObject):
    """Main-thread facade managing the background `QThread` simulation worker.

    All communication with `_SessionThreadWorker` occurs via queued Qt signals
    carrying immutable/picklable dataclasses so the GUI event loop never blocks.
    """

    frame_ready = Signal(object)  # Emits SimulationFrame on the main thread

    # Internal queued signals to the worker thread
    _sig_load = Signal(object, object, object)
    _sig_start = Signal()
    _sig_pause = Signal()
    _sig_stop = Signal()
    _sig_speed = Signal(str)
    _sig_toggle_switch = Signal(str)
    _sig_update_param = Signal(str, str, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _SessionThreadWorker()
        self._worker.moveToThread(self._thread)

        self._sig_load.connect(
            self._worker.handle_load_schematic, Qt.ConnectionType.QueuedConnection
        )
        self._sig_start.connect(
            self._worker.handle_start, Qt.ConnectionType.QueuedConnection
        )
        self._sig_pause.connect(
            self._worker.handle_pause, Qt.ConnectionType.QueuedConnection
        )
        self._sig_stop.connect(
            self._worker.handle_stop, Qt.ConnectionType.QueuedConnection
        )
        self._sig_speed.connect(
            self._worker.handle_set_speed, Qt.ConnectionType.QueuedConnection
        )
        self._sig_toggle_switch.connect(
            self._worker.handle_toggle_switch, Qt.ConnectionType.QueuedConnection
        )
        self._sig_update_param.connect(
            self._worker.handle_update_parameter, Qt.ConnectionType.QueuedConnection
        )
        self._worker.frame_emitted.connect(
            self.frame_ready, Qt.ConnectionType.QueuedConnection
        )
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def _ensure_thread_running(self) -> None:
        if not self._thread.isRunning():
            self._thread.start()

    def load_schematic(
        self,
        placed_components: Sequence[PlacedComponentSpec],
        wires: Sequence[WireSpec],
        explicit_junctions: Iterable[PointPx] = (),
    ) -> None:
        """Send an updated schematic snapshot to the worker thread."""
        self._ensure_thread_running()
        self._sig_load.emit(
            tuple(placed_components),
            tuple(wires),
            tuple(explicit_junctions),
        )

    def start(self) -> None:
        """Start or resume simulation on the worker thread."""
        self._ensure_thread_running()
        self._sig_start.emit()

    def pause(self) -> None:
        """Pause simulation on the worker thread."""
        if self._thread.isRunning():
            self._sig_pause.emit()

    def stop(self) -> None:
        """Stop simulation and reset states on the worker thread."""
        if self._thread.isRunning():
            self._sig_stop.emit()

    def set_speed(self, speed: SimulationSpeed) -> None:
        """Change target simulation speed on the worker thread."""
        self._ensure_thread_running()
        self._sig_speed.emit(speed.value)

    def toggle_switch(self, switch_name: str) -> None:
        """Toggle a switch live on the worker thread."""
        self._ensure_thread_running()
        self._sig_toggle_switch.emit(switch_name)

    def update_component_parameter(
        self, comp_name: str, param_key: str, value: float | str
    ) -> None:
        """Update a component parameter live on the worker thread."""
        self._ensure_thread_running()
        self._sig_update_param.emit(comp_name, param_key, value)

    def shutdown(self) -> None:
        """Cleanly stop the worker timer and join the background `QThread`."""
        if self._thread.isRunning():
            self._sig_stop.emit()
            self._thread.quit()
            self._thread.wait(2000)
