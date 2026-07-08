from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, TypedDict, List, Dict, Any


@dataclass(frozen=True)
class BBox:
    """像素坐标系：左上角 (x,y)，宽高 (w,h)"""

    x: int
    y: int
    w: int
    h: int

    def pad(self, p: int) -> "BBox":
        return BBox(self.x - p, self.y - p, self.w + 2 * p, self.h + 2 * p)


ElementType = Literal["card", "circle_badge", "arrow", "divider", "other"]
ImageRegionType = Literal["phone", "photo", "screenshot", "other"]


@dataclass
class TextItem:
    text: str
    bbox: BBox
    confidence: float = 1.0


@dataclass
class ElementItem:
    element_type: ElementType
    bbox: BBox
    color: Optional[str] = None
    radius: Optional[int] = None


@dataclass
class ImageRegionItem:
    region_type: ImageRegionType
    bbox: BBox


class LayoutDict(TypedDict, total=False):
    width: int
    height: int
    texts: List[Dict[str, Any]]
    elements: List[Dict[str, Any]]
    images: List[Dict[str, Any]]
    keep_in_background: List[str]
