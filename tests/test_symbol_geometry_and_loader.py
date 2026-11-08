"""Unit tests for pure-Python symbol metadata, grid snapping, and tolerant SVG loader."""

from __future__ import annotations

import math
import pytest

from circuitsim.canvas.symbol_geometry import (
    GRID_PITCH_PX,
    grid_to_px,
    load_all_iec_metadata,
    parse_symbol_metadata_dict,
    prepare_svg_for_theme,
    px_to_grid,
    snap_to_grid,
    transform_terminal_position,
)


def test_load_all_11_iec_symbol_metadata_files() -> None:
    """Verify all 11 Milestone 1-2 IEC symbol metadata JSON files exist and are valid."""
    catalog = load_all_iec_metadata()
    expected_ids = {
        "resistor",
        "capacitor",
        "inductor",
        "dc_voltage",
        "ac_voltage",
        "dc_current",
        "ground",
        "switch",
        "lightbulb",
        "voltmeter",
        "ammeter",
    }
    assert set(catalog.keys()) == expected_ids

    # Check standard 2-terminal 4x2 footprint (80x40 px) and terminals at [-2, 0], [2, 0]
    res_meta = catalog["resistor"]
    assert res_meta.grid_size == (4, 2)
    assert res_meta.pixel_size == (80, 40)
    assert len(res_meta.terminals) == 2
    assert res_meta.terminals[0].grid_pos == (-2.0, 0.0)
    assert res_meta.terminals[1].grid_pos == (2.0, 0.0)
    assert res_meta.terminals[0].local_px == (-40.0, 0.0)
    assert res_meta.terminals[1].local_px == (40.0, 0.0)

    # Check terminal coordinates in viewBox="0 0 80 40" vs viewBox="-40 -20 80 40"
    assert res_meta.terminal_in_svg_viewbox(
        res_meta.terminals[0], centered_viewbox=False
    ) == (0.0, 20.0)
    assert res_meta.terminal_in_svg_viewbox(
        res_meta.terminals[1], centered_viewbox=False
    ) == (80.0, 20.0)
    assert res_meta.terminal_in_svg_viewbox(
        res_meta.terminals[0], centered_viewbox=True
    ) == (-40.0, 0.0)
    assert res_meta.terminal_in_svg_viewbox(
        res_meta.terminals[1], centered_viewbox=True
    ) == (40.0, 0.0)

    # Check ground 2x2 footprint (40x40 px) and terminal at [0, -1] -> (20, 0) in 0 0 40 40
    gnd_meta = catalog["ground"]
    assert gnd_meta.grid_size == (2, 2)
    assert gnd_meta.pixel_size == (40, 40)
    assert len(gnd_meta.terminals) == 1
    assert gnd_meta.terminals[0].grid_pos == (0.0, -1.0)
    assert gnd_meta.terminal_in_svg_viewbox(
        gnd_meta.terminals[0], centered_viewbox=False
    ) == (20.0, 0.0)

    # Check switch states
    sw_meta = catalog["switch"]
    assert sw_meta.svg_filename_for_state("open") == "switch_open.svg"
    assert sw_meta.svg_filename_for_state("closed") == "switch_closed.svg"


def test_grid_snapping_and_terminal_transforms() -> None:
    """Verify 20 px grid snapping and terminal rotation/flip coordinate math."""
    assert GRID_PITCH_PX == 20
    assert snap_to_grid(23.4, -17.9) == (20.0, -20.0)
    assert snap_to_grid(9.9, -9.9) == (0.0, 0.0)
    assert grid_to_px(-2.0, 1.0) == (-40.0, 20.0)
    assert px_to_grid(-40.0, 20.0) == (-2.0, 1.0)

    # Terminal a at [-2, 0] around center (100, 200):
    # 0 deg, unflipped -> (60, 200)
    assert transform_terminal_position((-2.0, 0.0), (100.0, 200.0), rotation_deg=0) == (
        60.0,
        200.0,
    )
    # 0 deg, horizontally flipped -> (140, 200)
    assert transform_terminal_position(
        (-2.0, 0.0), (100.0, 200.0), rotation_deg=0, flipped_h=True
    ) == (140.0, 200.0)
    # 90 deg CW: (-40, 0) rotates to (0, -40) -> (100, 160)
    assert transform_terminal_position(
        (-2.0, 0.0), (100.0, 200.0), rotation_deg=90
    ) == (100.0, 160.0)
    # 180 deg: (-40, 0) rotates to (+40, 0) -> (140, 200)
    assert transform_terminal_position(
        (-2.0, 0.0), (100.0, 200.0), rotation_deg=180
    ) == (140.0, 200.0)
    # 270 deg CW: (-40, 0) rotates to (0, +40) -> (100, 240)
    assert transform_terminal_position(
        (-2.0, 0.0), (100.0, 200.0), rotation_deg=270
    ) == (100.0, 240.0)


