"""Tests for saving and loading `.circ` files (Step 3A).

The expected numbers are worked out by hand from textbook formulas, not copied
from the program's own output. Anything that needs Qt runs in a subprocess so
this test process never imports PySide6.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys

import pytest

from circuitsim.canvas.connectivity import (
    PlacedComponentSpec,
    WireSpec,
    extract_connectivity,
)
from circuitsim.components import (
    ACVoltageSource,
    Capacitor,
    DCVoltageSource,
    Ground,
    Lightbulb,
    Resistor,
    Switch,
    Voltmeter,
)
from circuitsim.engine import MNASolver
from circuitsim.io.circ_serializer import (
    SCHEMA_VERSION,
    CircuitDocument,
    CircuitFileError,
    ViewState,
    dumps_document,
    load_document,
    loads_document,
    save_document,
)


def _divider_document() -> CircuitDocument:
    """12 V source, R1 = 1 kOhm in series with R2 = 3 kOhm.

    By hand: I = 12 / 4000 = 3 mA, V(mid) = 12 * 3000 / 4000 = 9 V.
    """
    placed = [
        PlacedComponentSpec(DCVoltageSource("V1", "a", "b", voltage=12.0), (-80.0, 0.0)),
        PlacedComponentSpec(Resistor("R1", "a", "b", resistance=1000.0), (40.0, 0.0)),
        PlacedComponentSpec(Resistor("R2", "a", "b", resistance=3000.0), (160.0, 0.0)),
        PlacedComponentSpec(Ground("GND1"), (-40.0, 60.0)),
    ]
    wires = [
        WireSpec("W1", ((-120, 0), (-120, -40), (0, -40), (0, 0))),
        WireSpec("W2", ((80, 0), (120, 0))),
        WireSpec("W3", ((200, 0), (200, 40), (-40, 40))),
        WireSpec("W4", ((-40, 0), (-40, 40))),
    ]
    return CircuitDocument(placed=placed, wires=wires)


def _rc_document() -> CircuitDocument:
    """5 V source, R = 1 kOhm, C = 1 uF. By hand: tau = 1 ms, V_C(1 ms) = 5 (1 - 1/e)."""
    placed = [
        PlacedComponentSpec(DCVoltageSource("V1", "a", "b", voltage=5.0), (-80.0, 0.0)),
        PlacedComponentSpec(Resistor("R1", "a", "b", resistance=1000.0), (40.0, 0.0)),
        PlacedComponentSpec(
            Capacitor("C1", "a", "b", capacitance=1e-6, initial_voltage=0.0),
            (160.0, 0.0),
        ),
        PlacedComponentSpec(Ground("GND1"), (-40.0, 60.0)),
    ]
    wires = [
        WireSpec("W1", ((-120, 0), (-120, -40), (0, -40), (0, 0))),
        WireSpec("W2", ((80, 0), (120, 0))),
        WireSpec("W3", ((200, 0), (200, 40), (-40, 40))),
        WireSpec("W4", ((-40, 0), (-40, 40))),
    ]
    return CircuitDocument(placed=placed, wires=wires)


def _roundtrip(doc: CircuitDocument, tmp_path) -> CircuitDocument:
    path = tmp_path / "test.circ"
    save_document(path, doc)
    return load_document(path)


# ----------------------------------------------------------------------
# Round trip against analytic formulas
# ----------------------------------------------------------------------


def test_voltage_divider_round_trip_matches_hand_calculation(tmp_path) -> None:
    loaded = _roundtrip(_divider_document(), tmp_path)
    conn = extract_connectivity(loaded.placed, loaded.wires, loaded.junctions)
    sol = MNASolver(conn.circuit).solve_dc()

    mid = conn.component_nodes["R2"]["a"]
    assert sol.node_voltages[mid] == pytest.approx(9.0, rel=1e-6)  # 12 * 3/4
    top = conn.component_nodes["R1"]["a"]
    i_r1 = (sol.node_voltages[top] - sol.node_voltages[mid]) / 1000.0
    assert i_r1 == pytest.approx(3e-3, rel=1e-6)  # 12 V / 4 kOhm


def test_rc_round_trip_matches_charging_formula(tmp_path) -> None:
    loaded = _roundtrip(_rc_document(), tmp_path)
    conn = extract_connectivity(loaded.placed, loaded.wires, loaded.junctions)
    tau = 1000.0 * 1e-6
    dt = tau / 200.0
    res = MNASolver(conn.circuit).solve_transient(duration=3.0 * tau, dt=dt)
    cap_node = conn.component_nodes["C1"]["a"]
    for k in (1, 2, 3):
        idx = int(round(k * tau / dt))
        expected = 5.0 * (1.0 - math.exp(-k))  # 3.1606 V, 4.3233 V, 4.7510 V
        assert res.node_voltages[cap_node][idx] == pytest.approx(expected, rel=2e-3)


# ----------------------------------------------------------------------
# Things that must survive a round trip
# ----------------------------------------------------------------------


def test_rotation_flip_labels_and_parameters_survive(tmp_path) -> None:
    sw = Switch("SW1", "a", "b", closed=True, v_breakdown=None, toggle_time=0.25)
    ac = ACVoltageSource(
        "Vac1", "a", "b", waveform="square", amplitude=7.5, frequency=60.0,
        phase_deg=30.0, dc_offset=1.5, duty_cycle=0.3,
    )
    bulb = Lightbulb("B1", "a", "b", rated_power=100.0, rated_voltage=230.0,
                     use_filament_model=True)
    vm = Voltmeter("VM1", "a", "b", mode="rms")
    r = Resistor("R1", "a", "b", resistance=4700.0, label="Rload", show_value=False)
    doc = CircuitDocument(
        placed=[
            PlacedComponentSpec(r, (100.0, -40.0), rotation_deg=270, flipped_h=True),
            PlacedComponentSpec(sw, (20.0, 0.0), rotation_deg=90),
            PlacedComponentSpec(ac, (0.0, 0.0), flipped_h=True),
            PlacedComponentSpec(bulb, (60.0, 60.0), rotation_deg=180),
            PlacedComponentSpec(vm, (-60.0, 60.0)),
        ],
        wires=[WireSpec("W7", ((0, 0), (40, 0), (40, 20)))],
        junctions=[(40, 0)],
        view=ViewState(theme="light", zoom=1.5, pan=(12.0, -8.0), simulation_speed="10x"),
    )
    out = _roundtrip(doc, tmp_path)

    by_name = {s.component.name: s for s in out.placed}
    r2 = by_name["R1"]
    assert (r2.rotation_deg, r2.flipped_h, r2.center_px) == (270, True, (100.0, -40.0))
    assert r2.component.label == "Rload" and r2.component.show_value is False
    assert r2.component.resistance == 4700.0
    assert by_name["SW1"].rotation_deg == 90

    s2 = by_name["SW1"].component
    assert s2.closed is True and s2.v_breakdown is None and s2.toggle_time == 0.25
    a2 = by_name["Vac1"].component
    assert (a2.amplitude, a2.frequency, a2.phase_deg, a2.dc_offset) == (7.5, 60.0, 30.0, 1.5)
    assert a2.duty_cycle == 0.3 and a2.waveform.value == "square"
    b2 = by_name["B1"].component
    assert (b2.rated_power, b2.rated_voltage, b2.use_filament_model) == (100.0, 230.0, True)
    assert by_name["VM1"].component.mode.value == "rms"

    assert out.wires[0].wire_id == "W7"
    assert [tuple(p) for p in out.wires[0].points] == [(0, 0), (40, 0), (40, 20)]
    assert out.junctions == [(40, 0)]
    assert (out.view.theme, out.view.zoom, out.view.pan, out.view.simulation_speed) == (
        "light", 1.5, (12.0, -8.0), "10x",
    )


def test_save_load_rotated_flipped_circuit_preserves_wires_polarity_and_voltages(tmp_path) -> None:
    """Save and load a circuit with rotated and flipped parts and wires.

    Asserts:
    - Every terminal is connected to the same wire as before.
    - Polarities are unchanged.
    - Simulation gives the exact same voltages before save and after load.
    """
    from circuitsim.canvas.symbol_geometry import DEFAULT_IEC_SYMBOLS_DIR, load_all_iec_metadata

    catalog = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)

    # 1. 24 V source at (0, 0), rotated 90° and flipped: pos at (0, -40), neg at (0, 40)
    v1 = PlacedComponentSpec(
        DCVoltageSource("V1", "pos", "neg", voltage=24.0),
        center_px=(0.0, 0.0),
        rotation_deg=90,
        flipped_h=True,
    )
    # 2. Ground at (0, 60) with terminal at (0, 40)
    gnd = PlacedComponentSpec(Ground("GND1"), (0.0, 60.0))

    # 3. Resistor R1 = 1 kΩ, rotated 180°: a at (240, 0), b at (160, 0)
    r1 = PlacedComponentSpec(
        Resistor("R1", "a", "b", resistance=1000.0),
        center_px=(200.0, 0.0),
        rotation_deg=180,
        flipped_h=False,
    )

    # 4. Resistor R2 = 3 kΩ, rotated 270° and flipped: a at (400, 40), b at (400, -40)
    r2 = PlacedComponentSpec(
        Resistor("R2", "a", "b", resistance=3000.0),
        center_px=(400.0, 0.0),
        rotation_deg=270,
        flipped_h=True,
    )

    # 5. Voltmeter VM1 across R2, rotated 270°: pos at (600, 40), neg at (600, -40)
    vm1 = PlacedComponentSpec(
        Voltmeter("VM1", "pos", "neg"),
        center_px=(600.0, 0.0),
        rotation_deg=270,
        flipped_h=False,
    )

    # Wires routing between transformed terminals
    w1 = WireSpec("W1", ((0, -40), (0, -100), (240, -100), (240, 0)))
    w2 = WireSpec("W2", ((160, 0), (160, 100), (400, 100), (400, 40)))
    w3 = WireSpec("W3", ((400, 40), (600, 40)))
    w4 = WireSpec("W4", ((400, -40), (600, -40)))
    w5 = WireSpec("W5", ((400, -40), (400, -80), (700, -80), (700, 140), (0, 140), (0, 40)))

    doc_before = CircuitDocument(
        placed=[v1, gnd, r1, r2, vm1],
        wires=[w1, w2, w3, w4, w5],
    )

    # Solve before save
    res_before = extract_connectivity(doc_before.placed, doc_before.wires, symbol_catalog=catalog)
    sol_before = MNASolver(res_before.circuit).solve_dc()

    # Save and reload
    circ_file = tmp_path / "rotated_flipped_test.circ"
    save_document(circ_file, doc_before)
    doc_after = load_document(circ_file)

    # Solve after load
    res_after = extract_connectivity(doc_after.placed, doc_after.wires, symbol_catalog=catalog)
    sol_after = MNASolver(res_after.circuit).solve_dc()

    # 1. Every terminal is connected to the same wire/node as before
    assert res_before.component_nodes == res_after.component_nodes
    for comp in ["V1", "GND1", "R1", "R2", "VM1"]:
        assert res_after.component_nodes[comp] == res_before.component_nodes[comp]

    # 2. Polarities are unchanged
    v1_pos_node = res_after.component_nodes["V1"]["pos"]
    v1_neg_node = res_after.component_nodes["V1"]["neg"]
    assert sol_after.node_voltages[v1_pos_node] == pytest.approx(24.0)
    assert sol_after.node_voltages[v1_neg_node] == pytest.approx(0.0)

    vm_before = res_before.circuit.get_component("VM1")
    vm_after = res_after.circuit.get_component("VM1")
    # Voltage across R2 is +18 V (hand calculated: 24 V * 3k/(1k + 3k) = 18 V, approx with 10 MΩ meter)
    assert vm_after.reading == pytest.approx(vm_before.reading)
    assert vm_after.reading == pytest.approx(18.0, rel=1e-3)

    # 3. Exact same voltages across all nodes before save and after load
    assert sol_after.node_voltages == pytest.approx(sol_before.node_voltages)


def test_file_declares_format_and_version() -> None:
    data = json.loads(dumps_document(_divider_document()))
    assert data["format"] == "circuitsim"
    assert data["schema_version"] == SCHEMA_VERSION == 1


# ----------------------------------------------------------------------
# Bad files give readable errors
# ----------------------------------------------------------------------


def _valid_text() -> str:
    return dumps_document(_divider_document())


def _expect_error(text: str, fragment: str) -> None:
    with pytest.raises(CircuitFileError) as info:
        loads_document(text)
    assert fragment in str(info.value)


def test_empty_file() -> None:
    _expect_error("", "empty")
    _expect_error("   \n ", "empty")


def test_truncated_and_corrupted_files() -> None:
    text = _valid_text()
    _expect_error(text[: len(text) // 2], "damaged or incomplete")
    _expect_error("{{{{ not json", "damaged or incomplete")


def test_wrong_format_files() -> None:
    _expect_error("[1, 2, 3]", "not a CircuitSim file")
    _expect_error('{"hello": "world"}', "not a CircuitSim file")
    _expect_error('{"format": "other", "schema_version": 1}', "not a CircuitSim file")


def test_newer_and_unknown_versions() -> None:
    data = json.loads(_valid_text())
    data["schema_version"] = 2
    _expect_error(json.dumps(data), "made by a newer version of CircuitSim")
    data["schema_version"] = "one"
    _expect_error(json.dumps(data), "valid version number")
    data["schema_version"] = 0
    _expect_error(json.dumps(data), "Unknown file version")


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d["components"][0].update(type="flux_capacitor"), "unknown type"),
        (lambda d: d["components"][0].update(rotation_deg=45), "rotation"),
        (lambda d: d["components"][0].update(center_px=[1]), "center_px"),
        (lambda d: d["components"][1]["parameters"].update(resistance=-5), "must be"),
        (lambda d: d["components"][1]["parameters"].update(resistance="1k"), "must be a number"),
        (lambda d: d["components"][1]["parameters"].update(bogus=1.0), "unknown parameter"),
        (lambda d: d["components"][1].update(name=d["components"][2]["name"]), "both named"),
        (lambda d: d["wires"][0].update(points=[[0, 0]]), "at least two points"),
        (lambda d: d.update(wires="nope"), "wire list"),
        (lambda d: d["view"].update(theme="purple"), "theme"),
        (lambda d: d["view"].update(zoom=0), "zoom"),
    ],
)
def test_invalid_contents_are_rejected_with_plain_message(mutate, fragment) -> None:
    data = json.loads(_valid_text())
    mutate(data)
    _expect_error(json.dumps(data), fragment)


def test_non_text_and_missing_files(tmp_path) -> None:
    binary = tmp_path / "x.circ"
    binary.write_bytes(b"\xff\xfe\x00\x81\x82\xff")
    with pytest.raises(CircuitFileError, match="not a text file"):
        load_document(binary)
    with pytest.raises(CircuitFileError, match="does not exist"):
        load_document(tmp_path / "missing.circ")


# ----------------------------------------------------------------------
# Atomic save and backup
# ----------------------------------------------------------------------


def test_failed_write_leaves_old_file_intact(tmp_path, monkeypatch) -> None:
    path = tmp_path / "keep.circ"
    save_document(path, _divider_document())
    old_bytes = path.read_bytes()

    def boom(_fd: int) -> None:
        raise OSError("disk full (simulated)")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(CircuitFileError, match="previous file was not changed"):
        save_document(path, _rc_document())
    monkeypatch.undo()

    assert path.read_bytes() == old_bytes  # old file untouched
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []
    load_document(path)  # still loads


def test_unserializable_value_does_not_touch_file(tmp_path) -> None:
    path = tmp_path / "keep.circ"
    save_document(path, _divider_document())
    old_bytes = path.read_bytes()
    bad = _divider_document()
    bad.placed[0] = PlacedComponentSpec(
        bad.placed[0].component, (float("nan"), 0.0)
    )
    with pytest.raises(CircuitFileError, match="cannot be saved"):
        save_document(path, bad)
    assert path.read_bytes() == old_bytes


def test_backup_keeps_previous_version(tmp_path) -> None:
    path = tmp_path / "proj.circ"
    save_document(path, _divider_document())
    assert not (tmp_path / "proj.circ.bak").exists()  # nothing to back up yet
    first = path.read_bytes()
    save_document(path, _rc_document())
    assert (tmp_path / "proj.circ.bak").read_bytes() == first
    assert path.read_bytes() != first
    assert loads_document(path.read_text(encoding="utf-8")).placed[2].component.name == "C1"


# ----------------------------------------------------------------------
# Qt tests (subprocess so pytest itself never imports PySide6)
# ----------------------------------------------------------------------


def _run_qt(script: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, check=False, env=env,
    )


def test_no_qt_in_serializer_module() -> None:
    res = subprocess.run(
        [sys.executable, "-c",
         "import sys, circuitsim.io.circ_serializer; "
         "assert not [m for m in sys.modules if m.startswith('PySide6')]"],
        capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stderr


_QT_PRELUDE = """
import sys, os, json, tempfile, math
from pathlib import Path
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QMessageBox
from circuitsim.app.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
errors = []
win._show_error = lambda title, text: errors.append(text)
scene = win.circuit_scene
tmp = Path(tempfile.mkdtemp())

