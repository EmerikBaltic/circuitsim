"""Pure-Python symbol metadata, grid snapping, and tolerant SVG preparation (no Qt imports).

This module is intentionally free of any PySide6 / Qt dependencies so that
symbol JSON parsing, terminal coordinate transformations, grid snapping, and
SVG validation / theme recolouring can be tested directly with pytest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

GRID_PITCH_PX: int = 20

# Default path to the built-in IEC symbols directory
DEFAULT_IEC_SYMBOLS_DIR: Path = (
    Path(__file__).resolve().parent.parent / "resources" / "symbols" / "iec"
)


@dataclass(frozen=True)
class TerminalSpec:
    """Specification of a single component terminal in grid units relative to center."""

    name: str
    grid_pos: tuple[float, float]

    @property
    def local_px(self) -> tuple[float, float]:
        """Terminal coordinates in pixels relative to component center `(0, 0)`."""
        return (
            self.grid_pos[0] * GRID_PITCH_PX,
            self.grid_pos[1] * GRID_PITCH_PX,
        )


@dataclass(frozen=True)
class SymbolMetadata:
    """Parsed metadata for a schematic component symbol."""

    component_id: str
    display_name: str
    category: str
    style: str
    grid_size: tuple[int, int]
    terminals: tuple[TerminalSpec, ...]
    label_offset: tuple[float, float] = (0.0, -1.1)
    value_offset: tuple[float, float] = (0.0, 1.1)
    default_svg: str = ""
    states: dict[str, str] = field(default_factory=dict)
    symbol_dir: Path = DEFAULT_IEC_SYMBOLS_DIR

    @property
    def pixel_size(self) -> tuple[int, int]:
        """Expected symbol bounding box `(width_px, height_px)` at 100% scale."""
        return (
            self.grid_size[0] * GRID_PITCH_PX,
            self.grid_size[1] * GRID_PITCH_PX,
        )

    def svg_filename_for_state(self, state: str | None = None) -> str:
        """Return the SVG filename for a given state (e.g. 'open'/'closed'), or default."""
        if state and state in self.states:
            return self.states[state]
        return self.default_svg or f"{self.component_id}.svg"

    def svg_path_for_state(self, state: str | None = None) -> Path:
        """Return the full filesystem path to the SVG file for `state`."""
        return self.symbol_dir / self.svg_filename_for_state(state)

    def terminal_in_svg_viewbox(
        self,
        terminal: TerminalSpec,
        *,
        centered_viewbox: bool = False,
    ) -> tuple[float, float]:
        """Return terminal `(x, y)` in SVG coordinates.

        For `viewBox="0 0 80 40"` (`centered_viewbox=False`), the component center
        is at `(width_px / 2, height_px / 2) = (40, 20)`, so `[-2, 0]` maps to `(0, 20)`
        and `[+2, 0]` maps to `(80, 20)`.
        For `viewBox="-40 -20 80 40"` (`centered_viewbox=True`), the center is `(0, 0)`.
        """
        lx, ly = terminal.local_px
        if centered_viewbox:
            return (lx, ly)
        w_px, h_px = self.pixel_size
        return (w_px / 2.0 + lx, h_px / 2.0 + ly)


@dataclass(frozen=True)
class PreparedSvg:
    """Result of validating, cleaning, and recolouring an SVG file for a theme."""

    svg_bytes: bytes | None
    viewbox: tuple[float, float, float, float] | None = None
    warning: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.svg_bytes is not None and self.warning is None


def snap_to_grid(
    x_px: float,
    y_px: float,
    grid_px: int = GRID_PITCH_PX,
) -> tuple[float, float]:
    """Snap a pixel coordinate `(x_px, y_px)` to the nearest grid intersection."""
    if grid_px <= 0:
        raise ValueError("grid_px must be > 0.")
    sx = round(x_px / grid_px) * float(grid_px)
    sy = round(y_px / grid_px) * float(grid_px)
    # Normalize -0.0 to +0.0
    return (0.0 if sx == 0.0 else sx, 0.0 if sy == 0.0 else sy)


def px_to_grid(
    x_px: float,
    y_px: float,
    grid_px: int = GRID_PITCH_PX,
) -> tuple[float, float]:
    """Convert pixel coordinates to grid units."""
    if grid_px <= 0:
        raise ValueError("grid_px must be > 0.")
    return (x_px / float(grid_px), y_px / float(grid_px))


def grid_to_px(
    gx: float,
    gy: float,
    grid_px: int = GRID_PITCH_PX,
) -> tuple[float, float]:
    """Convert grid units to pixel coordinates."""
    if grid_px <= 0:
        raise ValueError("grid_px must be > 0.")
    return (gx * float(grid_px), gy * float(grid_px))


def transform_terminal_position(
    local_grid_pos: tuple[float, float],
    center_px: tuple[float, float],
    *,
    rotation_deg: int = 0,
    flipped_h: bool = False,
    grid_px: int = GRID_PITCH_PX,
) -> tuple[float, float]:
    """Compute scene pixel coordinates of a terminal after flip and 90-degree rotation.

    Order of local transforms (matching `ComponentItem` transform order):
        1. Horizontal mirror (`lx = -lx` if `flipped_h` is True).
        2. Clockwise rotation in screen coordinates (`+90°` maps `(x, y) -> (-y, x)`).
        3. Translation by `center_px`.
    """
    lx = local_grid_pos[0] * float(grid_px)
    ly = local_grid_pos[1] * float(grid_px)
    if flipped_h:
        lx = -lx

    angle_rad = math.radians(rotation_deg % 360)
    cos_a = round(math.cos(angle_rad), 12)
    sin_a = round(math.sin(angle_rad), 12)

    rx = lx * cos_a - ly * sin_a
    ry = lx * sin_a + ly * cos_a

    tx = center_px[0] + rx
    ty = center_px[1] + ry
    return snap_to_grid(tx, ty, grid_px=grid_px)


def parse_symbol_metadata_dict(
    data: dict[str, object],
    *,
    symbol_dir: Path = DEFAULT_IEC_SYMBOLS_DIR,
) -> SymbolMetadata:
    """Validate and convert a JSON dictionary into a `SymbolMetadata` instance."""
    comp_id = str(data.get("id", "")).strip()
    if not comp_id:
        raise ValueError("Symbol metadata JSON is missing non-empty 'id'.")

    raw_size = data.get("grid_size")
    if (
        not isinstance(raw_size, list)
        or len(raw_size) != 2
        or int(raw_size[0]) <= 0
        or int(raw_size[1]) <= 0
    ):
        raise ValueError(
            f"Symbol {comp_id!r}: 'grid_size' must be [width, height] with positive integers."
        )
    grid_size = (int(raw_size[0]), int(raw_size[1]))

    raw_terminals = data.get("terminals")
    if not isinstance(raw_terminals, list) or not raw_terminals:
        raise ValueError(f"Symbol {comp_id!r}: 'terminals' must be a non-empty list.")

    terminals: list[TerminalSpec] = []
    for t_entry in raw_terminals:
        if not isinstance(t_entry, dict):
            raise ValueError(f"Symbol {comp_id!r}: terminal entry must be an object.")
        t_name = str(t_entry.get("name", "")).strip()
        t_pos = t_entry.get("grid_pos")
        if (
            not t_name
            or not isinstance(t_pos, list)
            or len(t_pos) != 2
        ):
            raise ValueError(
                f"Symbol {comp_id!r}: each terminal needs 'name' and 'grid_pos': [gx, gy]."
            )
        terminals.append(
            TerminalSpec(name=t_name, grid_pos=(float(t_pos[0]), float(t_pos[1])))
        )

    raw_lbl = data.get("label_offset", [0.0, -1.1])
    raw_val = data.get("value_offset", [0.0, 1.1])
    label_offset = (
        (float(raw_lbl[0]), float(raw_lbl[1]))
        if isinstance(raw_lbl, list) and len(raw_lbl) == 2
        else (0.0, -1.1)
    )
    value_offset = (
        (float(raw_val[0]), float(raw_val[1]))
        if isinstance(raw_val, list) and len(raw_val) == 2
        else (0.0, 1.1)
    )

    display_name = str(data.get("display_name", comp_id.replace("_", " ").title()))
    category = str(data.get("category", "Misc"))
    style = str(data.get("style", "iec"))
    default_svg = str(data.get("default_svg", f"{comp_id}.svg"))

    raw_states = data.get("states", {})
    states: dict[str, str] = {}
    if isinstance(raw_states, dict):
        for k, v in raw_states.items():
            states[str(k)] = str(v)

    return SymbolMetadata(
        component_id=comp_id,
        display_name=display_name,
        category=category,
        style=style,
        grid_size=grid_size,
        terminals=tuple(terminals),
        label_offset=label_offset,
        value_offset=value_offset,
        default_svg=default_svg,
        states=states,
        symbol_dir=symbol_dir,
    )


def load_symbol_metadata(json_path: Path) -> SymbolMetadata:
    """Load and validate a single `.json` symbol metadata file."""
    raw_text = json_path.read_text(encoding="utf-8")
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError(f"Symbol metadata file {json_path} must contain a JSON object.")
    return parse_symbol_metadata_dict(data, symbol_dir=json_path.parent)


def load_all_iec_metadata(
    symbols_dir: Path = DEFAULT_IEC_SYMBOLS_DIR,
) -> dict[str, SymbolMetadata]:
    """Load all `.json` symbol metadata files from `symbols_dir` keyed by component id."""
    catalog: dict[str, SymbolMetadata] = {}
    if not symbols_dir.exists():
        return catalog
    for json_path in sorted(symbols_dir.glob("*.json")):
        meta = load_symbol_metadata(json_path)
        catalog[meta.component_id] = meta
    return catalog


def _local_tag_name(tag: str) -> str:
    """Strip XML namespace URI `{http://...}tag` down to `tag`."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_numeric_length(raw: str | None) -> float | None:
    if not raw:
        return None
    cleaned = raw.strip().removesuffix("px").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _is_background_rect(
    elem: ET.Element,
    min_x: float,
    min_y: float,
    exp_w: float,
    exp_h: float,
) -> bool:
    """Return True if `elem` is a full-canvas background rectangle exported by an editor."""
    if _local_tag_name(elem.tag).lower() != "rect":
        return False

    elem_id = (elem.attrib.get("id") or "").lower()
    if any(
        elem_id.startswith(prefix)
        for prefix in ("bg", "background", "artboard", "canvas", "frame")
    ):
        return True

    w = _parse_numeric_length(elem.attrib.get("width"))
    h = _parse_numeric_length(elem.attrib.get("height"))
    if w is None or h is None:
        return False

    if not (math.isclose(w, exp_w, abs_tol=0.5) and math.isclose(h, exp_h, abs_tol=0.5)):
        return False

    x = _parse_numeric_length(elem.attrib.get("x")) or 0.0
    y = _parse_numeric_length(elem.attrib.get("y")) or 0.0
    if not (
        math.isclose(x, min_x, abs_tol=0.5) and math.isclose(y, min_y, abs_tol=0.5)
    ):
        return False

    # A full-artboard rect covering the entire viewBox (80x40 or 40x40) is a background
    # rectangle (IEC component bodies are much smaller than the full terminal-to-terminal span).
    return True


