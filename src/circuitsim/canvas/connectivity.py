"""Pure-Python schematic connectivity, right-angle wire routing, and netlist extraction.

This module has NO PySide6 / Qt imports so that all connectivity rules,
union-find netlist extraction, T-junction vs. crossing wire rules, wire
normalization, and attached-wire re-routing can be tested directly with pytest.

Connectivity Rules:
    1. A wire end connects to a component terminal only if it sits exactly on it
       (or an explicit junction dot is placed there). Two wires that merely cross
       do NOT connect; they connect only at an explicit junction (a T-junction
       where a wire endpoint lands on another wire, or a placed junction dot).
    2. Deleting a component also deletes the wires attached to its terminals.
       Moving, rotating, or flipping a component keeps its wires attached and
       re-routes them at right angles.
    3. Zero-length wires, duplicate wires, and collinear overlapping wires are
       normalized without creating phantom connections.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from circuitsim.canvas.symbol_geometry import (
    DEFAULT_IEC_SYMBOLS_DIR,
    GRID_PITCH_PX,
    SymbolMetadata,
    load_all_iec_metadata,
    snap_to_grid,
    transform_terminal_position,
)
from circuitsim.components.base import Component
from circuitsim.components.ground import Ground
from circuitsim.engine.netlist import Circuit

GROUND_NODE: str = "0"
PointPx = tuple[int, int]


def normalize_point_px(
    pt: tuple[float, float] | PointPx,
    *,
    snap: bool = True,
    grid_px: int = GRID_PITCH_PX,
) -> PointPx:
    """Convert a 2D pixel coordinate to an integer `(x, y)` tuple."""
    x, y = float(pt[0]), float(pt[1])
    if snap:
        x, y = snap_to_grid(x, y, grid_px)
    return (int(round(x)), int(round(y)))


def simplify_orthogonal_points(
    points: Sequence[tuple[float, float] | PointPx],
    *,
    snap: bool = True,
    grid_px: int = GRID_PITCH_PX,
) -> tuple[PointPx, ...]:
    """Normalize an orthogonal polyline by removing zero-length and collinear points.

    Also collapses 180-degree backtracking folds along the same axis so that a
    wire folded back onto itself reduces to its true net span (or `< 2` points
    if zero-length overall).
    """
    cleaned: list[PointPx] = []
    for raw in points:
        pt = normalize_point_px(raw, snap=snap, grid_px=grid_px)
        if cleaned and cleaned[-1] == pt:
            continue
        cleaned.append(pt)
        # Collapse collinear triples A -> B -> C
        while len(cleaned) >= 3:
            a, b, c = cleaned[-3], cleaned[-2], cleaned[-1]
            same_x = a[0] == b[0] == c[0]
            same_y = a[1] == b[1] == c[1]
            if same_x or same_y:
                # Remove middle point B; if A == C, also remove C
                cleaned.pop(-2)
                if len(cleaned) >= 2 and cleaned[-1] == cleaned[-2]:
                    cleaned.pop()
            else:
                break

    if len(cleaned) < 2:
        return ()
    return tuple(cleaned)


def route_orthogonal_wire(
    start_px: tuple[float, float] | PointPx,
    end_px: tuple[float, float] | PointPx,
    *,
    prefer_horizontal_first: bool = True,
    snap: bool = True,
    grid_px: int = GRID_PITCH_PX,
) -> tuple[PointPx, ...]:
    """Compute a 2-segment (L-shaped) or 1-segment right-angle route between two points."""
    p0 = normalize_point_px(start_px, snap=snap, grid_px=grid_px)
    p1 = normalize_point_px(end_px, snap=snap, grid_px=grid_px)
    if p0 == p1:
        return ()
    if p0[0] == p1[0] or p0[1] == p1[1]:
        return (p0, p1)
    corner: PointPx = (p1[0], p0[1]) if prefer_horizontal_first else (p0[0], p1[1])
    return simplify_orthogonal_points((p0, corner, p1), snap=False)


def infer_horizontal_first(points: Sequence[tuple[float, float] | PointPx]) -> bool:
    """Return True if the first non-zero segment of `points` is horizontal."""
    if len(points) < 2:
        return True
    p0 = normalize_point_px(points[0], snap=False)
    for raw in points[1:]:
        p1 = normalize_point_px(raw, snap=False)
        if p1 != p0:
            return p0[1] == p1[1]
    return True


def point_on_orthogonal_segment(pt: PointPx, a: PointPx, b: PointPx) -> bool:
    """Return True if `pt` lies on the closed orthogonal segment `[a, b]`."""
    px, py = pt
    ax, ay = a
    bx, by = b
    if ax == bx:
        return px == ax and min(ay, by) <= py <= max(ay, by)
    if ay == by:
        return py == ay and min(ax, bx) <= px <= max(ax, bx)
    return False


def point_strictly_inside_orthogonal_segment(
    pt: PointPx, a: PointPx, b: PointPx
) -> bool:
    """Return True if `pt` lies strictly between `a` and `b` on an orthogonal segment."""
    return point_on_orthogonal_segment(pt, a, b) and pt != a and pt != b


def point_on_wire(pt: PointPx, wire_points: Sequence[PointPx]) -> bool:
    """Return True if `pt` lies anywhere along `wire_points` (endpoints or interior)."""
    for i in range(len(wire_points) - 1):
        if point_on_orthogonal_segment(pt, wire_points[i], wire_points[i + 1]):
            return True
    return False


def point_strictly_inside_wire(pt: PointPx, wire_points: Sequence[PointPx]) -> bool:
    """Return True if `pt` is on `wire_points` but is NOT one of the wire's two endpoints."""
    if len(wire_points) < 2:
        return False
    if pt == wire_points[0] or pt == wire_points[-1]:
        return False
    return point_on_wire(pt, wire_points)


