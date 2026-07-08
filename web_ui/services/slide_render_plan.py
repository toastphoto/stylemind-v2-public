from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

try:
    from services.campaign_style_catalog import campaign_style_render_tokens
except Exception:  # pragma: no cover - fallback when imported outside web_ui package path
    def campaign_style_render_tokens(page, style_description=""):
        return {"id": "default", "label": "默认结构化风格", "paper": "#F8FAFC", "accent": "#2563EB", "soft": "#E2E8F0", "grid": False}


try:
    from services.dashiai_theme_seed import build_component_spec_from_page
except Exception:  # pragma: no cover - fallback when optional seed registry is unavailable
    def build_component_spec_from_page(page, page_role, *, style_tokens=None, visual_profile=None, limit=6):
        return {
            "schema": "stylemind.component_spec.v1",
            "source": "feibo_template_first",
            "status": "component_spec_fallback_use_feibo_template_first",
            "page_role": page_role,
            "selected_seed": {},
            "selected_seed_key": "",
            "dashiai_seed_rejected": False,
            "render_hints": {
                "show_left_rail": False,
                "show_fixed_tag": False,
                "show_generic_separator": False,
                "prefer_open_layout": True,
            },
        }


@dataclass(frozen=True)
class SlideLayoutSpec:
    """Renderer-neutral Feibo page-skill layout contract."""

    key: str
    label: str
    accent: str
    title_box: tuple[float, float, float, float]
    body_box: tuple[float, float, float, float]
    image_box: tuple[float, float, float, float] | None
    card_boxes: tuple[tuple[float, float, float, float], ...]
    body_font_size: int = 17


@dataclass(frozen=True)
class FontProfile:
    """Font contract shared by future renderers."""

    title_font: str = "Microsoft YaHei"
    body_font: str = "Microsoft YaHei"
    latin_font: str = "Arial"
    east_asian_font: str = "Microsoft YaHei"
    fallback_font: str = "SimSun"


@dataclass(frozen=True)
class VisualProfile:
    """Reference-aesthetic controls shared by preview and PPTX renderers."""

    archetype: str
    density: str
    image_treatment: str
    composition: str
    reference_style_id: str
    reference_style_label: str


@dataclass(frozen=True)
class PageIntent:
    """What a page needs to say and do, before renderer-specific decisions."""

    index: int
    title: str
    page_role: str
    content_lines: tuple[str, ...]
    brief: str
    layout_label: str
    fixed_images: tuple[str, ...]
    background_images: tuple[str, ...]
    video_links: tuple[str, ...]
    font_profile: FontProfile
    source_page: Dict[str, Any]


@dataclass(frozen=True)
class SlideRenderPlan:
    """Renderer-neutral execution plan consumed by python-pptx/PptxGenJS/template renderers."""

    index: int
    intent: PageIntent
    layout_spec: SlideLayoutSpec
    style_tokens: Dict[str, Any]
    accent: str
    paper: str
    soft: str
    grid: bool
    visual_profile: VisualProfile
    title: str
    body_lines: tuple[str, ...]
    image_sources: tuple[str, ...]
    background_sources: tuple[str, ...]
    image_label: str
    card_texts: tuple[str, ...]
    video_links: tuple[str, ...]
    component_spec: Dict[str, Any]
    notes: tuple[str, ...]


FEIBO_PAGE_SKILLS: Dict[str, str] = {
    "opening": "开场定调",
    "opening_tone": "开场定调",
    "chapter": "章节转场",
    "chapter_transition": "章节转场",
    "content": "内容承接",
    "content_bridge": "内容承接",
    "idea": "创意主张",
    "creative_claim": "创意主张",
    "execution": "执行打法",
    "execution_plan": "执行打法",
    "case": "案例证据",
    "case_evidence": "案例证据",
    "data": "数据结果",
    "data_result": "数据结果",
    "video": "视频素材",
    "video_material": "视频素材",
}

