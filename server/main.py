"""cardsheet server - drop card art into a Cricut Print-Then-Cut template."""

from __future__ import annotations

import io
import json
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

import sheet as S
import stamp as ST

DATA = Path(os.environ.get("CARDSHEET_DATA", "/data"))
TEMPLATE_PDF = DATA / "ds_template.pdf"
META_JSON = DATA / "template.json"
SHEETS = DATA / "sheets"
STATIC = Path(os.environ.get("CARDSHEET_STATIC", "/app/static"))
MAX_UPLOAD = 40 * 1024 * 1024

app = FastAPI(title="cardsheet")

_cache: dict = {}


# ------------------------------------------------------------------ helpers

def load_template():
    """Rasterized template + slots, cached by file mtime."""
    if not TEMPLATE_PDF.exists():
        return None, None
    mtime = TEMPLATE_PDF.stat().st_mtime
    if _cache.get("mtime") != mtime:
        img = S.rasterize(TEMPLATE_PDF.read_bytes())
        _cache.update(mtime=mtime, img=img, slots=S.find_slots(img))
    return _cache["img"], _cache["slots"]


def template_payload():
    img, slots = load_template()
    if img is None:
        return {"loaded": False}
    meta = json.loads(META_JSON.read_text()) if META_JSON.exists() else {}
    return {
        "loaded": True,
        "filename": meta.get("filename", "ds_template.pdf"),
        "uploaded_at": meta.get("uploaded_at"),
        "page": {
            "w_px": img.width, "h_px": img.height,
            "w_in": round(img.width / S.DPI, 3), "h_in": round(img.height / S.DPI, 3),
            "w_cm": round(img.width / S.DPI * 2.54, 2), "h_cm": round(img.height / S.DPI * 2.54, 2),
        },
        "dpi": S.DPI,
        "slots": [s.json() for s in slots],
        "min_gap_mm": round(S.min_gap_px(slots) / S.DPI * 25.4, 2) if len(slots) > 1 else None,
        # Floor to whole pixels before converting. compose() turns bleed_mm
        # back into px with round(), so advertising half of an odd gap
        # (10.5 px -> 0.89 mm) comes back as 11 px and overlaps.
        "max_bleed_mm": (int(S.min_gap_px(slots) // 2 / S.DPI * 25.4 * 100) / 100
                         if len(slots) > 1 else 6.0),
    }


async def read_image(f: UploadFile) -> Image.Image:
    raw = await f.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, f"{f.filename} is over {MAX_UPLOAD // 1024 // 1024}MB.")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        return im
    except Exception:
        raise HTTPException(400, f"Could not read {f.filename} as an image.")


# -------------------------------------------------------------------- routes

@app.get("/api/template")
def get_template():
    try:
        return template_payload()
    except S.TemplateError as e:
        return {"loaded": False, "error": str(e)}


@app.post("/api/template")
async def put_template(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Template PDF is too large.")
    if not raw[:5].startswith(b"%PDF"):
        raise HTTPException(400, "That is not a PDF. Use Design Space's print-to-PDF output.")

    try:
        img = S.rasterize(raw)
        slots = S.find_slots(img)
    except S.TemplateError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Could not read that PDF: {e}")

    DATA.mkdir(parents=True, exist_ok=True)
    TEMPLATE_PDF.write_bytes(raw)
    META_JSON.write_text(json.dumps({
        "filename": file.filename,
        "uploaded_at": time.strftime("%Y-%m-%d %H:%M"),
        "slots": len(slots),
    }))
    _cache.clear()
    return template_payload()


@app.delete("/api/template")
def clear_template():
    for p in (TEMPLATE_PDF, META_JSON):
        p.unlink(missing_ok=True)
    _cache.clear()
    return {"loaded": False}


@app.get("/api/template/preview.png")
def template_preview(bleed_mm: float = 3.2, guides: bool = True):
    img, slots = load_template()
    if img is None:
        raise HTTPException(404, "No template loaded.")
    bleed_px = int(round(bleed_mm / 25.4 * S.DPI))
    return Response(S.preview_png(img, slots, bleed_px, guides=guides), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.post("/api/compose")
async def compose(files: list[UploadFile] = File(default=[]),
                  slots: str = Form("[]"),
                  bleed_mm: float = Form(3.2),
                  guides: bool = Form(False)):
    """files[i] belongs in slot index slots[i]."""
    img, slot_list = load_template()
    if img is None:
        raise HTTPException(400, "Upload the Design Space template PDF first.")

    try:
        idxs = json.loads(slots)
    except json.JSONDecodeError:
        raise HTTPException(400, "Bad slot mapping.")
    if len(idxs) != len(files):
        raise HTTPException(400, "Slot mapping does not match the uploaded files.")

    art: dict[int, Image.Image] = {}
    for f, i in zip(files, idxs):
        if not isinstance(i, int) or not (0 <= i < len(slot_list)):
            raise HTTPException(400, f"Slot {i} is out of range.")
        art[i] = await read_image(f)

    bleed_px = int(round(bleed_mm / 25.4 * S.DPI))
    # Stamp onto the original PDF page rather than rebuilding it as a raster.
    # The registration marks stay exactly as Design Space wrote them.
    out_pdf, warnings = ST.stamp(TEMPLATE_PDF.read_bytes(), slot_list, art, bleed_px)

    SHEETS.mkdir(parents=True, exist_ok=True)
    sid = uuid.uuid4().hex[:12]
    (SHEETS / f"{sid}.pdf").write_bytes(out_pdf)
    (SHEETS / f"{sid}.bleed").write_text(str(bleed_px))

    return JSONResponse({
        "id": sid,
        "pdf": f"/api/sheet/{sid}.pdf",
        "preview": f"/api/sheet/{sid}.png" + ("?guides=1" if guides else ""),
        "filled": sorted(art),
        "warnings": warnings,
        "page_in": [round(img.width / S.DPI, 3), round(img.height / S.DPI, 3)],
    })


@app.get("/api/sheet/{sid}/verify")
def verify_sheet(sid: str):
    """Prove this sheet's registration marks match the template exactly."""
    safe = "".join(c for c in sid if c.isalnum())
    p = SHEETS / f"{safe}.pdf"
    if not p.exists() or not TEMPLATE_PDF.exists():
        raise HTTPException(404, "No such sheet.")
    _, slot_list = load_template()
    bf = SHEETS / f"{safe}.bleed"
    bleed_px = int(bf.read_text()) if bf.exists() else int(round(3.2 / 25.4 * S.DPI))
    return ST.verify_marks_untouched(TEMPLATE_PDF.read_bytes(), p.read_bytes(),
                                     slot_list, bleed_px)


@app.get("/api/sheet/{sid}.pdf")
def get_sheet(sid: str, download: bool = False):
    p = SHEETS / f"{''.join(c for c in sid if c.isalnum())}.pdf"
    if not p.exists():
        raise HTTPException(404, "No such sheet.")
    return FileResponse(
        p, media_type="application/pdf",
        headers={"Content-Disposition":
                 f"{'attachment' if download else 'inline'}; filename=cardsheet_{sid}.pdf"},
    )


@app.get("/api/sheet/{sid}.png")
def get_sheet_png(sid: str, guides: bool = False):
    p = SHEETS / f"{''.join(c for c in sid if c.isalnum())}.pdf"
    if not p.exists():
        raise HTTPException(404, "No such sheet.")
    img = S.rasterize(p.read_bytes())
    _, slots = load_template()
    return Response(S.preview_png(img, slots or [], 0, guides=guides),
                    media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/health")
def health():
    return {"ok": True, "template": TEMPLATE_PDF.exists()}


if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