def segments_overlap_collinear(
    a1: PointPx, a2: PointPx, b1: PointPx, b2: PointPx
) -> bool:
    """Return True if two orthogonal segments are collinear and overlap with length > 0."""
    # Both vertical on the same X
    if a1[0] == a2[0] and b1[0] == b2[0] and a1[0] == b1[0]:
        low = max(min(a1[1], a2[1]), min(b1[1], b2[1]))
        high = min(max(a1[1], a2[1]), max(b1[1], b2[1]))
        return low < high
    # Both horizontal on the same Y
    if a1[1] == a2[1] and b1[1] == b2[1] and a1[1] == b1[1]:
        low = max(min(a1[0], a2[0]), min(b1[0], b2[0]))
        high = min(max(a1[0], a2[0]), max(b1[0], b2[0]))
        return low < high
    return False


def wires_overlap_collinear(
    pts_a: Sequence[PointPx], pts_b: Sequence[PointPx]
) -> bool:
    """Return True if any segment of `pts_a` collinearly overlaps any segment of `pts_b`."""
    for i in range(len(pts_a) - 1):
        for j in range(len(pts_b) - 1):
            if segments_overlap_collinear(
                pts_a[i], pts_a[i + 1], pts_b[j], pts_b[j + 1]
            ):
                return True
    return False


@dataclass(frozen=True)
class PlacedComponentSpec:
    """Pure-Python description of a placed component on the schematic."""

    component: Component
    center_px: tuple[float, float] = (0.0, 0.0)
    rotation_deg: int = 0
    flipped_h: bool = False
    terminals_px: dict[str, PointPx] | None = None

    def resolve_terminals_px(
        self, catalog: dict[str, SymbolMetadata]
    ) -> dict[str, PointPx]:
        """Compute world pixel coordinates `(x, y)` for every terminal of this component."""
        if self.terminals_px is not None:
            return {
                k: normalize_point_px(v, snap=True)
                for k, v in self.terminals_px.items()
            }
        meta = catalog[self.component.component_type]
        result: dict[str, PointPx] = {}
        for term in meta.terminals:
            tx, ty = transform_terminal_position(
                term.grid_pos,
                self.center_px,
                rotation_deg=self.rotation_deg,
                flipped_h=self.flipped_h,
                grid_px=GRID_PITCH_PX,
            )
            result[term.name] = normalize_point_px((tx, ty), snap=True)
        return result


