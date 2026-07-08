from __future__ import annotations

import base64
import io
from typing import Dict, List, Tuple, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw


def _clamp_bbox(x: int, y: int, w: int, h: int, W: int, H: int) -> Tuple[int, int, int, int]:
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(W, x + w)
    y1 = min(H, y + h)
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def build_mask_png_bytes(image_path: str, layout: Dict, padding: int = 8) -> bytes:
    """根据 layout 中 texts/elements/images 生成 inpaint mask（白=需要抹除）。"""
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    mask = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask)

    def add_bbox(bb: Dict):
        x, y, w, h = int(bb["x"]), int(bb["y"]), int(bb["w"]), int(bb["h"])
        x, y, w, h = _clamp_bbox(x - padding, y - padding, w + 2 * padding, h + 2 * padding, W, H)
        if w <= 0 or h <= 0:
            return
        draw.rectangle([x, y, x + w, y + h], fill=255)

    for t in layout.get("texts", []) or []:
        add_bbox(t.get("bbox", {}))
    for e in layout.get("elements", []) or []:
        add_bbox(e.get("bbox", {}))
    for r in layout.get("images", []) or []:
        add_bbox(r.get("bbox", {}))

    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    return buf.getvalue()


def local_inpaint(image_path: str, mask_png_bytes: bytes) -> bytes:
    """本地 OpenCV inpaint（免费回退方案，质量一般但稳定）。"""
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    mask = cv2.imdecode(np.frombuffer(mask_png_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None or mask is None:
        raise RuntimeError("Failed to read image/mask for local inpaint")
    # mask expects 0/255
    _, mask_bin = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    out = cv2.inpaint(img, mask_bin, 3, cv2.INPAINT_TELEA)
    ok, enc = cv2.imencode(".png", out)
    if not ok:
        raise RuntimeError("Failed to encode local inpaint result")
    return enc.tobytes()


def ai_inpaint(
    api_client,
    model: str,
    image_png_bytes: bytes,
    mask_png_bytes: bytes,
    prompt: str,
    size: str,
) -> Optional[bytes]:
    """调用聚合 API 的 image_edit；成功返回 png bytes，否则返回 None。"""
    try:
        result = api_client.image_edit(
            model=model,
            prompt=prompt,
            image_bytes=image_png_bytes,
            mask_bytes=mask_png_bytes,
            size=size,
        )
        # 兼容 url/b64_json
        for img in result.get("images", []) or []:
            b64 = img.get("b64_json")
            if b64:
                return base64.b64decode(b64)
        # 如果只给 url，就让上层去下载（这里返回 None）
        return None
    except Exception as e:
        print(f"[WARN] ai_inpaint failed ({model}): {e}")
        return None


def cleanup_background(
    api_client,
    inpaint_models: List[str],
    image_path: str,
    layout: Dict,
    size: str = "1792x1024",
) -> Tuple[bytes, bytes]:
    """
    背景去字/去元素：
    - 优先 AI inpaint（Banana 等）
    - 回退 OpenCV inpaint

    Returns:
      (clean_background_png_bytes, mask_png_bytes)
    """
    mask_png = build_mask_png_bytes(image_path, layout)
    with open(image_path, "rb") as f:
        image_png = f.read()

    prompt = (
        "Remove all text and UI elements inside the masked regions. "
        "Fill naturally to match surrounding background, lighting and gradients. "
        "Keep overall style consistent. Do NOT add any text."
    )

    for m in inpaint_models:
        out = ai_inpaint(api_client, m, image_png, mask_png, prompt=prompt, size=size)
        if out:
            return out, mask_png

    # fallback: local opencv inpaint (free)
    out = local_inpaint(image_path, mask_png)
    return out, mask_png


def cleanup_background_ai_only(
    api_client,
    inpaint_models: List[str],
    image_path: str,
    layout: Dict,
    size: str = "1792x1024",
    per_try_timeout_s: int = 60,
    retries: int = 1,
) -> Tuple[Optional[bytes], bytes]:
    """
    仅尝试 AI inpaint（不做本地 inpaint 回退）。
    返回 (clean_bytes_or_none, mask_png_bytes)
    """
    mask_png = build_mask_png_bytes(image_path, layout)
    with open(image_path, "rb") as f:
        image_png = f.read()

    prompt = (
        "Remove all text and UI elements inside the masked regions. "
        "Fill naturally to match surrounding background, lighting and gradients. "
        "Keep overall style consistent. Do NOT add any text."
    )

    for m in inpaint_models:
        for attempt in range(retries + 1):
            try:
                result = api_client.image_edit(
                    model=m,
                    prompt=prompt,
                    image_bytes=image_png,
                    mask_bytes=mask_png,
                    size=size,
                    timeout_s=per_try_timeout_s,
                )
                for img in result.get("images", []) or []:
                    b64 = img.get("b64_json")
                    if b64:
                        return base64.b64decode(b64), mask_png
                # 只给 url 的情况，按失败处理（避免额外不确定网络）
            except Exception as e:
                print(f"[WARN] ai_only_inpaint failed ({m}) attempt {attempt+1}: {e}")
                continue

    return None, mask_png


def redraw_background(api_client, image_model: str, prompt: str, size: str = "1792x1024") -> bytes:
    """
    背景重绘：直接生成一张“干净背景”（不含文字/卡片/照片/手机），用于作为 PPT 底图。
    说明：该模式更适合做默认，避免 inpaint 涂抹痕迹。
    """
    try:
        result = api_client.image_generate(model=image_model, prompt=prompt, size=size, n=1)
        for img in result.get("images", []) or []:
            b64 = img.get("b64_json")
            if b64:
                return base64.b64decode(b64)
            url = img.get("url")
            if url:
                import requests
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                return r.content
        raise RuntimeError("redraw_background: no image returned")
    except Exception as e:
        raise RuntimeError(f"redraw_background failed: {e}") from e
