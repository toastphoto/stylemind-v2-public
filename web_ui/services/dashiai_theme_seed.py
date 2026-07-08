"""Read vendored DashiAI theme seeds for StyleMind workbench planning.

The vendored source stays under third_party with its original license. This
module exposes only a compact registry used as inspiration and component seeds;
Feibo references remain the target aesthetic.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT_DIR / "reference_samples" / "dashiai_theme_seed" / "stylemind_dashiai_theme_seed_registry.json"


@lru_cache(maxsize=1)
def load_dashiai_seed_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {
            "schema": "stylemind.dashiai_theme_seed_registry.v1",
            "counts": {"themes": 0, "sourcePages": 0, "candidates": 0},
            "byRole": {},
            "candidates": [],
            "feiboOverlay": {},
            "source": {"license": "AGPL-3.0", "missing": True},
        }
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def match_dashiai_theme_seeds(page_role: str, *, limit: int = 3) -> list[dict[str, Any]]:
    registry = load_dashiai_seed_registry()
    candidates_by_key = {item.get("key"): item for item in registry.get("candidates", [])}
    keys = registry.get("byRole", {}).get(page_role, [])
    matches: list[dict[str, Any]] = []
    for key in keys:
        candidate = candidates_by_key.get(key)
        if not candidate:
            continue
        matches.append(
            {
                "key": candidate.get("key"),
                "theme": candidate.get("themeName") or candidate.get("themeKey"),
                "label": candidate.get("label"),
                "module_tags": candidate.get("moduleTags", [])[:4],
                "control_count": candidate.get("controlCount", 0),
                "has_media_slots": bool(candidate.get("hasMediaSlots")),
                "adaptation_status": candidate.get("adaptation", {}).get("status", "seed_needs_feibo_restyle"),
            }
        )
        if len(matches) >= limit:
            break
    return matches


def match_restyled_dashiai_theme_seeds(
    page_role: str,
    *,
    style_tokens: dict[str, Any] | None = None,
    visual_profile: Any | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return DashiAI seeds with Feibo restyle instructions attached."""
    seeds = match_dashiai_theme_seeds(page_role, limit=limit)
    restyle = build_feibo_restyle_policy(page_role, style_tokens or {}, visual_profile)
    return [{**seed, "feibo_restyle": restyle} for seed in seeds]


def build_component_spec_from_page(
    page: dict[str, Any] | None,
    page_role: str,
    *,
    style_tokens: dict[str, Any] | None = None,
    visual_profile: Any | None = None,
    limit: int = 6,
) -> dict[str, Any]:
    """Build a renderer-neutral component policy for a StyleMind page.

    This is intentionally not a DashiAI renderer. It only carries the chosen
    component seed plus the Feibo restyle policy that every renderer must obey.
    """
    source_page = page if isinstance(page, dict) else {}
    tokens = style_tokens or {}
    rejected = bool(source_page.get("dashiai_seed_rejected"))
    selected_key = str(source_page.get("dashiai_seed_key") or "").strip()
    seed_snapshot = source_page.get("dashiai_seed_snapshot") if isinstance(source_page.get("dashiai_seed_snapshot"), dict) else {}

    base_restyle = build_feibo_restyle_policy(page_role, tokens, visual_profile)
    selected_seed: dict[str, Any] | None = None

    if selected_key and not rejected:
        candidates = match_restyled_dashiai_theme_seeds(
            page_role,
            style_tokens=tokens,
            visual_profile=visual_profile,
            limit=limit,
        )
        selected_seed = next((seed for seed in candidates if seed.get("key") == selected_key), None)
        if not selected_seed and seed_snapshot.get("key") == selected_key:
            selected_seed = {**seed_snapshot, "feibo_restyle": seed_snapshot.get("feibo_restyle") or base_restyle}
        if not selected_seed:
            selected_seed = {
                "key": selected_key,
                "theme": source_page.get("dashiai_seed_theme") or selected_key,
                "label": source_page.get("dashiai_seed_label") or selected_key,
                "module_tags": _as_list(source_page.get("dashiai_seed_module_tags")),
                "control_count": 0,
                "has_media_slots": False,
                "adaptation_status": "selected_seed_not_in_current_top_candidates",
                "feibo_restyle": base_restyle,
            }

    if selected_seed:
        restyle = selected_seed.get("feibo_restyle") or base_restyle
        module_tags = _as_list(selected_seed.get("module_tags") or selected_seed.get("moduleTags"))
        status = "dashiai_seed_selected_needs_feibo_restyle"
        source = "dashiai_theme_seed"
    else:
        restyle_status = "dashiai_seed_rejected_use_feibo_template_first" if rejected else "no_dashiai_seed_use_feibo_template_first"
        restyle = {**base_restyle, "status": restyle_status}
        module_tags = []
        status = restyle_status
        source = "feibo_template_first"

    compact_seed = _compact_seed(selected_seed)
    render_hints = _render_hints_for_component(page_role, visual_profile, module_tags, bool(compact_seed))
    modules = _component_modules_for_page(page_role, visual_profile, module_tags, bool(compact_seed))
    if modules:
        render_hints["primary_module_key"] = modules[0]["key"]
        render_hints["primary_module_label"] = modules[0]["label"]
    return {
        "schema": "stylemind.component_spec.v1",
        "source": source,
        "status": status,
        "page_role": page_role,
        "selected_seed": compact_seed,
        "selected_seed_key": compact_seed.get("key") if compact_seed else "",
        "dashiai_seed_rejected": rejected,
        "feibo_restyle": restyle,
        "blocked_defaults": restyle.get("blocked_defaults", []),
        "modules": modules,
        "render_hints": render_hints,
        "transcription_target": "html_preview_to_native_editable_pptx_objects",
    }


