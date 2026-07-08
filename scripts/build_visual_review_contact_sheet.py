#!/usr/bin/env python3
"""Build a review contact sheet comparing reference samples and RenderPlan previews."""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WEB_UI = ROOT / "web_ui"
if str(WEB_UI) not in sys.path:
    sys.path.insert(0, str(WEB_UI))

from services.renderers.plan_preview_renderer import render_plan_preview_png  # noqa: E402
from services.slide_render_plan import build_deck_render_plan  # noqa: E402


OUTLINE_CACHE = ROOT / ".pytest_tmp/midea_social_outline_upload_response.json"
REFERENCE_MANIFEST = ROOT / "reference_samples/brand_campaign_ingest/reference_manifest.json"
DEFAULT_OUTPUT = ROOT / ".pytest_tmp/midea_social_visual_review_contact_sheet.jpg"


def load_font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def resize_cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    img = img.convert("RGB")
    target_w, target_h = size
    scale = max(target_w / img.width, target_h / img.height)
    resized = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def open_reference_samples(max_items: int) -> list[dict]:
    if not REFERENCE_MANIFEST.exists():
        return []
    manifest = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    selected = []
    for entry in manifest.get("entries", []):
        samples = entry.get("rendered_samples") or []
        for sample in samples[:2]:
            image_path = ROOT / sample.get("image", "")
            if image_path.exists():
                selected.append(
                    {
                        "kind": "reference",
                        "label": f"{entry.get('file', 'reference')} p{sample.get('page')}",
                        "image": Image.open(image_path),
                    }
                )
                if len(selected) >= max_items:
                    return selected
    return selected


def load_outline_from_cache() -> dict:
    if not OUTLINE_CACHE.exists():
        raise SystemExit(f"Outline cache not found: {OUTLINE_CACHE}. Run scripts/verify_docx_outline_render_chain.py first.")
    cached = json.loads(OUTLINE_CACHE.read_text(encoding="utf-8"))
    return cached["upload_response"]["outline"]


def generated_preview_samples(max_per_archetype: int) -> list[dict]:
    outline = load_outline_from_cache()
    plans = build_deck_render_plan(outline)
    grouped: OrderedDict[str, list] = OrderedDict()
    for plan in plans:
        grouped.setdefault(plan.visual_profile.archetype, [])
        if len(grouped[plan.visual_profile.archetype]) < max_per_archetype:
            grouped[plan.visual_profile.archetype].append(plan)

    selected = []
    for archetype, items in grouped.items():
        for plan in items:
            image = Image.open(io.BytesIO(render_plan_preview_png(plan)))
            selected.append(
                {
                    "kind": "generated",
                    "label": f"P{plan.index:02d} {plan.intent.page_role} / {archetype}",
                    "image": image,
                }
            )
    return selected


def draw_section(draw: ImageDraw.ImageDraw, x: int, y: int, text: str) -> None:
    font = load_font(28, bold=True)
    draw.text((x, y), text, fill=(17, 24, 39), font=font)


def draw_tile(draw: ImageDraw.ImageDraw, canvas: Image.Image, item: dict, x: int, y: int, tile_w: int, tile_h: int) -> None:
    label_h = 46
    thumb = resize_cover(item["image"], (tile_w, tile_h - label_h))
    canvas.paste(thumb, (x, y))
    draw.rectangle((x, y, x + tile_w, y + tile_h - label_h), outline=(203, 213, 225), width=2)
    draw.rectangle((x, y + tile_h - label_h, x + tile_w, y + tile_h), fill=(248, 250, 252), outline=(203, 213, 225), width=1)
    font = load_font(15)
    label = item["label"]
    if len(label) > 46:
        label = label[:43] + "..."
    draw.text((x + 8, y + tile_h - label_h + 12), label, fill=(51, 65, 85), font=font)


def build_contact_sheet(reference_items: list[dict], generated_items: list[dict], output: Path) -> dict:
    tile_w, tile_h = 320, 220
    margin = 28
    gap = 18
    cols = 3
    section_h = 48

    ref_rows = max(1, (len(reference_items) + cols - 1) // cols)
    gen_rows = max(1, (len(generated_items) + cols - 1) // cols)
    width = margin * 2 + cols * tile_w + (cols - 1) * gap
    height = margin * 2 + section_h * 2 + (ref_rows + gen_rows) * tile_h + (ref_rows + gen_rows + 1) * gap
    canvas = Image.new("RGB", (width, height), (245, 247, 251))
    draw = ImageDraw.Draw(canvas)

    y = margin
    draw_section(draw, margin, y, "Reference campaign samples")
    y += section_h
    for idx, item in enumerate(reference_items):
        row, col = divmod(idx, cols)
        draw_tile(draw, canvas, item, margin + col * (tile_w + gap), y + row * (tile_h + gap), tile_w, tile_h)
    y += ref_rows * (tile_h + gap) + gap

    draw_section(draw, margin, y, "StyleMind RenderPlan previews by visual archetype")
    y += section_h
    for idx, item in enumerate(generated_items):
        row, col = divmod(idx, cols)
        draw_tile(draw, canvas, item, margin + col * (tile_w + gap), y + row * (tile_h + gap), tile_w, tile_h)

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92)
    return {
        "output": str(output),
        "reference_samples": len(reference_items),
        "generated_samples": len(generated_items),
        "width": width,
        "height": height,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-reference", type=int, default=9)
    parser.add_argument("--max-per-archetype", type=int, default=1)
    args = parser.parse_args()

    reference_items = open_reference_samples(args.max_reference)
    generated_items = generated_preview_samples(args.max_per_archetype)
    if not generated_items:
        raise SystemExit("No generated RenderPlan preview samples found")

    stats = build_contact_sheet(reference_items, generated_items, args.output)
    print(json.dumps({"status": "ok", **stats}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