_BLACK_COLOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"#000000\b", re.IGNORECASE),
    re.compile(r"#000\b(?![0-9a-fA-F])", re.IGNORECASE),
    re.compile(r"\bcurrentColor\b", re.IGNORECASE),
    re.compile(r"\brgb\(\s*0\s*,\s*0\s*,\s*0\s*\)", re.IGNORECASE),
    re.compile(r'(?<=[":\s])black(?=["\s;]|$)', re.IGNORECASE),
)


def prepare_svg_for_theme(
    svg_source: str | Path,
    metadata: SymbolMetadata,
    *,
    stroke_color: str = "#E6EDF3",
) -> PreparedSvg:
    """Validate, sanitize, and recolour an SVG for the active theme.

    Rules enforced:
        1. Tolerant XML parsing: ignores Inkscape/Sodipodi/Figma `<metadata>` and
           `<namedview>` elements and removes any full-canvas background `<rect>`.
        2. Validates `viewBox` (or `width`/`height` if `viewBox` is omitted) against
           `metadata.pixel_size` (`80x40` for 4x2 components, `40x40` for 2x2 ground).
           Supports both `viewBox="0 0 W H"` and centered `viewBox="-W/2 -H/2 W H"`.
        3. Recolours `#000000`, `#000`, `black`, `rgb(0,0,0)`, and `currentColor`
           to `stroke_color`.
        4. Never raises on malformed XML or mismatched dimensions; returns a
           `PreparedSvg` with `svg_bytes=None` and a descriptive `warning` string.
    """
    source_label = str(svg_source)
    if isinstance(svg_source, Path):
        if not svg_source.exists():
            return PreparedSvg(
                svg_bytes=None,
                warning=f"SVG file does not exist: {svg_source.name}",
            )
        try:
            raw_xml = svg_source.read_text(encoding="utf-8")
        except OSError as exc:
            return PreparedSvg(
                svg_bytes=None,
                warning=f"Could not read SVG file {svg_source.name}: {exc}",
            )
    else:
        raw_xml = str(svg_source)

    if not raw_xml.strip():
        return PreparedSvg(
            svg_bytes=None,
            warning=f"SVG source for {metadata.component_id!r} is empty.",
        )

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        return PreparedSvg(
            svg_bytes=None,
            warning=f"Invalid XML in SVG for {metadata.component_id!r} ({source_label}): {exc}",
        )

    if _local_tag_name(root.tag).lower() != "svg":
        return PreparedSvg(
            svg_bytes=None,
            warning=f"Root element in {source_label} is <{_local_tag_name(root.tag)}>, expected <svg>.",
        )

    exp_w, exp_h = metadata.pixel_size
    vb_raw = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    if vb_raw:
        parts = [p for p in re.split(r"[\s,]+", vb_raw.strip()) if p]
        if len(parts) != 4:
            return PreparedSvg(
                svg_bytes=None,
                warning=f"Invalid viewBox={vb_raw!r} in {source_label}; expected 4 numbers.",
            )
        try:
            min_x, min_y, vb_w, vb_h = (float(p) for p in parts)
        except ValueError:
            return PreparedSvg(
                svg_bytes=None,
                warning=f"Non-numeric viewBox={vb_raw!r} in {source_label}.",
            )
    else:
        w_val = _parse_numeric_length(root.attrib.get("width"))
        h_val = _parse_numeric_length(root.attrib.get("height"))
        if w_val is None or h_val is None:
            return PreparedSvg(
                svg_bytes=None,
                warning=(
                    f"SVG for {metadata.component_id!r} is missing both viewBox and "
                    "width/height attributes."
                ),
            )
        min_x, min_y, vb_w, vb_h = 0.0, 0.0, w_val, h_val
        root.attrib["viewBox"] = f"0 0 {int(exp_w)} {int(exp_h)}"

    # Verify dimensions match metadata.pixel_size
    if not (
        math.isclose(vb_w, exp_w, abs_tol=0.5)
        and math.isclose(vb_h, exp_h, abs_tol=0.5)
    ):
        return PreparedSvg(
            svg_bytes=None,
            warning=(
                f"SVG viewBox size ({vb_w:g}x{vb_h:g}) for {metadata.component_id!r} "
                f"does not match JSON grid_size {metadata.grid_size} "
                f"({exp_w}x{exp_h} px)."
            ),
        )

    # Verify origin is either top-left (0, 0) or centered (-W/2, -H/2)
    is_top_left = math.isclose(min_x, 0.0, abs_tol=0.5) and math.isclose(
        min_y, 0.0, abs_tol=0.5
    )
    is_centered = math.isclose(min_x, -exp_w / 2.0, abs_tol=0.5) and math.isclose(
        min_y, -exp_h / 2.0, abs_tol=0.5
    )
    if not (is_top_left or is_centered):
        return PreparedSvg(
            svg_bytes=None,
            warning=(
                f"SVG viewBox origin ({min_x:g}, {min_y:g}) for {metadata.component_id!r} "
                f"must be (0, 0) or ({-exp_w / 2:g}, {-exp_h / 2:g})."
            ),
        )

    # Strip editor metadata tags and full-canvas background rectangles recursively
    def clean_children(parent: ET.Element) -> None:
        to_remove: list[ET.Element] = []
        for child in list(parent):
            local = _local_tag_name(child.tag).lower()
            if local in ("metadata", "namedview", "title", "desc"):
                to_remove.append(child)
            elif _is_background_rect(child, min_x, min_y, exp_w, exp_h):
                to_remove.append(child)
            else:
                clean_children(child)
        for child in to_remove:
            parent.remove(child)

    clean_children(root)

    serialized = ET.tostring(root, encoding="unicode")
    recoloured = serialized
    for pattern in _BLACK_COLOR_PATTERNS:
        recoloured = pattern.sub(stroke_color, recoloured)

    return PreparedSvg(
        svg_bytes=recoloured.encode("utf-8"),
        viewbox=(min_x, min_y, vb_w, vb_h),
        warning=None,
    )
