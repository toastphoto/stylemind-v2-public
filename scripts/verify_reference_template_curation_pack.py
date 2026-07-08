#!/usr/bin/env python3
"""Verify the reference-template curation work pack."""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".pytest_tmp" / "reference_template_curation_pack"
DECK = TMP / "reference_template_curation_pack.pptx"
PLAN = ROOT / "reference_samples" / "curated_templates" / "reference_template_curation_plan.json"
PDF = TMP / "reference_template_curation_pack.pdf"
RENDER_DIR = TMP / "rendered_pages"
CONTACT_SHEET = TMP / "reference_template_curation_contact_sheet.jpg"
EXPECTED_ARCHETYPES = {
    "hero_photo_claim",
    "section_divider",
    "strategy_claim_collage",
    "metric_dashboard",
    "evidence_wall",
    "campaign_timeline",
    "step_flow",
    "editorial_content_bridge",
    "video_material_board",
}


def tool_path(name: str, bundled: str | None = None) -> str:
    if name == "soffice":
        for candidate in ("/Applications/LibreOffice.app/Contents/MacOS/soffice", "/opt/homebrew/bin/soffice"):
            if Path(candidate).exists():
                return candidate
    found = shutil.which(name)
    if found:
        return found
    if bundled and Path(bundled).exists():
        return bundled
    raise SystemExit(f"required tool not found: {name}")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def active_slide_count(pptx_path: Path) -> int:
    with zipfile.ZipFile(pptx_path) as zf:
        root = ET.fromstring(zf.read("ppt/presentation.xml"))
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    return len(root.findall(".//p:sldId", ns))


def build_pack() -> dict:
    result = run(["node", "scripts/build_reference_template_curation_pack.mjs"])
    payload = json.loads(result.stdout)
    if not DECK.exists():
        raise SystemExit(f"curation pack deck missing: {DECK}")
    if not PLAN.exists():
        raise SystemExit(f"curation plan missing: {PLAN}")
    return payload


def validate_plan() -> dict:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if plan.get("schema") != "stylemind.reference_template_curation_plan.v1":
        raise SystemExit(f"unexpected curation plan schema: {plan.get('schema')}")
    selected = plan.get("selected") or []
    if plan.get("production_safe") is not False:
        raise SystemExit("curation plan must remain marked production_safe=false")
    if len(selected) < 18:
        raise SystemExit(f"expected at least 18 curation candidates, got {len(selected)}")
    archetypes = {item for row in selected for item in row.get("archetypes", [])}
    missing = sorted(EXPECTED_ARCHETYPES - archetypes)
    if missing:
        raise SystemExit(f"curation pack missing archetypes: {missing}")
    weak = [row for row in selected if row.get("readiness") == "weak"]
    if weak:
        raise SystemExit(f"curation pack contains weak candidates: {weak[:3]}")
    for row in selected:
        placeholders = row.get("suggested_placeholders") or {}
        if not placeholders.get("text_targets") and not placeholders.get("picture_targets"):
            raise SystemExit(f"candidate has no suggested placeholders: {row.get('candidate_id')}")
    deck_slides = active_slide_count(DECK)
    if deck_slides != len(selected):
        raise SystemExit(f"deck slide count mismatch: {deck_slides} != {len(selected)}")
    return plan


def convert_to_pdf() -> Path:
    soffice = tool_path("soffice")
    run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(TMP), str(DECK)])
    if not PDF.exists():
        raise SystemExit(f"LibreOffice did not create PDF: {PDF}")
    return PDF


def render_pdf_pages(pdf_path: Path) -> list[Path]:
    pdftoppm = tool_path("pdftoppm")
    if RENDER_DIR.exists():
        shutil.rmtree(RENDER_DIR)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    run([pdftoppm, "-jpeg", "-r", "100", str(pdf_path), str(RENDER_DIR / "page")])
    pages = sorted(RENDER_DIR.glob("page-*.jpg"))
    if not pages:
        raise SystemExit(f"no rendered pages from {pdf_path}")
    return pages


def load_font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
    return ImageFont.load_default()


def build_contact_sheet(page_images: list[Path], plan: dict) -> None:
    thumb_w, thumb_h = 300, 169
    margin, gap = 24, 16
    cols = 4
    rows = (len(page_images) + cols - 1) // cols
    width = margin * 2 + cols * thumb_w + (cols - 1) * gap
    height = margin * 2 + 54 + rows * (thumb_h + 42) + (rows - 1) * gap
    canvas = Image.new("RGB", (width, height), (245, 247, 251))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin), "Reference template curation pack", fill=(17, 24, 39), font=load_font(28, bold=True))
    selected = plan.get("selected") or []
    label_font = load_font(14)
    y0 = margin + 54
    for idx, image_path in enumerate(page_images):
        x = margin + (idx % cols) * (thumb_w + gap)
        y = y0 + (idx // cols) * (thumb_h + 42 + gap)
        image = Image.open(image_path).convert("RGB")
        scale = max(thumb_w / image.width, thumb_h / image.height)
        resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
        left = max(0, (resized.width - thumb_w) // 2)
        top = max(0, (resized.height - thumb_h) // 2)
        canvas.paste(resized.crop((left, top, left + thumb_w, top + thumb_h)), (x, y))
        draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline=(203, 213, 225), width=2)
        row = selected[idx] if idx < len(selected) else {}
        label = f"{idx + 1:02d} {row.get('candidate_id', '')} {'/'.join(row.get('archetypes', [])[:2])}"
        draw.rectangle((x, y + thumb_h, x + thumb_w, y + thumb_h + 42), fill=(248, 250, 252), outline=(203, 213, 225))
        draw.text((x + 8, y + thumb_h + 12), label[:48], fill=(51, 65, 85), font=label_font)
    CONTACT_SHEET.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(CONTACT_SHEET, quality=92)


def main() -> int:
    build_pack()
    plan = validate_plan()
    pdf = convert_to_pdf()
    page_count = len(PdfReader(str(pdf)).pages)
    if page_count != int(plan["selected_count"]):
        raise SystemExit(f"PDF page count mismatch: {page_count} != {plan['selected_count']}")
    pages = render_pdf_pages(pdf)
    build_contact_sheet(pages, plan)
    summary = {
        "status": "ok",
        "deck": str(DECK),
        "plan": str(PLAN),
        "pdf": str(pdf),
        "contact_sheet": str(CONTACT_SHEET),
        "selected_count": plan["selected_count"],
        "archetypes": sorted({item for row in plan["selected"] for item in row.get("archetypes", [])}),
        "production_safe": plan["production_safe"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
