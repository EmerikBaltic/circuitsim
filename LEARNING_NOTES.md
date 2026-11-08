# Learning Notes — CircuitSim

## Milestone 1 (Steps A & B): Modified Nodal Analysis (MNA), Companion Models & Switching Transients

Welcome to the core physics engine of **CircuitSim**! This guide explains how our circuit solver works in plain language and connects the Python code to the circuit analysis you already know from your electrical engineering classes.

---

### 1. Which Files to Read First

1. [`src/circuitsim/dialogs/value_parser.py`](src/circuitsim/dialogs/value_parser.py) — Small, self-contained module showing how strings like `"4.7k"` or `"15m"` are parsed into Python `float` values using regular expressions.
2. [`src/circuitsim/components/base.py`](src/circuitsim/components/base.py) & [`src/circuitsim/components/resistor.py`](src/circuitsim/components/resistor.py) — Shows how every component is represented as a pure-Python object with terminal node names (`nodes`) and live solved values (`voltage`, `current`, `power`).
3. [`src/circuitsim/components/capacitor.py`](src/circuitsim/components/capacitor.py) & [`src/circuitsim/components/inductor.py`](src/circuitsim/components/inductor.py) — Show how differential equations ($i = C\frac{dv}{dt}$ and $v = L\frac{di}{dt}$) become simple resistor-plus-current-source **companion models** at each time step.
4. [`src/circuitsim/components/switch.py`](src/circuitsim/components/switch.py) — Shows how a mechanical switch is modeled with $R_{\text{on}}$, $R_{\text{off}}$, $10\text{ pF}$ contact capacitance, and a simplified $350\text{ V}$ contact breakdown arc clamp.
5. [`src/circuitsim/engine/netlist.py`](src/circuitsim/engine/netlist.py) — Holds the `Circuit` graph, checks for breadboard mistakes using BFS and Union-Find, and computes exact Thévenin resistance (`thevenin_resistance`).
6. [`src/circuitsim/engine/solver.py`](src/circuitsim/engine/solver.py) — Builds and solves the **Modified Nodal Analysis (MNA)** matrix equation $\mathbf{A}\mathbf{x} = \mathbf{b}$ for both DC and Transient analysis.

---

### 2. Key Concepts

