from __future__ import annotations

from typing import List

from .layout_types import BBox, TextItem

_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is not None:
        return _ocr
    # PaddleOCR 初始化较重，延迟加载
    from paddleocr import PaddleOCR

    _ocr = PaddleOCR(use_angle_cls=True, lang="ch")
    return _ocr


def extract_text(image_path: str, min_conf: float = 0.5) -> List[TextItem]:
    """提取文本与 bbox（中文优先）。"""
    ocr = _get_ocr()
    result = ocr.ocr(image_path, cls=True)
    items: List[TextItem] = []
    for page in result or []:
        for line in page or []:
            pts, (txt, conf) = line
            if txt is None:
                continue
            conf_f = float(conf) if conf is not None else 0.0
            if conf_f < min_conf:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x0, y0, x1, y1 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            items.append(TextItem(text=str(txt), bbox=BBox(x0, y0, x1 - x0, y1 - y0), confidence=conf_f))
    return items