@dataclass(frozen=True)
class WireSpec:
    """Pure-Python description of a wire polyline on the schematic."""

    wire_id: str
    points: tuple[tuple[float, float] | PointPx, ...]

    def normalized_points(self) -> tuple[PointPx, ...]:
        """Return simplified orthogonal points (`()` if degenerate/zero-length)."""
        return simplify_orthogonal_points(self.points, snap=True)


@dataclass
class ConnectivityResult:
    """Result of extracting an electrical `Circuit` and visual junctions from a schematic."""

    circuit: Circuit
    component_nodes: dict[str, dict[str, str]] = field(default_factory=dict)
    wire_to_node: dict[str, str] = field(default_factory=dict)
    point_to_node: dict[PointPx, str] = field(default_factory=dict)
    junction_dots: set[PointPx] = field(default_factory=set)
    valid_wires: tuple[tuple[str, tuple[PointPx, ...]], ...] = ()
    unconnected_components: tuple[str, ...] = ()


class _UnionFind:
    """Disjoint-set (Union-Find) data structure over hashable keys."""

    def __init__(self) -> None:
        self._parent: dict[object, object] = {}

    def add(self, item: object) -> None:
        if item not in self._parent:
            self._parent[item] = item

    def find(self, item: object) -> object:
        self.add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        curr = item
        while curr != root:
            nxt = self._parent[curr]
            self._parent[curr] = root
            curr = nxt
        return root

    def union(self, a: object, b: object) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra != rb:
            self._parent[rb] = ra


def _branch_directions_at_point(
    pt: PointPx, wire_points: Sequence[PointPx]
) -> set[tuple[int, int]]:
    """Return the set of unit orthogonal directions `{(±1, 0), (0, ±1)}` of `wire_points` at `pt`."""
    dirs: set[tuple[int, int]] = set()
    px, py = pt
    for i in range(len(wire_points) - 1):
        a = wire_points[i]
        b = wire_points[i + 1]
        if not point_on_orthogonal_segment(pt, a, b):
            continue
        for end in (a, b):
            dx = end[0] - px
            dy = end[1] - py
            if dx > 0:
                dirs.add((1, 0))
            elif dx < 0:
                dirs.add((-1, 0))
            elif dy > 0:
                dirs.add((0, 1))
            elif dy < 0:
                dirs.add((0, -1))
    return dirs


