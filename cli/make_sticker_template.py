#!/usr/bin/env python3
"""
make_sticker_template.py - pack any number of stickers onto one Print Then Cut
sheet, as large as possible, and emit the magenta placeholder SVG.

Every sticker ends up the SAME AREA with its own aspect ratio kept, and that
area is made as large as will fit. So a wide sticker and a tall one look the
same size instead of one being 1 and the other 40.

    python3 make_sticker_template.py stickers/*.png
    python3 make_sticker_template.py dragons/*.png --gap 3mm

Transparent art is die-cut by default: the cut follows the silhouette, and the
shapes are nested so one sticker's concave gap can hold a neighbour's tail.
Pass --no-die-cut for plain rectangles.

The usable area is not a rectangle. Cricut parks a registration mark in each
corner, so the corners are cut away in a staircase. That shape lives in
pack.Region as a mask, so it can be corrected without touching the packer.

Slot order matters: cardsheet fills slots in reading order, so this writes a
.json mapping saying which image belongs in which slot.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pack  # noqa: E402

UU = 96.0
MM_PER_IN = 25.4
KEY = "#FF00FF"

# Measured off a Design Space Letter canvas: usable bounding box, then each
# corner cut back by roughly this much in a staircase.
USABLE = {"letter": (188.5, 251.4), "a4": (182.9, 269.7)}
CORNER_CUT_MM = 33.0
TRACE_TOL = 0.75          # source px; IoU 0.995 against the alpha channel


def to_mm(value, default="mm"):
    s = str(value).strip().lower()
    for suf, k in (("mm", 1.0), ("cm", 10.0), ("in", MM_PER_IN), ('"', MM_PER_IN)):
        if s.endswith(suf):
            return float(s[: -len(suf)]) * k
    return float(s) * (MM_PER_IN if default == "in" else 1.0)


def reading_order(placements, row_tol_mm=6.35):
    """The same banding cardsheet's find_slots uses: rows, then left to right."""
    ps = sorted(placements, key=lambda p: p[1])
    rows, cur = [], [ps[0]]
    for p in ps[1:]:
        if p[1] - cur[0][1] <= row_tol_mm:
            cur.append(p)
        else:
            rows.append(cur)
            cur = [p]
    rows.append(cur)
    out = []
    for row in rows:
        out.extend(sorted(row, key=lambda p: p[0]))
    return out


def build_svg(ordered, radius_mm=0.0, outlines=None):
    """outlines[n] = (alpha, rotated) cuts the silhouette instead of a rect."""
    xs0 = min(p[0] for p in ordered)
    ys0 = min(p[1] for p in ordered)
    w = max(p[0] + p[2] for p in ordered) - xs0
    h = max(p[1] + p[3] for p in ordered) - ys0
    k = UU / MM_PER_IN

    parts = []
    for n, p in enumerate(ordered):
        px, py = (p[0] - xs0) * k, (p[1] - ys0) * k
        if outlines:
            alpha, rot = outlines[n]
            d, _ = pack.outline_path(alpha, p[2], p[3], rot=rot, tol=TRACE_TOL)
            parts.append(f'  <g transform="translate({px:.4f},{py:.4f})">'
                         f'<path d="{d}" fill="{KEY}"/></g>')
        else:
            rx = (f' rx="{radius_mm*k:.4f}" ry="{radius_mm*k:.4f}"'
                  if radius_mm > 0 else "")
            parts.append(f'  <rect x="{px:.4f}" y="{py:.4f}"'
                         f' width="{p[2]*k:.4f}" height="{p[3]*k:.4f}"{rx}'
                         f' fill="{KEY}"/>')

    body = "\n".join(parts)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1"\n'
           f'     width="{w/MM_PER_IN:.4f}in" height="{h/MM_PER_IN:.4f}in"\n'
           f'     viewBox="0 0 {w*k:.4f} {h*k:.4f}">\n{body}\n</svg>\n')
    return svg, w, h


