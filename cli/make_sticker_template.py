#!/usr/bin/env python3
"""
make_sticker_template.py - pack any number of stickers onto one Print Then Cut
sheet, as large as possible.

Every sticker ends up the SAME AREA with its own aspect ratio kept, and that
area is made as large as will fit, so a wide sticker and a tall one look the
same size instead of one being 1 and the other 40.

    python3 make_sticker_template.py stickers/*.png
    python3 make_sticker_template.py dragons/*.png --gap 3mm

Transparent art is die-cut by default: the cut follows the silhouette, and the
shapes nest so one sticker's concave gap can hold a neighbour's tail. Art that
already has a white rim is detected and left alone; bare art gets one added.

Writes four things:
    <out>.svg           magenta placeholders for the cardsheet route
    <out>_sheet.png     transparent 300 dpi sheet, upload straight to Design Space
    <out>_preview.png   the layout, for eyeballing
    <out>.json          which image landed in which slot

This is a thin wrapper. The work is in server/stickers.py so the CLI and the
web UI cannot drift apart.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "server"))
import stickers as STK  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", help="sticker image files")
    ap.add_argument("--paper", default="letter", choices=sorted(STK.USABLE))
    ap.add_argument("--gap", default="3mm", help="space between stickers (default 3mm)")
    ap.add_argument("--radius", default="0",
                    help="corner radius for rectangular cuts, e.g. 2mm")
    ap.add_argument("--corner-cut", default=str(STK.CORNER_CUT_MM),
                    help="how far a registration mark eats each corner")
    ap.add_argument("--die-cut", dest="die_cut", action="store_true", default=None,
                    help="cut the silhouette (default when every image has alpha)")
    ap.add_argument("--no-die-cut", dest="die_cut", action="store_false",
                    help="cut rectangles even when the art is transparent")
    ap.add_argument("--border", default="0.9mm",
                    help="rim to add to art that has none (default 0.9mm)")
    ap.add_argument("--no-border", action="store_true",
                    help="never add a rim, even to art without one")
    ap.add_argument("--split", dest="split", action="store_true", default=None,
                    help="split a single sheet into its stickers "
                         "(default when you pass exactly one image)")
    ap.add_argument("--no-split", dest="split", action="store_false",
                    help="treat a lone image as one big sticker")
    ap.add_argument("-o", "--out", default="sticker_template.svg")
    a = ap.parse_args()

    paths = [pathlib.Path(p) for p in a.images]
    arts = [Image.open(p).convert("RGBA") for p in paths]

    try:
        r = STK.layout(arts,
                       gap_mm=STK.to_mm(a.gap),
                       border_mm=STK.to_mm(a.border),
                       add_border=not a.no_border,
                       die_cut=a.die_cut,
                       paper=a.paper,
                       corner_cut_mm=STK.to_mm(a.corner_cut),
                       radius_mm=STK.to_mm(a.radius),
                       split=a.split)
    except ValueError as e:
        sys.exit(str(e))

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(r["svg"], encoding="utf-8")

    sheet_path = out.with_name(out.stem + "_sheet.png")
    prev_path = out.with_name(out.stem + "_preview.png")
    sheet, gw, gh = STK.sheet_image(r["ordered"], r["arts"])
    sheet.save(sheet_path, dpi=(300, 300))
    STK.preview_image(r["ordered"], r["region"], outlines=r["outlines"]).save(prev_path)

    label = ((lambda i: f"{paths[0].name} #{i + 1}") if r["split"]
             else (lambda i: str(paths[i])))
    mapping = [dict(s, image=label(s["index"])) for s in r["slots"]]
    out.with_suffix(".json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")

    side = r["area_mm2"] ** 0.5
    print(f"wrote {out}")
    print(f"  {r['count']} stickers, {'die-cut' if r['die_cut'] else 'rectangular'}, "
          f"{r['area_mm2']:.0f} mm2 each "
          f"(a square one would be {side:.1f} x {side:.1f} mm)")
    print(f"  group {r['group_mm'][0]} x {r['group_mm'][1]} mm "
          f"({gw/STK.MM_PER_IN:.3f} x {gh/STK.MM_PER_IN:.3f} in)")
    print(f"  effective print resolution {r['dpi'][0]} to {r['dpi'][1]} dpi")
    for n in r["notes"]:
        print(f"  {n}")
    if r["rotated"]:
        print(f"  {r['rotated']} rotated 90 degrees to fit")
    print(f"  {sheet_path.name} is the print-ready transparent sheet, "
          f"{sheet.width} x {sheet.height} px at 300 dpi")
    print(f"    upload that to Design Space at "
          f"{r['group_mm'][0]} x {r['group_mm'][1]} mm")
    print(f"  {prev_path.name} previews the layout")
    print(f"  {out.with_suffix('.json').name} maps image -> slot")


if __name__ == "__main__":
    main()
