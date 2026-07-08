from __future__ import annotations

from typing import Dict

try:
    from services.renderers.python_pptx_renderer import render_plans_to_pptx
    from services.slide_render_plan import LAYOUT_SPECS, build_deck_render_plan, resolve_layout_spec, resolve_page_skill
except Exception:  # pragma: no cover - fallback when imported as package module
    from .renderers.python_pptx_renderer import render_plans_to_pptx
    from .slide_render_plan import LAYOUT_SPECS, build_deck_render_plan, resolve_layout_spec, resolve_page_skill


def build_structured_pptx(outline: Dict, output_path: str) -> str:
    """Build editable PPTX from outline pages through RenderPlan and python-pptx."""
    plans = build_deck_render_plan(outline)
    return render_plans_to_pptx(plans, output_path)


__all__ = [
    "LAYOUT_SPECS",
    "build_structured_pptx",
    "resolve_layout_spec",
    "resolve_page_skill",
]
