# cardsheet — context for Claude Code

Read this before changing anything. It records what is verified, what is not,
and the constraints that are not obvious from the code.

## What this is

A self-hosted web app for Cricut Print-Then-Cut card sheets. Tyler drops four
card images on a page, prints it on his own printer as many times as he likes,
and Cricut only does the cutting.

## The one idea everything depends on

Design Space owns the registration marks. We never draw them. The user exports
one print-to-PDF from Design Space with magenta `#FF00FF` placeholder
rectangles where cards go, and every sheet we build **is that PDF page** with
art stamped on top as a content-stream overlay (`server/stamp.py`).

Original page objects are never re-encoded. That matters: the real template's
top-left corner mark carries a small orientation **arrow**, and re-rastering
the page would redraw it. `verify_marks_untouched()` proves it each build by
isolating every ink pixel outside the card areas and diffing. Verified on the
real template: **41,175 mark pixels, zero changed**, plus zero change in a 20px
halo around them.

There is a legacy raster path (`sheet.compose`) that rebuilds the page as a
300 DPI image. It is **not** used by the API. Do not switch back to it.

## Hard constraints, learned the expensive way

- **Page geometry is sacred.** `sheet.rasterize()` snaps the raster back to the
  PDF's declared size because pdfium rounds up. A page off by one pixel invites
  the printer to rescale, which moves the marks and ruins the cut. Output must
  stay exactly 612 x 792 pt for Letter.
- **Design Space bleed must be OFF at export.** It inflates each placeholder by
  ~0.76 mm per side (0.03 in), so we detect the bleed edge instead of the cut
  line, and it eats the gaps between cards. Tyler's first template had this
  bug: 63 x 88 mm cards measured 64.52 x 89.49, and a 1.77 mm gap collapsed to
  0.25 mm. `min_gap_px()` / `max_bleed_mm` exist to catch it in the UI.
- **Bleed can only use half the gap per side.** Print Then Cut drifts about
  ±1 mm, so aim for 8 mm gaps (4 mm of headroom).
- **Slot detection is geometry-driven.** Nothing is hardcoded. Any grid of
  magenta rectangles works, returned in reading order. A 2x3 legal or 4x4
  tabloid template needs no code change.

## Layout

```
server/        FastAPI. sheet.py = detection/geometry, stamp.py = PDF overlay
               + verification, main.py = routes.
web/           Svelte 5 + Vite 6, built to static, served by FastAPI.
cli/           Standalone scripts. cardsheet.py does the same job headless;
               make_template.py generates placeholder SVGs; make_fixture.py
               builds a synthetic template so you can test without Tyler's PDF.
templates/     Ready-made placeholder SVGs to upload to Design Space.
```

Data lives in `/data` (a Docker volume): `ds_template.pdf`, `template.json`,
`sheets/*.pdf`.

## Verified

Driven in a real browser with Playwright, against Tyler's actual template:
template upload, slot detection, all four drop targets, build, mark
verification, gap warning. CLI and API outputs were pixel-identical when both
used the raster path.

## Shipped and verified on 2026-09-12

All three items that used to be unverified now are.

1. **The Docker build works.** First run of `.github/workflows/docker.yml`
   passed in 1m19s. Both stages build clean.
2. **Pushed.** `github.com/tylergraydev/cardsheet` is public, branch `main`.
   The local branch was `master` and had to be renamed, since the workflow
   only triggers on `main`.
3. **GHCR publish works.** `ghcr.io/tylergraydev/cardsheet:latest` plus a
   `sha-` tag. linux/amd64, 146 MB, 9 layers. Verified by doing the same
   token-then-manifest sequence `docker pull` does: anonymous fetch of the
   manifest, tag list, and config blob all succeed, so the package is
   **already public** with no visibility change needed. GitHub no longer
   defaults Actions-published packages to private in a public repo. The old
   note here said that flip was mandatory. It is not.

Still not done: **the container has never been run.** The image builds and
pulls, but nothing has started it and no sheet has been built from inside it.
That is the next thing to prove, on Unraid.

## Deploying it

GitHub and GHCR are done. What remains is Unraid:

Drop `unraid-template.xml` into
`/boot/config/plugins/dockerMan/templates-user/` and pick **cardsheet** from
the template dropdown. Port 8080, appdata at `/mnt/user/appdata/cardsheet`.

`DEPLOY-UNRAID.md` has the full detail plus two fallback routes.

Note: pushing to GHCR does **not** list it in Unraid Community Applications.
CA is a curated catalog requiring a separate submission at ca.unraid.net/submit.
Not needed to run it yourself.

## Testing locally without Docker

```bash
pip install -r server/requirements.txt
cd web && npm install && npm run build && cd ..
python3 cli/make_fixture.py                     # synthetic template + test art
CARDSHEET_DATA=./data CARDSHEET_STATIC=./web/dist \
  python3 -m uvicorn main:app --app-dir server --port 8000
```

Upload `fixtures/ds_template.pdf` and drop the four `fixtures/card*.png`.
The fixture's marks are fake and will not cut — testing only.

## Conventions

- Tyler dislikes em dashes in prose. Keep them out of docs and UI copy.
- Direct and technically precise. No hedging, no filler.
- Measurements in mm/cm in the UI, since the cards are metric (63 x 88 mm).
