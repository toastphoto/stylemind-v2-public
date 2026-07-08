from __future__ import annotations

import base64
import io
import os
import re
import textwrap
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont

try:
    from services.slide_render_plan import SlideRenderPlan
except Exception:  # pragma: no cover - fallback when imported as package module
    from ..slide_render_plan import SlideRenderPlan


SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5
CANVAS_W = 1280
CANVAS_H = 720
GENERATED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static", "generated"))


def _rgb(hex_color: str, default: str = "#1E293B") -> tuple[int, int, int]:
    color = (hex_color or default).strip()
    if len(color) != 7 or not color.startswith("#"):
        color = default
    try:
        return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    except ValueError:
        return _rgb(default)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _component_spec(plan: SlideRenderPlan) -> dict:
    spec = getattr(plan, "component_spec", {}) or {}
    return spec if isinstance(spec, dict) else {}


def _render_hint(plan: SlideRenderPlan, key: str, default=True):
    hints = _component_spec(plan).get("render_hints") or {}
    if not isinstance(hints, dict):
        return default
    return hints.get(key, default)


def _primary_module_key(plan: SlideRenderPlan) -> str:
    modules = _component_spec(plan).get("modules") or []
    if isinstance(modules, list) and modules and isinstance(modules[0], dict):
        return str(modules[0].get("key") or "")
    return str(_render_hint(plan, "primary_module_key", "") or "")


def _box(inch_box: Sequence[float]) -> tuple[int, int, int, int]:
    x, y, w, h = inch_box
    return (
        int(x / SLIDE_W_IN * CANVAS_W),
        int(y / SLIDE_H_IN * CANVAS_H),
        int((x + w) / SLIDE_W_IN * CANVAS_W),
        int((y + h) / SLIDE_H_IN * CANVAS_H),
    )


def _image_from_source(image_source: str) -> Image.Image | None:
    source = str(image_source or "").strip()
    if not source:
        return None
    if source.startswith("data:image") and "," in source:
        try:
            return Image.open(io.BytesIO(base64.b64decode(source.split(",", 1)[1]))).convert("RGB")
        except Exception:
            return None

    candidates = [source]
    if source.startswith("/api/generated/"):
        rel = source.split("/api/generated/", 1)[1]
        candidates.append(os.path.join(GENERATED_DIR, rel))
    if not os.path.isabs(source):
        candidates.append(os.path.abspath(source))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            try:
                return Image.open(candidate).convert("RGB")
            except Exception:
                continue
    return None


def _cover_canvas(image: Image.Image) -> Image.Image:
    src_w, src_h = image.size
    if src_w <= 0 or src_h <= 0:
        return Image.new("RGB", (CANVAS_W, CANVAS_H), (255, 255, 255))
    scale = max(CANVAS_W / src_w, CANVAS_H / src_h)
    resized = image.resize((int(src_w * scale), int(src_h * scale)))
    left = max(0, (resized.width - CANVAS_W) // 2)
    top = max(0, (resized.height - CANVAS_H) // 2)
    return resized.crop((left, top, left + CANVAS_W, top + CANVAS_H))


def _draw_round_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str | None = None, radius: int = 14, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=_rgb(fill), outline=_rgb(outline) if outline else None, width=width)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    for raw in str(text or "").splitlines() or [""]:
        raw = raw.strip()
        if not raw:
            continue
        if _text_width(draw, raw, font) <= max_width:
            lines.append(raw)
        else:
            wrapped = textwrap.wrap(raw, width=max(8, int(max_width / max(font.size, 12) * 1.8)))
            if wrapped:
                lines.extend(wrapped)
            else:
                lines.append(raw[:40])
        if len(lines) >= max_lines:
            break
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines and len(lines) == max_lines:
        lines[-1] = lines[-1][: max(0, len(lines[-1]) - 1)] + "..."
    return lines


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font,
    fill: str,
    max_lines: int,
    line_gap: int = 8,
) -> None:
    x0, y0, x1, y1 = box
    y = y0
    for line in _wrap_text(draw, text, font, max(10, x1 - x0), max_lines):
        draw.text((x0, y), line, fill=_rgb(fill), font=font)
        y += font.size + line_gap
        if y > y1:
            break


