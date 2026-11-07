# Suggestions & Ideas — CircuitSim

Below are improvement ideas identified during **Milestone 1 (Steps A & B)**. None of these will be implemented without your explicit approval.

1. **Switch Contact Arc / Breakdown Clamp for Inductive Kickback** *(Effort: Small)*
   - *Reason*: Interrupting $1\text{ A}$ in a $10\text{ mH}$ inductor into a $10\text{ pF}$ switch contact capacitance produces a theoretical lossless LC peak of $V_{\text{peak}} = I_0\sqrt{L/C_p} \approx 31.6\text{ kV}$ with a $2\text{ }\mu\text{s}$ ringing period. Adding an optional breakdown/arc clamp across the switch contacts (e.g., clamping above $V_{\text{arc}} \approx 300\text{ V}$–$1000\text{ V}$ as a conductive arc path) models real air-gap contact arcing and prevents multi-kilovolt spikes from dominating oscilloscope auto-scaling.
2. **Adaptive Time-Step Control via Local Truncation Error (LTE)** *(Effort: Medium)*
   - *Reason*: While our fixed-$dt$ solver with LU caching is very fast, adding an optional LTE step-size shrink/grow controller around switching transients would automatically resolve sub-microsecond inductive kickback spikes even when the user runs at a slow oscilloscope timebase.
3. **Diagonal Preconditioning (Row/Column Equilibration) for Extreme Conductance Ratios** *(Effort: Small)*
   - *Reason*: Scaling rows and columns of the MNA matrix before `lu_factor` reduces the condition number when $1\text{ m}\Omega$ ammeters/switches ($10^3\text{ S}$) coexist with $1\text{ G}\Omega$ open switches ($10^{-9}\text{ S}$) and `GMIN` ($10^{-12}\text{ S}$), improving numerical headroom on larger circuits.
4. **Optional 0 V Branch-Current Mode for Ideal Ammeters** *(Effort: Small)*
   - *Reason*: Allowing the user to select `"Ideal (0 Ω)"` in the ammeter properties dialog (stamping it like a $0\text{ V}$ voltage source) eliminates the $10^3\text{ S}$ conductance entry from $\mathbf{G}$ and removes all voltage burden on low-impedance circuits.
5. **Property-Based Fuzz Testing for the Value Parser** *(Effort: Small)*
   - *Reason*: Testing round-trip formatting and parsing (`parse_engineering_value(format_engineering_value(x))`) across 10 decades of values ensures the properties dialog never loses precision when displaying and re-saving values.
