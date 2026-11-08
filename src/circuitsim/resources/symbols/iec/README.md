# IEC Schematic Symbols (`src/circuitsim/resources/symbols/iec/`)

This directory holds **IEC 60617** schematic symbols (e.g., rectangular resistor) and their terminal metadata JSON files. A sibling folder (`ansi/`) can be added later to support switching between IEC and ANSI symbol sets.

## Coordinate, `viewBox`, and Grid Rules for Drawing Your Own SVGs

- **Canvas Grid Pitch**: `1 grid unit = 20 px`.
- **Standard 2-Terminal Component (`4 x 2` grid units = `80 x 40 px`)**:
  - **Recommended SVG `viewBox`**: `viewBox="0 0 80 40"` (with `width="80" height="40"`).
    - Left terminal (`"a"` or `"pos"`): **`x="0" y="20"`** (maps to `[-2, 0]` grid units from component center).
    - Right terminal (`"b"` or `"neg"`): **`x="80" y="20"`** (maps to `[+2, 0]` grid units from component center).
    - Component center: **`x="40" y="20"`**.
    - Lead stubs typically run from `(0, 20)` to `(20, 20)` on the left, and `(60, 20)` to `(80, 20)` on the right, leaving the central `40 x 40 px` area (`x` in `[20, 60]`) for the symbol body.
  - *(Centered `viewBox="-40 -20 80 40"` is also accepted automatically.)*
- **1-Terminal Ground Component (`2 x 2` grid units = `40 x 40 px`)**:
  - **Recommended SVG `viewBox`**: `viewBox="0 0 40 40"` (with `width="40" height="40"`).
    - Top terminal (`"gnd"`): **`x="20" y="0"`** (maps to `[0, -1]` grid units from component center `(20, 20)`).
  - *(Centered `viewBox="-20 -20 40 40"` is also accepted automatically.)*

## Stroke, Fill, and Theme Recolouring Rules

1. Draw with **pure black strokes (`stroke="#000000"` or `stroke="currentColor"`)**, **`stroke-width="2"`**, **`fill="none"`**, and **no `<text>` elements** (labels and values are positioned and rendered dynamically by the canvas using `label_offset` and `value_offset` from the JSON file).
2. The SVG loader is tolerant of Inkscape/Figma/Sodipodi exports:
   - It automatically strips `<metadata>`, `<sodipodi:namedview>`, `<defs>` editor cruft, and any full-artboard background `<rect>` covering the entire `80x40` (or `40x40`) canvas.
   - It recolours `#000000`, `black`, `rgb(0,0,0)`, and `currentColor` to the active theme's foreground color (`#E6EDF3` in Dark Theme, `#1F2328` in Light Theme).
   - If an SVG file has malformed XML or its `viewBox` dimensions do not match `grid_size * 20`, CircuitSim logs a clear warning and falls back to the built-in procedural IEC symbol without crashing.

## Previewing Your Symbols

Run the symbol preview tool at any time to inspect all symbols in both Dark and Light themes with the 20 px grid and terminal dots overlaid:

```powershell
.\.venv\Scripts\python.exe -m circuitsim.tools.symbol_preview
```

## File Naming Table

| `component_type` | Metadata File       | Default SVG File    | State SVG Files (if stateful)                      |
|------------------|---------------------|---------------------|----------------------------------------------------|
| `resistor`       | `resistor.json`     | `resistor.svg`      | —                                                  |
| `capacitor`      | `capacitor.json`    | `capacitor.svg`     | —                                                  |
| `inductor`       | `inductor.json`     | `inductor.svg`      | —                                                  |
| `dc_voltage`     | `dc_voltage.json`   | `dc_voltage.svg`    | —                                                  |
| `ac_voltage`     | `ac_voltage.json`   | `ac_voltage.svg`    | —                                                  |
| `dc_current`     | `dc_current.json`   | `dc_current.svg`    | —                                                  |
| `ground`         | `ground.json`       | `ground.svg`        | —                                                  |
| `switch`         | `switch.json`       | `switch_open.svg`   | `switch_open.svg`, `switch_closed.svg`             |
| `lightbulb`      | `lightbulb.json`    | `lightbulb.svg`     | —                                                  |
| `voltmeter`      | `voltmeter.json`    | `voltmeter.svg`     | —                                                  |
| `ammeter`        | `ammeter.json`      | `ammeter.svg`       | —                                                  |
