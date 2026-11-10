"""Orthogonal wire router with obstacle avoidance and orientation latching (no Qt).

Given a start point, end point, optional outward terminal directions, and a list of
obstacle bounding boxes, this module computes a clean orthogonal route.

Rules:
1. Orthogonal segments only (all points snapped to 20 px grid).
2. Leaves `start` in outward `start_dir` (if given).
3. Arrives at `end` in inward direction `-end_dir` (if given).
4. Avoids obstacles (does not pass through the interior of any obstacle box).
5. Prefers 0 bends (straight), then 1 bend (L), then 2 bends (Z).
6. Falls back to minimal-bend A* grid search when obstacles or terminal orientations
   prevent a direct <= 2 bend path.
7. Orientation latching: if `previous` route is provided, preserves its initial
   orientation (horizontal vs vertical) when multiple options are valid.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Sequence
from typing import NamedTuple

GRID_PX: int = 20
PointPx = tuple[int, int]
Direction = tuple[int, int] | None
RectPx = tuple[int, int, int, int]  # (min_x, min_y, max_x, max_y)


def snap_px(pt: tuple[float, float]) -> PointPx:
    """Snap a 2D point to the 20 px grid."""
    return (int(round(pt[0] / GRID_PX)) * GRID_PX, int(round(pt[1] / GRID_PX)) * GRID_PX)


def normalize_dir(d: Direction) -> Direction:
    """Normalize a direction vector to orthogonal unit vector or None."""
    if d is None:
        return None
    dx, dy = d
    if dx == 0 and dy == 0:
        return None
    if abs(dx) >= abs(dy):
        return (1 if dx > 0 else -1, 0)
    return (0, 1 if dy > 0 else -1)


def normalize_rect(r: tuple[float, float, float, float], margin: int = 0) -> RectPx:
    """Normalize (x1, y1, x2, y2) to (min_x, min_y, max_x, max_y) with optional margin."""
    min_x = int(min(r[0], r[2])) - margin
    max_x = int(max(r[0], r[2])) + margin
    min_y = int(min(r[1], r[3])) - margin
    max_y = int(max(r[1], r[3])) + margin
    return (min_x, min_y, max_x, max_y)


def simplify_orthogonal_points(points: Sequence[PointPx]) -> tuple[PointPx, ...]:
    """Eliminate duplicate consecutive points and remove intermediate collinear points."""
    if not points:
        return ()
    # 1. Remove consecutive duplicates
    cleaned: list[PointPx] = [points[0]]
    for pt in points[1:]:
        if pt != cleaned[-1]:
            cleaned.append(pt)
    if len(cleaned) <= 2:
        return tuple(cleaned)

    # 2. Remove collinear intermediate points
    out: list[PointPx] = [cleaned[0]]
    for i in range(1, len(cleaned) - 1):
        prev = out[-1]
        curr = cleaned[i]
        nxt = cleaned[i + 1]
        # Collinear horizontal
        if prev[1] == curr[1] == nxt[1]:
            continue
        # Collinear vertical
        if prev[0] == curr[0] == nxt[0]:
            continue
        out.append(curr)
    out.append(cleaned[-1])
    return tuple(out)


def infer_initial_orientation(points: Sequence[PointPx] | None) -> str | None:
    """Return 'H' if the first segment is horizontal, 'V' if vertical, else None."""
    if not points or len(points) < 2:
        return None
    p0 = points[0]
    for p1 in points[1:]:
        if p1 != p0:
            return "H" if p0[1] == p1[1] else "V"
    return None


def segment_intersects_rect(p1: PointPx, p2: PointPx, rect: RectPx) -> bool:
    """Return True if the orthogonal segment from p1 to p2 enters the INTERIOR of rect."""
    min_x, min_y, max_x, max_y = rect
    x1, y1 = p1
    x2, y2 = p2

    if y1 == y2:  # Horizontal segment
        y = y1
        if not (min_y < y < max_y):
            return False
        seg_min_x = min(x1, x2)
        seg_max_x = max(x1, x2)
        # Check if the intervals overlap strictly with length > 0
        overlap_min = max(seg_min_x, min_x)
        overlap_max = min(seg_max_x, max_x)
        return overlap_min < overlap_max

    if x1 == x2:  # Vertical segment
        x = x1
        if not (min_x < x < max_x):
            return False
        seg_min_y = min(y1, y2)
        seg_max_y = max(y1, y2)
        overlap_min = max(seg_min_y, min_y)
        overlap_max = min(seg_max_y, max_y)
        return overlap_min < overlap_max

    # Non-orthogonal segment: treat as intersecting bounding area
    return True


def path_collision_free(
    path: Sequence[PointPx],
    obstacles: Sequence[RectPx],
    start: PointPx,
    end: PointPx,
) -> bool:
    """Check if any segment in path intersects an obstacle interior, exempting start/end terminals."""
    if not obstacles:
        return True
    num_segs = len(path) - 1
    for seg_idx in range(num_segs):
        p1 = path[seg_idx]
        p2 = path[seg_idx + 1]
        for rect in obstacles:
            min_x, min_y, max_x, max_y = rect
            # If this is the first segment and start lies on/in rect, exempt leaving rect
            if seg_idx == 0 and (min_x <= start[0] <= max_x and min_y <= start[1] <= max_y):
                continue
            # If this is the last segment and end lies on/in rect, exempt entering rect
            if seg_idx == num_segs - 1 and (min_x <= end[0] <= max_x and min_y <= end[1] <= max_y):
                continue
            if segment_intersects_rect(p1, p2, rect):
                return False
    return True


def path_matches_directions(
    path: Sequence[PointPx],
    start_dir: Direction,
    end_dir: Direction,
) -> bool:
    """Verify that path leaves start in start_dir and enters end in -end_dir."""
    if len(path) < 2:
        return True
    if start_dir is not None:
        p0, p1 = path[0], path[1]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        step_dir = (1 if dx > 0 else (-1 if dx < 0 else 0), 1 if dy > 0 else (-1 if dy < 0 else 0))
        if step_dir != start_dir:
            return False

    if end_dir is not None:
        p_pen, p_last = path[-2], path[-1]
        dx = p_last[0] - p_pen[0]
        dy = p_last[1] - p_pen[1]
        step_dir = (1 if dx > 0 else (-1 if dx < 0 else 0), 1 if dy > 0 else (-1 if dy < 0 else 0))
        inward_dir = (-end_dir[0], -end_dir[1])
        if step_dir != inward_dir:
            return False

    return True


def count_bends(path: Sequence[PointPx]) -> int:
    """Number of 90-degree corners in a simplified orthogonal path."""
    simp = simplify_orthogonal_points(path)
    return max(0, len(simp) - 2)


# ---------------------------------------------------------------------------
# A* Grid Search Fallback
# ---------------------------------------------------------------------------


class _AStarState(NamedTuple):
    cost: int
    x: int
    y: int
    dir_x: int
    dir_y: int
    bends: int


def _route_astar(
    start: PointPx,
    end: PointPx,
    start_dir: Direction,
    end_dir: Direction,
    obstacles: Sequence[RectPx],
    latched_orientation: str | None,
) -> tuple[PointPx, ...]:
    """A* orthogonal grid search avoiding obstacles with minimal bends."""
    inward_dir = (-end_dir[0], -end_dir[1]) if end_dir is not None else None

    # Compute bounding box for grid search with generous margin
    all_x = [start[0], end[0]] + [r[0] for r in obstacles] + [r[2] for r in obstacles]
    all_y = [start[1], end[1]] + [r[1] for r in obstacles] + [r[3] for r in obstacles]
    margin = 120
    min_x = ((min(all_x) - margin) // GRID_PX) * GRID_PX
    max_x = ((max(all_x) + margin + GRID_PX - 1) // GRID_PX) * GRID_PX
    min_y = ((min(all_y) - margin) // GRID_PX) * GRID_PX
    max_y = ((max(all_y) + margin + GRID_PX - 1) // GRID_PX) * GRID_PX

    # Obstacle lookup: check if a 20 px step enters any obstacle
    def can_step(from_pt: PointPx, to_pt: PointPx) -> bool:
        tx, ty = to_pt
        if not (min_x <= tx <= max_x and min_y <= ty <= max_y):
            return False
        for rect in obstacles:
            rx1, ry1, rx2, ry2 = rect
            # Exempt start component for first step
            if from_pt == start and (rx1 <= start[0] <= rx2 and ry1 <= start[1] <= ry2):
                continue
            # Exempt end component for last step
            if to_pt == end and (rx1 <= end[0] <= rx2 and ry1 <= end[1] <= ry2):
                continue
            if segment_intersects_rect(from_pt, to_pt, rect):
                return False
        return True

    # Priority queue: (f_score, cost, x, y, dir_x, dir_y, bends)
    # State key: (x, y, dir_x, dir_y) -> lowest cost
    dist: dict[tuple[int, int, int, int], int] = {}
    parent: dict[tuple[int, int, int, int], tuple[int, int, int, int] | None] = {}

    initial_dirs = [start_dir] if start_dir is not None else [(1, 0), (-1, 0), (0, 1), (0, -1)]
    pq: list[tuple[int, int, int, int, int, int, int]] = []

    for d in initial_dirs:
        dx, dy = d
        state_key = (start[0], start[1], dx, dy)
        dist[state_key] = 0
        parent[state_key] = None
        # Heuristic: Manhattan distance
        h = abs(start[0] - end[0]) + abs(start[1] - end[1])
        heapq.heappush(pq, (h, 0, start[0], start[1], dx, dy, 0))

    target_state: tuple[int, int, int, int] | None = None

    while pq:
        f, cost, x, y, dx, dy, bends = heapq.heappop(pq)
        state_key = (x, y, dx, dy)
        if cost > dist.get(state_key, float("inf")):
            continue

        if (x, y) == end:
            # Check inward direction
            if inward_dir is None or (dx, dy) == inward_dir:
                target_state = state_key
                break

        # Explore neighbors
        # Allowed directions:
        # At start, if start_dir is given, the first step MUST follow start_dir.
        # Otherwise, continue straight or turn 90 degrees (not 180 reverse).
        if (x, y) == start and start_dir is not None:
            possible_dirs = [start_dir]
        else:
            possible_dirs = [(dx, dy), (-dy, dx), (dy, -dx)]

        for ndx, ndy in possible_dirs:
            nx = x + ndx * GRID_PX
            ny = y + ndy * GRID_PX

            # Entering end must match inward_dir
            if (nx, ny) == end and inward_dir is not None and (ndx, ndy) != inward_dir:
                continue

            if not can_step((x, y), (nx, ny)):
                continue

            is_turn = (ndx != dx or ndy != dy)
            new_bends = bends + (1 if is_turn else 0)
            # Step cost: 20 px per step + 80 penalty per turn to favor minimal bends
            step_cost = GRID_PX + (80 if is_turn else 0)
            # Latching bonus
            if (x, y) == start and latched_orientation is not None:
                step_ori = "H" if ndx != 0 else "V"
                if step_ori == latched_orientation:
                    step_cost -= 1

            new_cost = cost + step_cost
            next_key = (nx, ny, ndx, ndy)
            if new_cost < dist.get(next_key, float("inf")):
                dist[next_key] = new_cost
                parent[next_key] = state_key
                h = abs(nx - end[0]) + abs(ny - end[1]) + new_bends * 60
                heapq.heappush(pq, (new_cost + h, new_cost, nx, ny, ndx, ndy, new_bends))

    if target_state is None:
        # Direct fallback line if blocked
        return (start, end)

    # Reconstruct path
    curr: tuple[int, int, int, int] | None = target_state
    rev_pts: list[PointPx] = []
    while curr is not None:
        rev_pts.append((curr[0], curr[1]))
        curr = parent[curr]
    rev_pts.reverse()
    return simplify_orthogonal_points(rev_pts)


# ---------------------------------------------------------------------------
# Main Router
# ---------------------------------------------------------------------------


def route(
    start: tuple[float, float] | PointPx,
    end: tuple[float, float] | PointPx,
    start_dir: Direction = None,
    end_dir: Direction = None,
    obstacles: Iterable[tuple[float, float, float, float]] = (),
    previous: Sequence[PointPx] | None = None,
    *,
    margin: int = 0,
) -> tuple[PointPx, ...]:
    """Calculate an orthogonal obstacle-avoiding route between start and end.

    Parameters
    ----------
    start : (x, y)
        Start terminal position (snapped to 20 px grid).
    end : (x, y)
        End terminal position (snapped to 20 px grid).
    start_dir : (dx, dy) | None
        Outward unit vector leaving start terminal.
    end_dir : (dx, dy) | None
        Outward unit vector leaving end terminal.
    obstacles : iterable of (x1, y1, x2, y2)
        Component bounding boxes to avoid.
    previous : sequence of (x, y) | None
        Previous route points used for orientation latching.
    margin : int
        Extra clearance to inflate obstacle boxes.

    Returns
    -------
    tuple[PointPx, ...]
        Sequence of corner points forming an orthogonal polyline.
    """
    p0 = snap_px(start)
    p3 = snap_px(end)
    if p0 == p3:
        return (p0,)

    s_dir = normalize_dir(start_dir)
    e_dir = normalize_dir(end_dir)
    norm_obstacles = tuple(normalize_rect(r, margin=margin) for r in obstacles)
    latched_ori = infer_initial_orientation(previous)

    # 1. Generate fast analytic candidates (0, 1, 2 bends)
    candidates: list[tuple[PointPx, ...]] = []

    # --- 0-bend (straight line) ---
    if p0[0] == p3[0] or p0[1] == p3[1]:
        cand = (p0, p3)
        if path_matches_directions(cand, s_dir, e_dir) and path_collision_free(
            cand, norm_obstacles, p0, p3
        ):
            return cand

    # --- 1-bend (L-shape) ---
    c_h = (p0, (p3[0], p0[1]), p3)  # H first
    c_v = (p0, (p0[0], p3[1]), p3)  # V first
    l_candidates = [c_h, c_v]
    if latched_ori == "V":
        l_candidates = [c_v, c_h]

    for cand in l_candidates:
        cand_simp = simplify_orthogonal_points(cand)
        if (
            len(cand_simp) == 3
            and path_matches_directions(cand_simp, s_dir, e_dir)
            and path_collision_free(cand_simp, norm_obstacles, p0, p3)
        ):
            candidates.append(cand_simp)

    if candidates:
        return candidates[0]

    # --- 2-bend (Z-shape / U-shape) ---
    # Candidate Z-shapes: H-V-H and V-H-V with midpoint
    mid_x = (int(round((p0[0] + p3[0]) / (2 * GRID_PX)))) * GRID_PX
    mid_y = (int(round((p0[1] + p3[1]) / (2 * GRID_PX)))) * GRID_PX

    z_hvh = (p0, (mid_x, p0[1]), (mid_x, p3[1]), p3)
    z_vhv = (p0, (p0[0], mid_y), (p3[0], mid_y), p3)

    z_candidates = [z_hvh, z_vhv]
    if latched_ori == "V":
        z_candidates = [z_vhv, z_hvh]

    for cand in z_candidates:
        cand_simp = simplify_orthogonal_points(cand)
        if (
            count_bends(cand_simp) <= 2
            and path_matches_directions(cand_simp, s_dir, e_dir)
            and path_collision_free(cand_simp, norm_obstacles, p0, p3)
        ):
            candidates.append(cand_simp)

    if candidates:
        return candidates[0]

    # 2. Fallback: A* Grid Search around obstacles
    return _route_astar(p0, p3, s_dir, e_dir, norm_obstacles, latched_ori)
