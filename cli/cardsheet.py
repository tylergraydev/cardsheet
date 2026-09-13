#!/usr/bin/env python3
"""
cardsheet.py - composite card art into a Cricut Design Space Print-Then-Cut template.

The idea: let Design Space generate the registration marks ONCE (Make It ->
Print -> "Microsoft Print to PDF" / "Save as PDF"), with solid magenta
placeholder rectangles where the cards go. This script rasterizes that PDF,
finds the magenta rectangles, drops your art into them with bleed, and writes a
print-ready PDF. The registration marks are copied through untouched, so every
sheet you print registers identically to the saved Design Space project.

Usage:
    # check that slot detection is right before you waste paper
    python3 cardsheet.py --template ds_template.pdf --inspect

    # build a sheet
    python3 cardsheet.py --template ds_template.pdf -o sheet_v1.pdf \
        art/a.png art/b.png art/c.png art/d.png

    # a whole run of versions, 4 art files per sheet, in order
    python3 cardsheet.py --template ds_template.pdf --outdir sheets --batch art/*.png

Printing:
    100% scale. No "fit to page". No auto-rotate. Same paper size as the
    Design Space project. Anything that rescales the page moves the
    registration marks and the cut will be off.
"""

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

DEFAULT_DPI = 300
DEFAULT_KEY = "FF00FF"
DEFAULT_BLEED_IN = 0.125
MIN_SLOT_IN = 0.5  # ignore specks smaller than this on either side


# ---------------------------------------------------------------- template io

def rasterize(path, dpi):
    """Template -> RGB array. Accepts PDF or any raster format."""
    ext = os.path.splitext(path)[1].lower()
    if ext != ".pdf":
        return np.asarray(Image.open(path).convert("RGB"))

    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(path)
    if len(doc) != 1:
        print(f"note: template has {len(doc)} pages, using page 1", file=sys.stderr)
    page = doc[0]
    pil = page.render(scale=dpi / 72.0).to_pil().convert("RGB")

    # pdfium rounds the raster up; snap back to the page's true size so the
    # emitted PDF is exactly the paper size and the printer has no excuse to
    # rescale it (rescaling moves the registration marks).
    pw_pt, ph_pt = page.get_size()
    exact = (int(round(pw_pt / 72.0 * dpi)), int(round(ph_pt / 72.0 * dpi)))
    if pil.size != exact:
        pil = pil.resize(exact, Image.LANCZOS)
    return np.asarray(pil)


