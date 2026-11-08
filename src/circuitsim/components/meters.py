"""Voltmeter and Ammeter instrument components (Sections 5.5 and 5.6)."""

from __future__ import annotations

from collections import deque
from enum import Enum
import math

from circuitsim.components.base import Component
from circuitsim.dialogs.value_parser import format_engineering_value, parse_engineering_value


class MeterMode(str, Enum):
    """Display measurement mode for Voltmeter and Ammeter."""

    INSTANTANEOUS = "instantaneous"
    DC = "dc"
    RMS = "rms"
    PEAK = "peak"


class _BaseMeter(Component):
    """Shared sliding-window measurement logic for Voltmeter and Ammeter."""

    def __init__(
        self,
        name: str,
        node_pos: str,
        node_neg: str,
        r_internal: float | str,
        *,
        mode: MeterMode | str = MeterMode.INSTANTANEOUS,
        window_duration: float = 0.1,
        label: str | None = None,
        show_value: bool = True,
        color: str = "#FFFFFF",
    ) -> None:
        super().__init__(
            name=name,
            nodes=(node_pos, node_neg),
            label=label,
            show_value=show_value,
            color=color,
        )
        parsed_r = parse_engineering_value(r_internal)
        if parsed_r <= 0.0:
            raise ValueError(f"{self.__class__.__name__} {name!r}: r_internal must be > 0 Ω.")

        self.r_internal: float = parsed_r
        self.mode: MeterMode = MeterMode(mode) if not isinstance(mode, MeterMode) else mode
        self.window_duration: float = max(1e-6, float(window_duration))
        # Buffer of (sim_time, sample_value, dt) tuples for sliding window stats.
        self._samples: deque[tuple[float, float, float]] = deque()
        self.has_reading: bool = False

    @property
    def conductance(self) -> float:
        """Conductance G = 1 / R_internal in Siemens."""
        return 1.0 / self.r_internal

    def record_sample(self, sim_time: float, value: float, dt: float = 0.0) -> None:
        """Append a time-domain reading to the meter's sliding window.

        Each sample at `sim_time` with step size `dt` covers the interval
        `(sim_time - dt, sim_time]`. Evicting samples with timestamp
        `<= sim_time - window_duration` ensures that a window of duration
        `K * T` contains exactly `K * T / dt` intervals (and does not double-count
        both endpoints of a periodic waveform).
        """
        self.has_reading = True
        self._samples.append((sim_time, value, max(dt, 0.0)))
        cutoff = sim_time - self.window_duration + 1e-12
        while len(self._samples) > 1 and self._samples[0][0] <= cutoff:
            self._samples.popleft()

    def _instantaneous_value(self) -> float:
        raise NotImplementedError

    @property
    def reading(self) -> float:
        """Return the active meter reading according to `self.mode`."""
        inst = self._instantaneous_value()
        if self.mode == MeterMode.INSTANTANEOUS or not self._samples:
            return inst

        values = [s[1] for s in self._samples]
        weights = [s[2] for s in self._samples]
        total_weight = sum(weights)

        if self.mode == MeterMode.DC:
            if total_weight > 0.0:
                return sum(v * w for v, w in zip(values, weights)) / total_weight
            return sum(values) / len(values)

        if self.mode == MeterMode.RMS:
            if total_weight > 0.0:
                mean_sq = sum((v * v) * w for v, w in zip(values, weights)) / total_weight
            else:
                mean_sq = sum(v * v for v in values) / len(values)
            return math.sqrt(max(0.0, mean_sq))

        if self.mode == MeterMode.PEAK:
            # Return the signed peak with largest magnitude, or max positive peak.
            return max(values, key=abs)

        return inst

    def reset_state(self) -> None:
        """Clear recorded waveform history and electrical readings."""
        super().reset_state()
        self._samples.clear()
        self.has_reading = False


class Voltmeter(_BaseMeter):
    """Two-probe voltmeter with high internal resistance (default 10 MΩ, Section 5.5).

    Participates genuinely in the MNA simulation as a resistor between `node_pos`
    (red probe) and `node_neg` (black probe).
    """

    def __init__(
        self,
        name: str,
        node_pos: str,
        node_neg: str,
        *,
        r_internal: float | str = 10e6,
        mode: MeterMode | str = MeterMode.INSTANTANEOUS,
        window_duration: float = 0.1,
        label: str | None = None,
        show_value: bool = True,
        color: str = "#EF5350",
    ) -> None:
        super().__init__(
            name=name,
            node_pos=node_pos,
            node_neg=node_neg,
            r_internal=r_internal,
            mode=mode,
            window_duration=window_duration,
            label=label,
            show_value=show_value,
            color=color,
        )

    @property
    def component_type(self) -> str:
        return "voltmeter"

    def _instantaneous_value(self) -> float:
        return self.voltage

    def format_reading(self, sig_figs: int = 4) -> str:
        """Return polarity-aware, auto-ranged voltage string (or '-- V' before simulation)."""
        if not self.has_reading:
            return "-- V"
        return format_engineering_value(self.reading, unit="V", sig_figs=sig_figs)


class Ammeter(_BaseMeter):
    """Series ammeter with very low internal resistance (default 1 mΩ, Section 5.6).

    Participates genuinely in the MNA simulation as a small resistor between
    `node_pos` (current entry terminal) and `node_neg` (current exit terminal).
    """

    def __init__(
        self,
        name: str,
        node_pos: str,
        node_neg: str,
        *,
        r_internal: float | str = 1e-3,
        mode: MeterMode | str = MeterMode.INSTANTANEOUS,
        window_duration: float = 0.1,
        label: str | None = None,
        show_value: bool = True,
        color: str = "#42A5F5",
    ) -> None:
        super().__init__(
            name=name,
            node_pos=node_pos,
            node_neg=node_neg,
            r_internal=r_internal,
            mode=mode,
            window_duration=window_duration,
            label=label,
            show_value=show_value,
            color=color,
        )

    @property
    def component_type(self) -> str:
        return "ammeter"

    def _instantaneous_value(self) -> float:
        return self.current

    def format_reading(self, sig_figs: int = 4) -> str:
        """Return polarity-aware, auto-ranged current string (or '-- A' before simulation)."""
        if not self.has_reading:
            return "-- A"
        return format_engineering_value(self.reading, unit="A", sig_figs=sig_figs)