_SKILL_ALIASES: Dict[str, str] = {
    "封面": "开场定调",
    "首页": "开场定调",
    "开场": "开场定调",
    "转场": "章节转场",
    "目录": "章节转场",
    "正文": "内容承接",
    "内容": "内容承接",
    "观点": "创意主张",
    "创意": "创意主张",
    "策略": "创意主张",
    "打法": "执行打法",
    "执行": "执行打法",
    "路径": "执行打法",
    "案例": "案例证据",
    "证据": "案例证据",
    "数据": "数据结果",
    "结果": "数据结果",
    "视频": "视频素材",
    "素材": "视频素材",
}

LAYOUT_SPECS: Dict[str, SlideLayoutSpec] = {
    "开场定调": SlideLayoutSpec(
        key="opening",
        label="开场定调",
        accent="#E11D48",
        title_box=(0.78, 1.1, 7.55, 1.18),
        body_box=(0.86, 2.72, 6.0, 2.7),
        image_box=(7.62, 1.1, 4.65, 4.85),
        card_boxes=((0.86, 5.88, 3.1, 0.82), (4.2, 5.88, 3.1, 0.82)),
        body_font_size=19,
    ),
    "章节转场": SlideLayoutSpec(
        key="chapter",
        label="章节转场",
        accent="#7C3AED",
        title_box=(1.25, 2.34, 8.9, 1.18),
        body_box=(1.34, 3.82, 8.1, 1.2),
        image_box=None,
        card_boxes=((10.35, 1.28, 1.18, 4.95), (11.72, 1.28, 0.24, 4.95)),
        body_font_size=18,
    ),
    "内容承接": SlideLayoutSpec(
        key="content",
        label="内容承接",
        accent="#2563EB",
        title_box=(0.78, 0.72, 6.9, 0.72),
        body_box=(0.86, 1.78, 5.65, 4.75),
        image_box=(8.75, 1.58, 3.35, 3.95),
        card_boxes=((6.88, 1.78, 1.45, 4.75),),
        body_font_size=16,
    ),
    "创意主张": SlideLayoutSpec(
        key="idea",
        label="创意主张",
        accent="#F97316",
        title_box=(0.82, 0.76, 7.2, 0.9),
        body_box=(0.9, 2.0, 5.25, 3.6),
        image_box=(6.68, 1.96, 5.35, 3.42),
        card_boxes=((0.92, 5.84, 3.32, 0.86), (4.55, 5.84, 3.32, 0.86), (8.18, 5.84, 3.32, 0.86)),
        body_font_size=17,
    ),
    "执行打法": SlideLayoutSpec(
        key="execution",
        label="执行打法",
        accent="#0F766E",
        title_box=(0.76, 0.66, 6.8, 0.72),
        body_box=(0.9, 1.84, 11.1, 1.2),
        image_box=None,
        card_boxes=((0.9, 3.54, 2.55, 2.05), (3.88, 3.54, 2.55, 2.05), (6.86, 3.54, 2.55, 2.05), (9.84, 3.54, 2.55, 2.05)),
        body_font_size=16,
    ),
    "案例证据": SlideLayoutSpec(
        key="case",
        label="案例证据",
        accent="#9333EA",
        title_box=(0.76, 0.66, 6.8, 0.72),
        body_box=(7.08, 1.62, 4.65, 4.45),
        image_box=(0.94, 1.54, 5.32, 4.6),
        card_boxes=((0.94, 6.18, 2.52, 0.58), (3.74, 6.18, 2.52, 0.58)),
        body_font_size=15,
    ),
    "数据结果": SlideLayoutSpec(
        key="data",
        label="数据结果",
        accent="#0891B2",
        title_box=(0.78, 0.66, 7.4, 0.72),
        body_box=(0.96, 5.58, 10.8, 0.9),
        image_box=None,
        card_boxes=((0.96, 1.66, 2.72, 2.78), (4.2, 1.66, 2.72, 2.78), (7.44, 1.66, 2.72, 2.78), (10.68, 1.66, 1.35, 2.78)),
        body_font_size=15,
    ),
    "视频素材": SlideLayoutSpec(
        key="video",
        label="视频素材",
        accent="#DC2626",
        title_box=(0.78, 0.66, 6.8, 0.72),
        body_box=(7.16, 1.74, 4.58, 3.08),
        image_box=(0.94, 1.54, 5.45, 3.72),
        card_boxes=((0.94, 5.66, 5.45, 0.82), (7.16, 5.26, 4.58, 1.18)),
        body_font_size=15,
    ),
}


def clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(clean_text(v) for v in value if clean_text(v))
    if isinstance(value, dict):
        return "\n".join(f"{k}: {clean_text(v)}" for k, v in value.items() if clean_text(v))
    return str(value).strip()


def as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(v) for v in value if clean_text(v)]
    text = clean_text(value)
    return [text] if text else []


def content_lines(page: Dict[str, Any]) -> List[str]:
    candidates = [
        page.get("content"),
        page.get("brief"),
        page.get("description"),
        page.get("speaker_notes"),
    ]
    text = "\n".join(clean_text(v) for v in candidates if clean_text(v))
    lines = []
    for raw in re.split(r"[\n\r]+|(?<=[。；;])", text):
        line = raw.strip(" \t-•")
        if line:
            lines.append(line)
    return lines[:6] or ["补充页面要点，形成可编辑正文。"]


def page_text_blob(page: Dict[str, Any]) -> str:
    values = [
        page.get("page_type"),
        page.get("type"),
        page.get("layout_skill"),
        page.get("layout"),
        page.get("title"),
    ]
    return " ".join(clean_text(v) for v in values if clean_text(v))


def contains_any(text: str, keywords: tuple[str, ...] | list[str]) -> bool:
    return any(keyword.lower() in text.lower() for keyword in keywords)


def infer_page_role(page: Dict[str, Any], idx: int | None = None) -> str:
    """Map legacy parser layout/type labels into the retained Feibo taxonomy."""
    title = clean_text(page.get("title"))
    title_base = re.sub(r"【.*?】", "", title).strip(" .。．")
    layout = clean_text(page.get("layout") or page.get("layout_skill"))
    page_type = clean_text(page.get("page_type") or page.get("type"))
    content = clean_text(page.get("content"))
    text = "\n".join([title, layout, page_type, content]).lower()

    if idx == 1 or contains_any(title, ("需求回顾", "brief recap", "项目挑战")):
        return "开场定调"

    if re.match(r"^[一二三四五六七八九十]+[、.．]", title):
        if "需求回顾" in title:
            return "开场定调"
        return "章节转场"

    if title_base.lower() in {"目的", "roadmap", "策略回顾"}:
        return "执行打法"

    if "模块化-步骤流程" in layout or re.match(r"^step\s*\d+", title, re.IGNORECASE):
        return "执行打法"

    if "模块化-时间轴" in layout or page_type == "timeline":
        if contains_any(text, ("节奏", "链路", "roadmap", "起势", "爆发", "长尾", "规划")):
            return "执行打法"
        return "数据结果"

    if page_type == "chart" or "模块化-表格" in layout:
        return "数据结果"

    if contains_any(text, ("+%", "累计曝光", "搜索量", "互动率", "达人量级", "占比", "增长", "热度", "趋势", "数据", "投放建立起领先")):
        return "数据结果"

    if contains_any(text, ("demo", "视频", "脚本", "分镜", "达人内容示意", "内容标题")) and not re.match(r"^step\s*\d+", title, re.IGNORECASE):
        return "视频素材"

    if contains_any(text, ("案例", "内容参考", "竞品", "小米", "华为", "海尔", "石头", "科沃斯", "达人id", "xiaohongshu.com/explore", "爆文", "类型一", "类型二", "类型三")):
        return "案例证据"

    if contains_any(text, ("传播主题", "核心主题", "core idea", "创意落点", "创意思考", "主题", "主张", "核心结论", "场景拆解", "懒人的夏天", "孩子的夏天", "宠物的夏天", "长辈的夏天")):
        return "创意主张"

    if contains_any(text, ("传播规划", "传播动作", "达人", "koc", "矩阵", "分层", "话题", "线下", "公益", "搜索流量", "投流", "投放", "方法论", "选购清单", "采购攻略", "产品测评", "吐槽", "生活记录", "情绪故事", "搞笑瞬间")):
        return "执行打法"

    return "内容承接"


