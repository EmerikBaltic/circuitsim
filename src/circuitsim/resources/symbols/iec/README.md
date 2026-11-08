# IEC Schematic Symbols (`src/circuitsim/resources/symbols/iec/`)

This directory holds **IEC 60617** schematic symbols (e.g., rectangular resistor) and their terminal metadata JSON files. A sibling folder (`ansi/`) can be added later to support switching between IEC and ANSI symbol sets.

## Coordinate & Grid Convention

- **Canvas Grid Pitch**: `1 grid unit = 20 px`.
- **Standard 2-Terminal Component Footprint**: `4 x 2 grid units` (`80 x 40 px`), centered at `(0, 0)` in local item coordinates (`viewBox="-40 -20 80 40"` or `0 0 80 40` with `"origin": [40, 20]`).
  - Left terminal (`"a"` or `"pos"`): `[-2, 0]` in grid units (`(-40, 0)` px).
  - Right terminal (`"b"` or `"neg"`): `[2, 0]` in grid units (`(+40, 0)` px).
- **1-Terminal Ground Footprint**: `2 x 2 grid units` (`40 x 40 px`), with terminal `"gnd"` at `[0, -1]` grid units (`(0, -20)` px).

## File Naming Rules

Each component `component_type` has a `.json` metadata file and one or more `.svg` files in this folder:

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

When an `.svg` file is not present yet, CircuitSim automatically falls back to its built-in procedural IEC painter using the same grid geometry.

## Theme Recolouring Rule for SVGs

Use `currentColor` or `#FFFFFF` / `#000000` for strokes in your SVGs. Before rendering, CircuitSim replaces `"currentColor"` (and monochrome stroke placeholders) with the active theme's foreground stroke color (e.g., `#E0E6ED` in Dark Theme, `#1E242B` in Light Theme).
