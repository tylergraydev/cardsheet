"""
Generates a SYNTHETIC stand-in for a Cricut Design Space "Print to PDF" export,
purely so cardsheet.py can be tested without a real export.

Do not use this output for real cutting. Cricut's registration marks have a
specific geometry and position that only Design Space produces correctly.
"""
from PIL import Image, ImageDraw
import os

DPI = 300
PAGE_W_IN, PAGE_H_IN = 8.5, 11.0
CARD_W_IN, CARD_H_IN = 2.5, 3.5
KEY = (255, 0, 255)

I = lambda inches: int(round(inches * DPI))

page = Image.new("RGB", (I(PAGE_W_IN), I(PAGE_H_IN)), "white")
d = ImageDraw.Draw(page)

# --- fake corner registration marks (L-shaped, ~0.5in legs, 0.06in stroke) ---
m_in, leg, stroke = 0.35, 0.5, 0.06
for cx, cy, dx, dy in [
    (m_in, m_in, 1, 1),
    (PAGE_W_IN - m_in, m_in, -1, 1),
    (m_in, PAGE_H_IN - m_in, 1, -1),
    (PAGE_W_IN - m_in, PAGE_H_IN - m_in, -1, -1),
]:
    d.rectangle([I(min(cx, cx + dx * leg)), I(min(cy, cy + dy * stroke)),
                 I(max(cx, cx + dx * leg)), I(max(cy, cy + dy * stroke))], fill="black")
    d.rectangle([I(min(cx, cx + dx * stroke)), I(min(cy, cy + dy * leg)),
                 I(max(cx, cx + dx * stroke)), I(max(cy, cy + dy * leg))], fill="black")

# --- 4 magenta placeholder rects, 2x2, centered ---
grid_w, grid_h = 2 * CARD_W_IN, 2 * CARD_H_IN
gap = 0.35
total_w, total_h = grid_w + gap, grid_h + gap
ox, oy = (PAGE_W_IN - total_w) / 2, (PAGE_H_IN - total_h) / 2
for r in range(2):
    for c in range(2):
        x = ox + c * (CARD_W_IN + gap)
        y = oy + r * (CARD_H_IN + gap)
        d.rectangle([I(x), I(y), I(x + CARD_W_IN) - 1, I(y + CARD_H_IN) - 1], fill=KEY)

os.makedirs("fixtures", exist_ok=True)
page.save("fixtures/ds_template.pdf", "PDF", resolution=DPI)
print("wrote fixtures/ds_template.pdf", page.size)

# --- 4 test card images with off-center content, to prove cover-fit + bleed ---
palettes = [((36, 62, 99), (122, 176, 224)), ((92, 38, 58), (231, 145, 129)),
            ((30, 74, 60), (146, 204, 150)), ((74, 56, 96), (190, 160, 226))]
for i, (bg, fg) in enumerate(palettes, 1):
    # deliberately wrong aspect ratio (square) to exercise cover-fit cropping
    im = Image.new("RGB", (1200, 1200), bg)
    dd = ImageDraw.Draw(im)
    for k in range(14):
        dd.ellipse([60 * k - 200, 60 * k - 200, 1400 - 40 * k, 1400 - 40 * k], outline=fg, width=7)
    dd.rectangle([40, 40, 1160, 1160], outline=fg, width=14)
    dd.text((90, 90), f"CARD {i}", fill=fg)
    im.save(f"fixtures/card{i}.png")
print("wrote 4 test card images")
