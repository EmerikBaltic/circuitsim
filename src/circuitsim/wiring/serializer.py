"""Schema v2 serialization and v1-to-v2 migration (pure Python, no Qt).

Schema v2 records explicit connectivity:
- Components (same placed format as v1)
- Junctions: explicit junction objects [{"id": "J1", "x": 100, "y": 100}, ...]
- Wires: explicit attachments [{"id": "W1", "end_a": ..., "end_b": ..., "hints": ...}]
  Attachment kinds:
    - {"kind": "terminal", "component": "R1", "terminal": "a"}
    - {"kind": "junction", "id": "J1"}
    - {"kind": "free", "x": 100, "y": 80}
- View settings (theme, zoom, pan, simulation_speed)

Migration from v1:
- Runs geometric extraction once to resolve terminal positions and T-junctions
- Converts endpoints to TerminalRef, JunctionRef, or FreeEnd
- Slices wires that meet at T-junctions or explicit junction dots
- Preserves separation of crossing wires without dots
- Cleans up stray/redundant junction dots via WireGraph merge rules
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from circuitsim.app_info import APP_NAME
from circuitsim.canvas.symbol_geometry import (
    DEFAULT_IEC_SYMBOLS_DIR,
    SymbolMetadata,
    load_all_iec_metadata,
)
from circuitsim.io.circ_serializer import (
    CircuitDocument,
    CircuitFileError,
    PlacedComponentSpec,
    ViewState,
    _check_header,
    _component_from_dict,
    _component_to_dict,
    _require_dict,
    _require_list,
    _require_point,
    _view_from_dict,
    loads_document as loads_v1_document,
)
from circuitsim.wiring.model import (
    GRID_PX,
    Attachment,
    FreeEnd,
    Junction,
    JunctionRef,
    PointPx,
    TerminalRef,
    Wire,
    WireGraph,
    WireGraphError,
    snap_px,
)
from circuitsim.wiring.netlist import WiringNetlist, build_circuit

FORMAT_NAME: str = "circuitsim"
SCHEMA_VERSION_V2: int = 2


@dataclass
class CircuitDocumentV2:
    """A CircuitSim schematic document in Schema v2 format."""

    placed: list[PlacedComponentSpec] = field(default_factory=list)
    graph: WireGraph = field(default_factory=WireGraph)
    view: ViewState = field(default_factory=ViewState)

    def build_circuit(
        self, symbol_catalog: Mapping[str, SymbolMetadata] | None = None
    ) -> WiringNetlist:
        """Build solver-ready Circuit and netlist through the explicit WireGraph."""
        return build_circuit(
            self.graph,
            [p.component for p in self.placed],
            symbol_catalog=symbol_catalog,
        )


# ---------------------------------------------------------------------------
# Attachment serialization
# ---------------------------------------------------------------------------


def attachment_to_dict(att: Attachment) -> dict[str, Any]:
    if isinstance(att, TerminalRef):
        return {"kind": "terminal", "component": att.component, "terminal": att.terminal}
    if isinstance(att, JunctionRef):
        return {"kind": "junction", "id": att.id}
    if isinstance(att, FreeEnd):
        return {"kind": "free", "x": int(att.x), "y": int(att.y)}
    raise CircuitFileError(f"Unknown attachment type: {type(att)}")


def attachment_from_dict(d: object, who: str) -> Attachment:
    data = _require_dict(d, who)
    kind = data.get("kind")
    if kind == "terminal":
        comp = data.get("component")
        term = data.get("terminal")
        if not isinstance(comp, str) or not comp.strip():
            raise CircuitFileError(f"{who}: terminal attachment must have 'component'.")
        if not isinstance(term, str) or not term.strip():
            raise CircuitFileError(f"{who}: terminal attachment must have 'terminal'.")
        return TerminalRef(component=comp.strip(), terminal=term.strip())
    if kind == "junction":
        jid = data.get("id")
        if not isinstance(jid, str) or not jid.strip():
            raise CircuitFileError(f"{who}: junction attachment must have 'id'.")
        return JunctionRef(id=jid.strip())
    if kind == "free":
        x = data.get("x")
        y = data.get("y")
        if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
            raise CircuitFileError(f"{who}: free attachment must have numeric 'x' and 'y'.")
        return FreeEnd(x=int(round(x)), y=int(round(y)))
    raise CircuitFileError(f"{who}: unknown attachment kind {kind!r}.")


# ---------------------------------------------------------------------------
# Document -> Dict / JSON (v2)
# ---------------------------------------------------------------------------


def document_to_dict_v2(doc: CircuitDocumentV2) -> dict[str, Any]:
    """Convert CircuitDocumentV2 to JSON-compatible dictionary."""
    return {
        "format": FORMAT_NAME,
        "schema_version": SCHEMA_VERSION_V2,
        "components": [_component_to_dict(s) for s in doc.placed],
        "junctions": [{"id": j.id, "x": j.pos[0], "y": j.pos[1]} for j in doc.graph.junctions],
        "wires": [
            {
                "id": w.id,
                "end_a": attachment_to_dict(w.end_a),
                "end_b": attachment_to_dict(w.end_b),
                "hints": [[x, y] for x, y in w.hints],
            }
            for w in doc.graph.wires
        ],
        "view": {
            "theme": doc.view.theme,
            "zoom": float(doc.view.zoom),
            "pan": [float(doc.view.pan[0]), float(doc.view.pan[1])],
            "simulation_speed": doc.view.simulation_speed,
        },
    }


def dumps_document_v2(doc: CircuitDocumentV2) -> str:
    """Serialize CircuitDocumentV2 to indented JSON text."""
    try:
        return json.dumps(document_to_dict_v2(doc), indent=2, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise CircuitFileError(
            f"The circuit contains a value that cannot be saved ({exc})."
        ) from exc


# ---------------------------------------------------------------------------
# Dict / JSON -> Document (v2)
# ---------------------------------------------------------------------------


def dict_to_document_v2(data: object) -> CircuitDocumentV2:
    """Parse a v2 document dictionary into CircuitDocumentV2."""
    if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
        raise CircuitFileError(f"This is not an {APP_NAME} file (the 'format' marker is missing).")
    version = data.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise CircuitFileError("The file has no valid version number.")
    if version == 1:
        # Auto-migrate v1
        return migrate_v1_to_v2(data)
    if version > SCHEMA_VERSION_V2:
        raise CircuitFileError(
            f"This file was made by a newer version of {APP_NAME} (file version {version}, "
            f"this program understands up to {SCHEMA_VERSION_V2}). Please update {APP_NAME} to open it."
        )
    if version < 1:
        raise CircuitFileError(f"Unknown file version number {version}.")

    comps_raw = _require_list(data.get("components"), "The component list")
    junctions_raw = _require_list(data.get("junctions", []), "The junction list")
    wires_raw = _require_list(data.get("wires", []), "The wire list")

    placed = [_component_from_dict(e, i) for i, e in enumerate(comps_raw)]
    seen_names: set[str] = set()
    for spec in placed:
        if spec.component.name in seen_names:
            raise CircuitFileError(f"Two components are both named {spec.component.name}.")
        seen_names.add(spec.component.name)

    junctions: list[Junction] = []
    seen_jids: set[str] = set()
    for i, j_entry in enumerate(junctions_raw):
        jd = _require_dict(j_entry, f"Junction #{i + 1}")
        jid = jd.get("id")
        if not isinstance(jid, str) or not jid.strip():
            raise CircuitFileError(f"Junction #{i + 1} has no id.")
        jid = jid.strip()
        if jid in seen_jids:
            raise CircuitFileError(f"Junction id {jid} is used more than once.")
        seen_jids.add(jid)
        x = jd.get("x")
        y = jd.get("y")
        if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
            raise CircuitFileError(f"Junction {jid} must have numeric 'x' and 'y'.")
        junctions.append(Junction(jid, snap_px((float(x), float(y)))))

    wires: list[Wire] = []
    seen_wids: set[str] = set()
    for i, w_entry in enumerate(wires_raw):
        wd = _require_dict(w_entry, f"Wire #{i + 1}")
        wid = wd.get("id")
        if not isinstance(wid, str) or not wid.strip():
            raise CircuitFileError(f"Wire #{i + 1} has no id.")
        wid = wid.strip()
        if wid in seen_wids:
            raise CircuitFileError(f"Wire id {wid} is used more than once.")
        seen_wids.add(wid)
        end_a = attachment_from_dict(wd.get("end_a"), f"Wire {wid} (end_a)")
        end_b = attachment_from_dict(wd.get("end_b"), f"Wire {wid} (end_b)")
        raw_hints = _require_list(wd.get("hints", []), f"Wire {wid} (hints)")
        hints = tuple(
            snap_px(_require_point(h, f"Wire {wid} waypoint hint")) for h in raw_hints
        )
        wires.append(Wire(wid, end_a, end_b, hints))

    graph = WireGraph(wires=tuple(wires), junctions=tuple(junctions))
    # Validate attachment integrity
    catalog = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)
    terminals: dict[str, tuple[str, ...]] = {}
    for spec in placed:
        meta = catalog.get(spec.component.component_type)
        if meta is not None:
            terminals[spec.component.name] = tuple(t.name for t in meta.terminals)
    graph.validate(terminals)

    view = _view_from_dict(data.get("view"))
    return CircuitDocumentV2(placed=placed, graph=graph, view=view)


def loads_document_v2(text: str) -> CircuitDocumentV2:
    """Parse JSON text into CircuitDocumentV2 (auto-migrating v1)."""
    if not text.strip():
        raise CircuitFileError("The file is empty.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CircuitFileError(
            f"The file is damaged or incomplete and cannot be read (JSON problem at line {exc.lineno}, column {exc.colno})."
        ) from exc
    return dict_to_document_v2(data)


# ---------------------------------------------------------------------------
# Migration from Schema v1 to Schema v2
# ---------------------------------------------------------------------------


def _point_on_segment(pt: PointPx, a: PointPx, b: PointPx) -> bool:
    px, py = pt
    ax, ay = a
    bx, by = b
    if ax == bx:
        return px == ax and min(ay, by) <= py <= max(ay, by)
    if ay == by:
        return py == ay and min(ax, bx) <= px <= max(ax, bx)
    return False


def _point_strictly_inside_segment(pt: PointPx, a: PointPx, b: PointPx) -> bool:
    return _point_on_segment(pt, a, b) and pt != a and pt != b


def _polyline_length(points: Sequence[PointPx]) -> int:
    return sum(abs(points[i + 1][0] - points[i][0]) + abs(points[i + 1][1] - points[i][1]) for i in range(len(points) - 1))


def _dist_along_polyline(pt: PointPx, points: Sequence[PointPx]) -> int | None:
    dist = 0
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if _point_on_segment(pt, a, b):
            return dist + abs(pt[0] - a[0]) + abs(pt[1] - a[1])
        dist += abs(b[0] - a[0]) + abs(b[1] - a[1])
    return None


def _split_polyline_at_points(
    points: tuple[PointPx, ...], split_points: set[PointPx]
) -> list[tuple[PointPx, ...]]:
    """Slice a polyline at all specified split points (both interior vertices and along segments)."""
    results: list[tuple[PointPx, ...]] = []
    current_sub: list[PointPx] = [points[0]]
    last_idx = len(points) - 1

    for i in range(last_idx):
        p_a, p_b = points[i], points[i + 1]
        # Any split points strictly inside segment (p_a, p_b)
        seg_splits = [
            sp for sp in split_points if _point_strictly_inside_segment(sp, p_a, p_b)
        ]
        seg_splits.sort(key=lambda p: abs(p[0] - p_a[0]) + abs(p[1] - p_a[1]))

        for sp in seg_splits:
            current_sub.append(sp)
            if len(current_sub) >= 2:
                results.append(tuple(current_sub))
            current_sub = [sp]

        # Check vertex p_b
        if p_b in split_points and i + 1 < last_idx:
            current_sub.append(p_b)
            if len(current_sub) >= 2:
                results.append(tuple(current_sub))
            current_sub = [p_b]
        else:
            current_sub.append(p_b)

    if len(current_sub) >= 2:
        results.append(tuple(current_sub))
    return results


def migrate_v1_to_v2(v1_input: CircuitDocument | dict[str, Any] | str | Path) -> CircuitDocumentV2:
    """Migrate a Schema v1 circuit document into a Schema v2 CircuitDocumentV2."""
    if isinstance(v1_input, CircuitDocument):
        doc = v1_input
    elif isinstance(v1_input, (str, Path)):
        p = Path(v1_input)
        if p.exists() and p.is_file():
            doc = loads_v1_document(p.read_text(encoding="utf-8-sig"))
        else:
            doc = loads_v1_document(str(v1_input))
    elif isinstance(v1_input, dict):
        # Could be raw dict
        text = json.dumps(v1_input)
        doc = loads_v1_document(text)
    else:
        raise CircuitFileError("Unsupported input for migration.")

    catalog = load_all_iec_metadata(DEFAULT_IEC_SYMBOLS_DIR)

    # 1. Map terminal positions to TerminalRefs
    terminal_by_pos: dict[PointPx, TerminalRef] = {}
    for spec in doc.placed:
        cname = spec.component.name
        resolved = spec.resolve_terminals_px(catalog)
        for tname, pt in resolved.items():
            terminal_by_pos[snap_px(pt)] = TerminalRef(cname, tname)

    # 2. Filter zero-length wires and normalize
    raw_wires: list[tuple[str, tuple[PointPx, ...]]] = []
    for w in doc.wires:
        pts = tuple(snap_px(p) for p in w.points)
        # remove consecutive identical points
        cleaned: list[PointPx] = [pts[0]]
        for p in pts[1:]:
            if p != cleaned[-1]:
                cleaned.append(p)
        if len(cleaned) >= 2:
            raw_wires.append((w.wire_id, tuple(cleaned)))

    # 3. Identify junction locations:
    # A point is a junction if:
    # - It is an explicit junction dot in v1 AND touches at least one wire
    # - Two or more wire endpoints meet there AND it is NOT a component terminal
    # - A wire endpoint touches the interior of another wire segment (T-junction)
    explicit_juncs = {snap_px(p) for p in doc.junctions}

    endpoint_counts: dict[PointPx, int] = {}
    for _, pts in raw_wires:
        for ep in (pts[0], pts[-1]):
            endpoint_counts[ep] = endpoint_counts.get(ep, 0) + 1

    junction_points: set[PointPx] = set()

    # Check for T-junctions: any wire endpoint landing strictly inside another wire segment
    for _, pts in raw_wires:
        for ep in (pts[0], pts[-1]):
            for other_wid, other_pts in raw_wires:
                for i in range(len(other_pts) - 1):
                    if _point_strictly_inside_segment(ep, other_pts[i], other_pts[i + 1]):
                        junction_points.add(ep)

    # Multiple wire endpoints meeting without a terminal form a junction
    for pt, count in endpoint_counts.items():
        if count >= 3 or (count == 2 and pt not in terminal_by_pos):
            junction_points.add(pt)

    # Explicit v1 junctions that touch wires
    for jp in explicit_juncs:
        # Check if touches any wire
        touches_any = any(
            any(_point_on_segment(jp, pts[i], pts[i + 1]) for i in range(len(pts) - 1))
            for _, pts in raw_wires
        )
        if touches_any:
            junction_points.add(jp)

    # Create Junction objects
    junctions: list[Junction] = []
    pos_to_junction_id: dict[PointPx, str] = {}
    sorted_junc_pts = sorted(junction_points, key=lambda p: (p[0], p[1]))
    for idx, pt in enumerate(sorted_junc_pts, start=1):
        jid = f"J{idx}"
        pos_to_junction_id[pt] = jid
        junctions.append(Junction(jid, pt))

    # 4. Slice wires at internal junction points
    new_wires: list[Wire] = []
    wire_counter = 1

    for orig_id, pts in raw_wires:
        sub_paths = _split_polyline_at_points(pts, junction_points)

        # Convert each sub-path to a Wire
        for sub in sub_paths:
            ep_start = sub[0]
            ep_end = sub[-1]

            def resolve_att(pt: PointPx) -> Attachment:
                if pt in terminal_by_pos:
                    return terminal_by_pos[pt]
                if pt in pos_to_junction_id:
                    return JunctionRef(pos_to_junction_id[pt])
                return FreeEnd(*pt)

            att_a = resolve_att(ep_start)
            att_b = resolve_att(ep_end)
            if att_a == att_b:
                continue

            # Deduplicate wires sharing the same two attachments
            from circuitsim.wiring.model import _find_duplicate
            if _find_duplicate(new_wires, att_a, att_b) is not None:
                continue

            wid = f"W{wire_counter}"
            wire_counter += 1
            hints = tuple(sub[1:-1])
            new_wires.append(Wire(wid, att_a, att_b, hints))

    # Create WireGraph and let it normalize any degree < 3 junctions or stray dots
    # We use WireGraph.remove_wire / normalize by creating the graph directly
    graph = WireGraph(wires=tuple(new_wires), junctions=tuple(junctions))

    # Clean up any degree < 3 junctions using WireGraph merge rules
    affected = [j.id for j in junctions if graph.junction_degree(j.id) < 3]
    if affected:
        # Removing and re-normalizing
        wires_list = list(graph.wires)
        junctions_list = list(graph.junctions)
        from circuitsim.wiring.model import _normalize
        _normalize(wires_list, junctions_list, affected)
        graph = WireGraph(tuple(wires_list), tuple(junctions_list))

    return CircuitDocumentV2(placed=doc.placed, graph=graph, view=doc.view)


# ---------------------------------------------------------------------------
# File I/O (v2)
# ---------------------------------------------------------------------------


def load_document_v2(path: str | os.PathLike[str]) -> CircuitDocumentV2:
    """Read and validate a .circ file (Schema v2 or migrated v1)."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except FileNotFoundError as exc:
        raise CircuitFileError(f"The file '{p.name}' does not exist.") from exc
    except OSError as exc:
        raise CircuitFileError(f"The file '{p.name}' could not be read ({exc}).") from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CircuitFileError(f"'{p.name}' is not a text file, so it is not an {APP_NAME} circuit.") from exc
    return loads_document_v2(text)


def save_document_v2(path: str | os.PathLike[str], doc: CircuitDocumentV2) -> None:
    """Safely write CircuitDocumentV2 to path atomically."""
    target = Path(path)
    text = dumps_document_v2(doc)
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if target.exists():
            shutil.copyfile(target, str(target) + ".bak")
        os.replace(tmp_name, target)
        tmp_name = None
    except OSError as exc:
        raise CircuitFileError(
            f"The circuit could not be saved to '{target.name}' ({exc}). Your previous file was not changed."
        ) from exc
    finally:
        if tmp_name is not None:
            try:
                os.remove(tmp_name)
            except OSError:
                pass