def find_slots(rgb, key_hex, dpi, tol=60):
    """Locate key-colour rectangles. Returns boxes in reading order."""
    key = np.array([int(key_hex[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.int16)
    mask = (np.abs(rgb.astype(np.int16) - key).max(axis=2) <= tol)
    if not mask.any():
        raise SystemExit(
            f"no #{key_hex} found in the template.\n"
            "Fill the placeholder rectangles in Design Space with that exact colour,\n"
            "or pass --key with the hex you actually used."
        )

    labels, n = ndimage.label(mask)
    min_px = int(MIN_SLOT_IN * dpi)
    boxes = []
    for ys, xs in ndimage.find_objects(labels):
        w, h = xs.stop - xs.start, ys.stop - ys.start
        if w >= min_px and h >= min_px:
            boxes.append((xs.start, ys.start, xs.stop, ys.stop))

    if not boxes:
        raise SystemExit(f"found {n} key-coloured blobs but all were smaller than {MIN_SLOT_IN}in.")

    # reading order: group into rows, then sort each row left-to-right
    row_tol = int(0.25 * dpi)
    boxes.sort(key=lambda b: b[1])
    rows, cur = [], [boxes[0]]
    for b in boxes[1:]:
        if b[1] - cur[0][1] <= row_tol:
            cur.append(b)
        else:
            rows.append(cur)
            cur = [b]
    rows.append(cur)
    return [b for row in rows for b in sorted(row, key=lambda b: b[0])]


# ------------------------------------------------------------------ placement

def cover(img, w, h):
    """Scale to fill w*h preserving aspect, centre-crop the overflow."""
    img = img.convert("RGB")
    s = max(w / img.width, h / img.height)
    nw, nh = max(w, int(round(img.width * s))), max(h, int(round(img.height * s)))
    img = img.resize((nw, nh), Image.LANCZOS)
    return img.crop(((nw - w) // 2, (nh - h) // 2, (nw - w) // 2 + w, (nh - h) // 2 + h))


def overlaps(boxes):
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax0, ay0, ax1, ay1 = boxes[i]
            bx0, by0, bx1, by1 = boxes[j]
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                bad.append((i + 1, j + 1))
    return bad


def compose(rgb, slots, art_paths, bleed_px, page_wh):
    sheet = Image.fromarray(rgb.copy())
    pw, ph = page_wh

    bled = []
    for (x0, y0, x1, y1) in slots:
        bled.append((max(0, x0 - bleed_px), max(0, y0 - bleed_px),
                     min(pw, x1 + bleed_px), min(ph, y1 + bleed_px)))

    clash = overlaps(bled)
    if clash:
        print(f"warning: bleed boxes overlap for slot pairs {clash}. "
              f"Reduce --bleed or widen the gaps in the Design Space template.", file=sys.stderr)

    for i, (path, box) in enumerate(zip(art_paths, bled), 1):
        bx0, by0, bx1, by1 = box
        with Image.open(path) as im:
            sheet.paste(cover(im, bx1 - bx0, by1 - by0), (bx0, by0))
        print(f"  slot {i}: {os.path.basename(path)}")

    # any key colour still visible means a slot went unfilled
    leftover = find_key_remaining(np.asarray(sheet))
    if leftover:
        print(f"warning: {leftover} key-coloured pixels remain. "
              f"A slot was not filled and will print magenta.", file=sys.stderr)
    return sheet


def find_key_remaining(arr, key_hex=DEFAULT_KEY, tol=60):
    key = np.array([int(key_hex[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.int16)
    return int((np.abs(arr.astype(np.int16) - key).max(axis=2) <= tol).sum())


def annotate(rgb, slots, bleed_px):
    from PIL import ImageDraw
    im = Image.fromarray(rgb.copy())
    d = ImageDraw.Draw(im)
    for i, (x0, y0, x1, y1) in enumerate(slots, 1):
        d.rectangle([x0 - bleed_px, y0 - bleed_px, x1 + bleed_px, y1 + bleed_px],
                    outline=(255, 140, 0), width=6)
        d.rectangle([x0, y0, x1, y1], outline=(0, 160, 0), width=6)
        d.text((x0 + 16, y0 + 16), str(i), fill=(0, 0, 0))
    return im


# ----------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("art", nargs="*", help="card art files, in slot order")
    p.add_argument("--template", required=True, help="Design Space Print-to-PDF export")
    p.add_argument("-o", "--out", default="sheet.pdf")
    p.add_argument("--outdir", help="with --batch, where the sheets go")
    p.add_argument("--batch", action="store_true", help="chunk all art into consecutive sheets")
    p.add_argument("--inspect", action="store_true", help="write an annotated PNG and exit")
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    p.add_argument("--bleed", type=float, default=DEFAULT_BLEED_IN, help="inches past the cut line")
    p.add_argument("--key", default=DEFAULT_KEY, help="placeholder hex, default FF00FF")
    p.add_argument("--png", action="store_true", help="also write a PNG next to the PDF")
    a = p.parse_args()

    for d in {os.path.dirname(os.path.abspath(a.out)), os.path.abspath(a.outdir) if a.outdir else None}:
        if d:
            os.makedirs(d, exist_ok=True)

    rgb = rasterize(a.template, a.dpi)
    h, w = rgb.shape[:2]
    slots = find_slots(rgb, a.key.lstrip("#").upper(), a.dpi)
    bleed_px = int(round(a.bleed * a.dpi))

    print(f"template {w}x{h}px = {w/a.dpi:.2f} x {h/a.dpi:.2f} in @ {a.dpi} dpi")
    print(f"{len(slots)} slots detected:")
    for i, (x0, y0, x1, y1) in enumerate(slots, 1):
        w_in, h_in = (x1 - x0) / a.dpi, (y1 - y0) / a.dpi
        print(f"  {i}: {w_in:.3f} x {h_in:.3f} in  "
              f"({w_in*2.54:.2f} x {h_in*2.54:.2f} cm)  "
              f"at ({x0/a.dpi:.3f}, {y0/a.dpi:.3f}) in")

    if a.inspect:
        out = os.path.splitext(a.out)[0] + "_inspect.png"
        annotate(rgb, slots, bleed_px).save(out)
        print(f"\ngreen = cut line, orange = bleed edge -> {out}")
        return

    if not a.art:
        p.error("need art files (or use --inspect)")

    jobs = []
    if a.batch:
        n = len(slots)
        if len(a.art) % n:
            print(f"warning: {len(a.art)} art files is not a multiple of {n}; "
                  f"last sheet will be short.", file=sys.stderr)
        outdir = a.outdir or "."
        os.makedirs(outdir, exist_ok=True)
        for k in range(0, len(a.art), n):
            jobs.append((a.art[k:k + n], os.path.join(outdir, f"sheet_{k // n + 1:02d}.pdf")))
    else:
        if len(a.art) != len(slots):
            p.error(f"{len(slots)} slots but {len(a.art)} art files given")
        jobs.append((a.art, a.out))

    for art, out in jobs:
        print(f"\n{out}")
        sheet = compose(rgb, slots, art, bleed_px, (w, h))
        sheet.save(out, "PDF", resolution=a.dpi)
        if a.png:
            sheet.save(os.path.splitext(out)[0] + ".png")

    print(f"\nPrint at 100% scale, no fit-to-page, portrait, "
          f"{w/a.dpi:.1f} x {h/a.dpi:.1f} in paper.")


if __name__ == "__main__":
    main()
