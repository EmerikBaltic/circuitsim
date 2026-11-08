# Learning Notes — CircuitSim

## Milestone 2 — Step 2C: Live Simulation Session, Background `QThread` Worker, Upright Labels & Canvas Telemetry

In **Step 2C**, we brought the schematic canvas to life! Pressing **Run (`F5`)** solves your schematic continuously in a background worker thread while updating live voltmeter/ammeter readouts, lightbulb glow, switch animations, and problem highlighting on the canvas without ever freezing the GUI.

---

### 1. Which Files to Read First (Step 2C)

1. [`src/circuitsim/engine/simulation_session.py`](src/circuitsim/engine/simulation_session.py) — **Pure Python (zero Qt imports!)**. Defines `SimulationSession`, `SimulationBackendProtocol`, `SimulationFrame`, `ComponentTelemetry`, and `ProblemDiagnostic`. Because every command and output frame is a plain, picklable Python dataclass, you can run and test a full interactive simulation session without opening a window—or move the worker to a separate `multiprocessing.Process` later if needed.
2. [`src/circuitsim/app/sim_worker.py`](src/circuitsim/app/sim_worker.py) — Wraps `SimulationSession` inside `_SessionThreadWorker` on a background `QThread`, communicating with `MainWindow` strictly via queued Qt signals (`Qt.ConnectionType.QueuedConnection`).
3. [`src/circuitsim/canvas/component_item.py`](src/circuitsim/canvas/component_item.py) — Renders upright component labels/values under any rotation or flip, animates the switch blade with `QVariantAnimation`, draws the lightbulb's power-based radial glow and overload badge (`>100%!`), and outlines components with errors (red) or warnings (amber).
4. [`src/circuitsim/dialogs/quick_edit_dialog.py`](src/circuitsim/dialogs/quick_edit_dialog.py) — Builds a compact double-click editor dynamically from each component's `get_editable_parameters()` descriptor list (`ComponentParameter` in [`base.py`](src/circuitsim/components/base.py)), validates entries with `parse_engineering_value`, and applies changes live while running.

---

### 2. Key Engineering & UI Design Decisions in Step 2C

1. **Why Separate `SimulationSession` from `QThread`? (`SimulationBackendProtocol`)**:
   - GUI code is hard to unit-test if solver state is tangled inside `QMainWindow` slots. By putting all session control (`start`, `pause`, `stop`, `step_chunk`, `toggle_switch`, `update_component_parameter`) in [`simulation_session.py`](src/circuitsim/engine/simulation_session.py) with **zero `PySide6` imports**, our pytest suite tests live meter readings, switch toggling, live resistor edits, lightbulb over-brightness, and error diagnostics directly in pure Python.
   - `SimulationWorkerController` in [`sim_worker.py`](src/circuitsim/app/sim_worker.py) then runs `SimulationSession` on a background `QThread`. Every ~33 ms (~30 FPS), the worker advances a chunk of transient steps (`step_chunk`) and emits an immutable `SimulationFrame` back to the GUI thread.
2. **How We Verified That the UI Never Freezes During Simulation**:
   - In [`tests/test_simulation_session_and_step2c.py`](tests/test_simulation_session_and_step2c.py) (`test_qt_step2c_ui_responsiveness_upright_labels_speed_dropdown_and_quick_edit`), we start a main-thread `QTimer` firing every `10 ms` to measure GUI event-loop heartbeats while `win.start_simulation()` runs the solver continuously in its background `QThread`.
   - Over a `240 ms` window, the main GUI thread processes regular `10 ms` heartbeats without a single stall (`max_gap_ms < 120 ms`) while receiving live `SimulationFrame` updates that change the canvas voltmeter from `"-- V"` to `"12 V"`.
3. **Keeping Labels & Values Upright When Rotated or Flipped**:
   - If you rotate a `QGraphicsItem` using `item.setRotation(180)` or mirror it with `QTransform.fromScale(-1, 1)`, Qt rotates and mirrors all text drawn inside `paint()`, making labels upside-down or backwards!
   - Instead, `ComponentItem` keeps its `QGraphicsObject` transform as the **identity matrix** (`item.transform().isIdentity() == True`). Inside `ComponentItem.paint()`, we `painter.save()`, apply the rotation and horizontal flip *only* while drawing the symbol graphic, `painter.restore()`, and then draw the designator (`R1`) and value (`1 kΩ`) at `0°` in local coordinates—adjusting their offset above/below or to the right of the body when the component is vertical (`90°`/`270°`).
