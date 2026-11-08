"""Save and load CircuitSim `.circ` project files (pure Python, no Qt imports).

A `.circ` file is plain JSON. Example (shortened)::

    {
      "format": "circuitsim",
      "schema_version": 1,
      "components": [
        {"type": "resistor", "name": "R1", "label": "R1", "show_value": true,
         "center_px": [100, 0], "rotation_deg": 90, "flipped_h": false,
         "parameters": {"resistance": 1000.0}, "settings": {}}
      ],
      "wires": [{"id": "W1", "points": [[0, -40], [100, -40]]}],
      "junctions": [[100, -40]],
      "view": {"theme": "dark", "zoom": 1.0, "pan": [0, 0], "simulation_speed": "1x"}
    }

Design rules:
  * Loading is *strict*: any problem raises `CircuitFileError` with a plain
    sentence a student can read. Nothing is half-loaded.
  * Loading only builds new objects (`CircuitDocument`). The window replaces the
    current circuit afterwards, and only if the whole file was valid.
  * Saving is *atomic*: the new text is written to a temporary file next to the
    target, flushed to disk, and only then swapped in with `os.replace`. The
    previous version is kept as `name.circ.bak`.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from circuitsim.canvas.connectivity import PlacedComponentSpec, PointPx, WireSpec
from circuitsim.components.base import Component
from circuitsim.components.factory import (
    KNOWN_COMPONENT_TYPES,
    create_default_component_model,
)

FORMAT_NAME: str = "circuitsim"
SCHEMA_VERSION: int = 1
VALID_ROTATIONS: tuple[int, ...] = (0, 90, 180, 270)
VALID_THEMES: tuple[str, ...] = ("dark", "light")

# Settings that are not in `get_editable_parameters()` but must survive a save.
# kind: "float", "float_or_none", "bool", "str"
_EXTRA_SETTINGS: dict[str, dict[str, str]] = {
    "switch": {
        "closed": "bool",
        "r_off": "float",
        "c_parasitic": "float",
        "toggle_time": "float_or_none",
    },
    "ac_voltage": {"waveform": "str", "phase_deg": "float", "duty_cycle": "float"},
    "lightbulb": {"use_filament_model": "bool", "burnout_enabled": "bool"},
    "voltmeter": {"mode": "str"},
    "ammeter": {"mode": "str"},
}

# Editable parameters that may legitimately be "none" (feature switched off).
_NULLABLE_PARAMETERS: dict[tuple[str, str], bool] = {("switch", "v_breakdown"): True}


class CircuitFileError(Exception):
    """A `.circ` file could not be read or written. The message is user-friendly."""


@dataclass
class ViewState:
    """Window/view settings stored with the circuit."""

    theme: str = "dark"
    zoom: float = 1.0
    pan: tuple[float, float] = (0.0, 0.0)
    simulation_speed: str = "1x"


@dataclass
class CircuitDocument:
    """Everything stored in a `.circ` file, as plain Python objects."""

    placed: list[PlacedComponentSpec] = field(default_factory=list)
    wires: list[WireSpec] = field(default_factory=list)
    junctions: list[PointPx] = field(default_factory=list)
    view: ViewState = field(default_factory=ViewState)


# ----------------------------------------------------------------------
# Small validation helpers
# ----------------------------------------------------------------------


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _require_dict(value: object, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CircuitFileError(f"{what} is not in the expected format.")
    return value


def _require_list(value: object, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise CircuitFileError(f"{what} is not in the expected format.")
    return value


def _require_point(value: object, what: str) -> tuple[float, float]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not _is_number(value[0])
        or not _is_number(value[1])
    ):
        raise CircuitFileError(f"{what} must be a pair of numbers like [100, 40].")
    return (float(value[0]), float(value[1]))


# ----------------------------------------------------------------------
# Document -> dict
# ----------------------------------------------------------------------


def _component_to_dict(spec: PlacedComponentSpec) -> dict[str, Any]:
    comp = spec.component
    ctype = comp.component_type
    parameters: dict[str, Any] = {}
    for p in comp.get_editable_parameters():
        raw = getattr(comp, p.key)
        parameters[p.key] = None if raw is None else float(raw)

    settings: dict[str, Any] = {}
    for key, kind in _EXTRA_SETTINGS.get(ctype, {}).items():
        raw = getattr(comp, key)
        if kind == "bool":
            settings[key] = bool(raw)
        elif kind == "str":
            settings[key] = str(getattr(raw, "value", raw))
        else:
            settings[key] = None if raw is None else float(raw)
    # Note: for a switch "closed" is the position shown on the canvas (what the
    # user sees), so that is what gets saved.

    return {
        "type": ctype,
        "name": comp.name,
        "label": comp.label,
        "show_value": bool(comp.show_value),
        "center_px": [float(spec.center_px[0]), float(spec.center_px[1])],
        "rotation_deg": int(spec.rotation_deg),
        "flipped_h": bool(spec.flipped_h),
        "parameters": parameters,
        "settings": settings,
    }


def document_to_dict(doc: CircuitDocument) -> dict[str, Any]:
    """Convert a `CircuitDocument` into a JSON-ready dictionary."""
    return {
        "format": FORMAT_NAME,
        "schema_version": SCHEMA_VERSION,
        "components": [_component_to_dict(s) for s in doc.placed],
        "wires": [
            {"id": w.wire_id, "points": [[float(x), float(y)] for x, y in w.points]}
            for w in doc.wires
        ],
        "junctions": [[int(x), int(y)] for x, y in doc.junctions],
        "view": {
            "theme": doc.view.theme,
            "zoom": float(doc.view.zoom),
            "pan": [float(doc.view.pan[0]), float(doc.view.pan[1])],
            "simulation_speed": doc.view.simulation_speed,
        },
    }


def dumps_document(doc: CircuitDocument) -> str:
    """Return the JSON text for `doc` (refuses NaN/infinity so the file stays valid)."""
    try:
        return json.dumps(document_to_dict(doc), indent=2, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise CircuitFileError(
            f"The circuit contains a value that cannot be saved ({exc})."
        ) from exc


# ----------------------------------------------------------------------
# dict -> Document (strict validation)
# ----------------------------------------------------------------------


def _check_header(data: object) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
        raise CircuitFileError(
            "This is not a CircuitSim file (the 'format' marker is missing)."
        )
    version = data.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise CircuitFileError("The file has no valid version number.")
    if version > SCHEMA_VERSION:
        raise CircuitFileError(
            "This file was made by a newer version of CircuitSim "
            f"(file version {version}, this program understands up to "
            f"{SCHEMA_VERSION}). Please update CircuitSim to open it."
        )
    if version < 1:
        raise CircuitFileError(f"Unknown file version number {version}.")
    return data


def _apply_setting(comp: Component, ctype: str, key: str, kind: str, value: Any, who: str) -> None:
    if kind == "bool":
        if not isinstance(value, bool):
            raise CircuitFileError(f"{who}: setting '{key}' must be true or false.")
        setattr(comp, key, value)
        if ctype == "switch" and key == "closed":
            comp.initial_closed = value  # type: ignore[attr-defined]
    elif kind == "str":
        if not isinstance(value, str):
            raise CircuitFileError(f"{who}: setting '{key}' must be text.")
        current = getattr(comp, key)
        enum_cls = type(current) if hasattr(current, "value") else None
        try:
            setattr(comp, key, enum_cls(value) if enum_cls else value)
        except ValueError as exc:
            raise CircuitFileError(
                f"{who}: '{value}' is not a valid value for '{key}'."
            ) from exc
    else:
        if value is None and kind == "float_or_none":
            setattr(comp, key, None)
        elif _is_number(value):
            setattr(comp, key, float(value))
        else:
            raise CircuitFileError(f"{who}: setting '{key}' must be a number.")


def _component_from_dict(entry: object, index: int) -> PlacedComponentSpec:
    d = _require_dict(entry, f"Component #{index + 1}")
    ctype = d.get("type")
    if not isinstance(ctype, str) or ctype not in KNOWN_COMPONENT_TYPES:
        raise CircuitFileError(
            f"Component #{index + 1} has an unknown type {ctype!r}. "
            "The file may come from a different program or version."
        )
    name = d.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CircuitFileError(f"Component #{index + 1} has no name.")
    who = f"Component {name}"

    comp = create_default_component_model(ctype, name.strip())

    label = d.get("label", name)
    if not isinstance(label, str):
        raise CircuitFileError(f"{who}: the label must be text.")
    comp.label = label
    show_value = d.get("show_value", True)
    if not isinstance(show_value, bool):
        raise CircuitFileError(f"{who}: 'show_value' must be true or false.")
    comp.show_value = show_value

    params = _require_dict(d.get("parameters", {}), f"{who}: its parameter list")
    allowed = {p.key for p in comp.get_editable_parameters()}
    for key, value in params.items():
        if key not in allowed:
            raise CircuitFileError(f"{who} has an unknown parameter '{key}'.")
        if value is None and _NULLABLE_PARAMETERS.get((ctype, key)):
            setattr(comp, key, None)
            continue
        if not _is_number(value):
            raise CircuitFileError(f"{who}: parameter '{key}' must be a number.")
        try:
            comp.set_parameter_value(key, float(value))
        except ValueError as exc:
            raise CircuitFileError(f"{who}: {exc}") from exc

    settings = _require_dict(d.get("settings", {}), f"{who}: its settings")
    allowed_extra = _EXTRA_SETTINGS.get(ctype, {})
    for key, value in settings.items():
        if key not in allowed_extra:
            raise CircuitFileError(f"{who} has an unknown setting '{key}'.")
        _apply_setting(comp, ctype, key, allowed_extra[key], value, who)

    center = _require_point(d.get("center_px"), f"{who}: 'center_px'")
    rotation = d.get("rotation_deg", 0)
    if isinstance(rotation, bool) or rotation not in VALID_ROTATIONS:
        raise CircuitFileError(f"{who}: rotation must be 0, 90, 180 or 270 degrees.")
    flipped = d.get("flipped_h", False)
    if not isinstance(flipped, bool):
        raise CircuitFileError(f"{who}: 'flipped_h' must be true or false.")

    return PlacedComponentSpec(
        component=comp,
        center_px=center,
        rotation_deg=int(rotation),
        flipped_h=flipped,
    )


def _wire_from_dict(entry: object, index: int) -> WireSpec:
    d = _require_dict(entry, f"Wire #{index + 1}")
    wire_id = d.get("id")
    if not isinstance(wire_id, str) or not wire_id.strip():
        raise CircuitFileError(f"Wire #{index + 1} has no id.")
    pts_raw = _require_list(d.get("points"), f"Wire {wire_id}: its point list")
    if len(pts_raw) < 2:
        raise CircuitFileError(f"Wire {wire_id} needs at least two points.")
    pts = tuple(_require_point(p, f"Wire {wire_id}: a point") for p in pts_raw)
    return WireSpec(wire_id=wire_id, points=pts)


def _view_from_dict(raw: object) -> ViewState:
    if raw is None:
        return ViewState()
    d = _require_dict(raw, "The view settings")
    view = ViewState()
    theme = d.get("theme", view.theme)
    if theme not in VALID_THEMES:
        raise CircuitFileError("The theme in the file must be 'dark' or 'light'.")
    view.theme = theme
    zoom = d.get("zoom", view.zoom)
    if not _is_number(zoom) or zoom <= 0:
        raise CircuitFileError("The zoom level in the file must be a positive number.")
    view.zoom = float(zoom)
    view.pan = _require_point(d.get("pan", [0, 0]), "The view position ('pan')")
    speed = d.get("simulation_speed", view.simulation_speed)
    if not isinstance(speed, str):
        raise CircuitFileError("The simulation speed in the file must be text.")
    view.simulation_speed = speed
    return view


def dict_to_document(data: object) -> CircuitDocument:
    """Validate `data` (parsed JSON) and build a fresh `CircuitDocument`."""
    d = _check_header(data)
    comps_raw = _require_list(d.get("components"), "The component list")
    wires_raw = _require_list(d.get("wires"), "The wire list")
    junctions_raw = _require_list(d.get("junctions", []), "The junction list")

    placed = [_component_from_dict(e, i) for i, e in enumerate(comps_raw)]
    seen: set[str] = set()
    for spec in placed:
        if spec.component.name in seen:
            raise CircuitFileError(
                f"Two components are both named {spec.component.name}."
            )
        seen.add(spec.component.name)

    wires = [_wire_from_dict(e, i) for i, e in enumerate(wires_raw)]
    wire_ids: set[str] = set()
    for w in wires:
        if w.wire_id in wire_ids:
            raise CircuitFileError(f"Two wires both have the id {w.wire_id}.")
        wire_ids.add(w.wire_id)

    junctions: list[PointPx] = []
    for j in junctions_raw:
        x, y = _require_point(j, "A junction")
        junctions.append((int(round(x)), int(round(y))))

    return CircuitDocument(
        placed=placed,
        wires=wires,
        junctions=junctions,
        view=_view_from_dict(d.get("view")),
    )


def loads_document(text: str) -> CircuitDocument:
    """Parse `.circ` JSON text into a `CircuitDocument`."""
    if not text.strip():
        raise CircuitFileError("The file is empty.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CircuitFileError(
            "The file is damaged or incomplete and cannot be read "
            f"(JSON problem at line {exc.lineno}, column {exc.colno})."
        ) from exc
    return dict_to_document(data)


# ----------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------


def load_document(path: str | os.PathLike[str]) -> CircuitDocument:
    """Read and validate a `.circ` file. Never touches anything else."""
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
        raise CircuitFileError(
            f"'{p.name}' is not a text file, so it is not a CircuitSim circuit."
        ) from exc
    return loads_document(text)


def save_document(path: str | os.PathLike[str], doc: CircuitDocument) -> None:
    """Write `doc` to `path` safely.

    Steps: (1) build the text in memory, (2) write it to a temporary file in the
    same folder and flush it to disk, (3) copy the old file to `name.circ.bak`,
    (4) swap the temporary file in with `os.replace` (atomic on Windows and
    Linux). If anything fails, the old file is left exactly as it was.
    """
    target = Path(path)
    text = dumps_document(doc)  # may raise before touching any file
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
        )
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
            f"The circuit could not be saved to '{target.name}' ({exc}). "
            "Your previous file was not changed."
        ) from exc
    finally:
        if tmp_name is not None:
            try:
                os.remove(tmp_name)
            except OSError:
                pass
