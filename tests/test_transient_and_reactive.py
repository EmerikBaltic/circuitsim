"""Unit tests for Milestone 1 Step B: reactive components, AC sources, and transient MNA."""

from __future__ import annotations

import math
import numpy as np
import pytest

from circuitsim.components import (
    ACVoltageSource,
    Ammeter,
    Capacitor,
    DCVoltageSource,
    Ground,
    Inductor,
    MeterMode,
    Resistor,
    Switch,
    Voltmeter,
    WaveformType,
)
from circuitsim.engine import Circuit, IntegrationMethod, MNASolver


def test_rc_charging_analytical() -> None:
    """Verify RC step charging against V(t) = Vs * (1 - exp(-t / (R * C)))."""
    vs = 10.0
    r = 1000.0  # 1 kOhm
    c = 1e-6  # 1 uF -> tau = 1 ms
    tau = r * c

    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "in", "0", voltage=vs))
    circuit.add(Resistor("R1", "in", "cap", resistance=r))
    circuit.add(Capacitor("C1", "cap", "0", capacitance=c, initial_voltage=0.0))
    circuit.add(Ground("GND", "0"))

    solver = MNASolver(circuit)
    dt = tau / 200.0  # 5 us
    res = solver.solve_transient(duration=5.0 * tau, dt=dt)

    # Check only 2 matrix factorizations occurred across 1000 steps:
    # Step 1 (Backward Euler) + Step 2 (Trapezoidal, then reused for steps 3..1000)
    assert res.matrix_rebuild_count == 2

    for mult in (0.5, 1.0, 2.0, 3.0, 5.0):
        t_target = mult * tau
        idx = int(round(t_target / dt))
        t_actual = float(res.times[idx])
        v_sim = float(res.node_voltages["cap"][idx])
        v_exact = vs * (1.0 - math.exp(-t_actual / tau))
        assert math.isclose(v_sim, v_exact, rel_tol=1e-3, abs_tol=1e-4)


def test_rl_current_rise_and_thevenin_tau_analytical() -> None:
    """Verify RL current rise I(t) = (V_th / R_total) * (1 - exp(-t / tau)) with DCR and Thévenin R."""
    # Source V1 = 20 V driving a 200 Ohm / 200 Ohm voltage divider:
    # V_th = 10 V, R_thevenin = 200 || 200 = 100 Ohm.
    # Inductor L = 50 mH with DCR = 25 Ohm -> R_total = 125 Ohm, tau = 50mH / 125 = 0.4 ms.
    v_src = 20.0
    r1 = 200.0
    r2 = 200.0
    ind_l = 50e-3
    dcr = 25.0

    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "src", "0", voltage=v_src))
    circuit.add(Resistor("R1", "src", "th_node", resistance=r1))
    circuit.add(Resistor("R2", "th_node", "0", resistance=r2))
    inductor = Inductor("L1", "th_node", "0", inductance=ind_l, dcr=dcr, initial_current=0.0)
    circuit.add(inductor)
    circuit.add(Ground("GND", "0"))

    # 1. Verify exact Thévenin resistance and time constant tau = L / (R_thevenin + DCR):
    r_th = circuit.thevenin_resistance("th_node", "0", exclude_component="L1")
    assert math.isclose(r_th, 100.0, rel_tol=1e-12)

    expected_tau = ind_l / (100.0 + dcr)  # 0.05 / 125 = 0.0004 s (0.4 ms)
    assert math.isclose(inductor.time_constant(circuit), expected_tau, rel_tol=1e-12)

    # 2. Verify transient current rise against analytical formula:
    v_th = v_src * (r2 / (r1 + r2))  # 10.0 V
    i_final = v_th / (r_th + dcr)  # 10.0 / 125.0 = 0.08 A (80 mA)

    solver = MNASolver(circuit)
    dt = expected_tau / 200.0
    res = solver.solve_transient(duration=5.0 * expected_tau, dt=dt)

    for mult in (0.5, 1.0, 2.0, 3.0, 5.0):
        idx = int(round((mult * expected_tau) / dt))
        t_actual = float(res.times[idx])
        i_sim = float(res.branch_currents["L1"][idx])
        i_exact = i_final * (1.0 - math.exp(-t_actual / expected_tau))
        assert math.isclose(i_sim, i_exact, rel_tol=1e-3, abs_tol=1e-5)