def build_feibo_restyle_policy(
    page_role: str,
    style_tokens: dict[str, Any],
    visual_profile: Any | None = None,
) -> dict[str, Any]:
    archetype = _attr_or_key(visual_profile, "archetype") or "editorial_content_bridge"
    composition = _attr_or_key(visual_profile, "composition") or "open_editorial_layout"
    density = _attr_or_key(visual_profile, "density") or "balanced"
    photo = _attr_or_key(visual_profile, "image_treatment") or style_tokens.get("photo") or "supporting"
    paper = str(style_tokens.get("paper") or "#F8FAFC")
    accent = str(style_tokens.get("accent") or "#2563EB")
    soft = str(style_tokens.get("soft") or "#E2E8F0")
    style_id = str(style_tokens.get("id") or "campaign_emotion_cover")
    style_label = str(style_tokens.get("label") or "Campaign 情绪主视觉")
    return {
        "schema": "stylemind.feibo_restyle_policy.v1",
        "target_style_id": style_id,
        "target_style_label": style_label,
        "visual_archetype": archetype,
        "composition": composition,
        "density": density,
        "target_tokens": {
            "paper": paper,
            "accent": accent,
            "soft": soft,
            "photo_treatment": photo,
            "font_title": "Microsoft YaHei / 微软雅黑 / 京东朗正体 fallback",
            "font_body": "Microsoft YaHei / 微软雅黑 / SimSun fallback",
        },
        "rewrite_rules": _role_rewrite_rules(page_role, archetype),
        "blocked_defaults": [
            "keep_original_dashiai_palette_as_final",
            "keep_fixed_corner_index_by_default",
            "keep_generic_separator_lines",
            "use_full_slide_png_as_delivery",
            "leave_reference_images_when_current_assets_exist",
        ],
        "asset_policy": {
            "background_images": "bottom-layer replaceable picture objects",
            "fixed_images": "hero/cutout/evidence replaceable picture objects",
            "image_2": "material generation only; never page text/layout",
        },
        "status": "seed_selected_needs_feibo_restyle",
    }


def dashiai_seed_summary() -> dict[str, Any]:
    registry = load_dashiai_seed_registry()
    return {
        "schema": registry.get("schema"),
        "source": registry.get("source", {}),
        "counts": registry.get("counts", {}),
        "feibo_overlay": registry.get("feiboOverlay", {}),
        "role_counts": {role: len(keys) for role, keys in registry.get("byRole", {}).items()},
    }


