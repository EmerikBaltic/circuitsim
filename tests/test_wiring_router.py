"""Unit tests for Item 2: Pure-Python orthogonal wire router with obstacle avoidance and latching."""

from __future__ import annotations

import sys
import pytest

from circuitsim.wiring.router import (
    count_bends,
    infer_initial_orientation,
    route,
    segment_intersects_rect,
    simplify_orthogonal_points,
)


def test_no_qt_imports_in_router_module() -> None:
    """circuitsim.wiring.router must have zero Qt dependencies."""
    import circuitsim.wiring.router as r

    assert not hasattr(r, "QPointF")
    assert not hasattr(r, "QGraphicsItem")
    assert not hasattr(r, "QtCore")


def test_simplify_orthogonal_points() -> None:
    """Collinear intermediate points and redundant duplicates are removed."""
    pts = ((0, 0), (20, 0), (40, 0), (40, 20), (40, 40), (40, 40), (60, 40))
    simplified = simplify_orthogonal_points(pts)
    assert simplified == ((0, 0), (40, 0), (40, 40), (60, 40))


def test_route_straight_horizontal_and_vertical() -> None:
    """Straight orthogonal connection with 0 bends."""
    # Horizontal straight
    h_route = route(
        start=(0, 0),
        end=(100, 0),
        start_dir=(1, 0),
        end_dir=(-1, 0),
    )
    assert h_route == ((0, 0), (100, 0))
    assert count_bends(h_route) == 0

    # Vertical straight
    v_route = route(
        start=(0, 0),
        end=(0, 80),
        start_dir=(0, 1),
        end_dir=(0, -1),
    )
    assert v_route == ((0, 0), (0, 80))
    assert count_bends(v_route) == 0


def test_route_l_shape_one_bend() -> None:
    """L-shape connection with exactly 1 bend."""
    # 1. H first: leaves start to the right, enters end from below
    r_h = route(
        start=(0, 0),
        end=(60, 40),
        start_dir=(1, 0),
        end_dir=(0, -1),
    )
    assert r_h == ((0, 0), (60, 0), (60, 40))
    assert count_bends(r_h) == 1

    # 2. V first: leaves start downwards, enters end from the left
    r_v = route(
        start=(0, 0),
        end=(60, 40),
        start_dir=(0, 1),
        end_dir=(-1, 0),
    )
    assert r_v == ((0, 0), (0, 40), (60, 40))
    assert count_bends(r_v) == 1


def test_route_z_shape_two_bends() -> None:
    """Z-shape connection with at most 2 bends."""
    # Horizontal facing: start points right, end points left
    # Midpoint x = (0 + 100) / 2 = 50 -> snapped to 60 or 40
    r_z_h = route(
        start=(0, 0),
        end=(100, 60),
        start_dir=(1, 0),
        end_dir=(-1, 0),
    )
    assert count_bends(r_z_h) == 2
    assert r_z_h[0] == (0, 0)
    assert r_z_h[-1] == (100, 60)
    # Intermediate segment must be vertical
    assert r_z_h[1][1] == 0
    assert r_z_h[2][1] == 60
    assert r_z_h[1][0] == r_z_h[2][0]

    # Vertical facing: start points down, end points up
    r_z_v = route(
        start=(0, 0),
        end=(60, 100),
        start_dir=(0, 1),
        end_dir=(0, -1),
    )
    assert count_bends(r_z_v) == 2
    assert r_z_v[0] == (0, 0)
    assert r_z_v[-1] == (60, 100)
    assert r_z_v[1][0] == 0
    assert r_z_v[2][0] == 60
    assert r_z_v[1][1] == r_z_v[2][1]


def test_route_facing_and_opposed_terminals() -> None:
    """Facing terminals connect directly; opposed terminals loop cleanly."""
    # Facing terminals connect in 0 bends
    r_facing = route(
        start=(20, 40),
        end=(120, 40),
        start_dir=(1, 0),
        end_dir=(-1, 0),
    )
    assert r_facing == ((20, 40), (120, 40))

    # Opposed terminals (facing away along X):
    # start is at (60, 0) pointing left (-1, 0)
    # end is at (100, 0) pointing right (1, 0)
    r_opposed = route(
        start=(60, 0),
        end=(100, 0),
        start_dir=(-1, 0),
        end_dir=(1, 0),
    )
    assert r_opposed[0] == (60, 0)
    assert r_opposed[-1] == (100, 0)
    # Must leave start moving left (x < 60)
    assert r_opposed[1][0] < 60
    # Must enter end moving left into end (from x > 100)
    assert r_opposed[-2][0] > 100


def test_route_avoids_obstacles() -> None:
    """Router detours around obstacles placed directly in the path."""
    start = (0, 0)
    end = (120, 0)
    # Obstacle directly in the middle between x=40 and x=80, y=-30 to y=30
    obstacle = (40, -30, 80, 30)

    # Route without obstacle is straight
    r_clear = route(start, end, start_dir=(1, 0), end_dir=(-1, 0))
    assert r_clear == (start, end)

    # Route with obstacle detours around it
    r_detour = route(
        start,
        end,
        start_dir=(1, 0),
        end_dir=(-1, 0),
        obstacles=[obstacle],
    )
    assert r_detour[0] == start
    assert r_detour[-1] == end

    # Verify none of the route segments intersect the interior of the obstacle
    for i in range(len(r_detour) - 1):
        p1 = r_detour[i]
        p2 = r_detour[i + 1]
        assert not segment_intersects_rect(p1, p2, obstacle)


def test_route_orientation_latching() -> None:
    """When multiple orthogonal routes are valid, orientation latching preserves stability."""
    start = (0, 0)
    end = (60, 40)
    # When start_dir and end_dir are unconstrained, both H-first and V-first L-shapes are valid.

    # 1. With previous H-first route:
    prev_h = ((0, 0), (60, 0), (60, 40))
    r_latched_h = route(start, end, previous=prev_h)
    assert r_latched_h == ((0, 0), (60, 0), (60, 40))
    assert infer_initial_orientation(r_latched_h) == "H"

    # 2. With previous V-first route:
    prev_v = ((0, 0), (0, 40), (60, 40))
    r_latched_v = route(start, end, previous=prev_v)
    assert r_latched_v == ((0, 0), (0, 40), (60, 40))
    assert infer_initial_orientation(r_latched_v) == "V"

    # 3. Small drag preserving orientation:
    dragged_end = (60, 60)
    r_dragged = route(start, dragged_end, previous=prev_v)
    assert infer_initial_orientation(r_dragged) == "V"


def test_route_determinism() -> None:
    """Same input produces strictly identical output across repeated runs."""
    start = (20, 20)
    end = (140, 100)
    obs = [(40, 20, 80, 80), (100, 40, 120, 120)]
    first = route(start, end, start_dir=(1, 0), end_dir=(0, -1), obstacles=obs)
    for _ in range(50):
        assert route(start, end, start_dir=(1, 0), end_dir=(0, -1), obstacles=obs) == first


def test_route_start_equals_end() -> None:
    """When start equals end, returns a 1-point tuple."""
    assert route((40, 60), (40, 60)) == ((40, 60),)