def test_inductive_reactance_against_ac_rms_meters() -> None:
    """Section 11: verify X_L = 2 * pi * f * L against AC RMS voltmeter and ammeter readings."""
    freq = 1000.0  # 1 kHz
    v_peak = 10.0  # 10 V peak -> 7.0710678 V RMS
    ind_l = 10e-3  # 10 mH -> X_L = 2 * pi * 1000 * 0.01 = 62.831853 Ohm
    dcr = 10.0  # 10 Ohm winding resistance

    # Check Inductor helper methods first:
    expected_xl = 2.0 * math.pi * freq * ind_l
    ind = Inductor("L1", "n_load", "0", inductance=ind_l, dcr=dcr)
    assert math.isclose(ind.reactance(freq), expected_xl, rel_tol=1e-12)
    calc_l = Inductor.calculate_inductance_from_reactance(expected_xl, freq)
    assert math.isclose(calc_l, ind_l, rel_tol=1e-12)

    # Build AC test circuit with series Ammeter (RMS) and parallel Voltmeter (RMS)
    period = 1.0 / freq  # 1 ms
    # Set meter window to an exact integer number of periods (4 periods = 4 ms)
    window_dur = 4.0 * period

    circuit = Circuit()
    circuit.add(
        ACVoltageSource(
            "Vac",
            "n_src",
            "0",
            waveform=WaveformType.SINE,
            amplitude=v_peak,
            frequency=freq,
        )
    )
    ammeter = Ammeter(
        "A1", "n_src", "n_load", r_internal=1e-3, mode=MeterMode.RMS, window_duration=window_dur
    )
    voltmeter = Voltmeter(
        "VM1", "n_load", "0", r_internal=10e6, mode=MeterMode.RMS, window_duration=window_dur
    )
    circuit.add(ammeter)
    circuit.add(ind)
    circuit.add(voltmeter)
    circuit.add(Ground("GND", "0"))

    # Simulate for 25 periods so the RL DC transient (tau = 1 ms) completely dies out
    solver = MNASolver(circuit)
    dt = period / 200.0
    solver.solve_transient(duration=25.0 * period, dt=dt)

    # Analytical AC steady-state impedance Z = sqrt(R_total^2 + X_L^2):
    expected_v_rms = v_peak / math.sqrt(2.0)
    z_inductor = math.hypot(dcr, expected_xl)
    expected_i_rms = expected_v_rms / math.hypot(dcr + ammeter.r_internal, expected_xl)

    assert math.isclose(voltmeter.reading, expected_v_rms, rel_tol=2e-3)
    assert math.isclose(ammeter.reading, expected_i_rms, rel_tol=2e-3)

    # Measured impedance magnitude V_rms / I_rms from the meters matches sqrt(dcr^2 + X_L^2):
    measured_z = voltmeter.reading / ammeter.reading
    assert math.isclose(measured_z, z_inductor, rel_tol=2e-3)
    # Extract X_L from measured Z and dcr:
    measured_xl = math.sqrt(max(0.0, measured_z**2 - dcr**2))
    assert math.isclose(measured_xl, expected_xl, rel_tol=2e-3)


def test_series_rlc_resonance_analytical() -> None:
    """Section 11: verify series RLC resonance peaks at f0 = 1 / (2 * pi * sqrt(L * C))."""
    ind_l = 1e-3  # 1 mH
    cap_c = 1e-6  # 1 uF
    res_r = 10.0  # 10 Ohm
    v_peak = 5.0
    f0 = 1.0 / (2.0 * math.pi * math.sqrt(ind_l * cap_c))  # ~5032.92 Hz

    def measure_steady_state_current_peak(freq: float) -> float:
        c = Circuit()
        c.add(
            ACVoltageSource(
                "Vac", "n1", "0", waveform=WaveformType.SINE, amplitude=v_peak, frequency=freq
            )
        )
        c.add(Resistor("R1", "n1", "n2", resistance=res_r))
        c.add(Inductor("L1", "n2", "n3", inductance=ind_l, dcr=0.0))
        c.add(Capacitor("C1", "n3", "0", capacitance=cap_c))
        c.add(Ground("GND", "0"))

        period = 1.0 / freq
        dt = period / 150.0
        res = MNASolver(c).solve_transient(duration=25.0 * period, dt=dt)
        # Measure peak current over the final 3 periods
        tail_samples = int(3.0 * period / dt)
        return float(np.max(np.abs(res.branch_currents["R1"][-tail_samples:])))

    i_peak_below = measure_steady_state_current_peak(0.7 * f0)
    i_peak_res = measure_steady_state_current_peak(f0)
    i_peak_above = measure_steady_state_current_peak(1.4 * f0)

    # At resonance X_L == X_C, so Z = R = 10 Ohm and I_peak = V_peak / R = 0.5 A
    expected_i_res = v_peak / res_r
    assert math.isclose(i_peak_res, expected_i_res, rel_tol=5e-3)
    assert i_peak_res > i_peak_below * 1.8
    assert i_peak_res > i_peak_above * 1.8


