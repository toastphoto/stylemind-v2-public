#!/usr/bin/env python3
"""Render generated PPTX outputs to images and build a visual review contact sheet."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_visual_review_contact_sheet import draw_section, draw_tile, open_reference_samples  # noqa: E402


PLAN_JSON = ROOT / ".pytest_tmp/midea_social_render_plan.json"
PYTHON_PPTX = ROOT / ".pytest_tmp/midea_social_python_pptx.pptx"
PPTXGENJS_PPTX = ROOT / ".pytest_tmp/midea_social_pptxgenjs_spike.pptx"
RENDER_DIR = ROOT / ".pytest_tmp/pptx_render_review"
DEFAULT_OUTPUT = ROOT / ".pytest_tmp/midea_social_pptx_render_review_contact_sheet.jpg"


def tool_path(name: str, bundled: str | None = None) -> str:
    mac_app = Path(f"/Applications/LibreOffice.app/Contents/MacOS/{name}")
    if name == "soffice" and mac_app.exists():
        return str(mac_app)
    homebrew = Path(f"/opt/homebrew/bin/{name}")
    if name == "soffice" and homebrew.exists():
        return str(homebrew)
    found = shutil.which(name)
    if found:
        return found
    if bundled and Path(bundled).exists():
        return bundled
    raise SystemExit(f"Required tool not found: {name}")


def selected_pages(max_per_archetype: int) -> list[dict]:
    if not PLAN_JSON.exists():
        raise SystemExit(f"RenderPlan JSON not found: {PLAN_JSON}. Run scripts/verify_docx_outline_render_chain.py first.")
    payload = json.loads(PLAN_JSON.read_text(encoding="utf-8"))
    grouped: OrderedDict[str, list] = OrderedDict()
    for plan in payload.get("plans", []):
        visual = plan.get("visual_profile") or {}
        archetype = visual.get("archetype") or "unknown"
        grouped.setdefault(archetype, [])
        if len(grouped[archetype]) < max_per_archetype:
            grouped[archetype].append(
                {
                    "page": int(plan.get("index") or 0),
                    "role": ((plan.get("intent") or {}).get("page_role") or ""),
                    "archetype": archetype,
                }
            )
    return [item for items in grouped.values() for item in items]


def convert_pptx_to_pdf(pptx_path: Path) -> Path:
    soffice = tool_path("soffice", "/opt/homebrew/bin/soffice")
    with tempfile.TemporaryDirectory(prefix="stylemind_pptx_render_") as tmp:
        tmp_dir = Path(tmp)
        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(tmp_dir),
                str(pptx_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        pdfs = sorted(tmp_dir.glob("*.pdf"))
        if not pdfs:
            raise SystemExit(f"LibreOffice did not create a PDF for {pptx_path}")
        output_pdf = RENDER_DIR / f"{pptx_path.stem}.pdf"
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdfs[0], output_pdf)
        return output_pdf


def render_pdf_page(pdf_path: Path, page: int, out_prefix: Path) -> Path:
    pdftoppm = tool_path("pdftoppm")
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            pdftoppm,
            "-jpeg",
            "-r",
            "130",
            "-f",
            str(page),
            "-l",
            str(page),
            str(pdf_path),
            str(out_prefix),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    candidates = sorted(out_prefix.parent.glob(f"{out_prefix.name}-*.jpg"))
    if not candidates:
        raise SystemExit(f"pdftoppm did not render page {page} from {pdf_path}")
    final = out_prefix.with_suffix(".jpg")
    candidates[0].replace(final)
    return final


def render_pptx_samples(renderer: str, pptx_path: Path, page_records: list[dict]) -> list[dict]:
    if not pptx_path.exists():
        raise SystemExit(f"PPTX not found: {pptx_path}. Run scripts/verify_docx_outline_render_chain.py first.")
    pdf_path = convert_pptx_to_pdf(pptx_path)
    items = []
    for record in page_records:
        page = record["page"]
        image_path = render_pdf_page(pdf_path, page, RENDER_DIR / renderer / f"{renderer}_p{page:03d}")
        items.append(
            {
                "kind": renderer,
                "label": f"{renderer} P{page:02d} {record['role']} / {record['archetype']}",
                "image": Image.open(image_path),
            }
        )
    return items


def build_sheet(sections: list[tuple[str, list[dict]]], output: Path) -> dict:
    tile_w, tile_h = 320, 220
    margin = 28
    gap = 18
    cols = 3
    section_h = 48
    rows = [max(1, (len(items) + cols - 1) // cols) for _, items in sections]
    width = margin * 2 + cols * tile_w + (cols - 1) * gap
    height = margin * 2 + sum(section_h + row * tile_h + row * gap for row in rows)
    canvas = Image.new("RGB", (width, height), (245, 247, 251))
    draw = ImageDraw.Draw(canvas)

    y = margin
    for (title, items), row_count in zip(sections, rows):
        draw_section(draw, margin, y, title)
        y += section_h
        for idx, item in enumerate(items):
            row, col = divmod(idx, cols)
            draw_tile(draw, canvas, item, margin + col * (tile_w + gap), y + row * (tile_h + gap), tile_w, tile_h)
        y += row_count * (tile_h + gap)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92)
    return {"output": str(output), "width": width, "height": height}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-reference", type=int, default=9)
    parser.add_argument("--max-per-archetype", type=int, default=1)
    args = parser.parse_args()

    pages = selected_pages(args.max_per_archetype)
    if not pages:
        raise SystemExit("No visual archetype pages found in RenderPlan")

    reference_items = open_reference_samples(args.max_reference)
    python_items = render_pptx_samples("python-pptx", PYTHON_PPTX, pages)
    pptxgenjs_items = render_pptx_samples("pptxgenjs", PPTXGENJS_PPTX, pages)
    stats = build_sheet(
        [
            ("Reference campaign samples", reference_items),
            ("Rendered python-pptx output by visual archetype", python_items),
            ("Rendered PptxGenJS output by visual archetype", pptxgenjs_items),
        ],
        args.output,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                **stats,
                "reference_samples": len(reference_items),
                "python_pptx_samples": len(python_items),
                "pptxgenjs_samples": len(pptxgenjs_items),
                "pages": pages,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
