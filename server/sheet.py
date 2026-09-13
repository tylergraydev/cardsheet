"""Core template detection and compositing. Shared by the API and the CLI."""

from __future__ import annotations

import io
from dataclasses import dataclass, asdict

import numpy as np
import pypdfium2 as pdfium
from PIL import Image
from scipy import ndimage

KEY_HEX = "FF00FF"
KEY_TOL = 60
MIN_SLOT_IN = 0.5
DPI = 300


@dataclass
class Slot:
    index: int
    x: int
    y: int
    w: int
    h: int

    @property
    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def json(self, dpi: int = DPI):
        d = asdict(self)
        d.update(
            w_in=round(self.w / dpi, 3), h_in=round(self.h / dpi, 3),
            w_cm=round(self.w / dpi * 2.54, 1), h_cm=round(self.h / dpi * 2.54, 1),
            w_mm=round(self.w / dpi * 25.4, 1), h_mm=round(self.h / dpi * 25.4, 1),
        )
        return d


class TemplateError(Exception):
    pass


def rasterize(pdf_bytes: bytes, dpi: int = DPI) -> Image.Image:
    """Render page 1 at dpi, snapped to the page's exact declared size.

    The snap matters: pdfium rounds the raster up, and a page that is even one
    pixel off its true size can invite the printer to rescale, which moves the
    registration marks and ruins the cut.
    """
    doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    if len(doc) == 0:
        raise TemplateError("That PDF has no pages.")
    page = doc[0]
    pil = page.render(scale=dpi / 72.0).to_pil().convert("RGB")
    pw_pt, ph_pt = page.get_size()
    exact = (int(round(pw_pt / 72.0 * dpi)), int(round(ph_pt / 72.0 * dpi)))
    if pil.size != exact:
        pil = pil.resize(exact, Image.LANCZOS)
    return pil


def key_mask(arr: np.ndarray, key_hex: str = KEY_HEX, tol: int = KEY_TOL) -> np.ndarray:
    key = np.array([int(key_hex[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.int16)
    return np.abs(arr.astype(np.int16) - key).max(axis=2) <= tol


def find_slots(img: Image.Image, dpi: int = DPI, key_hex: str = KEY_HEX) -> list[Slot]:
    arr = np.asarray(img)
    mask = key_mask(arr, key_hex)
    if not mask.any():
        raise TemplateError(
            f"No #{key_hex} placeholders found. In Design Space the card "
            f"rectangles must be filled with that exact magenta, and Bleed "
            f"must be OFF when you print to PDF."
        )

    labels, _ = ndimage.label(mask)
    min_px = int(MIN_SLOT_IN * dpi)
    boxes = []
    for ys, xs in ndimage.find_objects(labels):
        w, h = xs.stop - xs.start, ys.stop - ys.start
        if w >= min_px and h >= min_px:
            boxes.append((xs.start, ys.start, w, h))

    if not boxes:
        raise TemplateError(
            f"Found magenta, but every region was under {MIN_SLOT_IN}in. "
            f"Check that the template printed at full size."
        )

    # reading order: band into rows, then left to right within each row
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
    ordered = [b for row in rows for b in sorted(row, key=lambda b: b[0])]

    return [Slot(i, x, y, w, h) for i, (x, y, w, h) in enumerate(ordered)]


def min_gap_px(slots: list[Slot]) -> int:
    """Smallest edge-to-edge gap between any two slots, in px.

    This caps how much bleed is physically possible: bleed can only use half
    the gap on each side before neighbouring cards start painting over each
    other. Returns a large number when there is only one slot.
    """
    if len(slots) < 2:
        return 1 << 30
    best = 1 << 30
    for i, a in enumerate(slots):
        for b in slots[i + 1:]:
            dx = max(b.x - (a.x + a.w), a.x - (b.x + b.w))
            dy = max(b.y - (a.y + a.h), a.y - (b.y + b.h))
            # only count the axis on which they are actually separated
            gap = max(dx, dy)
            if gap >= 0:
                best = min(best, gap)
    return best


def cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Fill w*h preserving aspect, centre-cropping the overflow."""
    img = img.convert("RGB")
    s = max(w / img.width, h / img.height)
    nw, nh = max(w, round(img.width * s)), max(h, round(img.height * s))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def bleed_boxes(slots: list[Slot], bleed_px: int, size: tuple[int, int]):
    pw, ph = size
    return [(max(0, s.x - bleed_px), max(0, s.y - bleed_px),
             min(pw, s.x + s.w + bleed_px), min(ph, s.y + s.h + bleed_px)) for s in slots]


def overlapping_pairs(boxes) -> list[tuple[int, int]]:
    out = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax0, ay0, ax1, ay1 = boxes[i]
            bx0, by0, bx1, by1 = boxes[j]
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                out.append((i + 1, j + 1))
    return out


def compose(template: Image.Image, slots: list[Slot],
            art: dict[int, Image.Image], bleed_px: int) -> tuple[Image.Image, list[str]]:
    """Paint art into the slots. Returns the sheet and any warnings."""
    sheet = template.copy()
    warnings: list[str] = []

    boxes = bleed_boxes(slots, bleed_px, sheet.size)
    clash = overlapping_pairs(boxes)
    if clash:
        warnings.append(
            f"Bleed areas overlap between slots {clash}. Reduce bleed or widen "
            f"the gaps in the Design Space template."
        )

    for slot, box in zip(slots, boxes):
        im = art.get(slot.index)
        if im is None:
            continue
        bx0, by0, bx1, by1 = box
        sheet.paste(cover(im, bx1 - bx0, by1 - by0), (bx0, by0))

    if key_mask(np.asarray(sheet)).any():
        warnings.append("Some slots are still empty and will print magenta.")

    return sheet, warnings


def preview_png(img: Image.Image, slots: list[Slot], bleed_px: int,
                max_px: int = 1100, guides: bool = True) -> bytes:
    """Downscaled preview with cut line and bleed guides drawn on."""
    from PIL import ImageDraw

    im = img.copy()
    if guides:
        d = ImageDraw.Draw(im)
        for s in slots:
            x0, y0, x1, y1 = s.box
            d.rectangle([x0 - bleed_px, y0 - bleed_px, x1 + bleed_px, y1 + bleed_px],
                        outline=(255, 150, 40), width=5)
            d.rectangle([x0, y0, x1, y1], outline=(0, 190, 120), width=5)

    im.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def to_pdf_bytes(sheet: Image.Image, dpi: int = DPI) -> bytes:
    buf = io.BytesIO()
    sheet.save(buf, "PDF", resolution=dpi)
    return buf.getvalue()