def test_lossless_lc_oscillation_constant_amplitude_and_period() -> None:
    """Extra test 3a: lossless LC oscillation with Trapezoidal integration has zero numerical damping."""
    ind_l = 1e-3  # 1 mH
    cap_c = 1e-6  # 1 uF
    v0 = 10.0  # Initial capacitor voltage 10 V
    expected_period = 2.0 * math.pi * math.sqrt(ind_l * cap_c)  # ~198.6918 us

    circuit = Circuit()
    cap = Capacitor("C1", "tank", "0", capacitance=cap_c, initial_voltage=v0)
    ind = Inductor("L1", "tank", "0", inductance=ind_l, dcr=0.0, initial_current=0.0)
    circuit.add(cap)
    circuit.add(ind)
    circuit.add(Ground("GND", "0"))

    # Use GMIN = 0.0 (pure lossless LC tank) and Trapezoidal integration from step 1
    solver = MNASolver(circuit, gmin=0.0)
    dt = expected_period / 200.0
    n_periods = 10
    res = solver.solve_transient(
        duration=n_periods * expected_period,
        dt=dt,
        method=IntegrationMethod.TRAPEZOIDAL,
        use_be_on_first_step=False,
    )

    v_wave = res.node_voltages["tank"]
    i_wave = res.branch_currents["L1"]

    # 1. Amplitude in the 1st period and 10th period must both match V0 = 10.0 V (no damping!)
    samples_per_period = 200
    peak_period_1 = float(np.max(v_wave[:samples_per_period]))
    peak_period_10 = float(np.max(v_wave[-samples_per_period:]))
    assert math.isclose(peak_period_1, v0, rel_tol=1e-4)
    assert math.isclose(peak_period_10, v0, rel_tol=1e-4)

    # Exact continuous amplitude envelope A(t) = sqrt(v_C(t)^2 + (L/C)*i_L(t)^2)
    # must stay constant at V0 = 10.0 V to machine precision (1e-12) across all 10 periods:
    z0_sq = ind_l / cap_c
    amp_envelope = np.sqrt(v_wave**2 + z0_sq * (i_wave**2))
    assert math.isclose(float(amp_envelope[1]), v0, rel_tol=1e-12)
    assert math.isclose(float(amp_envelope[-1]), v0, rel_tol=1e-12)
    assert math.isclose(float(amp_envelope[-1]), float(amp_envelope[1]), rel_tol=1e-12)

    # 2. Total electromagnetic energy E(t) = 0.5*C*v^2 + 0.5*L*i^2 is conserved at every step!
    initial_energy = 0.5 * cap_c * (v0**2)
    energy_trace = 0.5 * cap_c * (v_wave**2) + 0.5 * ind_l * (i_wave**2)
    max_energy_dev = float(np.max(np.abs(energy_trace - initial_energy)))
    assert max_energy_dev / initial_energy < 1e-12

    # 3. Measure period from rising zero-crossings with linear interpolation:
    zero_crossings: list[float] = []
    for k in range(len(v_wave) - 1):
        if v_wave[k] < 0.0 and v_wave[k + 1] >= 0.0:
            frac = -v_wave[k] / (v_wave[k + 1] - v_wave[k])
            t_cross = float(res.times[k]) + frac * dt
            zero_crossings.append(t_cross)

    measured_periods = np.diff(zero_crossings)
    avg_period = float(np.mean(measured_periods))
    assert math.isclose(avg_period, expected_period, rel_tol=1e-3)