def extract_connectivity(
    placed_components: Sequence[PlacedComponentSpec],
    wires: Sequence[WireSpec],
    explicit_junctions: Iterable[tuple[float, float] | PointPx] = (),
    *,
    symbol_catalog: dict[str, SymbolMetadata] | None = None,
) -> ConnectivityResult:
    """Extract electrical connectivity and build a solver-ready `Circuit`.

    Implements Rules 1–5:
        - Wire endpoints connect to component terminals only when sitting on them
          (or via an explicit junction dot).
        - Two wires that cross without sharing an endpoint or an explicit junction
          dot do NOT connect.
        - A wire endpoint landing on the interior of another wire segment forms a
          T-junction and connects.
        - Zero-length wires are discarded; duplicate and collinear overlapping wires
          are unified without creating phantom connections.
    """
    catalog = (
        symbol_catalog
        if symbol_catalog is not None
        else load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)
    )

    uf = _UnionFind()

    # 1. Resolve component terminal positions
    comp_terminals: dict[str, dict[str, PointPx]] = {}
    comp_term_order: dict[str, tuple[str, ...]] = {}
    terminals_at_point: dict[PointPx, list[tuple[str, str]]] = {}

    for spec in placed_components:
        cname = spec.component.name
        meta = catalog[spec.component.component_type]
        t_order = tuple(t.name for t in meta.terminals)
        comp_term_order[cname] = t_order
        resolved = spec.resolve_terminals_px(catalog)
        comp_terminals[cname] = resolved
        for tname in t_order:
            pt = resolved[tname]
            key = ("term", cname, tname)
            uf.add(key)
            terminals_at_point.setdefault(pt, []).append((cname, tname))

    # Connect coincident terminals sitting at the exact same point
    for pt, term_list in terminals_at_point.items():
        if len(term_list) > 1:
            first_key = ("term", term_list[0][0], term_list[0][1])
            for cname, tname in term_list[1:]:
                uf.union(first_key, ("term", cname, tname))

    # 2. Filter zero-length wires and deduplicate identical polylines (Rule 3)
    canonical_wires: list[tuple[str, tuple[PointPx, ...]]] = []
    seen_polylines: dict[tuple[PointPx, ...], str] = {}
    duplicate_wire_map: dict[str, str] = {}

    for w in wires:
        pts = w.normalized_points()
        if len(pts) < 2:
            # Zero-length wire: ignore completely so it cannot create a phantom junction
            continue
        rev_pts = tuple(reversed(pts))
        canon_sig = pts if pts <= rev_pts else rev_pts
        if canon_sig in seen_polylines:
            primary_id = seen_polylines[canon_sig]
            duplicate_wire_map[w.wire_id] = primary_id
            continue
        seen_polylines[canon_sig] = w.wire_id
        canonical_wires.append((w.wire_id, pts))
        uf.add(("wire", w.wire_id))

    # 3. Connect wire endpoints to component terminals (Rule 1)
    for wid, pts in canonical_wires:
        w_key = ("wire", wid)
        for ep in (pts[0], pts[-1]):
            for cname, tname in terminals_at_point.get(ep, ()):
                uf.union(w_key, ("term", cname, tname))

    # 4. Connect wire endpoints to other wires (shared endpoints & T-junctions, Rule 1)
    #    and unify collinear overlapping wires (Rule 3)
    num_wires = len(canonical_wires)
    t_junction_points: set[PointPx] = set()

    for i in range(num_wires):
        wid_a, pts_a = canonical_wires[i]
        key_a = ("wire", wid_a)
        ep_a0, ep_a1 = pts_a[0], pts_a[-1]

        for j in range(num_wires):
            if i == j:
                continue
            wid_b, pts_b = canonical_wires[j]
            key_b = ("wire", wid_b)

            # Check if either endpoint of wire A lies on wire B
            for ep in (ep_a0, ep_a1):
                if point_on_wire(ep, pts_b):
                    uf.union(key_a, key_b)
                    if point_strictly_inside_wire(ep, pts_b):
                        t_junction_points.add(ep)

            # Check collinear positive-length segment overlap (Rule 3)
            if i < j and wires_overlap_collinear(pts_a, pts_b):
                uf.union(key_a, key_b)

    # 5. Explicit junction dots (Rule 1 & Addition #4: a junction dot not on any wire
    #    must never create a net, a phantom connection, or a false warning)
    norm_junctions: set[PointPx] = {
        normalize_point_px(jp, snap=True) for jp in explicit_junctions
    }
    active_explicit_junctions: set[PointPx] = set()

    for jp in norm_junctions:
        wires_at_jp = [
            ("wire", wid)
            for wid, pts in canonical_wires
            if point_on_wire(jp, pts)
        ]
        if not wires_at_jp:
            # Junction dot is not on any wire: ignore completely
            continue
        touched_keys: list[object] = list(wires_at_jp)
        for cname, tname in terminals_at_point.get(jp, ()):
            touched_keys.append(("term", cname, tname))
        j_key = ("junc", jp)
        uf.add(j_key)
        for tk in touched_keys:
            uf.union(j_key, tk)
        active_explicit_junctions.add(jp)

    # 6. Group connected elements by Union-Find root and assign node names
    groups: dict[object, list[object]] = {}
    for spec in placed_components:
        cname = spec.component.name
        for tname in comp_term_order[cname]:
            k = ("term", cname, tname)
            groups.setdefault(uf.find(k), []).append(k)
    for wid, _ in canonical_wires:
        k = ("wire", wid)
        groups.setdefault(uf.find(k), []).append(k)
    for jp in active_explicit_junctions:
        k = ("junc", jp)
        groups.setdefault(uf.find(k), []).append(k)

    # Identify which groups contain a Ground component
    ground_comp_names: set[str] = {
        spec.component.name
        for spec in placed_components
        if isinstance(spec.component, Ground)
        or spec.component.component_type == "ground"
    }

    root_to_node: dict[object, str] = {}
    non_ground_roots: list[tuple[tuple[int, int, str], object]] = []

    for root, members in groups.items():
        is_ground = any(
            isinstance(m, tuple)
            and len(m) == 3
            and m[0] == "term"
            and m[1] in ground_comp_names
            for m in members
        )
        if is_ground:
            root_to_node[root] = GROUND_NODE
        else:
            # Sort key for deterministic node naming ("N1", "N2", ...)
            coords: list[PointPx] = []
            names: list[str] = []
            for m in members:
                if isinstance(m, tuple) and m[0] == "term":
                    _, cname, tname = m
                    coords.append(comp_terminals[cname][tname])
                    names.append(f"{cname}.{tname}")
                elif isinstance(m, tuple) and m[0] == "wire":
                    wid = m[1]
                    for w_id, w_pts in canonical_wires:
                        if w_id == wid:
                            coords.extend(w_pts)
                            names.append(w_id)
                            break
            min_pt = min(coords) if coords else (0, 0)
            min_name = min(names) if names else ""
            non_ground_roots.append(((min_pt[0], min_pt[1], min_name), root))

    non_ground_roots.sort(key=lambda item: item[0])
    for idx, (_, root) in enumerate(non_ground_roots, start=1):
        root_to_node[root] = f"N{idx}"

    # 7. Build component_nodes, wire_to_node, point_to_node, and Circuit
    component_nodes: dict[str, dict[str, str]] = {}
    point_to_node: dict[PointPx, str] = {}
    wire_to_node: dict[str, str] = {}

    for wid, pts in canonical_wires:
        node_name = root_to_node[uf.find(("wire", wid))]
        wire_to_node[wid] = node_name
        point_to_node[pts[0]] = node_name
        point_to_node[pts[-1]] = node_name

    for dup_id, primary_id in duplicate_wire_map.items():
        if primary_id in wire_to_node:
            wire_to_node[dup_id] = wire_to_node[primary_id]

    for jp in active_explicit_junctions:
        point_to_node[jp] = root_to_node[uf.find(("junc", jp))]

    circuit = Circuit()
    unconnected_list: list[str] = []
    comp_is_unconnected: dict[str, bool] = {}

    for spec in placed_components:
        cname = spec.component.name
        t_order = comp_term_order[cname]
        is_unconnected = all(
            len(groups.get(uf.find(("term", cname, tname)), ())) <= 1
            for tname in t_order
        )
        comp_is_unconnected[cname] = is_unconnected
        if is_unconnected:
            unconnected_list.append(cname)

    has_connected_non_ground = any(
        not comp_is_unconnected[spec.component.name]
        and spec.component.name not in ground_comp_names
        for spec in placed_components
    )

    for spec in placed_components:
        cname = spec.component.name
        t_order = comp_term_order[cname]
        term_map: dict[str, str] = {}
        ordered_nodes: list[str] = []
        for tname in t_order:
            node_name = root_to_node[uf.find(("term", cname, tname))]
            term_map[tname] = node_name
            ordered_nodes.append(node_name)
            point_to_node[comp_terminals[cname][tname]] = node_name
        component_nodes[cname] = term_map

        # Ignore completely unconnected parts so they do not block simulation
        # with a floating-node error (and an unwired Ground does not fake ground).
        if comp_is_unconnected[cname] and (
            has_connected_non_ground or cname in ground_comp_names
        ):
            continue

        cloned_comp = copy.deepcopy(spec.component)
        if isinstance(cloned_comp, Ground):
            cloned_comp.nodes = (GROUND_NODE,)
        else:
            cloned_comp.nodes = tuple(ordered_nodes)
        circuit.add(cloned_comp)

    # 8. Compute visual junction dots (T-junctions, 3+ branch wire joins, explicit junctions)
    junction_dots: set[PointPx] = set(active_explicit_junctions) | set(
        t_junction_points
    )
    candidate_points: set[PointPx] = set()
    for _, pts in canonical_wires:
        candidate_points.add(pts[0])
        candidate_points.add(pts[-1])

    for pt in candidate_points:
        # Collect directions of all connected wires at `pt` sharing the same net
        wires_at_pt = [
            (wid, pts)
            for wid, pts in canonical_wires
            if point_on_wire(pt, pts)
        ]
        if len(wires_at_pt) < 2:
            continue
        # Group by net at `pt`
        dirs_by_net: dict[str, set[tuple[int, int]]] = {}
        wires_count_by_net: dict[str, int] = {}
        for wid, pts in wires_at_pt:
            net = wire_to_node[wid]
            # Only count if `pt` is actually connected to this net (endpoint or T-junction or explicit junction)
            if (
                pt == pts[0]
                or pt == pts[-1]
                or pt in t_junction_points
                or pt in active_explicit_junctions
            ):
                wires_count_by_net[net] = wires_count_by_net.get(net, 0) + 1
                dirs_by_net.setdefault(net, set()).update(
                    _branch_directions_at_point(pt, pts)
                )
        for net, dirs in dirs_by_net.items():
            if wires_count_by_net.get(net, 0) >= 2 and len(dirs) >= 3:
                junction_dots.add(pt)

    return ConnectivityResult(
        circuit=circuit,
        component_nodes=component_nodes,
        wire_to_node=wire_to_node,
        point_to_node=point_to_node,
        junction_dots=junction_dots,
        valid_wires=tuple(canonical_wires),
        unconnected_components=tuple(unconnected_list),
    )