4. **Honest Meter Readouts (`"-- V"` and `"-- A"`)**:
   - Before a simulation starts (or after pressing **Stop** or encountering a circuit error), a meter has not measured anything. Showing `"0 V"` or `"0 A"` would mislead students into thinking the circuit was solved with zero voltage.
   - `Voltmeter` and `Ammeter` track `has_reading: bool = False` (set to `True` only when `record_sample()` receives a solver solution, and reset to `False` in `reset_state()`), displaying `"-- V"` and `"-- A"` until a real reading exists.
5. **Isolated Junction Dots Never Create Phantom Nets**:
   - In [`connectivity.py`](src/circuitsim/canvas/connectivity.py), an explicit junction dot placed in empty space (or anywhere not lying on at least one wire segment) is ignored during netlist extraction and visual dot rendering, so it can never create a floating net, a phantom connection, or a false warning.

---

### 3. Three Small Exercises You Can Try (Step 2C)

1. **Live Ohm's Law & Double-Click Value Editing**:
   Launch `.\.venv\Scripts\python.exe -m circuitsim.main`, wire a **DC Voltage Source** (`12 V`), a series **Switch**, a series **Ammeter**, a **Resistor** (`1 kΩ`) with a parallel **Voltmeter**, and a **Ground**. Notice the meters read `-- V` and `-- A`. Press **Run (`F5`)**, click the switch to close it (`12 V`, `12 mA`), and **double-click the resistor** while running to change its value to `2k` or `500`—watch the ammeter update immediately to `6 mA` or `24 mA`!
2. **Lightbulb Glow & Over-Bright Warning**:
   Replace the resistor with a **Lightbulb** (`60W / 120V`) and double-click the DC source to set `120V`. Press **Run (`F5`)** to see the warm yellow glow at 100% rated power. Now double-click the DC source and enter `180V`: the glow intensifies, an orange `>100%!` badge appears on the bulb, and the status bar warns that the bulb is overloaded (`225%`).
3. **Canvas Problem Highlighting**:
   Delete the **Ground** symbol while the circuit is running (or press **Run** without a ground): all components and wires highlight in red and the status bar reports `Error: No ground connected`. Press **`Ctrl+Z`** to undo deleting the ground and press **Run (`F5`)**—the red highlight clears and the simulation resumes!

---

## Milestone 2 — Step 2B: Schematic Connectivity Rules, Union-Find Netlist Extraction & `QUndoStack`

In **Step 2B**, we connected the visual schematic editor to the physics engine! When you place parts and draw orthogonal wires on the canvas, **CircuitSim** extracts an electrical netlist (`CircuitScene.build_circuit()`) that feeds directly into our Modified Nodal Analysis (`MNASolver`) engine from Milestone 1.

---

### 1. Which Files to Read First (Step 2B)

1. [`src/circuitsim/canvas/connectivity.py`](src/circuitsim/canvas/connectivity.py) — **Pure Python (zero Qt imports!)**. Implements right-angle wire routing (`route_orthogonal_wire`), polyline simplification (`simplify_orthogonal_points`), attached-wire re-routing (`reroute_wires_for_updated_terminals`), and the Union-Find netlist extractor (`extract_connectivity`).
2. [`src/circuitsim/canvas/wire_item.py`](src/circuitsim/canvas/wire_item.py) — Draws orthogonal wires (`QPainterPath`) with a 10 px hit-test stroke (`QPainterPathStroker`) for easy clicking/selection and a dashed live-preview mode while routing a new wire.
3. [`src/circuitsim/canvas/commands.py`](src/circuitsim/canvas/commands.py) — Implements `QUndoCommand` classes (`AddComponentCommand`, `AddWireCommand`, `MoveComponentsCommand`, `RotateComponentsCommand`, `FlipComponentsCommand`, `DeleteItemsCommand`, `PasteItemsCommand`, `ToggleJunctionCommand`, `EditComponentParametersCommand`) so every edit can be undone (`Ctrl+Z`) and redone (`Ctrl+Y`).
4. [`tests/test_connectivity_and_editing.py`](tests/test_connectivity_and_editing.py) — Shows how a voltage divider and an $RC$ transient circuit built from pixel coordinates and wires produce the exact same answers as hand-built Milestone 1 circuits and analytical formulas.

---

### 2. Schematic Connectivity Rules (Step 2B & Step 2C)

Real schematic capture tools (like KiCad, LTspice, and Altium) follow strict rules so you never get accidental short circuits when wires cross on a crowded diagram. **CircuitSim** enforces these core connectivity rules in [`connectivity.py`](src/circuitsim/canvas/connectivity.py):

