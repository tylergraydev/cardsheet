"""Sticker sheet layout: pack N stickers as large as they will go.

Shared by the API and cli/make_sticker_template.py so both produce identical
output. The packing itself lives in pack.py; this is the part that turns a
list of images into an SVG, a print-ready sheet, and a slot mapping.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

import pack

UU = 96.0                 # SVG user units per inch
MM_PER_IN = 25.4
KEY = "#FF00FF"

# Measured off a Design Space Letter canvas: usable bounding box, then each
# corner cut back by roughly this much in a staircase where a mark sits.
USABLE = {"letter": (188.5, 251.4), "a4": (182.9, 269.7)}
CORNER_CUT_MM = 33.0
TRACE_TOL = 0.75          # source px; scores 0.995 IoU against the alpha


def to_mm(value, default="mm"):
    s = str(value).strip().lower()
    for suf, k in (("mm", 1.0), ("cm", 10.0), ("in", MM_PER_IN), ('"', MM_PER_IN)):
        if s.endswith(suf):
            return float(s[: -len(suf)]) * k
    return float(s) * (MM_PER_IN if default == "in" else 1.0)


def split_sheet(img, min_area_frac=0.0015, close_px=2, pad_px=3):
    """Split one transparent sheet into its separate stickers.

    Each disconnected run of opaque pixels is one sticker. Soft drop shadows
    fall below the alpha threshold so they do not join neighbours together, and
    a small binary closing bridges the hairline gaps that antialiasing leaves
    inside a single piece of art.

    Returns [(image, (x, y))] in reading order, positions being where each came
    from so the caller can report sensibly.
    """
    from scipy import ndimage

    im = img.convert("RGBA")
    a = np.asarray(im)
    solid = a[:, :, 3] >= 128
    if not solid.any():
        return []
    m = ndimage.binary_closing(solid, iterations=close_px) if close_px else solid
    lab, n = ndimage.label(m)
    if n == 0:
        return []

    counts = ndimage.sum(m, lab, range(1, n + 1))
    floor = max(min_area_frac * solid.size, 64)
    keep = [i + 1 for i, c in enumerate(counts) if c >= floor]
    boxes = ndimage.find_objects(lab)

    out = []
    for k in keep:
        ys, xs = boxes[k - 1]
        y0 = max(0, ys.start - pad_px); y1 = min(a.shape[0], ys.stop + pad_px)
        x0 = max(0, xs.start - pad_px); x1 = min(a.shape[1], xs.stop + pad_px)
        crop = a[y0:y1, x0:x1].copy()
        # Blank any neighbour that reaches into this crop, but leave label 0
        # alone so soft shadows and antialiased fringes survive.
        other = (lab[y0:y1, x0:x1] != k) & (lab[y0:y1, x0:x1] != 0)
        crop[other] = 0
        out.append((Image.fromarray(crop), (x0, y0)))

    # reading order: band into rows by the row height, then left to right
    if out:
        hs = sorted(im.size[1] for _ in out)
        tol = max(8, int(0.4 * min(c.height for c, _ in out)))
        out.sort(key=lambda t: t[1][1])
        rows, cur = [], [out[0]]
        for t in out[1:]:
            if t[1][1] - cur[0][1][1] <= tol:
                cur.append(t)
            else:
                rows.append(cur); cur = [t]
        rows.append(cur)
        out = [t for row in rows for t in sorted(row, key=lambda q: q[1][0])]
    return out


def reading_order(placements, row_tol_mm=6.35):
    """The same banding sheet.find_slots uses: rows, then left to right."""
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


def _extent(ordered):
    x0 = min(p[0] for p in ordered)
    y0 = min(p[1] for p in ordered)
    return (x0, y0,
            max(p[0] + p[2] for p in ordered) - x0,
            max(p[1] + p[3] for p in ordered) - y0)


def build_svg(ordered, radius_mm=0.0, outlines=None):
    """outlines[n] = (alpha, rotated) cuts the silhouette instead of a rect."""
    xs0, ys0, w, h = _extent(ordered)
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
    return (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1"\n'
            f'     width="{w/MM_PER_IN:.4f}in" height="{h/MM_PER_IN:.4f}in"\n'
            f'     viewBox="0 0 {w*k:.4f} {h*k:.4f}">\n{body}\n</svg>\n'), w, h


def preview_image(ordered, region, scale=3, outlines=None):
    im = Image.new("RGB", (int(region.w_mm * scale), int(region.h_mm * scale)), "white")
    d = ImageDraw.Draw(im)
    blk = region.blocked
    step = max(1, int(round(1.0 / region.res)))
    for yy in range(0, blk.shape[0], step):
        for xx in range(0, blk.shape[1], step):
            if blk[yy, xx]:
                x, y = xx * region.res * scale, yy * region.res * scale
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
        d.text((x * scale + 5, y * scale + 5),
               f"{n + 1}" + ("R" if rot else ""), fill=(30, 30, 30))
    return im


def sheet_image(ordered, arts, dpi=300):
    """The packed layout as one transparent PNG.

    Design Space traces the cut line from the alpha itself, so uploading this
    skips the magenta template entirely.
    """
    k = dpi / MM_PER_IN
    xs0, ys0, w, h = _extent(ordered)
    canvas = Image.new("RGBA", (int(round(w * k)), int(round(h * k))), (0, 0, 0, 0))
    for (x, y, pw, ph, idx, rot) in ordered:
        im = arts[idx]
        if rot:
            im = im.transpose(Image.ROTATE_90)
        im = im.resize((max(1, int(round(pw * k))), max(1, int(round(ph * k)))),
                       Image.LANCZOS)
        canvas.alpha_composite(im, (int(round((x - xs0) * k)),
                                    int(round((y - ys0) * k))))
    return canvas, w, h


def layout(arts, *, gap_mm=2.0, border_mm=0.9, add_border=True, die_cut=None,
           paper="letter", corner_cut_mm=CORNER_CUT_MM, radius_mm=0.0,
           split=None):
    """Pack RGBA images. Returns a dict of everything the callers need.

    split=None splits a lone image into its separate stickers when it clearly
    holds more than one, which is the usual case for a sheet exported as a
    single transparent PNG. Pass False to treat it as one big sticker.
    """
    arts = [im.convert("RGBA") for im in arts]
    notes = []
    split_from_sheet = False

    if (split is None or split) and len(arts) == 1:
        parts = split_sheet(arts[0])
        if len(parts) >= 2:
            arts = [p for p, _ in parts]
            split_from_sheet = True
            notes.append(f"split the sheet into {len(arts)} stickers")
        elif split:
            notes.append("only found one shape on that sheet, nothing to split")

    aspects = [im.width / im.height for im in arts]
    alphas = [np.asarray(im)[:, :, 3] for im in arts]

    transparent = all((al < 128).mean() > 0.02 for al in alphas)
    die = transparent if die_cut is None else bool(die_cut)

    w_mm, h_mm = USABLE[paper]
    region = pack.Region(w_mm, h_mm, res_mm=1.0 if die else 0.5)
    region.block_corner_staircase(corner_cut_mm)

    if die:
        area, placed = pack.solve_shapes(alphas, region, gap_mm=gap_mm)
    else:
        area, placed = pack.solve(aspects, region, gap_mm=gap_mm)
    if not placed:
        raise ValueError(f"Could not fit {len(arts)} stickers with a "
                         f"{gap_mm:g} mm gap. Try a smaller gap.")

    if die and add_border:
        found = [pack.detect_border(im) for im in arts]
        need = [i for i, h in enumerate(found) if h == 0]
        kept = len(found) - len(need)
        if kept:
            notes.append(f"{kept} already had a border, left alone")
        if need:
            # The rim is given in mm at the printed size, but adding rims
            # changes the silhouettes, which changes the pack, which changes
            # the printed size. Re-add from the ORIGINAL art each pass so rims
            # never compound, and iterate to a fixed point. For a rim of w mm
            # on art o px wide printed p mm wide: b = w*o / (p - 2w).
            orig = [arts[i] for i in need]
            for _ in range(4):
                prev = area
                for n, i in enumerate(need):
                    printed_w = (area * aspects[i]) ** 0.5
                    denom = printed_w - 2 * border_mm
                    if denom <= 0:
                        continue
                    arts[i] = pack.add_border(
                        orig[n], border_mm * orig[n].width / denom)
                    alphas[i] = np.asarray(arts[i])[:, :, 3]
                    aspects[i] = arts[i].width / arts[i].height
                area, placed = pack.solve_shapes(alphas, region, gap_mm=gap_mm)
                if not placed:
                    raise ValueError("Could not fit the stickers once rims "
                                     "were added. Try a smaller gap or rim.")
                if abs(area - prev) / max(area, 1) < 0.01:
                    break
            got = [pack.detect_border(arts[i]) * (area * aspects[i]) ** 0.5
                   / arts[i].width for i in need]
            notes.append(f"added a {min(got):.2f}-{max(got):.2f} mm rim to "
                         f"{len(need)} that had none")

    ordered = reading_order(placed)
    outs = [(alphas[p[4]], p[5]) for p in ordered] if die else None
    svg, gw, gh = build_svg(ordered, radius_mm, outlines=outs)
    dpis = [min(alphas[p[4]].shape[1] / (p[2] / MM_PER_IN),
                alphas[p[4]].shape[0] / (p[3] / MM_PER_IN)) for p in ordered]

    return {
        "ordered": ordered, "arts": arts, "region": region, "outlines": outs,
        "svg": svg, "area_mm2": area, "die_cut": die, "notes": notes,
        "count": len(arts), "split": split_from_sheet,
        "group_mm": [round(gw, 1), round(gh, 1)],
        "dpi": [round(min(dpis)), round(max(dpis))],
        "rotated": sum(1 for p in ordered if p[5]),
        "slots": [{"slot": n + 1, "index": p[4], "w_mm": round(p[2], 2),
                   "h_mm": round(p[3], 2), "rotated": p[5]}
                  for n, p in enumerate(ordered)],
    }
