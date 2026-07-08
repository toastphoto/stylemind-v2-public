#!/usr/bin/env python3
"""Verify the vendored DashiAI theme seed registry used by StyleMind."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "third_party" / "dashiai-ppt-skill"
LICENSE_FILE = VENDOR_DIR / "LICENSE"
README_FILE = VENDOR_DIR / "README.md"
REGISTRY_FILE = ROOT / "reference_samples" / "dashiai_theme_seed" / "stylemind_dashiai_theme_seed_registry.json"

REQUIRED_ROLES = {
    "开场定调",
    "章节转场",
    "内容承接",
    "创意主张",
    "执行打法",
    "案例证据",
    "数据结果",
    "视频素材",
}


def main() -> int:
    errors: list[str] = []
    for path in [VENDOR_DIR, LICENSE_FILE, README_FILE, REGISTRY_FILE]:
        if not path.exists():
            errors.append(f"missing: {path.relative_to(ROOT)}")

    registry: dict = {}
    if REGISTRY_FILE.exists():
        registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        if registry.get("schema") != "stylemind.dashiai_theme_seed_registry.v1":
            errors.append("registry schema mismatch")
        source = registry.get("source") or {}
        if source.get("license") != "AGPL-3.0":
            errors.append("registry must record AGPL-3.0 source license")
        counts = registry.get("counts") or {}
        if int(counts.get("themes") or 0) < 12:
            errors.append("expected at least 12 theme packs")
        if int(counts.get("sourcePages") or 0) < 1000:
            errors.append("expected at least 1000 source pages")
        if int(counts.get("candidates") or 0) < 800:
            errors.append("expected at least 800 seed candidates")
        by_role = registry.get("byRole") or {}
        missing_roles = sorted(role for role in REQUIRED_ROLES if not by_role.get(role))
        if missing_roles:
            errors.append(f"missing role seed candidates: {', '.join(missing_roles)}")
        candidates = registry.get("candidates") or []
        if not any((item.get("adaptation") or {}).get("status") == "seed_needs_feibo_restyle" for item in candidates):
            errors.append("candidates must be marked as needing Feibo restyle")

    if LICENSE_FILE.exists() and "GNU AFFERO GENERAL PUBLIC LICENSE" not in LICENSE_FILE.read_text(encoding="utf-8", errors="ignore")[:5000]:
        errors.append("vendored LICENSE does not look like AGPL")
    if README_FILE.exists() and "Feibo reference" not in README_FILE.read_text(encoding="utf-8", errors="ignore"):
        errors.append("vendored README must document Feibo adaptation policy")

    if errors:
        print("[FAIL] DashiAI theme seed registry verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    counts = registry.get("counts") or {}
    print(
        "[OK] DashiAI theme seed registry verified: "
        f"{counts.get('themes')} themes, {counts.get('sourcePages')} source pages, {counts.get('candidates')} candidates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