def _attr_or_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if not value:
        return []
    return [value]


def _compact_seed(seed: dict[str, Any] | None) -> dict[str, Any]:
    if not seed:
        return {}
    return {
        "key": seed.get("key"),
        "theme": seed.get("theme") or seed.get("themeName") or seed.get("themeKey"),
        "label": seed.get("label") or seed.get("key"),
        "module_tags": _as_list(seed.get("module_tags") or seed.get("moduleTags"))[:6],
        "control_count": int(seed.get("control_count") or seed.get("controlCount") or 0),
        "has_media_slots": bool(seed.get("has_media_slots") or seed.get("hasMediaSlots")),
        "adaptation_status": seed.get("adaptation_status") or seed.get("adaptationStatus") or "seed_needs_feibo_restyle",
    }


def _render_hints_for_component(
    page_role: str,
    visual_profile: Any | None,
    module_tags: list[Any],
    has_seed: bool,
) -> dict[str, Any]:
    archetype = _attr_or_key(visual_profile, "archetype") or ""
    tags = [str(tag) for tag in module_tags if tag]
    return {
        "show_left_rail": False,
        "show_fixed_tag": False,
        "show_generic_separator": False,
        "prefer_open_layout": True,
        "prefer_image_led": page_role in {"开场定调", "创意主张", "案例证据", "视频素材"} or bool(has_seed),
        "preserve_metric_structure": archetype == "metric_dashboard" or "metric_dashboard" in tags,
        "preserve_process_structure": archetype in {"step_flow", "campaign_timeline"} or any(tag in {"step_flow", "timeline"} for tag in tags),
        "borrowed_module_tags": tags[:6],
    }


def _component_modules_for_page(
    page_role: str,
    visual_profile: Any | None,
    module_tags: list[Any],
    has_seed: bool,
) -> list[dict[str, Any]]:
    archetype = _attr_or_key(visual_profile, "archetype") or ""
    tags = {str(tag) for tag in module_tags if tag}

    if archetype == "metric_dashboard" or page_role == "数据结果" or "metric_dashboard" in tags:
        return [
            {
                "schema": "stylemind.component_module.v1",
                "key": "feibo_metric_result_strip",
                "label": "飞博化数据结果条",
                "source": "dashiai_seed_metric" if has_seed else "feibo_role_default",
                "slot_contract": [
                    {"key": "primary_metric", "kind": "metric", "source": "card_texts[0]", "editable": True},
                    {"key": "support_metric_1", "kind": "metric", "source": "card_texts[1]", "editable": True},
                    {"key": "support_metric_2", "kind": "metric", "source": "card_texts[2]", "editable": True},
                    {"key": "insight_copy", "kind": "text", "source": "body_lines", "editable": True},
                ],
                "render_behavior": {
                    "large_primary_metric": True,
                    "soft_support_tiles": True,
                    "avoid_dashboard_frame": True,
                    "allow_semantic_connectors": False,
                },
            }
        ]

    if archetype in {"step_flow", "campaign_timeline"} or page_role == "执行打法" or tags.intersection({"step_flow", "timeline"}):
        return [
            {
                "schema": "stylemind.component_module.v1",
                "key": "feibo_process_rhythm",
                "label": "飞博化执行节奏",
                "source": "dashiai_seed_process" if has_seed else "feibo_role_default",
                "slot_contract": [
                    {"key": "step_1", "kind": "process_step", "source": "card_texts[0]", "editable": True},
                    {"key": "step_2", "kind": "process_step", "source": "card_texts[1]", "editable": True},
                    {"key": "step_3", "kind": "process_step", "source": "card_texts[2]", "editable": True},
                    {"key": "step_4", "kind": "process_step", "source": "card_texts[3]", "editable": True},
                ],
                "render_behavior": {
                    "open_step_blocks": True,
                    "allow_semantic_connectors": True,
                    "avoid_software_dashboard_tiles": True,
                },
            }
        ]

    if archetype == "evidence_wall" or page_role == "案例证据" or "media_collage" in tags:
        return [
            {
                "schema": "stylemind.component_module.v1",
                "key": "feibo_evidence_wall",
                "label": "飞博化案例证据墙",
                "source": "dashiai_seed_evidence" if has_seed else "feibo_role_default",
                "slot_contract": [
                    {"key": "evidence_image", "kind": "image", "source": "image_sources[0]", "editable": True},
                    {"key": "proof_caption", "kind": "text", "source": "card_texts[0]", "editable": True},
                    {"key": "supporting_proof", "kind": "text", "source": "body_lines", "editable": True},
                ],
                "render_behavior": {
                    "image_led": True,
                    "native_captions": True,
                    "replace_reference_imagery": True,
                },
            }
        ]

    if archetype == "video_material_board" or page_role == "视频素材":
        return [
            {
                "schema": "stylemind.component_module.v1",
                "key": "feibo_video_storyboard",
                "label": "飞博化视频素材板",
                "source": "feibo_role_default",
                "slot_contract": [
                    {"key": "video_thumbnail", "kind": "image", "source": "image_sources[0]", "editable": True},
                    {"key": "video_link", "kind": "video_link", "source": "video_links[0]", "editable": True},
                    {"key": "caption", "kind": "text", "source": "body_lines", "editable": True},
                ],
                "render_behavior": {
                    "thumbnail_first": True,
                    "native_link_label": True,
                    "avoid_baked_video_text": True,
                },
            }
        ]

    return [
        {
            "schema": "stylemind.component_module.v1",
            "key": "feibo_editorial_image_copy",
            "label": "飞博化图文承接",
            "source": "feibo_role_default",
            "slot_contract": [
                {"key": "title", "kind": "text", "source": "title", "editable": True},
                {"key": "body", "kind": "text", "source": "body_lines", "editable": True},
                {"key": "support_image", "kind": "image", "source": "image_sources[0]", "editable": True},
            ],
            "render_behavior": {
                "open_editorial_layout": True,
                "image_supporting": True,
                "avoid_generic_card_wall": True,
            },
        }
    ]


