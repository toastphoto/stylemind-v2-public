#!/usr/bin/env python3
"""Verify cleaned reference templates with semantic placeholders."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "reference_samples" / "curated_templates" / "stylemind_cleaned_reference_templates.pptx"
REGISTRY = ROOT / "reference_samples" / "curated_templates" / "stylemind_cleaned_reference_templates_registry.json"
TMP = ROOT / ".pytest_tmp" / "cleaned_reference_template_probe"
PROBE_OUTPUT = TMP / "stylemind_cleaned_reference_template_probe.pptx"
PROBE_IMAGE = TMP / "cleaned-reference-probe-image.png"
PDF = TMP / "stylemind_cleaned_reference_template_probe.pdf"
CONTACT_SHEET = TMP / "cleaned_reference_template_probe_contact_sheet.jpg"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


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


def build_library() -> None:
    run(["node", "scripts/build_cleaned_reference_template_library.mjs"])
    if not TEMPLATE.exists():
        raise SystemExit(f"cleaned template deck missing: {TEMPLATE}")
    if not REGISTRY.exists():
        raise SystemExit(f"cleaned template registry missing: {REGISTRY}")


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


def missing_media_relationships(pptx_path: Path) -> list[tuple[str, str]]:
    with zipfile.ZipFile(pptx_path) as zf:
        names = set(zf.namelist())
        missing: list[tuple[str, str]] = []
        for rel_path in sorted(name for name in names if name.startswith("ppt/slides/_rels/") and name.endswith(".rels")):
            raw = zf.read(rel_path).decode("utf-8", errors="ignore")
            for target in re.findall(r'Target="([^"]+)"', raw):
                if not target.startswith("../media/"):
                    continue
                media_path = f"ppt/{target[3:]}"
                if media_path not in names:
                    missing.append((rel_path, media_path))
        return missing


def inspect_cleaned_template() -> dict:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if registry.get("schema") != "stylemind.cleaned_reference_template_library.v1":
        raise SystemExit(f"unexpected cleaned registry schema: {registry.get('schema')}")
    entries = registry.get("entries") or []
    if len(entries) < 18:
        raise SystemExit(f"expected at least 18 cleaned templates, got {len(entries)}")
    if registry.get("production_safe") is not False:
        raise SystemExit("cleaned template library must stay production_safe=false until visual QA is complete")

    targets = active_slide_targets(TEMPLATE)
    if len(targets) != len(entries):
        raise SystemExit(f"active slide count mismatch: {len(targets)} != {len(entries)}")
    missing_media = missing_media_relationships(TEMPLATE)
    if missing_media:
        raise SystemExit(f"cleaned template has broken media relationships: {missing_media[:8]}")

    allowed_text = {"{{title}}", "{{body}}"}
    with zipfile.ZipFile(TEMPLATE) as zf:
        for idx, (slide_path, entry) in enumerate(zip(targets, entries), start=1):
            raw = zf.read(slide_path).decode("utf-8", errors="ignore")
            names = set(re.findall(r'<p:cNvPr[^>]+name="([^"]+)"', raw))
            texts = [text.strip() for text in re.findall(r"<a:t>(.*?)</a:t>", raw) if text.strip()]
            required_names = {"title"}
            if "body" in set(entry.get("placeholders", {}).get("text", [])):
                required_names.add("body")
            missing = required_names - names
            if missing:
                raise SystemExit(f"slide {idx} missing placeholders: {sorted(missing)}")
            if not (set(entry.get("placeholders", {}).get("pictures", [])) & names):
                raise SystemExit(f"slide {idx} missing picture placeholder names")
            unexpected = [text for text in texts if text not in allowed_text]
            if unexpected:
                raise SystemExit(f"slide {idx} has non-placeholder editable text: {unexpected[:4]}")

    return {"entries": entries, "targets": targets}


def run_probe() -> dict:
    result = run(["node", "scripts/run_cleaned_reference_template_probe.mjs"])
    payload = json.loads(result.stdout)
    if not PROBE_OUTPUT.exists():
        raise SystemExit(f"probe output missing: {PROBE_OUTPUT}")
    if not PROBE_IMAGE.exists():
        raise SystemExit(f"probe image missing: {PROBE_IMAGE}")
    with zipfile.ZipFile(PROBE_OUTPUT) as zf:
        texts = []
        for target in active_slide_targets(PROBE_OUTPUT):
            raw = zf.read(target).decode("utf-8", errors="ignore")
            texts.extend(re.findall(r"<a:t>(.*?)</a:t>", raw))
    if payload["probeText"]["title"] not in texts:
        raise SystemExit("probe output missing replaced title")
    if payload["probeText"]["body"] not in texts:
        raise SystemExit("probe output missing replaced body")
    return payload


def convert_probe_to_pdf() -> Path:
    soffice = tool_path("soffice")
    run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(TMP), str(PROBE_OUTPUT)])
    if not PDF.exists():
        raise SystemExit(f"LibreOffice did not create PDF: {PDF}")
    return PDF


def render_probe_page(pdf_path: Path) -> Path:
    pdftoppm = tool_path("pdftoppm")
    prefix = TMP / "probe_page"
    run([pdftoppm, "-jpeg", "-r", "120", "-f", "1", "-l", "1", str(pdf_path), str(prefix)])
    pages = sorted(TMP.glob("probe_page-*.jpg"))
    if not pages:
        raise SystemExit(f"no rendered probe pages from {pdf_path}")
    return pages[0]


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


def build_contact_sheet(page_image: Path) -> None:
    image = Image.open(page_image).convert("RGB")
    thumb_w, thumb_h = 640, 360
    scale = max(thumb_w / image.width, thumb_h / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    left = max(0, (resized.width - thumb_w) // 2)
    top = max(0, (resized.height - thumb_h) // 2)
    crop = resized.crop((left, top, left + thumb_w, top + thumb_h))
    canvas = Image.new("RGB", (thumb_w + 56, thumb_h + 110), (245, 247, 251))
    draw = ImageDraw.Draw(canvas)
    draw.text((28, 24), "Cleaned reference template probe", fill=(17, 24, 39), font=load_font(28, bold=True))
    canvas.paste(crop, (28, 76))
    draw.rectangle((28, 76, 28 + thumb_w, 76 + thumb_h), outline=(203, 213, 225), width=2)
    CONTACT_SHEET.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(CONTACT_SHEET, quality=92)


def main() -> int:
    build_library()
    inspected = inspect_cleaned_template()
    probe = run_probe()
    pdf = convert_probe_to_pdf()
    page_count = len(PdfReader(str(pdf)).pages)
    if page_count != 1:
        raise SystemExit(f"expected one probe page, got {page_count}")
    rendered = render_probe_page(pdf)
    build_contact_sheet(rendered)
    summary = {
        "status": "ok",
        "template": str(TEMPLATE),
        "registry": str(REGISTRY),
        "entries": len(inspected["entries"]),
        "probe_output": str(PROBE_OUTPUT),
        "contact_sheet": str(CONTACT_SHEET),
        "production_safe": False,
        "picture_placeholder": probe["picturePlaceholder"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