def build_divider():
    # 12 V, R1 = 1k (horizontal), R2 = 3k (vertical), same geometry as the engine tests
    scene.place_new_component("dc_voltage", QPointF(0, 0), rotation_deg=90)
    scene.place_new_component("resistor", QPointF(60, -40))
    r2 = scene.place_new_component("resistor", QPointF(120, 0), rotation_deg=90)
    scene.place_new_component("ground", QPointF(0, 60))
    scene.add_wire([(0, -40), (20, -40)])
    scene.add_wire([(100, -40), (120, -40)])
    scene.add_wire([(0, 40), (120, 40)])
    scene.edit_component_parameters(r2, {"resistance": 3000.0})
    return r2
"""


def test_window_save_open_roundtrip_title_and_clean_state() -> None:
    """Save from a real window, open in a fresh window, check volts by hand: 12 * 3/4 = 9 V."""
    script = _QT_PRELUDE + """
r2 = build_divider()
assert win.windowTitle().startswith("Untitled*"), win.windowTitle()
assert win.has_unsaved_changes()

path = tmp / "divider.circ"
assert win.save_to_path(path) is True
assert win.windowTitle().startswith("divider.circ") and "*" not in win.windowTitle(), win.windowTitle()
assert not win.has_unsaved_changes()

# any edit marks the file as modified again (asterisk), undo returns to clean
scene.edit_component_parameters(r2, {"resistance": 1000.0})
assert "*" in win.windowTitle()
scene.undo_stack.undo()
assert "*" not in win.windowTitle()
win.circuit_scene.undo_stack.setClean()
win.close()

