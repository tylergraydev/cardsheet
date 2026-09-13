#!/usr/bin/env python3
"""
make_sticker_template.py - pack any number of stickers onto one Print Then Cut
sheet, as large as possible, and emit the magenta placeholder SVG.

Every sticker ends up the SAME AREA with its own aspect ratio kept, and that
area is made as large as will fit. So a wide sticker and a tall one look the
same size instead of one being 1 and the other 40.

    python3 make_sticker_template.py stickers/*.png
    python3 make_sticker_template.py art/*.png --gap 3mm --count 20

The usable area is not a rectangle. Cricut parks a registration mark in each
corner, so the corners are cut away in a staircase. That shape lives in
pack.Region and the packer treats it as a mask, so it can be corrected without
touching the algorithm.

Slot order matters: cardsheet fills slots in reading order, so this writes a
.json mapping saying which image belongs in which slot.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pack  # noqa: E402

UU = 96.0        # SVG user units per inch
MM_PER_IN = 25.4
KEY = "#FF00FF"

# Measured off a Design Space Letter canvas: usable bounding box, then each
# corner cut back by roughly this much in a staircase.
USABLE = {"letter": (188.5, 251.4), "a4": (182.9, 269.7)}
CORNER_CUT_MM = 33.0


def to_mm(value, default="mm"):
    s = str(value).strip().lower()
    for suf, k in (("mm", 1.0), ("cm", 10.0), ("in", MM_PER_IN), ('"', MM_PER_IN)):
        if s.endswith(suf):
            return float(s[: -len(suf)]) * k
    return float(s) * (MM_PER_IN if default == "in" else 1.0)


def reading_order(placements, row_tol_mm=6.35):
    """Same banding cardsheet's find_slots uses: rows, then left to right."""
    ps = sorted(placements, key=lambda p: p[1])
    rows, cur = [], [ps[0]]
    for p in ps[1:]:
        if p[1] - cur[0][1] <= row_tol_mm:
            cur.append(p)
        else:
            rows.append(cur); cur = [p]
    rows.append(cur)
    out = []
    for row in rows:
        out.extend(sorted(row, key=lambda p: p[0]))
    return out


def build_svg(ordered, radius_mm=0.0):
    xs0 = min(p[0] for p in ordered); ys0 = min(p[1] for p in ordered)
    w = max(p[0] + p[2] for p in ordered) - xs0
    h = max(p[1] + p[3] for p in ordered) - ys0
    k = UU / MM_PER_IN
    rx = f' rx="{radius_mm * k:.4f}" ry="{radius_mm * k:.4f}"' if radius_mm > 0 else ""
    rects = "\n".join(
        f'  <rect x="{(p[0]-xs0)*k:.4f}" y="{(p[1]-ys0)*k:.4f}"'
        f' width="{p[2]*k:.4f}" height="{p[3]*k:.4f}"{rx} fill="{KEY}"/>'
        for p in ordered
    )
    return (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1"\n'
            f'     width="{w/MM_PER_IN:.4f}in" height="{h/MM_PER_IN:.4f}in"\n'
            f'     viewBox="0 0 {w*k:.4f} {h*k:.4f}">\n{rects}\n</svg>\n'), w, h


def preview(ordered, region, path, scale=3):
    im = Image.new("RGB", (int(region.w_mm * scale), int(region.h_mm * scale)), "white")
    d = ImageDraw.Draw(im)
    blocked = region.blocked
    for yy in range(0, blocked.shape[0], 2):
        for xx in range(0, blocked.shape[1], 2):
            if blocked[yy, xx]:
                x = xx * region.res * scale; y = yy * region.res * scale
                d.rectangle([x, y, x + region.res * 2 * scale, y + region.res * 2 * scale],
                            fill=(235, 235, 235))
    for n, (x, y, w, h, idx, rot) in enumerate(ordered):
        d.rectangle([x*scale, y*scale, (x+w)*scale, (y+h)*scale],
                    fill=(255, 0, 255), outline=(80, 0, 80))
        d.text((x*scale + 6, y*scale + 6), f"{n}<-{idx}" + ("R" if rot else ""), fill="white")
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="sticker image files")
    ap.add_argument("--paper", default="letter", choices=sorted(USABLE))
    ap.add_argument("--gap", default="2mm", help="space between stickers (default 2mm)")
    ap.add_argument("--radius", default="0", help="corner radius on the cut, e.g. 2mm")
    ap.add_argument("--corner-cut", default=str(CORNER_CUT_MM),
                    help="how far each corner is eaten by a registration mark")
    ap.add_argument("-o", "--out", default="sticker_template.svg")
    a = ap.parse_args()

    paths = [pathlib.Path(p) for p in a.images]
    aspects = []
    for p in paths:
        with Image.open(p) as im:
            aspects.append(im.width / im.height)

    w_mm, h_mm = USABLE[a.paper]
    region = pack.Region(w_mm, h_mm)
    region.block_corner_staircase(to_mm(a.corner_cut))

    gap = to_mm(a.gap)
    area, placed = pack.solve(aspects, region, gap_mm=gap)
    if not placed:
        sys.exit(f"Could not fit {len(paths)} stickers with a {gap:g} mm gap.")

    ordered = reading_order(placed)
    svg, gw, gh = build_svg(ordered, to_mm(a.radius))
    out = pathlib.Path(a.out)
    out.write_text(svg, encoding="utf-8")

    mapping = [{"slot": n, "image": str(paths[p[4]]),
                "w_mm": round(p[2], 2), "h_mm": round(p[3], 2), "rotated": p[5]}
               for n, p in enumerate(ordered)]
    out.with_suffix(".json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    preview(ordered, region, out.with_suffix(".png"))

    side = area ** 0.5
    print(f"wrote {out}")
    print(f"  {len(paths)} stickers, {area:.0f} mm2 each (a square one would be "
          f"{side:.1f} x {side:.1f} mm)")
    print(f"  gap {gap:g} mm, group {gw:.1f} x {gh:.1f} mm "
          f"({gw/MM_PER_IN:.3f} x {gh/MM_PER_IN:.3f} in)")
    print(f"  fill {100*area*len(paths)/region.area_mm2():.1f}% of the usable area")
    print(f"  {out.with_suffix('.json').name} lists which image goes in which slot")
    print(f"  {out.with_suffix('.png').name} previews the layout")
    rot = sum(1 for p in ordered if p[5])
    if rot:
        print(f"  {rot} sticker(s) rotated 90 degrees to fit")


if __name__ == "__main__":
    main()
