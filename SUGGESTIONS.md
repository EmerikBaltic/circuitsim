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
10. **Check Spacing Between a Source's Selection Box and the Ground Label (GND2)** *(Effort: Small)*
    - *Reason*: In testing, the selection box of a voltage source touches the ground label (`GND2`); label placement near the `Ground` symbol needs a quick geometry check like the one done for value labels.
11. **Recent Files List in the File Menu** *(Effort: Small)*
    - *Reason*: Reopening the last few `.circ` files with one click is the first thing students will want once they have more than two saved circuits.
12. **Saved Parts / Favourites** *(Effort: Medium)*
    - *Note*: saved parts / favourites, redesign later if users ask for it. Digit keys are no longer reserved for it.
13. **Mark a Switch Click as an Unsaved Change** *(Effort: Small)*
    - *Reason*: Clicking a switch on the canvas changes the saved state but is not on the undo stack, so the title asterisk does not appear. Making it an undoable action fixes both.