1. **Terminals, Crossings, T-Junctions, and Explicit Junction Dots**:
   - **Terminal connection**: A wire connects to a component terminal **only if a wire endpoint sits at that terminal's exact grid coordinate** (or an explicit junction dot on a wire is placed there). A wire passing straight over a terminal without ending there does *not* connect.
   - **Crossing wires do NOT connect**: Two perpendicular wires that cross at an interior point `(x, y)` (where neither wire ends) remain electrically separate nets.
   - **T-junctions and Explicit Junction Dots DO connect**: Two wires connect if and only if:
     - They share an endpoint at `(x, y)`,
     - One wire's endpoint lands on the interior segment of another wire (forming a **T-junction**), or
     - You place an explicit **Junction Dot** (`J` key or right-click menu) at their intersection `(x, y)`.
   - **Isolated Junction Dots are ignored**: A junction dot that is not on any wire never creates a net, a phantom connection, or a false warning.
2. **Attached Wires on Delete, Move, Rotate, and Flip**:
   - **Deleting a component** automatically finds and deletes all wires whose endpoints sit on any of that component's terminals (and pressing `Ctrl+Z` restores both the component and all of its attached wires).
   - **Moving, rotating (`R`), or flipping (`F`)** one or more components keeps all attached wire endpoints locked to their respective component terminals and automatically re-routes the wires at $90^\circ$ right angles.
3. **Zero-Length, Duplicate, and Overlapping Wires**:
   - **Zero-length wires** (where start and end collapse to the same point, including folded-back paths like `(0,0) -> (20,0) -> (0,0)`) are discarded during normalization so they can never act as phantom T-junctions on a wire crossing.
   - **Duplicate wires** (identical polylines drawn forward or backward) are deduplicated.
   - **Collinear overlapping wires** (two horizontal segments on the same $y$ or two vertical segments on the same $x$ whose spans overlap with positive length) are unified into a single conductor without creating phantom connections to perpendicular crossing wires.

---

### 3. How Union-Find Extracts the Netlist (`extract_connectivity`)

How do we turn a drawing of components and wires into node names like `"0"`, `"N1"`, `"N2"`?
We use the **Disjoint-Set (Union-Find)** algorithm:
1. Every component terminal `("term", comp_name, term_name)` and every normalized wire `("wire", wire_id)` starts in its own singleton set.
2. Whenever a wire endpoint sits on a terminal, we call `uf.union(wire, terminal)`.
3. Whenever a wire endpoint lies on another wire (endpoint-to-endpoint or T-junction), or two collinear wire segments overlap, we call `uf.union(wire_a, wire_b)`.
4. Whenever an explicit junction dot sits at `(x, y)` on at least one wire, we union all wires and terminals passing through `(x, y)`.
5. After all unions finish, every disjoint set is one **electrical node (net)**:
   - Any set containing a `Ground` component's terminal is named `"0"` (the $0\text{ V}$ reference node).
   - Every other set gets a deterministic name `"N1"`, `"N2"`, ... sorted by grid position.
   - Each component is cloned into a `Circuit` with its terminal node names filled in!

---

## Milestone 2 — Step 2A: Qt Graphics View Architecture, Grid Geometry & Hybrid SVG/Procedural Symbols

1. [`src/circuitsim/canvas/symbol_geometry.py`](src/circuitsim/canvas/symbol_geometry.py) — Converts grid units (`1 grid unit = 20 px`) to pixels, transforms terminal coordinates under rotation/flip, and validates/recolours custom SVGs (`viewBox="0 0 80 40"` or centered `"-40 -20 80 40"`).
2. [`src/circuitsim/canvas/symbol_renderer.py`](src/circuitsim/canvas/symbol_renderer.py) — Renders custom SVGs when present in `resources/symbols/iec/` or procedural IEC 60617 fallback graphics via `QPainter`.

---

## Milestone 1 (Steps A & B): Modified Nodal Analysis (MNA), Companion Models & Switching Transients

1. [`src/circuitsim/dialogs/value_parser.py`](src/circuitsim/dialogs/value_parser.py) — Case-sensitive engineering notation parser (`"4.7k"`, `"15m"`, `"10M"`).
2. [`src/circuitsim/components/`](src/circuitsim/components/) & [`src/circuitsim/engine/`](src/circuitsim/engine/) — Companion models and MNA solver ($\mathbf{A}\mathbf{x} = \mathbf{b}$) using cached `scipy.linalg.lu_factor` / `lu_solve`, Backward Euler switching/arc settling, and Trapezoidal integration.