def preview(ordered, region, path, scale=3, outlines=None):
    im = Image.new("RGB", (int(region.w_mm * scale), int(region.h_mm * scale)), "white")
    d = ImageDraw.Draw(im)
    blk = region.blocked
    step = max(1, int(round(1.0 / region.res)))
    for yy in range(0, blk.shape[0], step):
        for xx in range(0, blk.shape[1], step):
            if blk[yy, xx]:
                x = xx * region.res * scale
                y = yy * region.res * scale
                d.rectangle([x, y, x + region.res * step * scale,
                             y + region.res * step * scale], fill=(232, 232, 232))
    for n, (x, y, w, h, idx, rot) in enumerate(ordered):
        if outlines:
            alpha, r = outlines[n]
            a = np.rot90(alpha) if r else alpha
            pts = pack.simplify(pack.trace_outline(a), TRACE_TOL)
            ah, aw = a.shape
            sx, sy = w * scale / aw, h * scale / ah
            d.polygon([(x * scale + p[0] * sx, y * scale + p[1] * sy) for p in pts],
                      fill=(255, 0, 255), outline=(90, 0, 90))
        else:
            d.rectangle([x * scale, y * scale, (x + w) * scale, (y + h) * scale],
                        fill=(255, 0, 255), outline=(90, 0, 90))
        label = f"{n}<-{idx}" + ("R" if rot else "")
        d.text((x * scale + 5, y * scale + 5), label, fill=(30, 30, 30))
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="sticker image files")
    ap.add_argument("--paper", default="letter", choices=sorted(USABLE))
    ap.add_argument("--gap", default="2mm", help="space between stickers (default 2mm)")
    ap.add_argument("--radius", default="0",
                    help="corner radius for rectangular cuts, e.g. 2mm")
    ap.add_argument("--corner-cut", default=str(CORNER_CUT_MM),
                    help="how far a registration mark eats each corner")
    ap.add_argument("--die-cut", dest="die_cut", action="store_true", default=None,
                    help="cut the silhouette (default when every image has alpha)")
    ap.add_argument("--no-die-cut", dest="die_cut", action="store_false",
                    help="cut rectangles even when the art is transparent")
    ap.add_argument("-o", "--out", default="sticker_template.svg")
    a = ap.parse_args()

    paths = [pathlib.Path(p) for p in a.images]
    aspects, alphas = [], []
    for p in paths:
        with Image.open(p) as im:
            rgba = im.convert("RGBA")
            aspects.append(rgba.width / rgba.height)
            alphas.append(np.asarray(rgba)[:, :, 3])

    transparent = all((al < 128).mean() > 0.02 for al in alphas)
    die = transparent if a.die_cut is None else a.die_cut
    if a.die_cut is None and die:
        print("every image has transparency, cutting silhouettes "
              "(--no-die-cut for rectangles)")

    w_mm, h_mm = USABLE[a.paper]
    gap = to_mm(a.gap)
    region = pack.Region(w_mm, h_mm, res_mm=1.0 if die else 0.5)
    region.block_corner_staircase(to_mm(a.corner_cut))

    if die:
        area, placed = pack.solve_shapes(alphas, region, gap_mm=gap)
    else:
        area, placed = pack.solve(aspects, region, gap_mm=gap)
    if not placed:
        sys.exit(f"Could not fit {len(paths)} stickers with a {gap:g} mm gap.")

    ordered = reading_order(placed)
    outs = [(alphas[p[4]], p[5]) for p in ordered] if die else None
    svg, gw, gh = build_svg(ordered, to_mm(a.radius), outlines=outs)

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    mapping = [{"slot": n, "image": str(paths[p[4]]), "w_mm": round(p[2], 2),
                "h_mm": round(p[3], 2), "rotated": p[5]}
               for n, p in enumerate(ordered)]
    out.with_suffix(".json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    preview(ordered, region, out.with_suffix(".png"), outlines=outs)

    side = area ** 0.5
    dpi = [min(alphas[p[4]].shape[1] / (p[2] / MM_PER_IN),
               alphas[p[4]].shape[0] / (p[3] / MM_PER_IN)) for p in ordered]
    kind = "die-cut" if die else "rectangular"
    print(f"wrote {out}")
    print(f"  {len(paths)} stickers, {kind}, {area:.0f} mm2 each "
          f"(a square one would be {side:.1f} x {side:.1f} mm)")
    print(f"  gap {gap:g} mm, group {gw:.1f} x {gh:.1f} mm "
          f"({gw/MM_PER_IN:.3f} x {gh/MM_PER_IN:.3f} in)")
    print(f"  effective print resolution {min(dpi):.0f} to {max(dpi):.0f} dpi")
    rot = sum(1 for p in ordered if p[5])
    if rot:
        print(f"  {rot} rotated 90 degrees to fit")
    print(f"  {out.with_suffix('.json').name} maps image -> slot")
    print(f"  {out.with_suffix('.png').name} previews the layout")


if __name__ == "__main__":
    main()