def _draw_body(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], lines: Iterable[str]) -> None:
    x0, y0, x1, y1 = box
    font = _font(25)
    y = y0
    for line in list(lines)[:5]:
        _draw_wrapped(draw, (x0, y, x1, min(y1, y + 70)), str(line), font, "#233044", max_lines=2, line_gap=5)
        y += 72
        if y >= y1:
            break


def _soft_fill(hex_color: str, amount: float = 0.82) -> tuple[int, int, int]:
    base = _rgb(hex_color)
    return tuple(int(channel + (255 - channel) * amount) for channel in base)


def _draw_photo_field(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], accent: str, label: str, mode: str = "hero") -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=18, fill=_soft_fill(accent, 0.82), outline=_rgb(accent), width=2)
    if mode in {"hero", "cutout", "evidence", "thumbnail"}:
        for idx in range(7):
            y = y0 + int((idx + 1) * (y1 - y0) / 8)
            color = _soft_fill(accent, 0.68 + idx * 0.025)
            draw.rectangle((x0, y, x1, min(y1, y + 42)), fill=color)
    if mode == "evidence":
        card_w = max(80, (x1 - x0 - 56) // 2)
        card_h = max(52, (y1 - y0 - 68) // 2)
        for row in range(2):
            for col in range(2):
                cx = x0 + 20 + col * (card_w + 16)
                cy = y0 + 22 + row * (card_h + 16)
                draw.rounded_rectangle((cx, cy, cx + card_w, cy + card_h), radius=10, fill=(255, 255, 255), outline=_rgb("#CBD5E1"), width=2)
                draw.rectangle((cx + 10, cy + 12, cx + card_w - 10, cy + 28), fill=_soft_fill(accent, 0.62))
                draw.line((cx + 10, cy + card_h - 18, cx + card_w - 10, cy + card_h - 18), fill=_rgb("#CBD5E1"), width=2)
    else:
        draw.line((x0 + 24, y1 - 28, x1 - 24, y0 + 28), fill=_rgb(accent), width=3)
        draw.line((x0 + 24, y0 + 28, x1 - 24, y1 - 28), fill=_soft_fill(accent, 0.4), width=3)
    _draw_wrapped(draw, (x0 + 24, y0 + 22, x1 - 24, y0 + 86), label, _font(21, bold=True), "#334155", 2)


def _extract_metric_value(text: str) -> str:
    match = re.search(r"([+-]?\d+(?:\.\d+)?\s*%|[+-]?\d+(?:\.\d+)?\s*(?:万|亿|k|K|w|W)?)", text or "")
    return match.group(1).replace(" ", "") if match else (text or "")[:12]


def _split_metric_text(text: str, fallback_label: str) -> tuple[str, str]:
    raw = str(text or "").strip()
    value = _extract_metric_value(raw)
    label = re.split(r"[:：\s]+", raw, maxsplit=1)[0][:14] or fallback_label
    if label == value:
        label = fallback_label
    return label, value


def _draw_metric_tile(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, value: str, accent: str) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=18, fill=(255, 255, 255), outline=_rgb(accent), width=3)
    draw.rectangle((x0, y0, x0 + 10, y1), fill=_rgb(accent))
    _draw_wrapped(draw, (x0 + 24, y0 + 20, x1 - 20, y0 + 58), label, _font(18, bold=True), "#475569", 1)
    _draw_wrapped(draw, (x0 + 24, y0 + 70, x1 - 20, y1 - 24), value, _font(36, bold=True), accent, 1)


def _draw_feibo_metric_strip(draw: ImageDraw.ImageDraw, plan: SlideRenderPlan, accent: str, soft: str) -> None:
    boxes = [_box(card) for card in plan.layout_spec.card_boxes]
    if not boxes:
        return
    metrics = list(plan.card_texts) or list(plan.body_lines) or [plan.layout_spec.label]

    x0, y0, x1, y1 = boxes[0]
    label, value = _split_metric_text(metrics[0], "核心指标")
    draw.rounded_rectangle((x0, y0, x1, y1), radius=20, fill=_soft_fill(soft, 0.42), outline=_rgb("#FFFFFF"), width=2)
    _draw_wrapped(draw, (x0 + 24, y0 + 22, x1 - 24, y0 + 58), label, _font(20, bold=True), "#64748B", 1)
    _draw_wrapped(draw, (x0 + 24, y0 + 76, x1 - 24, y1 - 48), value, _font(52, bold=True), accent, 1)
    draw.rectangle((x0 + 24, y1 - 34, x0 + int((x1 - x0) * 0.48), y1 - 28), fill=_rgb(accent))

    for idx, box in enumerate(boxes[1:], start=1):
        bx0, by0, bx1, by1 = box
        support_label, support_value = _split_metric_text(metrics[idx % len(metrics)], f"支撑指标 {idx}")
        draw.rounded_rectangle((bx0, by0 + 14, bx1, by1), radius=18, fill=(255, 255, 255), outline=_rgb("#E2E8F0"), width=2)
        _draw_wrapped(draw, (bx0 + 20, by0 + 34, bx1 - 20, by0 + 66), support_label, _font(17, bold=True), "#64748B", 1)
        _draw_wrapped(draw, (bx0 + 20, by0 + 82, bx1 - 20, by1 - 20), support_value, _font(32, bold=True), "#0F172A", 1)


def _draw_reference_texture(draw: ImageDraw.ImageDraw, plan: SlideRenderPlan, accent: str, soft: str) -> None:
    visual = plan.visual_profile
    if visual.archetype in {"section_divider", "campaign_timeline", "metric_dashboard"} or plan.grid:
        for x in range(90, CANVAS_W - 80, 96):
            draw.line((x, 82, x, CANVAS_H - 78), fill=_rgb(soft), width=1)
        for y in range(108, CANVAS_H - 84, 84):
            draw.line((72, y, CANVAS_W - 72, y), fill=_rgb(soft), width=1)

    if visual.archetype == "evidence_wall":
        for idx in range(5):
            x = 86 + idx * 104
            y = 612
            draw.rounded_rectangle((x, y, x + 82, y + 48), radius=8, outline=_rgb(accent), width=2, fill=_rgb("#FFFFFF"))
    elif visual.archetype == "strategy_claim_collage":
        for idx, size in enumerate((42, 30, 24)):
            x = 1040 + idx * 48
            y = 92 + idx * 34
            draw.rectangle((x, y, x + size, y + size), fill=_rgb(soft), outline=_rgb(accent), width=2)
    elif visual.archetype == "campaign_timeline":
        y = 630
        draw.line((170, y, 1070, y), fill=_rgb(accent), width=4)
        for x in (250, 560, 870):
            draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=_rgb(accent))


