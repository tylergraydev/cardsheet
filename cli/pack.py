"""
pack.py - fit N stickers into the Print Then Cut area, as large as possible.

The area Cricut gives you is not a rectangle. It is a rectangle with the four
corners cut away in a staircase, because that is where the registration marks
live. So the region is carried as a raster mask rather than a width and height,
and any shape works: change the mask and nothing else has to change.

Sizing rule: every sticker gets the SAME AREA, with its own aspect ratio kept.

    w = sqrt(area * aspect)      h = sqrt(area / aspect)

Then binary search for the largest area where they all still fit. Equal area is
what makes the results comparable. A wide sticker and a tall one come out
looking the same size, rather than one being 1 and the other 40.

Placement is lowest-then-leftmost fit, evaluated for every position at once
with a summed-area table, which is what lets an arbitrary region work: a
position is legal exactly when the window sum over the occupancy mask is zero.
"""
from __future__ import annotations

import sys

import numpy as np

sys.setrecursionlimit(20000)

MM_PER_IN = 25.4


class Region:
    """Allowed area as a mask. Blocked cells are True."""

    def __init__(self, w_mm: float, h_mm: float, res_mm: float = 0.5):
        self.res = res_mm
        self.w_mm, self.h_mm = w_mm, h_mm
        self.nx = int(round(w_mm / res_mm))
        self.ny = int(round(h_mm / res_mm))
        self.blocked = np.zeros((self.ny, self.nx), dtype=bool)

    def block_corner_staircase(self, cut_mm: float, steps: int = 3):
        """Cut a staircase out of each corner, where the marks sit.

        Blocked out to the OUTER envelope of the diagonal, so a sticker is
        never placed somewhere the real area might not reach.
        """
        for k in range(steps):
            dx = int(round(cut_mm * (k + 1) / steps / self.res))
            dy = int(round(cut_mm * (steps - k) / steps / self.res))
            for x0, x1 in ((0, dx), (self.nx - dx, self.nx)):
                for y0, y1 in ((0, dy), (self.ny - dy, self.ny)):
                    self.blocked[y0:y1, x0:x1] = True

    def area_mm2(self) -> float:
        return float((~self.blocked).sum()) * self.res * self.res


def _sat(mask: np.ndarray) -> np.ndarray:
    s = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), dtype=np.int32)
    s[1:, 1:] = mask.astype(np.int32).cumsum(0).cumsum(1)
    return s


def _lowest_fit(sat: np.ndarray, wc: int, hc: int):
    """Lowest then leftmost cell where a wc x hc window is entirely free."""
    ny, nx = sat.shape[0] - 1, sat.shape[1] - 1
    if wc > nx or hc > ny or wc <= 0 or hc <= 0:
        return None
    win = (sat[hc:, wc:] - sat[:-hc, wc:] - sat[hc:, :-wc] + sat[:-hc, :-wc])
    ys, xs = np.nonzero(win == 0)
    if len(ys) == 0:
        return None
    i = np.lexsort((xs, ys))[0]          # lowest y, then leftmost x
    return int(xs[i]), int(ys[i])


def _place_all(sizes, region, gap_mm):
    """sizes = [(w_mm, h_mm, index)] largest first. None if any fails."""
    res = region.res
    occ = region.blocked.copy()
    g = gap_mm
    out = []
    for w, h, idx in sizes:
        best = None
        sat = _sat(occ)
        for pw, ph, rot in ((w, h, False), (h, w, True)):
            wc = int(np.ceil((pw + g) / res))
            hc = int(np.ceil((ph + g) / res))
            pos = _lowest_fit(sat, wc, hc)
            if pos is None:
                continue
            cand = (pos[1], pos[0], pos, pw, ph, rot, wc, hc)
            if best is None or cand[:2] < best[:2]:
                best = cand
        if best is None:
            return None
        (_, _, (cx, cy), pw, ph, rot, wc, hc) = best
        occ[cy:cy + hc, cx:cx + wc] = True
        out.append((cx * res, cy * res, pw, ph, idx, rot))
    return out


def _orderings(aspects, area, restarts: int = 6):
    """Every sticker has the same area, so only the SHAPES differ. Order
    matters a lot for greedy packing, and no single rule wins, so try a few
    deterministic rules and then seeded shuffles."""
    dims = [(float(np.sqrt(area * a)), float(np.sqrt(area / a)), i)
            for i, a in enumerate(aspects)]
    yield sorted(dims, key=lambda d: -max(d[0], d[1]))        # longest side
    yield sorted(dims, key=lambda d: -d[1])                   # tallest
    yield sorted(dims, key=lambda d: -d[0])                   # widest
    yield sorted(dims, key=lambda d: -abs(np.log(d[0] / d[1])))  # most extreme
    rng = np.random.default_rng(12345)
    for _ in range(restarts):
        yield [dims[i] for i in rng.permutation(len(dims))]