def test_convergence_order_trapezoidal_vs_backward_euler() -> None:
    """Extra test 3b: halving dt reduces RC error by ~4x (2nd order) for Trap and ~2x (1st order) for BE."""
    vs = 10.0
    r = 1000.0
    c = 1e-6
    tau = r * c  # 1 ms
    t_end = tau
    v_exact = vs * (1.0 - math.exp(-t_end / tau))

    def run_rc_error(dt_val: float, method: IntegrationMethod) -> float:
        circ = Circuit()
        circ.add(DCVoltageSource("V1", "in", "0", voltage=vs))
        circ.add(Resistor("R1", "in", "cap", resistance=r))
        circ.add(Capacitor("C1", "cap", "0", capacitance=c, initial_voltage=0.0))
        circ.add(Ground("GND", "0"))
        solver = MNASolver(circ, gmin=0.0)
        res = solver.solve_transient(
            duration=t_end,
            dt=dt_val,
            method=method,
            use_be_on_first_step=(method == IntegrationMethod.BACKWARD_EULER),
        )
        return abs(float(res.node_voltages["cap"][-1]) - v_exact)

    dts = [tau / 20.0, tau / 40.0, tau / 80.0, tau / 160.0]

    # 1. Trapezoidal integration: error ratio when halving dt must approach 4.0 (order 2)
    trap_errors = [run_rc_error(dt_val, IntegrationMethod.TRAPEZOIDAL) for dt_val in dts]
    trap_ratios = [trap_errors[i] / trap_errors[i + 1] for i in range(len(trap_errors) - 1)]
    for ratio in trap_ratios:
        assert 3.85 < ratio < 4.15

    # 2. Backward Euler integration: error ratio when halving dt must approach 2.0 (order 1)
    be_errors = [run_rc_error(dt_val, IntegrationMethod.BACKWARD_EULER) for dt_val in dts]
    be_ratios = [be_errors[i] / be_errors[i + 1] for i in range(len(be_errors) - 1)]
    for ratio in be_ratios:
        assert 1.90 < ratio < 2.10


def test_switch_event_numerical_ringing_without_be_and_fix_with_be() -> None:
    """Extra test 3c: prove Trapezoidal rings after a switch event unless Backward Euler is used."""
    # A 1 uF capacitor starts uncharged (0 V) behind an OPEN switch connected to a 10 V source.
    # At t = 20 us, the switch closes (R_on = 1 mOhm, time constant R_on * C = 1 ns << dt = 10 us).
    def run_switch_cap(use_be_on_switch: bool) -> np.ndarray:
        circ = Circuit()
        circ.add(DCVoltageSource("V1", "src", "0", voltage=10.0))
        circ.add(
            Switch(
                "SW1",
                "src",
                "cap",
                closed=False,
                r_on=1e-3,
                r_off=1e9,
                c_parasitic=0.0,
                toggle_time=20e-6,
            )
        )
        circ.add(Capacitor("C1", "cap", "0", capacitance=1e-6, initial_voltage=0.0))
        circ.add(Ground("GND", "0"))

        solver = MNASolver(circ)
        res = solver.solve_transient(
            duration=100e-6,
            dt=10e-6,
            method=IntegrationMethod.TRAPEZOIDAL,
            use_be_on_switch=use_be_on_switch,
        )
        return res.branch_currents["C1"]

    # 1. WITHOUT Backward Euler after switch event:
    # After the switch closes at step 2 (t = 20 us), the capacitor is already charged to 10 V,
    # yet Trapezoidal's companion source reflects +I_impulse into -I_impulse on every subsequent step!
    i_no_be = run_switch_cap(use_be_on_switch=False)
    post_switch_no_be = i_no_be[4:]  # t = 40 us .. 100 us (well after the 1 ns charging event)
    # Verify violent alternating sign changes (+2 A, -2 A, +2 A, -2 A...) are present:
    assert float(np.max(np.abs(post_switch_no_be))) > 1.0
    assert np.all(post_switch_no_be[:-1] * post_switch_no_be[1:] < 0.0)

    # 2. WITH Backward Euler after switch event (the default fix):
    # Post-switch current settles cleanly to 0 A with zero ringing!
    i_with_be = run_switch_cap(use_be_on_switch=True)
    post_switch_with_be = i_with_be[4:]
    assert float(np.max(np.abs(post_switch_with_be))) < 1e-6