def _draw_archetype_foreground(draw: ImageDraw.ImageDraw, plan: SlideRenderPlan, accent: str, soft: str) -> bool:
    visual = plan.visual_profile
    spec = plan.layout_spec
    if _primary_module_key(plan) == "feibo_metric_result_strip":
        _draw_feibo_metric_strip(draw, plan, accent, soft)
        return True
    if visual.archetype in {"metric_dashboard", "campaign_timeline", "step_flow"}:
        for idx, card in enumerate(spec.card_boxes):
            card_box = _box(card)
            text = plan.card_texts[idx % len(plan.card_texts)] if plan.card_texts else spec.label
            if visual.archetype == "metric_dashboard":
                _draw_metric_tile(draw, card_box, str(text).split("：", 1)[0][:12], _extract_metric_value(str(text)), accent)
            else:
                x0, y0, x1, y1 = card_box
                draw.rounded_rectangle(card_box, radius=16, fill=(255, 255, 255), outline=_rgb(accent), width=2)
                draw.ellipse((x0 + 18, y0 + 18, x0 + 48, y0 + 48), fill=_rgb(accent))
                draw.text((x0 + 29, y0 + 23), str(idx + 1), fill=(255, 255, 255), font=_font(17, bold=True))
                _draw_wrapped(draw, (x0 + 62, y0 + 18, x1 - 16, y1 - 14), str(text), _font(18, bold=idx == 0), "#334155", 4)
        return True

    if visual.archetype == "evidence_wall" and spec.image_box:
        _draw_photo_field(draw, _box(spec.image_box), accent, "证据截图 / 素材占位", "evidence")
        return False

    if visual.archetype in {"hero_photo_claim", "strategy_claim_collage", "video_material_board"} and spec.image_box:
        label = "主视觉素材" if visual.archetype != "video_material_board" else "视频缩略图 / DEMO"
        _draw_photo_field(draw, _box(spec.image_box), accent, label, visual.image_treatment)
        return False

    return False