def fits(aspects, area, region, gap_mm):
    seen = set()
    for order in _orderings(aspects, area):
        key = tuple(d[2] for d in order)
        if key in seen:
            continue
        seen.add(key)
        got = _place_all(order, region, gap_mm)
        if got:
            return got
    return None


def solve(aspects, region, gap_mm=2.0, tol=1.0):
    """Largest equal area in mm^2 that fits. Returns (area_mm2, placements)."""
    if not aspects:
        return 0.0, []
    hi = region.area_mm2() / len(aspects)
    got = fits(aspects, hi, region, gap_mm)
    if got:
        return hi, got
    lo, best = 0.0, None
    for _ in range(40):
        if hi - lo < tol:
            break
        mid = (lo + hi) / 2
        got = fits(aspects, mid, region, gap_mm)
        if got:
            lo, best = mid, got
        else:
            hi = mid
    return lo, best


# ---------------------------------------------------------------------------
# Irregular (die-cut) stickers.
#
# Packing bounding boxes wastes whatever the silhouette does not fill, which
# for these is about a third. Nesting lets one sticker's concave gap hold a
# neighbour's tail. The region is already a mask, so the only change is the
# legality test: instead of asking whether a rectangular window is clear, ask
# whether the SHAPE overlaps anything, which is a correlation. Zero overlap
# positions are exactly where the convolution is zero.
# ---------------------------------------------------------------------------

def _shape_cells(alpha, w_mm, h_mm, res, grow_cells):
    """Resample an alpha mask to w x h mm in grid cells, grown by the gap."""
    from PIL import Image as _I
    from scipy import ndimage as _nd
    wc = max(1, int(round(w_mm / res)))
    hc = max(1, int(round(h_mm / res)))
    im = _I.fromarray((alpha >= 128).astype(np.uint8) * 255).resize((wc, hc), _I.BILINEAR)
    m = np.asarray(im) >= 128
    if grow_cells > 0:
        m = _nd.binary_dilation(m, iterations=int(grow_cells))
    return m


def _place_shapes(items, region, gap_mm):
    """items = [(alpha, w_mm, h_mm, index)] largest first. None if any fails."""
    from scipy.signal import fftconvolve
    res = region.res
    occ = region.blocked.copy()
    grow = max(0, int(round(gap_mm / 2 / res)))
    out = []
    for alpha, w, h, idx in items:
        best = None
        for rot in (False, True):
            a = np.rot90(alpha) if rot else alpha
            ww, hh = (h, w) if rot else (w, h)
            s = _shape_cells(a, ww, hh, res, grow)
            if s.shape[0] > occ.shape[0] or s.shape[1] > occ.shape[1]:
                continue
            conv = fftconvolve(occ.astype(np.float32), s[::-1, ::-1].astype(np.float32),
                               mode="valid")
            ys, xs = np.nonzero(conv < 0.5)
            if len(ys) == 0:
                continue
            i = np.lexsort((xs, ys))[0]
            cand = (int(ys[i]), int(xs[i]), s, ww, hh, rot)
            if best is None or cand[:2] < best[:2]:
                best = cand
        if best is None:
            return None
        cy, cx, s, ww, hh, rot = best
        occ[cy:cy + s.shape[0], cx:cx + s.shape[1]] |= s
        out.append((cx * res, cy * res, ww, hh, idx, rot))
    return out


def fits_shapes(alphas, aspects, area, region, gap_mm, restarts=2):
    dims = [(alphas[i], float(np.sqrt(area * a)), float(np.sqrt(area / a)), i)
            for i, a in enumerate(aspects)]
    orders = [sorted(dims, key=lambda d: -max(d[1], d[2])),
              sorted(dims, key=lambda d: -d[2])]
    rng = np.random.default_rng(99)
    orders += [[dims[i] for i in rng.permutation(len(dims))] for _ in range(restarts)]
    for o in orders:
        got = _place_shapes(o, region, gap_mm)
        if got:
            return got
    return None


def solve_shapes(alphas, region, gap_mm=2.0, tol=2.0):
    """Largest equal BOUNDING-BOX area that fits when shapes may interlock."""
    aspects = [a.shape[1] / a.shape[0] for a in alphas]
    hi = region.area_mm2() / max(len(alphas), 1) * 2.5
    lo, best = 0.0, None
    for _ in range(30):
        if hi - lo < tol:
            break
        mid = (lo + hi) / 2
        got = fits_shapes(alphas, aspects, mid, region, gap_mm)
        if got:
            lo, best = mid, got
        else:
            hi = mid
    return lo, best