def find_wires_attached_to_components(
    component_terminals: dict[str, dict[str, PointPx]],
    target_component_names: set[str],
    wires: Sequence[WireSpec],
) -> list[str]:
    """Return IDs of all wires whose start or end sits on a terminal of `target_component_names`."""
    target_points: set[PointPx] = set()
    for cname in target_component_names:
        for pt in component_terminals.get(cname, {}).values():
            target_points.add(normalize_point_px(pt, snap=True))

    attached_ids: list[str] = []
    for w in wires:
        pts = w.normalized_points()
        if len(pts) < 2:
            continue
        if pts[0] in target_points or pts[-1] in target_points:
            attached_ids.append(w.wire_id)
    return attached_ids


def _route_cuts_box(pts: Sequence[PointPx], box: tuple[int, int, int, int]) -> bool:
    """Return True if any orthogonal segment in `pts` passes through the interior of `box`."""
    min_x, min_y, max_x, max_y = box
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        if y1 == y2:
            if min_y < y1 < max_y:
                seg_min_x, seg_max_x = min(x1, x2), max(x1, x2)
                if max(seg_min_x, min_x) < min(seg_max_x, max_x):
                    return True
        elif x1 == x2:
            if min_x < x1 < max_x:
                seg_min_y, seg_max_y = min(y1, y2), max(y1, y2)
                if max(seg_min_y, min_y) < min(seg_max_y, max_y):
                    return True
    return False


