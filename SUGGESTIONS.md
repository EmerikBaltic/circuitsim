# Suggestions & Ideas — CircuitSim

Below are improvement ideas identified during **Milestones 1 & 2**. None of these will be implemented without your explicit approval.

1. **Symbol Style Setting (IEC / ANSI)** *(Effort: Small)*
   - *Reason*: Since schematic symbols are stored under `src/circuitsim/resources/symbols/iec/`, adding a parallel `ansi/` folder (zigzag resistor, curved capacitor, etc.) and a Preferences toggle lets students switch between European (IEC 60617) and North American (ANSI/IEEE) schematic conventions at any time.
2. **Analysis Tutor (Thévenin / Norton Step-by-Step)** *(Effort: Medium)*
   - *Reason*: We already compute exact $R_{\text{thevenin}}$ and $V_{\text{oc}}$ in the engine; wrapping this into an interactive "Analysis Tutor" dialog that highlights the two chosen terminals, shows the circuit with independent sources zeroed, and displays the step-by-step $V_{\text{th}}$, $R_{\text{th}}$, and $I_{\text{N}}$ derivation would be a great study tool for second-year EE courses.
3. **Adaptive Time-Step Control via Local Truncation Error (LTE)** *(Effort: Medium)*
   - *Reason*: While our fixed-$dt$ solver with LU caching is very fast, adding an optional LTE step-size shrink/grow controller around switching transients would automatically resolve sub-microsecond events even when the user runs at a slow oscilloscope timebase.
4. **Diagonal Preconditioning (Row/Column Equilibration) for Extreme Conductance Ratios** *(Effort: Small)*
   - *Reason*: Scaling rows and columns of the MNA matrix before `lu_factor` reduces the condition number when $1\text{ m}\Omega$ ammeters/switches ($10^3\text{ S}$) coexist with $1\text{ G}\Omega$ open switches ($10^{-9}\text{ S}$) and `GMIN` ($10^{-12}\text{ S}$), improving numerical headroom on larger circuits.
5. **Optional 0 V Branch-Current Mode for Ideal Ammeters** *(Effort: Small)*
   - *Reason*: Allowing the user to select `"Ideal (0 Ω)"` in the ammeter properties dialog (stamping it like a $0\text{ V}$ voltage source) eliminates the $10^3\text{ S}$ conductance entry from $\mathbf{G}$ and removes all voltage burden on low-impedance circuits.
6. **GitHub Actions CI Running `pytest` on Every Push + README Status Badge** *(Effort: Small)*
   - *Reason*: Adding a `.github/workflows/ci.yml` workflow that runs `pytest` on every push and pull request (setting `QT_QPA_PLATFORM=offscreen` for the headless Qt subprocess tests) and displaying a green status badge in `README.md` gives immediate confidence that every commit passes on a clean machine.
7. **Number-Format / Locale Display Setting (Dot vs. Comma Decimal)** *(Effort: Small)*
   - *Reason*: While the input parser already accepts both `"5.65 G"` and `"5,65 G"`, adding a Preferences option to format *displayed* values on the canvas and in dialogs with either a decimal dot (`4.7 kΩ`) or a decimal comma (`4,7 kΩ`) would make the UI feel native in Croatian and other European locales.
8. **Startup Self-Check for Stale or Missing Symbol Metadata / SVG Files** *(Effort: Small)*
   - *Reason*: Running a fast check on startup that verifies all 11 built-in IEC symbol `.json` definitions exist, match the expected terminal grid footprints, and log a non-blocking banner if a user-edited `.svg` file has syntax or viewBox mismatches makes custom symbol authoring easier to debug.
9. **Optional Bulb Burn-Out When Overloaded for Too Long** *(Effort: Small)*
   - *Reason*: `Lightbulb` already has `burnout_enabled`, `burnout_power_ratio` and `burnout_time` in the engine; exposing them in the properties dialog (off by default) would let students see a bulb fail at e.g. 120% power for 0.5 s.
10. **Check Spacing Between a Source's Selection Box and the Ground Label (GND2)** *(Done in Item 4)*
    - *Resolution*: Ground label placement adjusted below the earth bars (`label_offset[1] >= 0`), providing 30 px clearance and ensuring Voltage Source selection outline never touches `GND2` label.
11. **Recent Files List in the File Menu** *(Effort: Small)*
    - *Reason*: Reopening the last few `.circ` files with one click is the first thing students will want once they have more than two saved circuits.
12. **Saved Parts / Favourites** *(Effort: Medium)*
    - *Note*: saved parts / favourites, redesign later if users ask for it. Digit keys are no longer reserved for it.
13. **Mark a Switch Click as an Unsaved Change** *(Done in Item 4)*
    - *Resolution*: Toggling a switch on the canvas now marks the document modified (`has_unsaved_changes() = True`, window title asterisk `*`), but does not push to `QUndoStack` (not undoable). Saving clears the modified state.

---

## Planned order

The recommended sequence for future work on CircuitSim:

1. **Step 4: Canvas Integration of Explicit Wiring Model (`WireGraph` + `WireItem` + `JunctionItem`)**
   - *Why first*: This is the core architectural prerequisite to eliminate coordinate-based connectivity bugs, short circuits on rotation, and detour heuristics. Steps 1 to 3 are complete and tested in pure Python; Step 4 connects them to the user-facing canvas.
2. **Recent Files List in the File Menu (Item 11)**
   - *Why second*: High-value, low-effort usability feature. Once users have save/load working, easily reopening recent `.circ` projects makes working with multiple circuits seamless.
3. **Properties Dialog (Step 3C) & Analysis Tutor (Item 2)**
   - *Why third*: Completes Milestone 3 by exposing secondary component settings (e.g., initial switch state, AC waveform types, capacitor initial voltage) and provides an interactive educational tool for student circuit analysis.
4. **GitHub Actions CI (Item 6)**
   - *Why fourth*: Automates running `pytest` (headless offscreen) on every push and pull request, protecting code quality and preventing regressions on clean machines.

---

## Defer until a real problem appears

Items to deliberately postpone until an actual practical problem arises:

1. **Saved Parts / Favourites (Item 12)**
   - *Reason to defer*: Cancelled by design decision after testing; digit keys are unreserved. Only revisit if users explicitly demand a redesigned favourite parts palette.
2. **Diagonal Preconditioning (Item 4)**
   - *Reason to defer*: Current circuits (tens of components) solve with condition numbers well within SciPy's standard LU factorization limits. Defer until large benchmarks (>500 nodes) show numerical degradation.
3. **Adaptive Time-Step Control via LTE (Item 3)**
   - *Reason to defer*: Fixed-$dt$ with Trapezoidal integration and Backward Euler switching settling is deterministic, robust, and fast. Defer until high-frequency oscillator or chaotic circuit simulations show stepping artifacts.
4. **Symbol Style Setting (IEC / ANSI) (Item 1)**
   - *Reason to defer*: IEC 60617 symbols are already complete, clean, and unambiguous. Maintaining dual SVG/procedural symbol catalogs doubles asset and test maintenance overhead without adding simulation functionality.
5. **0 V Branch-Current Mode for Ideal Ammeters (Item 5)**
   - *Reason to defer*: The current $1\text{ m}\Omega$ ammeter companion model introduces negligible burden voltage in standard student circuits. Defer until ultra-low-impedance circuits require exact zero-burden current sensing.