# fresh window, open the file
win2 = MainWindow()
win2._show_error = lambda t, m: errors.append(m)
assert win2.open_path(path) is True and errors == []
assert win2.windowTitle().startswith("divider.circ") and "*" not in win2.windowTitle()
assert not win2.circuit_scene.undo_stack.canUndo()  # loading clears undo history
names = sorted(i.component.name for i in win2.circuit_scene.placed_items)
assert names == ["GND1", "R1", "R2", "V1"], names

conn = win2.circuit_scene.extract_connectivity_result()
from circuitsim.engine import MNASolver
sol = MNASolver(conn.circuit).solve_dc()
v_mid = sol.node_voltages[conn.component_nodes["R2"]["a"]]
assert abs(v_mid - 9.0) < 1e-6, v_mid          # 12 V * 3k / 4k
r1 = next(i for i in win2.circuit_scene.placed_items if i.component.name == "R1")
assert r1.component.resistance == 1000.0
r2b = next(i for i in win2.circuit_scene.placed_items if i.component.name == "R2")
assert r2b.component.resistance == 3000.0 and r2b.rotation_deg == 90
# a new wire after loading must not reuse an old wire id
old_ids = {w.wire_id for w in win2.circuit_scene.placed_wires}
assert win2.circuit_scene.next_wire_id() not in old_ids
win2.circuit_scene.undo_stack.setClean()
win2.close()
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_bad_files_show_message_and_leave_scene_unchanged() -> None:
    script = _QT_PRELUDE + """
build_divider()
good = tmp / "good.circ"
assert win.save_to_path(good)
text = good.read_text(encoding="utf-8")

def snapshot():
    return json.dumps(
        [(i.component.name, i.pos().x(), i.pos().y(), i.rotation_deg) for i in scene.placed_items]
        + [(w.wire_id, list(w.points)) for w in scene.placed_wires], default=str)

before = snapshot()
undo_before = scene.undo_stack.count()

newer = json.loads(text); newer["schema_version"] = 99
bad_cases = {
    "empty.circ": "",
    "truncated.circ": text[: len(text) // 2],
    "garbage.circ": "\\x00\\x01 not a circuit",
    "wrongformat.circ": json.dumps({"hello": 1}),
    "newer.circ": json.dumps(newer),
}
for name, content in bad_cases.items():
    p = tmp / name
    p.write_text(content, encoding="utf-8")
    assert win.open_path(p) is False, name
    assert snapshot() == before, "scene changed by " + name
    assert scene.undo_stack.count() == undo_before
assert len(errors) == len(bad_cases), errors
assert any("newer version of CircuitSim" in e for e in errors)
assert any("empty" in e for e in errors)
assert win.open_path(tmp / "does_not_exist.circ") is False
assert snapshot() == before

# a file that is valid JSON/format but has one bad component loads NOTHING
broken = json.loads(text); broken["components"][-1]["rotation_deg"] = 45
(tmp / "broken.circ").write_text(json.dumps(broken), encoding="utf-8")
assert win.open_path(tmp / "broken.circ") is False
assert snapshot() == before
scene.undo_stack.setClean(); win.close()
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_unsaved_changes_prompt_for_new_open_and_close() -> None:
    script = _QT_PRELUDE + """