def test_svg_loader_supports_top_left_and_centered_viewbox_and_recolours() -> None:
    """Verify viewBox='0 0 80 40' and '-40 -20 80 40' and #000000 theme recolouring."""
    res_meta = load_all_iec_metadata()["resistor"]

    svg_top_left = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 40" width="80" height="40">
      <line x1="0" y1="20" x2="22" y2="20" stroke="#000000" stroke-width="2" fill="none"/>
      <rect x="22" y="13" width="36" height="14" stroke="#000000" stroke-width="2" fill="none"/>
      <line x1="58" y1="20" x2="80" y2="20" stroke="#000000" stroke-width="2" fill="none"/>
    </svg>
    """
    dark_prep = prepare_svg_for_theme(svg_top_left, res_meta, stroke_color="#E6EDF3")
    assert dark_prep.is_valid
    assert dark_prep.viewbox == (0.0, 0.0, 80.0, 40.0)
    assert dark_prep.svg_bytes is not None
    dark_text = dark_prep.svg_bytes.decode("utf-8")
    assert "#E6EDF3" in dark_text
    assert "#000000" not in dark_text

    light_prep = prepare_svg_for_theme(svg_top_left, res_meta, stroke_color="#1F2328")
    assert light_prep.is_valid
    assert light_prep.svg_bytes is not None
    assert "#1F2328" in light_prep.svg_bytes.decode("utf-8")

    # Centered viewBox="-40 -20 80 40"
    svg_centered = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="-40 -20 80 40">
      <path d="M -40 0 L 40 0" stroke="currentColor" stroke-width="2" fill="none"/>
    </svg>
    """
    centered_prep = prepare_svg_for_theme(
        svg_centered, res_meta, stroke_color="#E6EDF3"
    )
    assert centered_prep.is_valid
    assert centered_prep.viewbox == (-40.0, -20.0, 80.0, 40.0)


def test_svg_loader_strips_inkscape_figma_metadata_and_background_rect() -> None:
    """Verify editor metadata and full-artboard background rects are removed cleanly."""
    res_meta = load_all_iec_metadata()["resistor"]
    inkscape_figma_svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
         viewBox="0 0 80 40" width="80" height="40">
      <metadata id="metadata1">Inkscape cruft</metadata>
      <sodipodi:namedview id="base" pagecolor="#ffffff"/>
      <rect id="bg_artboard" x="0" y="0" width="80" height="40" fill="#FFFFFF"/>
      <rect id="resistor_body" x="22" y="13" width="36" height="14" stroke="#000000" stroke-width="2" fill="none"/>
    </svg>
    """
    prep = prepare_svg_for_theme(
        inkscape_figma_svg, res_meta, stroke_color="#E6EDF3"
    )
    assert prep.is_valid
    assert prep.svg_bytes is not None
    cleaned_xml = prep.svg_bytes.decode("utf-8")
    # Background 80x40 rect and metadata must be gone, while the 36x14 resistor_body rect stays!
    assert "bg_artboard" not in cleaned_xml
    assert "metadata1" not in cleaned_xml
    assert "namedview" not in cleaned_xml
    assert "resistor_body" in cleaned_xml


def test_svg_loader_rejects_malformed_xml_or_mismatched_dimensions_gracefully() -> None:
    """Verify invalid XML or wrong viewBox dimensions return a readable warning instead of crashing."""
    res_meta = load_all_iec_metadata()["resistor"]

    # 1. Malformed XML
    bad_xml = "<svg viewBox='0 0 80 40'><line x1='0'></svg>"
    res_bad = prepare_svg_for_theme(bad_xml, res_meta)
    assert not res_bad.is_valid
    assert res_bad.svg_bytes is None
    assert res_bad.warning is not None
    assert "Invalid XML" in res_bad.warning

    # 2. Wrong dimensions (100x60 instead of 80x40)
    wrong_size_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60"></svg>'
    res_size = prepare_svg_for_theme(wrong_size_svg, res_meta)
    assert not res_size.is_valid
    assert res_size.svg_bytes is None
    assert res_size.warning is not None
    assert "does not match JSON grid_size" in res_size.warning


def test_parse_symbol_metadata_dict_validation() -> None:
    """Verify invalid metadata dictionaries raise clear ValueErrors."""
    with pytest.raises(ValueError, match="missing non-empty 'id'"):
        parse_symbol_metadata_dict({})

    with pytest.raises(ValueError, match="grid_size"):
        parse_symbol_metadata_dict({"id": "bad", "grid_size": [0, 2]})

    with pytest.raises(ValueError, match="terminals"):
        parse_symbol_metadata_dict({"id": "bad", "grid_size": [4, 2], "terminals": []})
    _ = math
