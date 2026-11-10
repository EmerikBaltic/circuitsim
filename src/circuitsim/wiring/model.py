"""Explicit wiring model: wires attach to terminals and junctions, never to coordinates.

This module has NO Qt imports. It is the replacement for the geometric rule
"two wire ends that happen to sit on the same point are connected".

Concepts
--------
* A **wire** has two ends. Each end is an *attachment*:
  - `TerminalRef(component, terminal)`: glued to a part's terminal,
  - `JunctionRef(id)`: glued to a junction object,
  - `FreeEnd(x, y)`: connected to NOTHING (drawn later with a hollow marker).
* A **junction** is an object with an id and a grid position. Junctions are only
  ever created explicitly (placed by the user, or by splitting a wire).
* Electrical connectivity is decided only by which attachments a wire joins
  (see `circuitsim.wiring.netlist`). Positions play no part: crossing or
  overlapping wires never connect, and moving things never changes connectivity.

Immutability
------------
`WireGraph` is a frozen dataclass. Every operation returns a NEW graph and leaves
the old one untouched, so undo/redo can simply keep a list of graphs and swap them.
Graphs are tiny (tens of wires), so copying the tuples is cheap and much easier to
reason about than in-place editing.

Ids
---
New ids are the lowest unused number (`W1`, `W2`, ... / `J1`, `J2`, ...), just like
component names. They are a pure function of the current graph (no hidden counter),
so the same sequence of operations always produces the same ids.

Merge rules (run automatically after an operation REMOVES a wire from a junction)
-------------------------------------------------------------------------------
* junction left with 2 wires -> the 2 wires become ONE wire; the junction position
  is kept as a waypoint hint so the drawing does not jump,
* junction left with 1 wire  -> junction removed, that wire end becomes a `FreeEnd`
  at the junction position,
* junction left with 0 wires -> junction deleted,
* wires with the same two attachments are deduplicated, and a wire whose two
  ends would be identical is dropped; either can lower a junction's wire count,
  so the rules repeat until nothing changes.

A junction that was just placed or created by a split is NOT merged at that moment
(otherwise "place a junction, then attach the third wire" could never work). The
rules only look at junctions that lost a wire.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import NamedTuple, Union

GRID_PX: int = 20
PointPx = tuple[int, int]


def snap_px(pt: tuple[float, float]) -> PointPx:
    """Round a point to the nearest 20 px grid intersection (integer result)."""
    return (int(round(pt[0] / GRID_PX)) * GRID_PX, int(round(pt[1] / GRID_PX)) * GRID_PX)


class WireGraphError(ValueError):
    """Raised when an operation or a graph is not valid (message is plain language)."""


@dataclass(frozen=True)
class TerminalRef:
    """Wire end glued to one terminal of one component."""

    component: str
    terminal: str


@dataclass(frozen=True)
class JunctionRef:
    """Wire end glued to a junction object."""

    id: str


@dataclass(frozen=True)
class FreeEnd:
    """Wire end that is connected to nothing. Position is snapped to the grid."""

    x: int
    y: int

    def __post_init__(self) -> None:
        sx, sy = snap_px((self.x, self.y))
        object.__setattr__(self, "x", sx)
        object.__setattr__(self, "y", sy)

    @property
    def pos(self) -> PointPx:
        return (self.x, self.y)


Attachment = Union[TerminalRef, JunctionRef, FreeEnd]


@dataclass(frozen=True)
class Wire:
    """A wire between two attachments.

    `hints` are optional waypoints (ordered from `end_a` to `end_b`). They only
    suggest a route to the drawing code; connectivity never uses them.
    """

    id: str
    end_a: Attachment
    end_b: Attachment
    hints: tuple[PointPx, ...] = ()

    def reversed(self) -> Wire:
        """Same wire with its ends (and hints) swapped."""
        return Wire(self.id, self.end_b, self.end_a, tuple(reversed(self.hints)))

    def touches(self, att: Attachment) -> bool:
        return self.end_a == att or self.end_b == att


@dataclass(frozen=True)
class Junction:
    """A junction object. `pos` is snapped to the 20 px grid on creation."""

    id: str
    pos: PointPx

    def __post_init__(self) -> None:
        object.__setattr__(self, "pos", snap_px(self.pos))


class SplitResult(NamedTuple):
    """Result of `WireGraph.split_wire_at`."""

    graph: WireGraph
    junction_id: str
    first_wire_id: str  # a -> junction (keeps the id of the wire that was split)
    second_wire_id: str  # junction -> b


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _lowest_free_id(prefix: str, used: Iterable[str]) -> str:
    taken = set(used)
    n = 1
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"


def _snap_hints(hints: Iterable[tuple[float, float]]) -> tuple[PointPx, ...]:
    out: list[PointPx] = []
    for h in hints:
        p = snap_px(h)
        if not out or out[-1] != p:
            out.append(p)
    return tuple(out)


def _junction_id_of(att: Attachment) -> str | None:
    return att.id if isinstance(att, JunctionRef) else None


def _find_duplicate(
    wires: list[Wire], a: Attachment, b: Attachment, ignore_index: int | None = None
) -> int | None:
    """Index of a wire joining the same two attachments (either direction), if any."""
    for i, w in enumerate(wires):
        if i == ignore_index:
            continue
        if (w.end_a == a and w.end_b == b) or (w.end_a == b and w.end_b == a):
            return i
    return None


def _queue_ends(queue: list[str], *atts: Attachment) -> None:
    for att in atts:
        jid = _junction_id_of(att)
        if jid is not None:
            queue.append(jid)


def _normalize(wires: list[Wire], junctions: list[Junction], affected: Iterable[str]) -> None:
    """Apply the merge rules (in place) to the junctions in `affected` and cascade."""
    queue = sorted(set(affected))
    while queue:
        jid = queue.pop(0)
        jidx = next((i for i, j in enumerate(junctions) if j.id == jid), None)
        if jidx is None:
            continue
        junc = junctions[jidx]
        ref = JunctionRef(jid)
        attached = [i for i, w in enumerate(wires) if w.touches(ref)]
        if len(attached) >= 3:
            continue
        del junctions[jidx]
        if not attached:
            continue
        if len(attached) == 1:
            i = attached[0]
            w = wires[i]
            free = FreeEnd(*junc.pos)
            new_a = free if w.end_a == ref else w.end_a
            new_b = free if w.end_b == ref else w.end_b
            old = wires.pop(i)
            if new_a == new_b or _find_duplicate(wires, new_a, new_b) is not None:
                # The wire became pointless: its other end lost a wire.
                _queue_ends(queue, old.end_a, old.end_b)
                continue
            wires.insert(i, Wire(old.id, new_a, new_b, old.hints))
            continue
        # Exactly two wires meet here: they become one wire.
        i1, i2 = attached
        w1, w2 = wires[i1], wires[i2]
        w1o = w1 if w1.end_b == ref else w1.reversed()  # ... -> J
        w2o = w2 if w2.end_a == ref else w2.reversed()  # J -> ...
        hints = _snap_hints(w1o.hints + (junc.pos,) + w2o.hints)
        x, y = w1o.end_a, w2o.end_b
        wires.pop(i2)
        wires.pop(i1)
        if x == y or _find_duplicate(wires, x, y) is not None:
            _queue_ends(queue, x, y)
            continue
        wires.insert(i1, Wire(w1.id, x, y, hints))


# ---------------------------------------------------------------------------
# the graph
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WireGraph:
    """Immutable set of wires and junctions. Every operation returns a new graph."""

    wires: tuple[Wire, ...] = ()
    junctions: tuple[Junction, ...] = ()

    # --- lookups -----------------------------------------------------------

    def wire(self, wire_id: str) -> Wire:
        for w in self.wires:
            if w.id == wire_id:
                return w
        raise WireGraphError(f"There is no wire {wire_id}.")

    def junction(self, junction_id: str) -> Junction:
        for j in self.junctions:
            if j.id == junction_id:
                return j
        raise WireGraphError(f"There is no junction {junction_id}.")

    def has_wire(self, wire_id: str) -> bool:
        return any(w.id == wire_id for w in self.wires)

    def has_junction(self, junction_id: str) -> bool:
        return any(j.id == junction_id for j in self.junctions)

    def attached_wires(self, att: Attachment) -> tuple[Wire, ...]:
        """All wires with at least one end on `att`."""
        return tuple(w for w in self.wires if w.touches(att))

    def junction_degree(self, junction_id: str) -> int:
        """Number of wires attached to a junction."""
        return len(self.attached_wires(JunctionRef(junction_id)))

    def junction_dot_visible(self, junction_id: str) -> bool:
        """A junction is drawn as a dot only with 3 or more wires (2 is just a bend)."""
        return self.junction_degree(junction_id) >= 3

    def new_wire_id(self) -> str:
        return _lowest_free_id("W", (w.id for w in self.wires))

    def new_junction_id(self) -> str:
        return _lowest_free_id("J", (j.id for j in self.junctions))

    # --- operations (each returns a NEW graph) ------------------------------

    def add_wire(
        self,
        end_a: Attachment,
        end_b: Attachment,
        hints: Iterable[tuple[float, float]] = (),
        wire_id: str | None = None,
    ) -> WireGraph:
        """Add a wire. If a wire between the same two attachments exists, nothing changes."""
        if end_a == end_b:
            raise WireGraphError("A wire needs two different ends.")
        for att in (end_a, end_b):
            if isinstance(att, JunctionRef) and not self.has_junction(att.id):
                raise WireGraphError(f"There is no junction {att.id}.")
        wires = list(self.wires)
        if _find_duplicate(wires, end_a, end_b) is not None:
            return self
        if wire_id is None:
            wire_id = self.new_wire_id()
        elif self.has_wire(wire_id):
            raise WireGraphError(f"Wire {wire_id} already exists.")
        wires.append(Wire(wire_id, end_a, end_b, _snap_hints(hints)))
        return WireGraph(tuple(wires), self.junctions)

    def remove_wire(self, wire_id: str) -> WireGraph:
        """Remove a wire and apply the merge rules to the junctions it was attached to."""
        victim = self.wire(wire_id)
        wires = [w for w in self.wires if w.id != wire_id]
        junctions = list(self.junctions)
        affected: list[str] = []
        _queue_ends(affected, victim.end_a, victim.end_b)
        _normalize(wires, junctions, affected)
        return WireGraph(tuple(wires), tuple(junctions))

    def add_junction(self, pos: tuple[float, float], junction_id: str | None = None) -> WireGraph:
        """Add a junction object (position snapped to the grid). It starts with no wires."""
        if junction_id is None:
            junction_id = self.new_junction_id()
        elif self.has_junction(junction_id):
            raise WireGraphError(f"Junction {junction_id} already exists.")
        return WireGraph(self.wires, self.junctions + (Junction(junction_id, snap_px(pos)),))

    def split_wire_at(
        self,
        wire_id: str,
        pos: tuple[float, float],
        *,
        junction_id: str | None = None,
        hints_before: int = 0,
    ) -> SplitResult:
        """Split a wire in two at a junction.

        The wire `a -> b` becomes `a -> J` (keeps the old wire id) and `J -> b`
        (gets the lowest free wire id). The first `hints_before` waypoints stay
        with the first half, the rest go to the second half. If `junction_id` names
        an existing junction it is reused (e.g. a junction shared by two crossing
        wires); otherwise a new junction is created at `pos`.
        """
        old = self.wire(wire_id)
        junctions = list(self.junctions)
        if junction_id is None or not self.has_junction(junction_id):
            junction_id = junction_id or self.new_junction_id()
            junctions.append(Junction(junction_id, snap_px(pos)))
        ref = JunctionRef(junction_id)
        if old.touches(ref):
            raise WireGraphError("A wire cannot be split at a junction it already ends on.")
        if not 0 <= hints_before <= len(old.hints):
            raise WireGraphError("hints_before is outside the wire's waypoint list.")
        wires = list(self.wires)
        idx = wires.index(old)
        first = Wire(old.id, old.end_a, ref, old.hints[:hints_before])
        second_id = _lowest_free_id("W", (w.id for w in wires))
        second = Wire(second_id, ref, old.end_b, old.hints[hints_before:])
        wires[idx] = first
        dup = _find_duplicate(wires, second.end_a, second.end_b)
        if dup is not None:
            second_id = wires[dup].id  # an identical wire already exists: keep that one
        else:
            wires.insert(idx + 1, second)
        return SplitResult(WireGraph(tuple(wires), tuple(junctions)), junction_id, old.id, second_id)

    def remove_junction(self, junction_id: str) -> WireGraph:
        """Remove a junction object. Its wires stay, with FreeEnds where it was."""
        junc = self.junction(junction_id)
        ref = JunctionRef(junction_id)
        free = FreeEnd(*junc.pos)
        converted: list[Wire] = []
        for w in self.wires:
            if w.touches(ref):
                new_a = free if w.end_a == ref else w.end_a
                new_b = free if w.end_b == ref else w.end_b
                converted.append(Wire(w.id, new_a, new_b, w.hints))
            else:
                converted.append(w)
        # Moving the ends to a FreeEnd can make a wire pointless or identical to
        # another one; drop those (first one wins) and let neighbours re-check.
        wires: list[Wire] = []
        affected: list[str] = []
        for w in converted:
            if w.end_a == w.end_b or _find_duplicate(wires, w.end_a, w.end_b) is not None:
                _queue_ends(affected, w.end_a, w.end_b)
            else:
                wires.append(w)
        junctions = [j for j in self.junctions if j.id != junction_id]
        _normalize(wires, junctions, affected)
        return WireGraph(tuple(wires), tuple(junctions))

    def remove_component(self, component: str) -> WireGraph:
        """Delete every wire attached to `component`, then clean up the junctions."""
        wires: list[Wire] = []
        affected: list[str] = []
        for w in self.wires:
            on_part = any(
                isinstance(e, TerminalRef) and e.component == component
                for e in (w.end_a, w.end_b)
            )
            if on_part:
                _queue_ends(affected, w.end_a, w.end_b)
            else:
                wires.append(w)
        junctions = list(self.junctions)
        _normalize(wires, junctions, affected)
        return WireGraph(tuple(wires), tuple(junctions))

    # --- validation ---------------------------------------------------------

    def problems(self, terminals: Mapping[str, Collection[str]] | None = None) -> list[str]:
        """List everything wrong with this graph (empty list = valid).

        `terminals` maps each existing component name to its terminal names; when
        given, attachments to missing components or terminals are reported.
        """
        found: list[str] = []
        wire_ids = [w.id for w in self.wires]
        junction_ids = [j.id for j in self.junctions]
        for wid in sorted({i for i in wire_ids if wire_ids.count(i) > 1}):
            found.append(f"Wire id {wid} is used more than once.")
        for jid in sorted({i for i in junction_ids if junction_ids.count(i) > 1}):
            found.append(f"Junction id {jid} is used more than once.")
        known_junctions = set(junction_ids)
        pairs: dict[frozenset[Attachment], str] = {}
        for w in self.wires:
            if w.end_a == w.end_b:
                found.append(f"Wire {w.id} has the same attachment on both ends.")
            key = frozenset((w.end_a, w.end_b))
            if key in pairs:
                found.append(f"Wires {pairs[key]} and {w.id} join the same two attachments.")
            else:
                pairs[key] = w.id
            for att in (w.end_a, w.end_b):
                if isinstance(att, JunctionRef) and att.id not in known_junctions:
                    found.append(f"Wire {w.id} is attached to missing junction {att.id}.")
                if isinstance(att, TerminalRef) and terminals is not None:
                    if att.component not in terminals:
                        found.append(
                            f"Wire {w.id} is attached to missing component {att.component}."
                        )
                    elif att.terminal not in terminals[att.component]:
                        found.append(
                            f"Wire {w.id} is attached to missing terminal "
                            f"{att.component}.{att.terminal}."
                        )
        return found

    def validate(self, terminals: Mapping[str, Collection[str]] | None = None) -> None:
        """Raise `WireGraphError` listing all problems, or return quietly if valid."""
        found = self.problems(terminals)
        if found:
            raise WireGraphError(" ".join(found))
