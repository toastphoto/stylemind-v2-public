"""Campaign aesthetics distilled from Feibo reference decks.

This is a local, deterministic style catalog. It is not a replacement for the
full 500-page sample library, but it keeps the current PPTX renderer anchored to
the higher-aesthetic campaign directions already extracted from references.
"""

from __future__ import annotations

import re
from typing import Any


CAMPAIGN_STYLE_SYSTEMS = [
    {
        "id": "campaign_emotion_cover",
        "label": "Campaign 情绪主视觉",
        "keywords": ["封面", "主视觉", "生活节", "艺术节", "城市", "烟火气", "酒店", "旅行", "心动", "节日", "春节"],
        "page_types": ["cover", "opening", "section", "creative"],
        "render": {"paper": "#F7F3EA", "accent": "#1F6D6B", "soft": "#E8DDCB", "grid": False, "photo": "hero"},
    },
    {
        "id": "xhs_lifestyle_grid",
        "label": "小红书生活方式网格",
        "keywords": ["小红书", "生活家", "慢人节", "生活方式", "招商", "艺术", "创作者", "seeding", "种草"],
        "page_types": ["content", "creative", "opening"],
        "render": {"paper": "#FFF7F7", "accent": "#EF6F83", "soft": "#F8DDE4", "grid": False, "photo": "cutout"},
    },
    {
        "id": "summer_home_campaign",
        "label": "夏日家居情绪片",
        "keywords": ["夏天", "夏日", "盛夏", "美的", "美享家", "宠物", "孩子", "长辈", "家庭", "清洁", "全屋智能", "生活方式"],
        "page_types": ["cover", "opening", "creative", "content", "evidence"],
        "render": {"paper": "#F8FBFF", "accent": "#1B75D0", "soft": "#D7ECF5", "grid": False, "photo": "hero"},
    },
    {
        "id": "evidence_wall",
        "label": "案例证据墙",
        "keywords": ["案例", "证据", "达人", "koc", "kol", "ugc", "截图", "笔记", "门店", "探店", "复盘", "传播动作"],
        "page_types": ["evidence", "case", "execution", "video"],
        "render": {"paper": "#FAF7F1", "accent": "#D7332F", "soft": "#F2E6D8", "grid": False, "photo": "evidence"},
    },
    {
        "id": "light_data_path",
        "label": "轻数据传播路径",
        "keywords": ["数据", "路径", "链路", "流程", "传播", "规划", "节奏", "阶段", "策略", "增长", "预算"],
        "page_types": ["data", "execution", "content"],
        "render": {"paper": "#F8FAFC", "accent": "#2667FF", "soft": "#DCE7FF", "grid": False, "photo": "diagram"},
    },
    {
        "id": "city_travel_photo",
        "label": "文旅酒店影像风",
        "keywords": ["酒店", "心动榜", "旅行", "城市", "马路", "烟火", "寻味", "生活服务", "目的地", "街区"],
        "page_types": ["cover", "opening", "section", "evidence"],
        "render": {"paper": "#F2F6F2", "accent": "#2F6B4F", "soft": "#DCE8D8", "grid": False, "photo": "hero"},
    },
    {
        "id": "ip_sticker_system",
        "label": "IP 贴纸化视觉",
        "keywords": ["ip", "角色", "贴纸", "手绘", "插画", "胶带", "便签", "节日", "创作者"],
        "page_types": ["creative", "content", "execution"],
        "render": {"paper": "#FFF8E8", "accent": "#F24822", "soft": "#F7E2B8", "grid": True, "photo": "sticker"},
    },
]


def _haystack(page: dict[str, Any], style_description: str = "") -> str:
    director = page.get("proposal_director") if isinstance(page.get("proposal_director"), dict) else {}
    parts = [
        page.get("title"),
        page.get("content"),
        page.get("brief"),
        page.get("page_type"),
        page.get("type"),
        page.get("layout"),
        page.get("layout_skill"),
        director.get("page_role"),
        director.get("narrative_role"),
        director.get("visual_intent"),
        director.get("asset_logic"),
        director.get("acting_visual_brief"),
        style_description,
    ]
    return "\n".join(str(part or "") for part in parts).lower()


def infer_campaign_style(page: dict[str, Any], style_description: str = "") -> dict[str, Any]:
    text = _haystack(page or {}, style_description)
    page_type = str((page or {}).get("page_type") or (page or {}).get("type") or "").lower()
    scored = []
    for style in CAMPAIGN_STYLE_SYSTEMS:
        score = 0
        for kw in style["keywords"]:
            if str(kw).lower() in text:
                score += 3
        if page_type and page_type in style.get("page_types", []):
            score += 2
        if re.search(r"campaign|lifestyle|evidence|city|travel|sticker|grid", text) and style["id"] in {
            "campaign_emotion_cover",
            "xhs_lifestyle_grid",
            "evidence_wall",
            "city_travel_photo",
            "ip_sticker_system",
        }:
            score += 1
        scored.append((score, style))
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return CAMPAIGN_STYLE_SYSTEMS[0]


def campaign_style_render_tokens(page: dict[str, Any], style_description: str = "") -> dict[str, Any]:
    style = infer_campaign_style(page, style_description)
    return {"id": style["id"], "label": style["label"], **style.get("render", {})}
