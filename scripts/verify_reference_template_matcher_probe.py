#!/usr/bin/env python3
"""Verify the reference-template-first route for higher-aesthetic PPTX output."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".pytest_tmp" / "reference_template_probe"
DEFAULT_INPUT = ROOT / ".pytest_tmp" / "midea_social_render_plan.json"
CLEANED_REGISTRY = ROOT / "reference_samples" / "curated_templates" / "stylemind_cleaned_reference_templates_registry.json"
OUTPUT = TMP / "stylemind_reference_template_match_verified.pptx"
REPORT = TMP / "reference_template_match_verified_report.json"
PDF = TMP / "stylemind_reference_template_match_verified.pdf"
RENDER_DIR = TMP / "verified_pages"
CONTACT_SHEET = TMP / "reference_template_match_verified_contact_sheet.jpg"


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
    raise SystemExit(f"Required tool not found: {name}")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def slide_xml_counts(pptx_path: Path) -> dict:
    with zipfile.ZipFile(pptx_path) as zf:
        slide_names = sorted(name for name in zf.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
        names = set(zf.namelist())
        active_slide_ids = []
        try:
            root = ET.fromstring(zf.read("ppt/presentation.xml"))
            ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
            active_slide_ids = [node.attrib for node in root.findall(".//p:sldId", ns)]
        except Exception:
            active_slide_ids = []
        text_nodes = 0
        picture_tags = 0
        shape_tags = 0
        missing_media = []
        for name in slide_names:
            raw = zf.read(name).decode("utf-8", errors="ignore")
            text_nodes += raw.count("<a:t>")
            picture_tags += raw.count("<p:pic>")
            shape_tags += raw.count("<p:sp>")
        for rel_path in sorted(name for name in names if name.startswith("ppt/slides/_rels/") and name.endswith(".rels")):
            raw = zf.read(rel_path).decode("utf-8", errors="ignore")
            for target in raw.split('Target="')[1:]:
                target = target.split('"', 1)[0]
                if target.startswith("../media/") and f"ppt/{target[3:]}" not in names:
                    missing_media.append((rel_path, target))
    return {
        "slide_xml_files": len(slide_names),
        "presentation_slide_ids": len(active_slide_ids),
        "text_nodes": text_nodes,
        "picture_tags": picture_tags,
        "shape_tags": shape_tags,
        "missing_media_relationships": missing_media,
    }


def active_slide_targets(pptx_path: Path) -> list[str]:
    with zipfile.ZipFile(pptx_path) as zf:
        presentation = ET.fromstring(zf.read("ppt/presentation.xml"))
        rels = ET.fromstring(zf.read("ppt/_rels/presentation.xml.rels"))
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"].lstrip("../") for rel in rels.findall("rel:Relationship", ns)}
    targets = []
    for node in presentation.findall(".//p:sldId", ns):
        rid = node.attrib.get(f"{{{ns['r']}}}id")
        if rid in rel_map:
            targets.append(f"ppt/{rel_map[rid]}")
    return targets


def active_text_values(pptx_path: Path) -> list[str]:
    texts: list[str] = []
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    with zipfile.ZipFile(pptx_path) as zf:
        for target in active_slide_targets(pptx_path):
            root = ET.fromstring(zf.read(target))
            for node in root.findall(".//a:t", ns):
                if node.text and node.text.strip():
                    texts.append(node.text.strip())
    return texts


def convert_to_pdf(pptx_path: Path) -> Path:
    soffice = tool_path("soffice")
    run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(TMP), str(pptx_path)])
    pdf = TMP / f"{pptx_path.stem}.pdf"
    if not pdf.exists():
        raise SystemExit(f"LibreOffice did not create PDF: {pdf}")
    return pdf


def render_pdf_pages(pdf_path: Path) -> list[Path]:
    pdftoppm = tool_path("pdftoppm")
    if RENDER_DIR.exists():
        shutil.rmtree(RENDER_DIR)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    run([pdftoppm, "-jpeg", "-r", "120", str(pdf_path), str(RENDER_DIR / "page")])
    pages = sorted(RENDER_DIR.glob("page-*.jpg"))
    if not pages:
        raise SystemExit(f"No rendered pages from PDF: {pdf_path}")
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


def build_contact_sheet(page_images: list[Path], output: Path) -> None:
    thumb_w, thumb_h = 360, 203
    margin, gap = 28, 18
    cols = 3
    rows = (len(page_images) + cols - 1) // cols
    width = margin * 2 + cols * thumb_w + (cols - 1) * gap
    height = margin * 2 + 56 + rows * (thumb_h + 38) + (rows - 1) * gap
    canvas = Image.new("RGB", (width, height), (245, 247, 251))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin), "Reference-template-first verified output", fill=(17, 24, 39), font=load_font(30, bold=True))
    y0 = margin + 56
    label_font = load_font(18)
    for idx, image_path in enumerate(page_images):
        x = margin + (idx % cols) * (thumb_w + gap)
        y = y0 + (idx // cols) * (thumb_h + 38 + gap)
        image = Image.open(image_path).convert("RGB")
        scale = max(thumb_w / image.width, thumb_h / image.height)
        resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
        left = max(0, (resized.width - thumb_w) // 2)
        top = max(0, (resized.height - thumb_h) // 2)
        canvas.paste(resized.crop((left, top, left + thumb_w, top + thumb_h)), (x, y))
        draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline=(203, 213, 225), width=2)
        draw.rectangle((x, y + thumb_h, x + thumb_w, y + thumb_h + 38), fill=(248, 250, 252), outline=(203, 213, 225))
        draw.text((x + 8, y + thumb_h + 10), f"P{idx + 1:02d} template-first", fill=(51, 65, 85), font=label_font)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92)


def main() -> int:
    if not DEFAULT_INPUT.exists():
        raise SystemExit(f"RenderPlan not found: {DEFAULT_INPUT}. Run scripts/verify_docx_outline_render_chain.py first.")
    TMP.mkdir(parents=True, exist_ok=True)
    run(
        [
            "node",
            "scripts/run_reference_template_matcher_probe.mjs",
            "--input",
            str(DEFAULT_INPUT.relative_to(ROOT)),
            "--output",
            str(OUTPUT.relative_to(ROOT)),
            "--report",
            str(REPORT.relative_to(ROOT)),
            "--max-pages",
            "9",
        ]
    )
    pdf = convert_to_pdf(OUTPUT)
    page_count = len(PdfReader(str(pdf)).pages)
    page_images = render_pdf_pages(pdf)
    build_contact_sheet(page_images, CONTACT_SHEET)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    selected = report.get("selected", [])
    if CLEANED_REGISTRY.exists():
        if not report.get("cleanedLibraryUsed"):
            raise SystemExit("reference-template matcher did not enable cleaned reference template library")
        non_cleaned = [item for item in selected if item.get("matchSource") != "cleaned-library"]
        if non_cleaned:
            raise SystemExit(f"reference-template matcher did not prefer cleaned templates: {non_cleaned[:3]}")
    elif not report.get("registryUsed"):
        raise SystemExit("reference-template matcher did not use template registry fallback")
    weak = [item for item in report.get("selected", []) if item.get("templateReadiness") == "weak"]
    if weak:
        raise SystemExit(f"reference-template matcher selected weak templates: {weak[:3]}")
    counts = slide_xml_counts(OUTPUT)
    if counts["missing_media_relationships"]:
        raise SystemExit(f"reference-template output has broken media relationships: {counts['missing_media_relationships'][:8]}")
    if page_count != report.get("pageCount"):
        raise SystemExit(f"PDF page count mismatch: expected {report.get('pageCount')}, got {page_count}")
    if counts["picture_tags"] < page_count:
        raise SystemExit(f"expected reference pictures to be preserved, got {counts['picture_tags']}")
    picture_summary = report.get("pictureReplacementSummary") or {}
    if picture_summary.get("totalReplacements", 0) < page_count:
        raise SystemExit(f"expected picture relationship replacements, got {picture_summary}")
    stale_skips = [
        item
        for item in selected
        if (item.get("pictureReplacement") or {}).get("skipped") == "no_current_page_assets"
    ]
    if stale_skips:
        raise SystemExit(f"reference-template output still uses stale no-current-asset skips: {stale_skips[:3]}")
    unsafe = [
        item
        for item in selected
        if "automizer_copy_unsafe" in (item.get("templateQualityTags") or [])
    ]
    if unsafe:
        raise SystemExit(f"reference-template matcher selected copy-unsafe templates: {unsafe[:3]}")
    hard_red = [
        item
        for item in selected
        if "hard_red_chrome" in (item.get("templateQualityTags") or [])
    ]
    if hard_red:
        raise SystemExit(f"reference-template matcher selected hard red chrome templates: {hard_red[:3]}")
    placeholder_text = [text for text in active_text_values(OUTPUT) if "{{" in text or "}}" in text or text.startswith("请输入")]
    if placeholder_text:
        raise SystemExit(f"active slides still contain template placeholder text: {placeholder_text[:8]}")
    summary = {
        "status": "ok",
        "strategy": "reference_template_first",
        "output": str(OUTPUT),
        "pdf": str(pdf),
        "contact_sheet": str(CONTACT_SHEET),
        "page_count": page_count,
        "pptx_size_mb": round(OUTPUT.stat().st_size / 1024 / 1024, 1),
        "xml_counts": counts,
        "selected": selected,
        "known_limitations": [
            "cleaned reference templates are still production_safe=false until visual QA is complete",
            "pages without current background_images or fixed_images receive generated neutral placeholders and still need final visual assets",
            "some source text may be baked into images or grouped artwork",
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