#### What is Modified Nodal Analysis (MNA)?
In standard **Nodal Analysis** (Kirchhoff's Current Law at every non-ground node), resistors and current sources are easy to write in matrix form:

$$\mathbf{G} \mathbf{v} = \mathbf{i}$$

where $\mathbf{v}$ is the vector of unknown node voltages. A resistor $R$ between node $a$ and node $b$ has conductance $G = 1/R$ and adds a $2 \times 2$ **stamp** into the matrix $\mathbf{G}$:
- $+G$ on the diagonals $(a, a)$ and $(b, b)$
- $-G$ on the off-diagonals $(a, b)$ and $(b, a)$

An **ideal voltage source** ($V_a - V_b = V_s$) does not have a finite conductance $G = 1/R$. **Modified Nodal Analysis (MNA)** appends each voltage source's unknown branch current $I_{V_k}$ as an extra unknown at the bottom of $\mathbf{x}$, and adds the KVL constraint equation $V_a - V_b = V_s$ as an extra row at the bottom of $\mathbf{A}$:

$$\begin{bmatrix} \mathbf{G} & \mathbf{B} \\ \mathbf{B}^T & \mathbf{D} \end{bmatrix} \begin{bmatrix} \mathbf{v} \\ \mathbf{i}_V \end{bmatrix} = \begin{bmatrix} \mathbf{i}_s \\ \mathbf{v}_s \end{bmatrix}$$

#### What is a Companion Model (Capacitors and Inductors)?
Computers cannot directly solve continuous derivatives like $i_C(t) = C \frac{dv_C}{dt}$ inside an algebraic matrix. Instead, we discretize time into small steps of size $dt = t_n - t_{n-1}$.
Using the **Trapezoidal rule** (which averages the derivative at the start and end of the step):

$$v_C(t_n) - v_C(t_{n-1}) = \frac{dt}{2C}\left(i_C(t_n) + i_C(t_{n-1})\right)$$

Rearranging for $i_C(t_n)$ gives:

$$i_C(t_n) = \underbrace{\frac{2C}{dt}}_{G_{\text{eq}}} v_C(t_n) - \underbrace{\left(\frac{2C}{dt} v_C(t_{n-1}) + i_C(t_{n-1})\right)}_{I_{\text{eq}}}$$

At step $t_n$, the capacitor looks *identical* to a resistor of conductance $G_{\text{eq}} = \frac{2C}{dt}$ in parallel with a known DC current source $I_{\text{eq}}$ computed from the previous step! That equivalent circuit is called a **companion model**.

#### Why Use Trapezoidal Most of the Time, but Backward Euler After Switching?
- **Trapezoidal integration** is second-order accurate ($\mathcal{O}(dt^2)$—halving $dt$ cuts the error by $4\times$) and preserves energy in lossless $LC$ circuits without artificial damping.
- However, if a switch closes abruptly and charges a capacitor in a single step ($dt \gg R_{\text{on}}C$), $v_C$ jumps to a constant value while $i_C(t_n)$ has a huge charging spike. On the next step, $v_C(t_{n+1}) = v_C(t_n)$, so Trapezoidal's equation $0 = i_C(t_{n+1}) + i_C(t_n)$ forces $i_C(t_{n+1}) = -i_C(t_n)$! The current bounces back and forth ($\pm I$) forever—this is called **Trapezoidal numerical ringing**.
- **Backward Euler** ($i_C(t_n) = \frac{C}{dt}(v_C(t_n) - v_C(t_{n-1}))$) does not depend on $i_C(t_{n-1})$. Using Backward Euler on the first step and right after any switch or arc state change damps out the discontinuous impulse cleanly before handing back to Trapezoidal integration.

#### Simplified Switch Contact Breakdown / Arc Model
When you open a switch in series with a current-carrying inductor, the inductor tries to keep current flowing ($v_L = L \frac{di}{dt}$). With an ideal contact and $10\text{ pF}$ capacitance, interrupting $1\text{ A}$ in a $10\text{ mH}$ inductor would ring up to $V_{\text{peak}} = I_0\sqrt{L/C_p} \approx 31.6\text{ kV}$!
In reality, air across a small opening contact gap breaks down at roughly **$350\text{ V}$** (Paschen's law) and forms a plasma arc. In `Switch`, we model this with a **simplified piecewise-linear arc clamp**:
- When the switch is open and $|V_{\text{sw}}| > V_{\text{breakdown}}$ (default $350\text{ V}$), the arc ignites and acts as a $350\text{ V}$ opposing source in series with $R_{\text{arc}} = 1\text{ }\Omega$, clamping the voltage spike near $350\text{ V}$ while converting the inductor's magnetic energy ($\frac{1}{2}LI_0^2$) into heat in the arc.
- Once the inductor current decays below the holding threshold ($I_{\text{hold}} = 1\text{ mA}$), the plasma can no longer sustain itself, so the arc extinguishes and the switch returns to $1\text{ G}\Omega$. (Real physical arcs have a time-varying gap length and negative dynamic resistance, so this constant-voltage clamp is a simplified educational model; you can also set `v_breakdown=None` on a `Switch` to observe the ideal unclamped $LC_p$ spike.)

---

### 3. Three Small Exercises You Can Try

1. **Change the AC Frequency and Check $X_L$**:
   In [`src/circuitsim/main.py`](src/circuitsim/main.py), change the `ACVoltageSource` frequency from `1000.0` (1 kHz) to `2000.0` (2 kHz) and run `.\.venv\Scripts\python.exe -m circuitsim.main`. Notice how $X_L = 2\pi f L$ doubles from $62.83\text{ }\Omega$ to $125.66\text{ }\Omega$, while the AC RMS voltmeter across the source reads a rock-solid `7.071 V` ($10 / \sqrt{2}$).
2. **Compare Clamped vs. Unclamped Inductive Kickback**:
   Open [`tests/test_transient_and_reactive.py`](tests/test_transient_and_reactive.py) and compare `test_inductive_kickback_clamped_by_contact_breakdown_arc` (`v_breakdown=350.0`, which clamps at $351\text{ V}$ and dissipates $50\text{ mJ}$) against `test_inductive_kickback_unclamped_when_v_breakdown_disabled` (`v_breakdown=None`, which spikes past $30\text{ kV}$).
3. **Explore RLC Resonance**:
   In `test_series_rlc_resonance_analytical`, try changing the resistor from $10\text{ }\Omega$ to $2\text{ }\Omega$ (increasing the quality factor $Q = \frac{1}{R}\sqrt{\frac{L}{C}}$ by $5\times$) and see how much sharper the resonance current peak becomes at $f_0 = \frac{1}{2\pi\sqrt{LC}}$.