def test_inductive_kickback_with_10pf_contact_capacitance_and_warning() -> None:
    """Verify inductive kickback warning and LC_parasitic peak when interrupting an inductor."""
    # 12 V source driving a 10 mH inductor (with 12 Ohm DCR -> 1.0 A steady-state current)
    # through a closed switch with 10 pF parasitic contact capacitance.
    circuit = Circuit()
    circuit.add(DCVoltageSource("V1", "src", "0", voltage=12.0))
    sw = Switch(
        "SW1",
        "src",
        "sw_out",
        closed=True,
        r_on=1e-3,
        r_off=1e9,
        c_parasitic=10e-12,
        toggle_time=1e-6,
    )
    ind = Inductor(
        "L1",
        "sw_out",
        "0",
        inductance=10e-3,
        dcr=12.0,
        initial_current=1.0,
    )
    circuit.add(sw)
    circuit.add(ind)
    circuit.add(Ground("GND", "0"))

    solver = MNASolver(circuit)
    # Step with dt = 50 ns across the switch opening at t = 1 us
    res = solver.solve_transient(duration=3e-6, dt=50e-9)

    kickback_warnings = [w for w in res.warnings if w.code == "inductive_kickback"]
    assert len(kickback_warnings) == 1
    assert "Inductive kickback, consider a flyback diode" in kickback_warnings[0].message

    # Peak kickback voltage across the inductor reaches kilovolts when 1 A is interrupted into 10 pF
    peak_v_ind = float(np.max(np.abs(res.component_voltages["L1"])))
    assert peak_v_ind > 1000.0


def test_ac_voltage_source_waveforms() -> None:
    """Verify sine, square, triangle, sawtooth, and pulse waveforms with DC offset."""
    f = 1000.0
    t_quarter = 0.25 / f
    t_three_quarter = 0.75 / f

    s_sine = ACVoltageSource(
        "Vsin", "a", "0", waveform=WaveformType.SINE, amplitude=5.0, frequency=f, dc_offset=1.0
    )
    assert math.isclose(s_sine.voltage_at(0.0), 1.0, abs_tol=1e-12)
    assert math.isclose(s_sine.voltage_at(t_quarter), 6.0, rel_tol=1e-12)
    assert math.isclose(s_sine.voltage_at(t_three_quarter), -4.0, rel_tol=1e-12)

    s_sq = ACVoltageSource(
        "Vsq", "a", "0", waveform=WaveformType.SQUARE, amplitude=5.0, frequency=f, dc_offset=1.0
    )
    assert math.isclose(s_sq.voltage_at(t_quarter), 6.0, rel_tol=1e-12)
    assert math.isclose(s_sq.voltage_at(t_three_quarter), -4.0, rel_tol=1e-12)

    s_tri = ACVoltageSource(
        "Vtri", "a", "0", waveform=WaveformType.TRIANGLE, amplitude=4.0, frequency=f
    )
    assert math.isclose(s_tri.voltage_at(0.0), 0.0, abs_tol=1e-12)
    assert math.isclose(s_tri.voltage_at(t_quarter), 4.0, rel_tol=1e-12)
    assert math.isclose(s_tri.voltage_at(t_three_quarter), -4.0, rel_tol=1e-12)

    s_saw = ACVoltageSource(
        "Vsaw", "a", "0", waveform=WaveformType.SAWTOOTH, amplitude=4.0, frequency=f
    )
    assert math.isclose(s_saw.voltage_at(0.0), -4.0, rel_tol=1e-12)
    assert math.isclose(s_saw.voltage_at(0.5 / f), 0.0, abs_tol=1e-12)

    s_pulse = ACVoltageSource(
        "Vpls",
        "a",
        "0",
        waveform=WaveformType.PULSE,
        amplitude=3.3,
        frequency=f,
        duty_cycle=0.2,
        dc_offset=0.5,
    )
    assert math.isclose(s_pulse.voltage_at(0.1 / f), 3.8, rel_tol=1e-12)
    assert math.isclose(s_pulse.voltage_at(0.3 / f), 0.5, rel_tol=1e-12)