# ---------------------------------------------------------------------------
# Turning an alpha mask into a cut path.
#
# Design Space needs a vector outline, so the silhouette is boundary-traced
# (Moore neighbourhood) and then simplified with Douglas-Peucker. Traced at the
# image's own resolution and scaled afterwards, so simplification tolerance is
# in source pixels and does not change with the printed size.
# ---------------------------------------------------------------------------

_MOORE = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def trace_outline(alpha, thresh=128):
    """Outer boundary of the largest blob, as [(x, y)] in pixel coords."""
    from scipy import ndimage as _nd
    m = alpha >= thresh
    lab, n = _nd.label(m)
    if n == 0:
        raise ValueError("empty alpha")
    sizes = _nd.sum(m, lab, range(1, n + 1))
    m = (lab == (int(np.argmax(sizes)) + 1))
    m = _nd.binary_fill_holes(m)
    m = np.pad(m, 1)

    ys, xs = np.nonzero(m)
    y0 = int(ys.min())
    x0 = int(xs[ys == y0].min())
    start = (y0, x0)

    # Moore-neighbour tracing. _MOORE runs clockwise from north, so the
    # opposite of direction d is (d + 4) % 8. The pixel west of the topmost,
    # leftmost pixel is always background, so start backtracking from west.
    b_px, back = start, 6
    out = []
    for _ in range(4 * m.size):
        out.append((b_px[1] - 1, b_px[0] - 1))      # undo the pad
        moved = False
        for k in range(1, 9):
            d = (back + k) % 8
            ny, nx = b_px[0] + _MOORE[d][0], b_px[1] + _MOORE[d][1]
            if m[ny, nx]:
                b_px, back = (ny, nx), (d + 4) % 8  # resume just past where we came from
                moved = True
                break
        if not moved or (len(out) > 2 and b_px == start):
            break
    return out


def simplify(pts, tol=1.5):
    """Douglas-Peucker on a closed ring."""
    if len(pts) < 3:
        return pts

    def dp(p):
        if len(p) < 3:
            return p
        a, b = np.array(p[0]), np.array(p[-1])
        ab = b - a
        n = np.hypot(*ab)
        P = np.array(p)
        if n == 0:
            d = np.hypot(*(P - a).T)
        else:
            d = np.abs(np.cross(ab, P - a)) / n
        i = int(np.argmax(d))
        if d[i] <= tol:
            return [p[0], p[-1]]
        return dp(p[:i + 1])[:-1] + dp(p[i:])

    ring = list(pts) + [pts[0]]
    half = len(ring) // 2
    out = dp(ring[:half + 1])[:-1] + dp(ring[half:])
    return out[:-1] if len(out) > 1 and out[0] == out[-1] else out


def outline_path(alpha, w_mm, h_mm, rot=False, tol=1.5, uu_per_mm=96.0 / 25.4):
    """SVG path 'd' for the silhouette, scaled into a w x h mm box at 0,0."""
    a = np.rot90(alpha) if rot else alpha
    pts = simplify(trace_outline(a), tol)
    ah, aw = a.shape
    sx, sy = w_mm * uu_per_mm / aw, h_mm * uu_per_mm / ah
    d = " ".join(("M" if i == 0 else "L") + f"{x*sx:.2f},{y*sy:.2f}"
                 for i, (x, y) in enumerate(pts))
    return d + " Z", len(pts)


# ---------------------------------------------------------------------------
# Sticker borders.
#
# Some art already has the white rim drawn in, some does not. Telling them
# apart is easy: walk inward from the alpha edge one pixel ring at a time and
# count how many consecutive rings are near-white. Art with a rim gives several
# such rings, art without gives none, because the first ring is already
# artwork.
# ---------------------------------------------------------------------------

def detect_border(rgba, max_depth=14, white=235, frac=0.70):
    """Thickness in pixels of an existing white rim. 0 means none."""
    from scipy import ndimage as _nd
    a = np.asarray(rgba)
    alpha = a[:, :, 3] >= 128
    rgb = a[:, :, :3]
    prev = alpha
    depth = 0
    for d in range(1, max_depth + 1):
        er = _nd.binary_erosion(alpha, iterations=d)
        ring = prev & ~er
        if not ring.any():
            break
        if (rgb[ring] >= white).all(axis=1).mean() < frac:
            break
        depth = d
        prev = er
    return depth


def add_border(rgba, px, colour=(255, 255, 255)):
    """Grow a solid rim around the silhouette, expanding the canvas to suit."""
    from scipy import ndimage as _nd
    from PIL import Image as _I
    p = int(round(px))
    if p <= 0:
        return rgba
    a = np.pad(np.asarray(rgba.convert("RGBA")), ((p, p), (p, p), (0, 0)))
    alpha = a[:, :, 3] >= 128
    ring = _nd.binary_dilation(alpha, iterations=p) & ~alpha
    out = a.copy()
    out[ring] = (*colour, 255)
    return _I.fromarray(out)