def _role_rewrite_rules(page_role: str, archetype: str) -> list[str]:
    shared = [
        "use open spacing and asymmetry from Feibo references",
        "prefer image-led campaign atmosphere over generic UI cards",
        "keep text editable and avoid baking copy into background images",
    ]
    by_role = {
        "开场定调": [
            "make the brand/campaign signal dominant in the first viewport",
            "use one strong emotional visual instead of multiple small decorative marks",
        ],
        "章节转场": [
            "use confident whitespace and one structural gesture, not repeated corner labels",
            "make section hierarchy clear without template-looking badges",
        ],
        "内容承接": [
            "keep paragraphs short and editorial, with one supporting visual system",
            "avoid dense card walls unless the reference page uses that rhythm",
        ],
        "创意主张": [
            "prioritize one memorable claim and a campaign image layer",
            "remove generic sticker noise unless Feibo reference calls for it",
        ],
        "执行打法": [
            "turn process steps into campaign rhythm, not software dashboard tiles",
            "use timeline/roadmap only when it clarifies action sequencing",
        ],
        "案例证据": [
            "use evidence-wall crops and real screenshot/media hierarchy",
            "separate proof captions from decorative labels",
        ],
        "数据结果": [
            "make the main result legible first, then support with chart/table detail",
            "use Feibo light-data palette and avoid hard dashboard blocks",
        ],
        "视频素材": [
            "treat video as a thumbnail/storyboard board with native text labels",
            "keep link and caption editable outside the thumbnail image",
        ],
    }
    rules = shared + by_role.get(page_role, [])
    if archetype in {"metric_dashboard", "campaign_timeline"}:
        rules.append("preserve data structure but restyle axis, callouts, and rhythm toward Feibo samples")
    if archetype in {"hero_photo_claim", "strategy_claim_collage", "evidence_wall"}:
        rules.append("current page assets should replace inherited DashiAI/reference imagery before final export")
    return rules
