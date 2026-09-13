"""Vector-preserving compositing.

The raster path rebuilds the whole page as a 300 DPI image. That reproduces the
registration marks accurately but it does re-encode them, turning whatever
Design Space drew (vector paths, an orientation arrow, anything) into pixels.

This path does not touch them at all. It keeps the original PDF page exactly as
Design Space wrote it and stamps the card art on top as a content-stream
overlay. Every original page object survives byte for byte, so the marks are
literally Cricut's own, in their original form, whatever shape they are.
"""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import sheet as S


def build_overlay(page_w_pt: float, page_h_pt: float,
                  placements: list[tuple[Image.Image, tuple[float, float, float, float]]]) -> bytes:
    """An otherwise-empty page carrying just the art, positioned in PDF points."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w_pt, page_h_pt))
    for img, (x, y, w, h) in placements:
        c.drawImage(ImageReader(img.convert("RGB")), x, y, width=w, height=h,
                    preserveAspectRatio=False, anchor="sw", mask=None)
    c.showPage()
    c.save()
    return buf.getvalue()


def stamp(template_pdf: bytes, slots: list[S.Slot], art: dict[int, Image.Image],
          bleed_px: int, dpi: int = S.DPI) -> tuple[bytes, list[str]]:
    """Return a PDF with art laid over the untouched original page."""
    warnings: list[str] = []

    reader = PdfReader(io.BytesIO(template_pdf))
    base = reader.pages[0]
    pw_pt = float(base.mediabox.width)
    ph_pt = float(base.mediabox.height)

    # px (top-left origin, 300 dpi) -> pt (bottom-left origin, 72/in)
    page_px = (round(pw_pt / 72 * dpi), round(ph_pt / 72 * dpi))
    boxes = S.bleed_boxes(slots, bleed_px, page_px)

    clash = S.overlapping_pairs(boxes)
    if clash:
        warnings.append(
            f"Bleed areas overlap between slots {clash}. Reduce bleed or widen "
            f"the gaps in the Design Space template."
        )

    k = 72.0 / dpi
    placements = []
    for slot, (bx0, by0, bx1, by1) in zip(slots, boxes):
        im = art.get(slot.index)
        if im is None:
            continue
        w_px, h_px = bx1 - bx0, by1 - by0
        placements.append((
            S.cover(im, w_px, h_px),
            (bx0 * k, ph_pt - by1 * k, w_px * k, h_px * k),
        ))

    if len(placements) < len(slots):
        warnings.append("Some slots are still empty and will print magenta.")

    if placements:
        overlay = PdfReader(io.BytesIO(build_overlay(pw_pt, ph_pt, placements))).pages[0]
        base.merge_page(overlay)

    writer = PdfWriter()
    writer.add_page(base)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), warnings


def verify_marks_untouched(template_pdf: bytes, output_pdf: bytes,
                           slots: list[S.Slot], bleed_px: int,
                           dpi: int = S.DPI) -> dict:
    """Prove the registration marks came through untouched.

    Renders the original template and the output, isolates every pixel of ink
    that sits outside the card areas (that is the marks, whatever shape they
    are), and compares them. It also checks a 20px halo around them, so a
    near-miss still fails. Anti-aliasing along the art edges is expected and is
    reported separately rather than counted as a failure.
    """
    import numpy as np
    from scipy import ndimage

    a = np.asarray(S.rasterize(template_pdf, dpi).convert("RGB")).astype(np.int16)
    b = np.asarray(S.rasterize(output_pdf, dpi).convert("RGB")).astype(np.int16)

    if a.shape != b.shape:
        return {"ok": False, "reason": f"page size changed: {a.shape[1]}x{a.shape[0]} "
                                       f"-> {b.shape[1]}x{b.shape[0]}"}

    outside = np.ones(a.shape[:2], dtype=bool)
    for (x0, y0, x1, y1) in S.bleed_boxes(slots, bleed_px, (a.shape[1], a.shape[0])):
        outside[y0:y1, x0:x1] = False

    ink = (a.max(axis=2) < 200) & outside
    band = ndimage.binary_dilation(ink, np.ones((41, 41), dtype=bool)) & outside
    diff = np.abs(a - b).max(axis=2)

    changed_marks = int((diff[ink] > 0).sum())
    changed_band = int((diff[band] > 0).sum())
    edge_halo = int((diff[outside] > 0).sum()) - changed_band

    return {
        "ok": changed_marks == 0 and changed_band == 0,
        "mark_pixels": int(ink.sum()),
        "mark_pixels_changed": changed_marks,
        "halo_pixels_changed": changed_band,
        "art_edge_antialiasing_px": max(0, edge_halo),
        "page_pt": [round(a.shape[1] / dpi * 72, 2), round(a.shape[0] / dpi * 72, 2)],
    }