def _route_wire_avoiding_body(
    p_start: PointPx,
    p_end: PointPx,
    *,
    cname: str,
    tname: str,
    new_terminals: dict[str, dict[str, PointPx]],
    prefer_horizontal_first: bool = True,
    terminal_at_start: bool = True,
) -> tuple[PointPx, ...]:
    """Route an orthogonal wire between `p_start` and `p_end` without cutting through `cname`'s body."""
    terms = new_terminals.get(cname, {})
    if len(terms) >= 2:
        t_vals = list(terms.values())
        cx = (t_vals[0][0] + t_vals[1][0]) // 2
        cy = (t_vals[0][1] + t_vals[1][1]) // 2
        is_horiz = (t_vals[0][1] == t_vals[1][1])
        if is_horiz:
            body_box = (cx - 39, cy - 19, cx + 39, cy + 19)
        else:
            body_box = (cx - 19, cy - 39, cx + 19, cy + 39)
        t_sorted = sorted(terms.keys())
        side_factor = -1 if (tname in t_sorted and t_sorted.index(tname) == 0) else 1
    elif len(terms) == 1:
        gpt = list(terms.values())[0]
        cx, cy = gpt[0], gpt[1] + 20
        body_box = (cx - 15, cy - 15, cx + 15, cy + 15)
        is_horiz = True
        side_factor = 1
    else:
        return route_orthogonal_wire(p_start, p_end, prefer_horizontal_first=prefer_horizontal_first)

    # 1. Try simple 2-segment routes (preferring the requested direction first)
    cands = [
        route_orthogonal_wire(p_start, p_end, prefer_horizontal_first=prefer_horizontal_first),
        route_orthogonal_wire(p_start, p_end, prefer_horizontal_first=not prefer_horizontal_first),
    ]
    for cand in cands:
        if cand and not _route_cuts_box(cand, body_box):
            return cand

    # 2. If simple routes cut through the body (e.g. 180° rotation / opposite-side connection),
    # construct an orthogonal bypass detour around the component body
    term_pt = p_start if terminal_at_start else p_end
    other_pt = p_end if terminal_at_start else p_start

    if is_horiz:
        bypass_y = cy + side_factor * 40
        route = (term_pt, (term_pt[0], bypass_y), (other_pt[0], bypass_y), other_pt)
    else:
        bypass_x = cx + side_factor * 40
        route = (term_pt, (bypass_x, term_pt[1]), (bypass_x, other_pt[1]), other_pt)

    if not terminal_at_start:
        route = tuple(reversed(route))
    return simplify_orthogonal_points(route, snap=False)