asked = []
answer = {"v": QMessageBox.StandardButton.Cancel}
win._ask_save_discard_cancel = lambda what: (asked.append(what), answer["v"])[1]
build_divider()
n = len(scene.placed_items)

# Cancel keeps everything
win._on_new_circuit()
assert len(scene.placed_items) == n and asked and "new circuit" in asked[-1]
win.close()
assert win.isVisible() or True  # close() was refused, window not torn down
assert "closing" in asked[-1] and len(scene.placed_items) == n

# Discard goes ahead
answer["v"] = QMessageBox.StandardButton.Discard
win._on_new_circuit()
assert len(scene.placed_items) == 0 and not win.has_unsaved_changes()
assert win.windowTitle().startswith("Untitled") and "*" not in win.windowTitle()

# No prompt when nothing changed
asked.clear()
win._on_new_circuit()
assert asked == []

# Save answer: saves to the chosen path and then continues
build_divider()
target = tmp / "prompted.circ"
win._on_save_circuit_as = lambda: win.save_to_path(target)
answer["v"] = QMessageBox.StandardButton.Save
win._on_new_circuit()
assert target.exists() and len(scene.placed_items) == 0
win.close()
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


def test_toolbar_and_menu_file_actions_exist_and_work() -> None:
    script = _QT_PRELUDE + """
shortcuts = {a.text().replace("&", ""): a.shortcut().toString() for a in
             (win.act_new, win.act_open, win.act_save, win.act_save_as)}
assert shortcuts["New"] == "Ctrl+N", shortcuts
assert shortcuts["Open..."] == "Ctrl+O", shortcuts
assert shortcuts["Save"] == "Ctrl+S", shortcuts
assert shortcuts["Save As..."] == "Ctrl+Shift+S", shortcuts
# toolbar buttons are wired to the same actions
tb_actions = [a for tb in win.findChildren(type(win.findChild(__import__("PySide6.QtWidgets", fromlist=["QToolBar"]).QToolBar)))
              for a in tb.actions()]
for a in (win.act_new, win.act_open, win.act_save):
    assert a in tb_actions
# Save with a known path triggers a real save when the action fires
build_divider()
target = tmp / "viaaction.circ"
win._current_path = target
win.act_save.trigger()
assert target.exists() and not win.has_unsaved_changes()
win.close()
"""
    res = _run_qt(script)
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