def resolve_page_skill(page: Dict[str, Any], idx: int | None = None) -> str:
    """Resolve outline page metadata to the retained Feibo page-skill taxonomy."""
    blob = page_text_blob(page)
    for canonical in LAYOUT_SPECS:
        if canonical in blob:
            return canonical

    metadata = [
        clean_text(page.get("page_type")),
        clean_text(page.get("type")),
        clean_text(page.get("layout_skill")),
        clean_text(page.get("layout")),
    ]
    lowered = "\n".join(metadata).lower()
    for key, label in FEIBO_PAGE_SKILLS.items():
        if key == "content":
            continue
        if key in lowered:
            return label

    for word, label in _SKILL_ALIASES.items():
        if word in {"内容", "素材", "视频", "策略", "数据"}:
            continue
        if word in blob:
            return label

    return infer_page_role(page, idx)


def resolve_layout_spec(page: Dict[str, Any], idx: int | None = None) -> SlideLayoutSpec:
    return LAYOUT_SPECS[resolve_page_skill(page, idx)]


def parse_font_profile(page: Dict[str, Any]) -> FontProfile:
    raw = page.get("font_profile")
    if isinstance(raw, dict):
        title = clean_text(raw.get("title_font") or raw.get("title") or raw.get("heading"))
        body = clean_text(raw.get("body_font") or raw.get("body"))
        latin = clean_text(raw.get("latin_font") or raw.get("latin"))
        east_asian = clean_text(raw.get("east_asian_font") or raw.get("cjk") or raw.get("chinese"))
        fallback = clean_text(raw.get("fallback_font") or raw.get("fallback"))
        return FontProfile(
            title_font=title or "Microsoft YaHei",
            body_font=body or "Microsoft YaHei",
            latin_font=latin or "Arial",
            east_asian_font=east_asian or body or title or "Microsoft YaHei",
            fallback_font=fallback or "SimSun",
        )
    if clean_text(raw):
        name = clean_text(raw)
        return FontProfile(title_font=name, body_font=name, east_asian_font=name)
    return FontProfile()


def build_page_intent(page: Dict[str, Any], idx: int) -> PageIntent:
    role = resolve_page_skill(page, idx)
    lines = tuple(content_lines(page))
    layout_label = clean_text(page.get("layout") or page.get("layout_skill") or "结构化页面")
    background_images = (
        as_list(page.get("background_images"))
        or as_list(page.get("background_image"))
        or as_list(page.get("background_assets"))
        or as_list(page.get("background_asset"))
    )
    return PageIntent(
        index=idx,
        title=clean_text(page.get("title")) or f"第 {idx} 页",
        page_role=role,
        content_lines=lines,
        brief=clean_text(page.get("brief")) or (lines[0] if lines else ""),
        layout_label=layout_label,
        fixed_images=tuple(as_list(page.get("fixed_images"))),
        background_images=tuple(background_images),
        video_links=tuple(as_list(page.get("video_links"))),
        font_profile=parse_font_profile(page),
        source_page=page,
    )


def build_card_texts(intent: PageIntent) -> tuple[str, ...]:
    cards = [intent.layout_label, intent.brief]
    if intent.fixed_images:
        cards.append(f"素材图：{intent.fixed_images[0]}")
    if intent.background_images:
        cards.append(f"背景图：{intent.background_images[0]}")
    if intent.video_links:
        cards.append(f"视频：{intent.video_links[0]}")
    cards.extend(intent.content_lines[1:])
    return tuple(card for card in cards if card)