def reroute_wires_for_updated_terminals(
    old_terminals: dict[str, dict[str, PointPx]],
    new_terminals: dict[str, dict[str, PointPx]],
    wires: Sequence[WireSpec],
) -> dict[str, tuple[PointPx, ...]]:
    """Re-route wires at right angles when attached components move, rotate, or flip.

    Returns a mapping `wire_id -> new_points` for every wire whose attached
    terminal(s) changed position.
    """
    # Map old terminal position -> (comp_name, term_name)
    old_pt_to_term: dict[PointPx, tuple[str, str]] = {}
    for cname, tmap in old_terminals.items():
        for tname, pt in tmap.items():
            old_pt_to_term[normalize_point_px(pt, snap=True)] = (cname, tname)

    updated: dict[str, tuple[PointPx, ...]] = {}
    for w in wires:
        pts = w.normalized_points()
        if len(pts) < 2:
            continue
        start_pt, end_pt = pts[0], pts[-1]
        new_start = start_pt
        new_end = end_pt

        start_cname, start_tname = None, None
        end_cname, end_tname = None, None

        if start_pt in old_pt_to_term:
            cname, tname = old_pt_to_term[start_pt]
            if cname in new_terminals and tname in new_terminals[cname]:
                new_start = normalize_point_px(
                    new_terminals[cname][tname], snap=True
                )
                start_cname, start_tname = cname, tname

        if end_pt in old_pt_to_term:
            cname, tname = old_pt_to_term[end_pt]
            if cname in new_terminals and tname in new_terminals[cname]:
                new_end = normalize_point_px(
                    new_terminals[cname][tname], snap=True
                )
                end_cname, end_tname = cname, tname

        if new_start != start_pt or new_end != end_pt:
            dx_s = new_start[0] - start_pt[0]
            dy_s = new_start[1] - start_pt[1]
            dx_e = new_end[0] - end_pt[0]
            dy_e = new_end[1] - end_pt[1]
            if (dx_s, dy_s) == (dx_e, dy_e) and (dx_s != 0 or dy_s != 0):
                updated[w.wire_id] = tuple(
                    (px + dx_s, py + dy_s) for px, py in pts
                )
            else:
                horiz_first = infer_horizontal_first(pts)
                if start_cname is not None:
                    updated[w.wire_id] = _route_wire_avoiding_body(
                        new_start,
                        new_end,
                        cname=start_cname,
                        tname=start_tname,
                        new_terminals=new_terminals,
                        prefer_horizontal_first=horiz_first,
                        terminal_at_start=True,
                    )
                elif end_cname is not None:
                    updated[w.wire_id] = _route_wire_avoiding_body(
                        new_start,
                        new_end,
                        cname=end_cname,
                        tname=end_tname,
                        new_terminals=new_terminals,
                        prefer_horizontal_first=horiz_first,
                        terminal_at_start=False,
                    )
                else:
                    updated[w.wire_id] = route_orthogonal_wire(
                        new_start, new_end, prefer_horizontal_first=horiz_first
                    )

    return updated
