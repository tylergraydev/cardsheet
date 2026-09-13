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

import numpy as np

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