def infer_visual_profile(intent: PageIntent, style_tokens: Dict[str, Any]) -> VisualProfile:
    text = "\n".join([intent.title, intent.layout_label, intent.brief, *intent.content_lines]).lower()
    role = intent.page_role
    if role == "开场定调":
        archetype = "hero_photo_claim"
        composition = "large_title_with_hero_asset"
    elif role == "章节转场":
        archetype = "section_divider"
        composition = "oversized_title_with_side_marks"
    elif role == "创意主张":
        archetype = "strategy_claim_collage"
        composition = "claim_left_visual_right"
    elif role == "执行打法":
        archetype = "step_flow"
        composition = "horizontal_process_cards"
        if "时间轴" in intent.layout_label or contains_any(text, ("roadmap", "节奏", "预热", "爆发", "长尾")):
            archetype = "campaign_timeline"
            composition = "timeline_nodes"
    elif role == "案例证据":
        archetype = "evidence_wall"
        composition = "screenshot_plus_evidence_notes"
    elif role == "数据结果":
        archetype = "metric_dashboard"
        composition = "metric_cards_with_explanation"
    elif role == "视频素材":
        archetype = "video_material_board"
        composition = "thumbnail_and_link_panel"
    else:
        archetype = "editorial_content_bridge"
        composition = "text_with_supporting_asset"

    line_count = len([line for line in intent.content_lines if line])
    if role in {"案例证据", "数据结果"} or line_count >= 5:
        density = "dense"
    elif role in {"开场定调", "章节转场", "创意主张"} and line_count <= 3:
        density = "sparse"
    else:
        density = "balanced"

    image_treatment = str(style_tokens.get("photo") or "").strip()
    if not image_treatment:
        image_treatment = {
            "开场定调": "hero",
            "章节转场": "graphic_mark",
            "内容承接": "supporting",
            "创意主张": "cutout",
            "执行打法": "diagram",
            "案例证据": "evidence",
            "数据结果": "diagram",
            "视频素材": "thumbnail",
        }.get(role, "supporting")

    return VisualProfile(
        archetype=archetype,
        density=density,
        image_treatment=image_treatment,
        composition=composition,
        reference_style_id=str(style_tokens.get("id") or "default"),
        reference_style_label=str(style_tokens.get("label") or "默认结构化风格"),
    )


def build_slide_render_plan(page: Dict[str, Any], idx: int) -> SlideRenderPlan:
    intent = build_page_intent(page, idx)
    spec = LAYOUT_SPECS[intent.page_role]
    style_tokens = campaign_style_render_tokens(page, clean_text(page.get("style_description")))
    visual_profile = infer_visual_profile(intent, style_tokens)
    accent = style_tokens.get("accent") or spec.accent
    paper = style_tokens.get("paper") or "#F8FAFC"
    soft = style_tokens.get("soft") or "#FFFFFF"
    image_label = intent.fixed_images[0] if intent.fixed_images else f"{spec.label}素材图"
    component_spec = build_component_spec_from_page(
        intent.source_page,
        intent.page_role,
        style_tokens=style_tokens,
        visual_profile=visual_profile,
    )
    selected_seed = component_spec.get("selected_seed") or {}
    notes = (
        f"结构化 PPTX 导出：{spec.label}",
        f"参考审美系统：{style_tokens.get('label')} ({style_tokens.get('id')})",
        f"视觉原型：{visual_profile.archetype} / {visual_profile.composition} / {visual_profile.density}",
        f"组件策略：{component_spec.get('status')} / {selected_seed.get('label') or '飞博模板优先'}",
        "image-2 仅作为素材图来源，不负责整页排版和文字。",
        "背景图作为底层可替换图片对象，标题/正文/数据仍保持原生可编辑。",
        clean_text(page.get("video_links")),
    )
    return SlideRenderPlan(
        index=idx,
        intent=intent,
        layout_spec=spec,
        style_tokens=style_tokens,
        accent=accent,
        paper=paper,
        soft=soft,
        grid=bool(style_tokens.get("grid")),
        visual_profile=visual_profile,
        title=intent.title,
        body_lines=intent.content_lines,
        image_sources=intent.fixed_images,
        background_sources=intent.background_images,
        image_label=image_label,
        card_texts=build_card_texts(intent),
        video_links=intent.video_links,
        component_spec=component_spec,
        notes=tuple(note for note in notes if note),
    )


def build_deck_render_plan(outline: Dict[str, Any]) -> list[SlideRenderPlan]:
    pages = outline.get("pages") or []
    return [build_slide_render_plan(page, idx) for idx, page in enumerate(pages, start=1)]


def render_plan_to_dict(plan: SlideRenderPlan) -> Dict[str, Any]:
    """Serialize a render plan for non-Python renderers."""
    return asdict(plan)


def deck_render_plan_to_dict(outline: Dict[str, Any]) -> Dict[str, Any]:
    plans = build_deck_render_plan(outline)
    return {
        "schema": "stylemind.render_plan.v1",
        "page_count": len(plans),
        "plans": [render_plan_to_dict(plan) for plan in plans],
    }
