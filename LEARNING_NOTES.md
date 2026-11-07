# Learning Notes — CircuitSim

## Milestone 1 (Step A): Modified Nodal Analysis (MNA) & Component Stamps

Welcome to the core physics engine of **CircuitSim**! This guide explains how our circuit solver works in plain language and connects the Python code to the circuit analysis you already know from your electrical engineering classes.

---

### 1. Which Files to Read First

1. [`src/circuitsim/dialogs/value_parser.py`](src/circuitsim/dialogs/value_parser.py) — Small, self-contained module showing how strings like `"4.7k"` or `"15m"` are parsed into Python `float` values using regular expressions.
2. [`src/circuitsim/components/base.py`](src/circuitsim/components/base.py) & [`src/circuitsim/components/resistor.py`](src/circuitsim/components/resistor.py) — Shows how every component is represented as a pure-Python object with terminal node names (`nodes`) and live solved values (`voltage`, `current`, `power`).
3. [`src/circuitsim/components/lightbulb.py`](src/circuitsim/components/lightbulb.py) — Implements $R_{\text{hot}} = V_{\text{rated}}^2 / P_{\text{rated}}$ and the optional thermal filament differential equation.
4. [`src/circuitsim/engine/netlist.py`](src/circuitsim/engine/netlist.py) — Holds the `Circuit` graph and checks for common breadboard mistakes (forgot ground, floating wire, shorted voltage sources, or an ammeter placed directly across a battery) using Breadth-First Search (BFS) and Union-Find.
5. [`src/circuitsim/engine/solver.py`](src/circuitsim/engine/solver.py) — Builds and solves the **Modified Nodal Analysis (MNA)** matrix equation $\mathbf{A}\mathbf{x} = \mathbf{b}$.

---

### 2. Key Concepts

#### What is Modified Nodal Analysis (MNA)?
In standard **Nodal Analysis** (Kirchhoff's Current Law at every non-ground node), resistors and current sources are easy to write in matrix form:

$$\mathbf{G} \mathbf{v} = \mathbf{i}$$

where $\mathbf{v}$ is the vector of unknown node voltages. A resistor $R$ between node $a$ and node $b$ has conductance $G = 1/R$ and adds a $2 \times 2$ **stamp** into the matrix $\mathbf{G}$:
- $+G$ on the diagonals $(a, a)$ and $(b, b)$
- $-G$ on the off-diagonals $(a, b)$ and $(b, a)$

However, an **ideal voltage source** ($V_a - V_b = V_s$) does not have a finite conductance $G = 1/R$! **Modified Nodal Analysis (MNA)** solves this by appending each voltage source's unknown branch current $I_{V_k}$ as an extra unknown at the bottom of the vector $\mathbf{x}$, and adding the KVL constraint equation $V_a - V_b = V_s$ as an extra row at the bottom of the matrix $\mathbf{A}$:

$$\begin{bmatrix} \mathbf{G} & \mathbf{B} \\ \mathbf{B}^T & \mathbf{D} \end{bmatrix} \begin{bmatrix} \mathbf{v} \\ \mathbf{i}_V \end{bmatrix} = \begin{bmatrix} \mathbf{i}_s \\ \mathbf{v}_s \end{bmatrix}$$

#### Why Do We Add `GMIN` ($10^{-12}\text{ S}$)?
A conductance of $10^{-12}\text{ S}$ is equivalent to a $1\text{ T}\Omega$ ($10^{12}\text{ }\Omega$) resistor from every node to ground. In normal circuits ($1\text{ }\Omega$ to $10\text{ M}\Omega$), $1\text{ T}\Omega$ draws only picoamps of current, which is completely negligible. However, if a sub-circuit is isolated behind open switches or capacitors, `GMIN` prevents a row of zeros in the matrix (which would cause a `SingularMatrixError` division by zero during LU elimination).

#### Why Do We Cache the LU Factorization (`scipy.linalg.lu_factor`)?
Solving an $N \times N$ linear system from scratch using Gaussian elimination (LU decomposition) takes $\mathcal{O}(N^3)$ operations. Once we factorize $\mathbf{A} = \mathbf{P}\mathbf{L}\mathbf{U}$, solving for a new right-hand-side vector $\mathbf{b}$ (for example, when an input source voltage changes) only requires forward and backward substitution, which takes $\mathcal{O}(N^2)$ operations. Our solver tracks a conductance signature and only re-runs `lu_factor` when a component's conductance or switch state actually changes.

---

### 3. Three Small Exercises You Can Try

1. **Test a Different Lightbulb Rating**:
   Open [`src/circuitsim/main.py`](src/circuitsim/main.py) and change the lightbulb from `rated_power=60.0` to `rated_power=100.0` (a 100 W / 120 V bulb). Before running `.\.venv\Scripts\python.exe -m circuitsim.main`, calculate $R_{\text{hot}} = 120^2 / 100$ by hand, then run the script to see if the printed resistance matches your calculation.
2. **Observe Voltmeter Loading on a High-Impedance Divider**:
   In a test or in `main.py`, build a voltage divider using two $10\text{ M}\Omega$ resistors connected to a $10\text{ V}$ source. With no voltmeter attached, the midpoint is $5.0\text{ V}$. Now attach a `Voltmeter` (which has a real $10\text{ M}\Omega$ internal resistance!) from the midpoint to ground. Why does the midpoint voltage drop to $3.333\text{ V}$?
3. **Trigger a Circuit Error Intentionally**:
   In `main.py`, comment out `circuit.add(Ground("GND", "0"))` and run the demo. Observe how `validate_topology()` catches the missing reference node and raises `NoGroundError: No ground connected` before any matrix math is attempted.
