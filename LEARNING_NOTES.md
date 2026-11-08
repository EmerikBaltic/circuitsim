# Learning Notes — CircuitSim

## Milestone 2 — Step 2A: Qt Graphics View Architecture, Grid Geometry & Hybrid SVG/Procedural Symbols

In **Step 2A**, we built the visual foundation of **CircuitSim**: the dockable `QMainWindow`, the searchable component palette, the hybrid SVG + procedural IEC 60617 symbol renderer, and the interactive schematic canvas (`QGraphicsScene` + `QGraphicsView`).

---

### 1. Which Files to Read First (Step 2A)

1. [`src/circuitsim/canvas/symbol_geometry.py`](src/circuitsim/canvas/symbol_geometry.py) — Pure Python (no Qt imports!). Shows how grid coordinates (`1 grid unit = 20 px`) are converted to pixels, how terminal positions transform when a component is rotated or flipped, and how SVG files are validated and recoloured using Python's built-in `xml.etree.ElementTree`.
2. [`src/circuitsim/resources/symbols/iec/resistor.json`](src/circuitsim/resources/symbols/iec/resistor.json) & [`switch.json`](src/circuitsim/resources/symbols/iec/switch.json) — Small JSON files declaring each component's grid size (`[4, 2]`), terminal coordinates (`[-2, 0]` and `[2, 0]`), and visual states (`open`, `closed`).
3. [`src/circuitsim/canvas/symbol_renderer.py`](src/circuitsim/canvas/symbol_renderer.py) — The `SymbolLibrary` class that checks if a custom `.svg` file exists in `resources/symbols/iec/`; if so, it renders the recoloured SVG with `QSvgRenderer`, and if not, it draws the IEC 60617 symbol procedurally using `QPainter`.
4. [`src/circuitsim/canvas/component_item.py`](src/circuitsim/canvas/component_item.py) — Represents a placed component on the schematic (`QGraphicsObject`), handling 20 px grid snapping in `itemChange`, 90° rotation (`R`), horizontal flip (`F`), and reference/value labels (`R1`, `1 kΩ`).
5. [`src/circuitsim/canvas/scene.py`](src/circuitsim/canvas/scene.py) & [`src/circuitsim/canvas/view.py`](src/circuitsim/canvas/view.py) — The `QGraphicsScene` (draws the 20 px minor / 100 px major background grid and manages the translucent ghost preview) and `QGraphicsView` (handles cursor-centered mouse-wheel zoom, middle-click or `Space`+drag panning, and palette drag-and-drop).
6. [`src/circuitsim/app/main_window.py`](src/circuitsim/app/main_window.py) — Assembles the dockable panels (`QDockWidget`), toolbars, status bar, and Dark/Light theme switching.

---

### 2. Key Concepts in Step 2A

#### How `QGraphicsScene`, `QGraphicsView`, and `QGraphicsObject` Work Together
Qt's Graphics View framework separates **what** is in the schematic from **how** you look at it:
- **`CircuitScene` (`QGraphicsScene`)** is the infinite 2D world in **scene coordinates** (where $1\text{ grid unit} = 20\text{ px}$). A resistor placed at `(100, 60)` stays at `(100, 60)` in scene coordinates regardless of how far you zoom or pan.
- **`CircuitView` (`QGraphicsView`)** is the camera window looking at the scene. When you roll the mouse wheel, `CircuitView` calls `self.scale(factor, factor)` with `AnchorUnderMouse`, which zooms smoothly around the exact point under your cursor without modifying any component's scene coordinates.
- **`ComponentItem` (`QGraphicsObject`)** lives inside the scene and has its own **local item coordinates** centered at `(0, 0)`. For a `4x2` component (`80x40 px`), its local bounding box spans $x \in [-40, +40]$ and $y \in [-20, +20]$, with terminals at `(-40, 0)` and `(+40, 0)`.

