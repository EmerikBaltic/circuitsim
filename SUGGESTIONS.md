# Suggestions & Ideas — CircuitSim

Below are improvement ideas identified during **Milestone 1 (Step A)**. None of these will be implemented without your explicit approval.

1. **Diagonal Preconditioning (Row/Column Equilibration) for Extreme Conductance Ratios** *(Effort: Small)*
   - *Reason*: Scaling rows and columns of the MNA matrix before `lu_factor` reduces the condition number when $1\text{ m}\Omega$ ammeters/switches ($10^3\text{ S}$) coexist with $1\text{ G}\Omega$ open switches ($10^{-9}\text{ S}$) and `GMIN` ($10^{-12}\text{ S}$), improving numerical headroom on larger circuits.
2. **Optional 0 V Branch-Current Mode for Ideal Ammeters** *(Effort: Small)*
   - *Reason*: While the default $1\text{ m}\Omega$ resistive ammeter works well, allowing the user to select `"Ideal (0 Ω)"` in the ammeter properties dialog (stamping it like a $0\text{ V}$ voltage source) eliminates the $10^3\text{ S}$ conductance entry from $\mathbf{G}$ and removes all voltage burden on low-impedance circuits.
3. **Thévenin Equivalent Resistance Helper (`circuit.thevenin_resistance(node_a, node_b)`)** *(Effort: Small)*
   - *Reason*: Reusing the already-factorized MNA matrix with a $1\text{ A}$ test current injection between two terminals lets us compute the exact $R_{\text{total}}$ seen by an inductor in any arbitrary resistor network for the $\tau = L / R_{\text{total}}$ display in Milestone 1 Step B and Milestone 3.
4. **Property-Based Fuzz Testing for the Value Parser** *(Effort: Small)*
   - *Reason*: Testing round-trip formatting and parsing (`parse_engineering_value(format_engineering_value(x))`) across 10 decades of values ensures the properties dialog never loses precision when displaying and re-saving values.
