# Suggestions & Ideas — CircuitSim

Below are improvement ideas identified during **Milestone 1**. None of these will be implemented without your explicit approval.

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
