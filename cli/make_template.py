#!/usr/bin/env python3
"""
make_template.py - generate the placeholder SVG you upload to Cricut Design Space.

Emits N magenta rectangles in a grid at exact card size. You upload this,
set every rect to Print Then Cut, save the project, and print-to-PDF once.
cardsheet.py then finds those rectangles in the PDF and fills them with art.

    python3 make_template.py                       # 2x2 letter, 2.5 x 3.5 cards
    python3 make_template.py --cols 2 --rows 3 --paper legal
    python3 make_template.py --card 3.5x2 --cols 2 --rows 4 --radius 0.125
    python3 make_template.py --list                # what fits on what paper
"""

import argparse
import sys

# usable Print Then Cut design area per paper size, inches
PAPER = {
    "letter":  (7.44, 9.94),
    "legal":   (7.44, 12.94),
    "a4":      (7.20, 10.62),
    "tabloid": (9.94, 15.94),
    "a3":      (10.64, 15.44),
}

KEY = "#FF00FF"
UU = 96.0  # SVG user units per inch

UNIT_IN = {"in": 1.0, '"': 1.0, "cm": 1 / 2.54, "mm": 1 / 25.4}


def to_in(value, default_unit="in"):
    """Parse '6.3', '6.3cm', '88mm', '2.5in' -> inches."""
    s = str(value).strip().lower()
    for suf in ("mm", "cm", "in", '"'):
        if s.endswith(suf):
            return float(s[: -len(suf)]) * UNIT_IN[suf]
    return float(s) * UNIT_IN[default_unit]


def fmt(inches, unit):
    if unit == "cm":
        return f"{inches * 2.54:.2f} cm"
    if unit == "mm":
        return f"{inches * 25.4:.1f} mm"
    return f"{inches:.3f} in"


def build_svg(cw, ch, cols, rows, gap_x, gap_y, radius):
    total_w = cols * cw + (cols - 1) * gap_x
    total_h = rows * ch + (rows - 1) * gap_y
    rx = f' rx="{radius * UU:.4f}" ry="{radius * UU:.4f}"' if radius > 0 else ""

    rects = []
    for r in range(rows):
        for c in range(cols):
            x = c * (cw + gap_x) * UU
            y = r * (ch + gap_y) * UU
            rects.append(
                f'  <rect x="{x:.4f}" y="{y:.4f}" '
                f'width="{cw * UU:.4f}" height="{ch * UU:.4f}"{rx} fill="{KEY}"/>'
            )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1"\n'
        f'     width="{total_w:.4f}in" height="{total_h:.4f}in"\n'
        f'     viewBox="0 0 {total_w * UU:.4f} {total_h * UU:.4f}">\n'
        + "\n".join(rects)
        + "\n</svg>\n"
    )
    return svg, total_w, total_h


def fits_table(cw, ch):
    print(f"\nwhat fits at {cw} x {ch} in (usable Print Then Cut area):\n")
    print(f'  {"paper":<10}{"area":<18}{"grid":<8}{"cards":<8}{"slack w":<10}slack h')
    for name, (w, h) in PAPER.items():
        c, r = int(w // cw), int(h // ch)
        if c < 1 or r < 1:
            print(f"  {name:<10}{f'{w} x {h}':<18}does not fit")
            continue
        print(f"  {name:<10}{f'{w} x {h}':<18}{f'{c}x{r}':<8}{c*r:<8}"
              f"{w - c*cw:<10.2f}{h - r*ch:.2f}")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--card", default="2.5x3.5",
                   help="card size WxH, e.g. 2.5x3.5 or 6.3x8.8cm or 63x88mm")
    p.add_argument("--cols", type=int, default=2)
    p.add_argument("--rows", type=int, default=2)
    p.add_argument("--paper", default="letter", choices=sorted(PAPER), help="for the fit check")
    p.add_argument("--gap", default="0.35", help="between cards, e.g. 0.35 or 9mm (default 0.35in)")
    p.add_argument("--gap-y", help="vertical gap, if different from --gap")
    p.add_argument("--radius", default="0", help="corner radius, e.g. 0.125 or 3mm (0 = square)")
    p.add_argument("--units", default=None, choices=["in", "cm", "mm"],
                   help="unit for bare numbers and for reporting (default inferred from --card)")
    p.add_argument("-o", "--out", help="output .svg (default auto-named)")
    p.add_argument("--list", action="store_true", help="print the fit table and exit")
    a = p.parse_args()

    card = a.card.strip().lower()
    unit = a.units or next((u for u in ("mm", "cm", "in") if card.endswith(u)), "in")

    try:
        cw_s, ch_s = card.split("x")
        cw = to_in(cw_s, unit)
        ch = to_in(ch_s, unit)  # suffix on the second half applies to both
    except ValueError:
        p.error("--card must look like 2.5x3.5, 6.3x8.8cm, or 63x88mm")

    if a.list:
        fits_table(cw, ch)
        return

    gap = to_in(a.gap, unit)
    gap_y = gap if a.gap_y is None else to_in(a.gap_y, unit)
    radius = to_in(a.radius, unit)
    svg, tw, th = build_svg(cw, ch, a.cols, a.rows, gap, gap_y, radius)

    pw, ph = PAPER[a.paper]
    tag = f"{cw*2.54:.1f}x{ch*2.54:.1f}cm" if unit == "cm" else (
          f"{cw*25.4:.0f}x{ch*25.4:.0f}mm" if unit == "mm" else f"{cw}x{ch}in")
    out = a.out or f"template_{a.cols}x{a.rows}_{tag}_{a.paper}.svg"
    with open(out, "w") as f:
        f.write(svg)

    print(f"wrote {out}")
    print(f"  {a.cols} x {a.rows} = {a.cols * a.rows} cards at {fmt(cw, unit)} x {fmt(ch, unit)}")
    print(f"  gaps: {fmt(gap, unit)} horizontal, {fmt(gap_y, unit)} vertical")
    if radius:
        print(f"  corner radius: {fmt(radius, unit)}")
    print(f"  group size: {fmt(tw, unit)} x {fmt(th, unit)}  ({tw:.3f} x {th:.3f} in)")
    print(f"  {a.paper} usable area: {fmt(pw, unit)} x {fmt(ph, unit)}")

    if tw > pw or th > ph:
        print(f"\n  DOES NOT FIT on {a.paper}. Over by "
              f"{max(0, tw - pw):.2f} in wide, {max(0, th - ph):.2f} in tall.", file=sys.stderr)
        print("  Reduce --gap, drop a row or column, or use bigger paper.", file=sys.stderr)
        fits_table(cw, ch)
        sys.exit(1)

    print(f"  fits with {fmt(pw - tw, unit)} horizontal and {fmt(ph - th, unit)} vertical to spare")
    print(f"\nIn Design Space, set units to {'cm' if unit != 'in' else 'inches'} "
          f"and confirm the group reads {fmt(tw, unit)} W x {fmt(th, unit)} H.")
    print(f"Each individual card should read {fmt(cw, unit)} x {fmt(ch, unit)}.")


if __name__ == "__main__":
    main()