def render_plan_preview_png(plan: SlideRenderPlan) -> bytes:
    spec = plan.layout_spec
    paper = plan.paper or "#F8FAFC"
    accent = plan.accent or spec.accent
    soft = plan.soft or "#E2E8F0"

    background_source = (getattr(plan, "background_sources", None) or ("",))[0] if getattr(plan, "background_sources", None) else ""
    background_image = _image_from_source(background_source)
    if background_image:
        img = _cover_canvas(background_image)
        overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (*_rgb(paper, "#F8FAFC"), 56))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    else:
        img = Image.new("RGB", (CANVAS_W, CANVAS_H), _rgb(paper, "#F8FAFC"))
    draw = ImageDraw.Draw(img)
    _draw_reference_texture(draw, plan, accent, soft)

    if _render_hint(plan, "show_left_rail", True):
        draw.rectangle((0, 0, 18, CANVAS_H), fill=_rgb(accent))
    if _render_hint(plan, "show_fixed_tag", True):
        draw.rounded_rectangle((74, 28, 230, 62), radius=12, fill=_rgb(accent))
        tag_font = _font(17, bold=True)
        draw.text((96, 34), spec.label, fill=(255, 255, 255), font=tag_font)

    title_box = _box(spec.title_box)
    title_font = _font(42, bold=True)
    _draw_wrapped(draw, title_box, plan.title, title_font, "#0F172A", max_lines=2, line_gap=10)
    if _render_hint(plan, "show_generic_separator", True):
        draw.line((74, title_box[3] + 16, 1195, title_box[3] + 16), fill=_rgb(accent), width=3)

    _draw_body(draw, _box(spec.body_box), plan.body_lines)

    cards_drawn = _draw_archetype_foreground(draw, plan, accent, soft)

    if spec.image_box and plan.visual_profile.archetype not in {"hero_photo_claim", "strategy_claim_collage", "evidence_wall", "video_material_board"}:
        image_box = _box(spec.image_box)
        _draw_photo_field(draw, image_box, accent, plan.image_label or "素材图占位", plan.visual_profile.image_treatment)

    for idx, card in enumerate(spec.card_boxes):
        if cards_drawn:
            break
        card_box = _box(card)
        _draw_round_rect(draw, card_box, soft, accent, radius=14, width=2)
        draw.rectangle((card_box[0], card_box[1], card_box[0] + 8, card_box[3]), fill=_rgb(accent))
        card_text = plan.card_texts[idx % len(plan.card_texts)] if plan.card_texts else spec.label
        _draw_wrapped(draw, (card_box[0] + 22, card_box[1] + 18, card_box[2] - 18, card_box[3] - 16), card_text, _font(20, bold=idx == 0), "#334155", 3)

    if plan.video_links:
        draw.rounded_rectangle((890, 638, 1192, 678), radius=10, outline=_rgb(accent), width=2, fill=_rgb("#FFFFFF"))
        draw.text((910, 646), "video link", fill=_rgb(accent), font=_font(19, bold=True))

    component_spec = _component_spec(plan)
    selected_seed = component_spec.get("selected_seed") or {}
    seed_note = selected_seed.get("label") or "Feibo template first"
    footer = f"RenderPlan preview - {plan.visual_profile.reference_style_label} / {seed_note} -> editable PPTX"
    draw.text((72, CANVAS_H - 36), footer, fill=_rgb("#64748B"), font=_font(16))

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_plan_preview_data_url(plan: SlideRenderPlan) -> str:
    encoded = base64.b64encode(render_plan_preview_png(plan)).decode("ascii")
    return f"data:image/png;base64,{encoded}"
