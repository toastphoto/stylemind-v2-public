from __future__ import annotations

import base64
import io
import json
import re
from typing import Any, Dict

from PIL import Image

from .layout_types import LayoutDict


LAYOUT_PROMPT_V2 = """You are extracting editable layers from a PPT screenshot image.
Return ONLY valid JSON (no markdown fences), with this schema:
{
  "texts": [
    {"text":"", "bbox":{"x":0,"y":0,"w":0,"h":0}, "kind":"title|subtitle|card_title|body|small", "font_size_pt": 0}
  ],
  "elements": [
    {"element_type":"card|circle_badge|arrow|divider|other", "bbox":{"x":0,"y":0,"w":0,"h":0}, "color":"#RRGGBB or rgba", "radius": 0}
  ],
  "images": [
    {"region_type":"phone|photo|screenshot|other", "bbox":{"x":0,"y":0,"w":0,"h":0}}
  ],
  "keep_in_background": ["dot_matrix_top_right"]
}

Hard requirements:
- MUST extract ALL visible Chinese text EXACTLY as shown (including title and subtitles). Put every text into texts[] with bbox.
- For each text, set kind (title/subtitle/card_title/body/small) and a reasonable font_size_pt suggestion.
- MUST detect: 3 card containers, 1/2/3 circular badges, arrows between cards, vertical dividers/lines.
- MUST detect separate image regions: phone mockups AND photo backgrounds for each card.
- Dot matrix on top-right can stay in background (keep_in_background).
- bbox coordinates are PIXELS in the provided image coordinate system.

Tips:
- For a 'card' element, bbox should cover the rounded rectangle container.
- For a 'phone' region, bbox should tightly bound the phone device frame.
- For a 'photo' region, bbox should tightly bound the photo area behind the phone.
"""

BACKGROUND_PROMPT = """You are generating a CLEAN BACKGROUND for a PPT slide based on a screenshot.
The output should be a background-only image (16:9) that matches the screenshot's overall style and mood, but with ALL content removed.

Remove:
- all text
- all cards/containers
- all arrows/dividers/badges
- all phones, photos, UI screenshots

Keep:
- subtle gradients / light background tone
- top-right dot matrix decoration (keep it, but it can be simplified)
- overall soft lighting and modern minimal feel

Return ONLY a single image-generation prompt in English, no markdown, no extra commentary.
"""


def build_background_redraw_prompt(api_client, chat_model: str, image_path: str) -> str:
    """从截图提炼“背景重绘”提示词。"""
    with Image.open(image_path) as im:
        w, h = im.size
        max_side = max(w, h)
        target_max = 900
        if max_side > target_max:
            scale = target_max / max_side
            im = im.resize((int(w * scale), int(h * scale)))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": BACKGROUND_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }
    ]
    resp = api_client.chat(model=chat_model, messages=messages, max_tokens=300, timeout=60)
    prompt = (resp.get("content", "") or "").strip()
    # 兜底：避免模型输出引号/多余前后缀
    prompt = prompt.strip("`").strip()
    return prompt or "Minimal clean light background for a PPT slide, subtle soft gradient, top-right dot matrix decoration, 16:9, no text, no photos, no UI, no cards."


def analyze_layout(api_client, chat_model: str, image_path: str) -> LayoutDict:
    """V2：多模态抽取 texts/elements/images（避免 OCR 依赖导致崩溃/不兼容）。"""
    # image dims
    with Image.open(image_path) as im:
        w, h = im.size
        # 为了降低多模态成本与延迟：超大图先缩放到可控尺寸，再把 bbox 按比例放回原图坐标
        max_side = max(w, h)
        target_max = 1200
        scale = 1.0
        if max_side > target_max:
            scale = target_max / max_side
            new_w = int(w * scale)
            new_h = int(h * scale)
            im = im.resize((new_w, new_h))
        else:
            new_w, new_h = w, h

    # multimodal JSON layout
    # 使用缩放后的图进行多模态分析
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": LAYOUT_PROMPT_V2},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }
    ]

    resp = api_client.chat(model=chat_model, messages=messages, max_tokens=1400, timeout=90)
    content = resp.get("content", "") or ""
    m = re.search(r"\{[\s\S]*\}", content)
    raw_json = m.group() if m else ""

    def _load_or_repair(raw: str) -> Dict[str, Any]:
        if not raw:
            return {"texts": [], "elements": [], "images": [], "keep_in_background": []}
        try:
            return json.loads(raw)
        except Exception:
            # 让模型把“近似 JSON”修复为严格 JSON（避免非确定性输出导致解析失败）
            repair_prompt = (
                "Fix the following to STRICT JSON that matches the schema exactly. "
                "Return ONLY JSON, no markdown.\n\n"
                f"{raw}"
            )
            repaired = api_client.chat(
                model=chat_model,
                messages=[{"role": "user", "content": repair_prompt}],
                max_tokens=1200,
                timeout=60,
            ).get("content", "")
            m2 = re.search(r"\{[\s\S]*\}", repaired or "")
            if not m2:
                raise
            return json.loads(m2.group())

    layout: Dict[str, Any] = _load_or_repair(raw_json)

    # 将 bbox 放回原图坐标
    if scale != 1.0:
        inv = 1.0 / scale

        def _scale_bbox(bb: Dict[str, Any]) -> Dict[str, int]:
            return {
                "x": int(bb.get("x", 0) * inv),
                "y": int(bb.get("y", 0) * inv),
                "w": int(bb.get("w", 0) * inv),
                "h": int(bb.get("h", 0) * inv),
            }

        for t in layout.get("texts", []) or []:
            if "bbox" in t:
                t["bbox"] = _scale_bbox(t["bbox"])
        for e in layout.get("elements", []) or []:
            if "bbox" in e:
                e["bbox"] = _scale_bbox(e["bbox"])
        for r in layout.get("images", []) or []:
            if "bbox" in r:
                r["bbox"] = _scale_bbox(r["bbox"])

    return {
        "width": w,
        "height": h,
        "texts": layout.get("texts", []),
        "elements": layout.get("elements", []),
        "images": layout.get("images", []),
        "keep_in_background": layout.get("keep_in_background", []),
    }
