#!/usr/bin/env python3
"""Export a five-page StyleMind render-plan fixture for renderer spikes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_UI = ROOT / "web_ui"
if str(WEB_UI) not in sys.path:
    sys.path.insert(0, str(WEB_UI))

from services.slide_render_plan import deck_render_plan_to_dict  # noqa: E402


DEFAULT_OUT = ROOT / ".pytest_tmp" / "stylemind_render_plan_fixture.json"


def sample_outline() -> dict:
    return {
        "title": "StyleMind RenderPlan Spike",
        "pages": [
            {
                "title": "开场定调：把夏天变成可参与的生活提案",
                "page_type": "opening",
                "layout_skill": "开场定调",
                "brief": "先给出提案气质和核心判断。",
                "content": "用户不只是在寻找消暑内容，而是在寻找一个可以被分享、被参与、被证明的夏日生活理由。",
                "fixed_images": ["campaign-hero.png"],
                "font_profile": {"title_font": "京东朗正体", "body_font": "微软雅黑", "latin_font": "Arial", "east_asian_font": "微软雅黑"},
            },
            {
                "title": "章节转场：传播主题",
                "page_type": "chapter_transition",
                "layout_skill": "章节转场",
                "content": "从需求回顾进入传播主题，建立下一章节的阅读节奏。",
            },
            {
                "title": "创意主张：让宠物友好成为城市夏日的新入口",
                "page_type": "creative_claim",
                "layout_skill": "创意主张",
                "content": "核心创意不是单点话题，而是一组能被达人、用户和品牌共同演绎的场景资产。",
            },
            {
                "title": "执行打法：四段式传播路径",
                "page_type": "execution_plan",
                "layout_skill": "执行打法",
                "content": "Step 1：预热种草，释放情绪钩子。\nStep 2：达人共创，形成内容密度。\nStep 3：线下事件，制造可拍可传的参与点。\nStep 4：复盘沉淀，形成品牌可复用资产。",
            },
            {
                "title": "案例证据：用真实内容证明可复制",
                "page_type": "case_evidence",
                "layout_skill": "案例证据",
                "content": "通过达人笔记、话题互动、线下照片和数据截图，证明方案不是只停留在创意描述，而是具备落地证据。",
                "fixed_images": ["evidence-wall.png"],
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outline", type=Path, help="Optional outline JSON file. Defaults to a five-page fixture.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if args.outline:
        outline = json.loads(args.outline.read_text(encoding="utf-8"))
    else:
        outline = sample_outline()

    payload = deck_render_plan_to_dict(outline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "page_count": payload["page_count"], "schema": payload["schema"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
