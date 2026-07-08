#!/usr/bin/env python3
"""Verify the reference-template candidate registry used by the 95-point route."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reference_samples" / "brand_campaign_ingest" / "reference_manifest.json"
REGISTRY = ROOT / "reference_samples" / "brand_campaign_ingest" / "template_registry.json"
EXPECTED_ARCHETYPES = {
    "hero_photo_claim",
    "section_divider",
    "strategy_claim_collage",
    "metric_dashboard",
    "evidence_wall",
    "campaign_timeline",
    "step_flow",
    "editorial_content_bridge",
    "video_material_board",
}


def run_builder() -> None:
    subprocess.run(
        ["node", "scripts/build_reference_template_registry.mjs"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def main() -> int:
    if not MANIFEST.exists():
        raise SystemExit(f"reference manifest missing: {MANIFEST}")

    run_builder()
    if not REGISTRY.exists():
        raise SystemExit(f"template registry missing: {REGISTRY}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if registry.get("schema") != "stylemind.reference_template_registry.v1":
        raise SystemExit(f"unexpected registry schema: {registry.get('schema')}")

    expected_count = int(manifest.get("pptx_pages") or 0)
    candidates = registry.get("candidates") or []
    if len(candidates) != expected_count:
        raise SystemExit(f"expected {expected_count} candidates, got {len(candidates)}")

    selected = registry.get("selected_recipes") or {}
    missing = sorted(EXPECTED_ARCHETYPES - set(selected))
    if missing:
        raise SystemExit(f"missing selected archetypes: {missing}")

    candidate_ids = {item.get("id") for item in candidates}
    selected_ids = []
    for archetype, recipe in selected.items():
        candidate_id = recipe.get("candidate_id")
        selected_ids.append(candidate_id)
        if candidate_id not in candidate_ids:
            raise SystemExit(f"{archetype} points to unknown candidate: {candidate_id}")
        if not recipe.get("file") or not recipe.get("slide"):
            raise SystemExit(f"{archetype} recipe missing file/slide: {recipe}")

    unique_selected = len(set(selected_ids))
    if unique_selected < 5:
        raise SystemExit(f"template registry is too repetitive: only {unique_selected} unique selected slides")

    readiness_counts: dict[str, int] = {}
    for item in candidates:
        readiness_counts[item.get("readiness", "unknown")] = readiness_counts.get(item.get("readiness", "unknown"), 0) + 1

    summary = {
        "status": "ok",
        "registry": str(REGISTRY),
        "candidate_count": len(candidates),
        "selected_archetypes": len(selected),
        "unique_selected_slides": unique_selected,
        "readiness_counts": readiness_counts,
        "selected": selected,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