#### Supporting Both `viewBox="0 0 80 40"` and Centered Coordinates
When you draw a symbol in Inkscape or Figma on an $80 \times 40\text{ px}$ canvas, the tool exports `viewBox="0 0 80 40"` where the top-left corner is `(0, 0)`, the center is `(40, 20)`, and the left/right terminals sit at `(0, 20)` and `(80, 20)`.
Meanwhile, `ComponentItem` rotates around its center `(0, 0)`, so it always passes the centered target rectangle `QRectF(-40, -20, 80, 40)` to `QSvgRenderer.render(painter, target_rect)`. Because `QSvgRenderer` automatically maps the SVG's `viewBox` onto `target_rect`:
- Point `(0, 20)` in `viewBox="0 0 80 40"` maps to `(-40, 0)` in item coordinates (Terminal `a`).
- Point `(80, 20)` in `viewBox="0 0 80 40"` maps to `(+40, 0)` in item coordinates (Terminal `b`).
Both `viewBox="0 0 80 40"` and `viewBox="-40 -20 80 40"` therefore land on the exact same grid terminals!

#### Terminal Math Under Flip and Rotation
To keep terminal positions testable without opening a Qt window, `transform_terminal_px` in [`symbol_geometry.py`](src/circuitsim/canvas/symbol_geometry.py) applies the exact same two-step transform as `ComponentItem._apply_transform`:
1. **Horizontal Flip (`flipped=True`)**: Negate local $x$: $(x_1, y_1) = (-x_0, y_0)$.
2. **Clockwise Rotation (`rotation_deg` in `{0, 90, 180, 270}`)**:
   - $0^\circ$: $(x_1, y_1)$
   - $90^\circ$ CW (in screen coordinates where $+y$ points down): $(-y_1, x_1)$
   - $180^\circ$: $(-x_1, -y_1)$
   - $270^\circ$ CW: $(y_1, -x_1)$

Because every terminal starts on an integer grid coordinate and is rotated by multiples of $90^\circ$ around a grid-snapped center, **every terminal is guaranteed to land on an exact multiple of $20\text{ px}$** after any combination of rotations and flips.

---

### 3. Three Small Exercises You Can Try (Step 2A)

1. **Inspect All Symbols and Terminal Dots**:
   Run `.\.venv\Scripts\python.exe -m circuitsim.tools.symbol_preview` and compare the Dark and Light theme columns. Notice how every red/orange terminal dot sits on a 20 px grid intersection.
2. **Test Custom SVG Hot-Loading**:
   Create a simple file `src/circuitsim/resources/symbols/iec/resistor.svg` with `viewBox="0 0 80 40"` and a `#000000` stroke path from `(0, 20)` to `(80, 20)`, then re-run `python -m circuitsim.tools.symbol_preview`. Its subtitle will automatically change from `[procedural IEC]` to `[SVG file]` and recolour in both themes!
3. **Break an SVG on Purpose to See the Tolerant Fallback**:
   Change `viewBox="0 0 80 40"` in your test `resistor.svg` to `viewBox="0 0 999 999"` and run the preview tool. You will see a clear warning explaining the dimension mismatch while the app stays up and falls back to the procedural IEC resistor.

---

## Milestone 1 (Steps A & B): Modified Nodal Analysis (MNA), Companion Models & Switching Transients

### 1. Core Engine Files
1. [`src/circuitsim/dialogs/value_parser.py`](src/circuitsim/dialogs/value_parser.py) — Parses engineering strings (`"4.7k"`, `"15m"`) into Python `float` values.
2. [`src/circuitsim/components/capacitor.py`](src/circuitsim/components/capacitor.py) & [`src/circuitsim/components/inductor.py`](src/circuitsim/components/inductor.py) — Discretize $i = C\frac{dv}{dt}$ and $v = L\frac{di}{dt}$ into companion models ($G_{\text{eq}}$ in parallel with $I_{\text{eq}}$).
3. [`src/circuitsim/components/switch.py`](src/circuitsim/components/switch.py) — Models a switch with $R_{\text{on}}$, $R_{\text{off}}$, $10\text{ pF}$ contact capacitance, and a simplified $350\text{ V}$ contact breakdown arc clamp.
4. [`src/circuitsim/engine/netlist.py`](src/circuitsim/engine/netlist.py) & [`src/circuitsim/engine/solver.py`](src/circuitsim/engine/solver.py) — Builds and solves the MNA matrix equation $\mathbf{A}\mathbf{x} = \mathbf{b}$ using cached `scipy.linalg.lu_factor` / `lu_solve`, using Backward Euler after switch/arc events and Trapezoidal integration on normal steps.
