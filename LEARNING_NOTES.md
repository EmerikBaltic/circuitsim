# Learning Notes — CircuitSim

## Milestone 2 — Step 2B: Schematic Connectivity Rules, Union-Find Netlist Extraction & `QUndoStack`

In **Step 2B**, we connected the visual schematic editor to the physics engine! When you place parts and draw orthogonal wires on the canvas, **CircuitSim** extracts an electrical netlist (`CircuitScene.build_circuit()`) that feeds directly into our Modified Nodal Analysis (`MNASolver`) engine from Milestone 1.

---

### 1. Which Files to Read First (Step 2B)

1. [`src/circuitsim/canvas/connectivity.py`](src/circuitsim/canvas/connectivity.py) — **Pure Python (zero Qt imports!)**. Implements right-angle wire routing (`route_orthogonal_wire`), polyline simplification (`simplify_orthogonal_points`), attached-wire re-routing (`reroute_wires_for_updated_terminals`), and the Union-Find netlist extractor (`extract_connectivity`).
2. [`src/circuitsim/canvas/wire_item.py`](src/circuitsim/canvas/wire_item.py) — Draws orthogonal wires (`QPainterPath`) with a 10 px hit-test stroke (`QPainterPathStroker`) for easy clicking/selection and a dashed live-preview mode while routing a new wire.
3. [`src/circuitsim/canvas/commands.py`](src/circuitsim/canvas/commands.py) — Implements `QUndoCommand` classes (`AddComponentCommand`, `AddWireCommand`, `MoveComponentsCommand`, `RotateComponentsCommand`, `FlipComponentsCommand`, `DeleteItemsCommand`, `PasteItemsCommand`, `ToggleJunctionCommand`) so every edit can be undone (`Ctrl+Z`) and redone (`Ctrl+Y`).
4. [`tests/test_connectivity_and_editing.py`](tests/test_connectivity_and_editing.py) — Shows how a voltage divider and an $RC$ transient circuit built from pixel coordinates and wires produce the exact same answers as hand-built Milestone 1 circuits and analytical formulas.

---

### 2. Schematic Connectivity Rules (Step 2B)

Real schematic capture tools (like KiCad, LTspice, and Altium) follow strict rules so you never get accidental short circuits when wires cross on a crowded diagram. **CircuitSim** enforces these three core connectivity rules in [`connectivity.py`](src/circuitsim/canvas/connectivity.py):

1. **Terminals, Crossings, T-Junctions, and Explicit Junction Dots**:
   - **Terminal connection**: A wire connects to a component terminal **only if a wire endpoint sits at that terminal's exact grid coordinate** (or an explicit junction dot is placed there). A wire passing straight over a terminal without ending there does *not* connect.
   - **Crossing wires do NOT connect**: Two perpendicular wires that cross at an interior point `(x, y)` (where neither wire ends) remain electrically separate nets.
   - **T-junctions and Explicit Junction Dots DO connect**: Two wires connect if and only if:
     - They share an endpoint at `(x, y)`,
     - One wire's endpoint lands on the interior segment of another wire (forming a **T-junction**), or
     - You place an explicit **Junction Dot** (`J` key or right-click menu) at their intersection `(x, y)`.
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
4. Whenever an explicit junction dot sits at `(x, y)`, we union all wires and terminals passing through `(x, y)`.
5. After all unions finish, every disjoint set is one **electrical node (net)**:
   - Any set containing a `Ground` component's terminal is named `"0"` (the $0\text{ V}$ reference node).
   - Every other set gets a deterministic name `"N1"`, `"N2"`, ... sorted by grid position.
   - Each component is cloned into a `Circuit` with its terminal node names filled in!

---

### 4. Three Small Exercises You Can Try (Step 2B)

1. **Wire Up a Voltage Divider and Inspect Live Nets**:
   Launch `.\.venv\Scripts\python.exe -m circuitsim.main`, drag a **DC Voltage Source**, two **Resistors**, and a **Ground** onto the canvas, and drag wires between their terminals. Click each resistor and look at the **Properties / Info Panel** on the right—you will see the exact resolved net names (`Node 0`, `Node N1`, `Node N2`) for every terminal!
2. **Test Crossing Wires vs. Junction Dots (`J`)**:
   Draw two wires that cross like a `+` sign between four resistors. Click the resistors to verify the horizontal and vertical wires have *different* node names (`Node N1` vs. `Node N2`). Now move your cursor to the crossing point and press **`J`** (or right-click → **Toggle Junction Dot Here**): a junction dot appears and both wires immediately unify into the same node!
3. **Drag, Rotate (`R`), Delete (`Del`), and Undo (`Ctrl+Z`)**:
   Drag a wired resistor to a new spot on the canvas and watch its attached wires re-route at right angles in real time. Press `Del` to delete the resistor (which also removes its attached wires), then press `Ctrl+Z` to bring the resistor and all its wires right back.

---

## Milestone 2 — Step 2A: Qt Graphics View Architecture, Grid Geometry & Hybrid SVG/Procedural Symbols

1. [`src/circuitsim/canvas/symbol_geometry.py`](src/circuitsim/canvas/symbol_geometry.py) — Converts grid units (`1 grid unit = 20 px`) to pixels, transforms terminal coordinates under rotation/flip, and validates/recolours custom SVGs (`viewBox="0 0 80 40"` or centered `"-40 -20 80 40"`).
2. [`src/circuitsim/canvas/symbol_renderer.py`](src/circuitsim/canvas/symbol_renderer.py) — Renders custom SVGs when present in `resources/symbols/iec/` or procedural IEC 60617 fallback graphics via `QPainter`.

---

## Milestone 1 (Steps A & B): Modified Nodal Analysis (MNA), Companion Models & Switching Transients

1. [`src/circuitsim/dialogs/value_parser.py`](src/circuitsim/dialogs/value_parser.py) — Case-sensitive engineering notation parser (`"4.7k"`, `"15m"`, `"10M"`).
2. [`src/circuitsim/components/`](src/circuitsim/components/) & [`src/circuitsim/engine/`](src/circuitsim/engine/) — Companion models and MNA solver ($\mathbf{A}\mathbf{x} = \mathbf{b}$) using cached `scipy.linalg.lu_factor` / `lu_solve`, Backward Euler switching/arc settling, and Trapezoidal integration.
