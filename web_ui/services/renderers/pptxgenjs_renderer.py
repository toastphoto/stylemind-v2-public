from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from services.slide_render_plan import SlideRenderPlan, deck_render_plan_to_dict, render_plan_to_dict
except Exception:  # pragma: no cover - fallback when imported as package module
    from ..slide_render_plan import SlideRenderPlan, deck_render_plan_to_dict, render_plan_to_dict


ROOT = Path(__file__).resolve().parents[3]
WEB_UI_DIR = ROOT / "web_ui"
DEFAULT_RENDER_PLAN_DIR = WEB_UI_DIR / "static" / "generated" / "render_plans"
PPTXGENJS_SCRIPT = ROOT / "scripts" / "render_plan_pptxgenjs.mjs"


@dataclass(frozen=True)
class PptxGenJSRenderResult:
    output_path: str
    render_plan_path: str
    page_count: int
    stdout: str = ""
    stderr: str = ""


class PptxGenJSRendererError(RuntimeError):
    """Raised when the Node PptxGenJS renderer cannot produce a PPTX."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def _default_render_plan_path() -> Path:
    DEFAULT_RENDER_PLAN_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_RENDER_PLAN_DIR / f"render_plan_{int(time.time())}_{uuid.uuid4().hex[:8]}.json"


def _validate_payload(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema")
    if schema != "stylemind.render_plan.v1":
        raise ValueError(f"unsupported RenderPlan schema: {schema}")
    if not isinstance(payload.get("plans"), list):
        raise ValueError("RenderPlan payload must include a plans list")


def render_payload_to_pptxgenjs(
    payload: Mapping[str, Any],
    output_path: str | Path,
    *,
    render_plan_path: str | Path | None = None,
    timeout: int = 120,
) -> PptxGenJSRenderResult:
    """Render a serialized StyleMind RenderPlan payload with PptxGenJS."""
    _validate_payload(payload)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    plan_path = Path(render_plan_path) if render_plan_path else _default_render_plan_path()
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        completed = subprocess.run(
            ["node", str(PPTXGENJS_SCRIPT), "--input", str(plan_path), "--output", str(output)],
            cwd=str(ROOT),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise PptxGenJSRendererError("Node.js is required for the PptxGenJS renderer") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise PptxGenJSRendererError(
            f"PptxGenJS renderer failed: {detail[:800]}",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PptxGenJSRendererError(
            f"PptxGenJS renderer timed out after {timeout}s",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        ) from exc

    if not output.exists() or output.stat().st_size == 0:
        raise PptxGenJSRendererError("PptxGenJS renderer did not create a PPTX file")

    return PptxGenJSRenderResult(
        output_path=str(output),
        render_plan_path=str(plan_path),
        page_count=int(payload.get("page_count") or len(payload.get("plans") or [])),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def render_outline_to_pptxgenjs(
    outline: Mapping[str, Any],
    output_path: str | Path,
    *,
    render_plan_path: str | Path | None = None,
    timeout: int = 120,
) -> PptxGenJSRenderResult:
    """Build the shared RenderPlan from an outline, then render it with PptxGenJS."""
    return render_payload_to_pptxgenjs(
        deck_render_plan_to_dict(dict(outline)),
        output_path,
        render_plan_path=render_plan_path,
        timeout=timeout,
    )


def render_plans_to_pptxgenjs(
    plans: Sequence[SlideRenderPlan],
    output_path: str | Path,
    *,
    render_plan_path: str | Path | None = None,
    timeout: int = 120,
) -> PptxGenJSRenderResult:
    """Render existing SlideRenderPlan objects with PptxGenJS."""
    payload = {
        "schema": "stylemind.render_plan.v1",
        "page_count": len(plans),
        "plans": [render_plan_to_dict(plan) for plan in plans],
    }
    return render_payload_to_pptxgenjs(payload, output_path, render_plan_path=render_plan_path, timeout=timeout)


__all__ = [
    "PptxGenJSRendererError",
    "PptxGenJSRenderResult",
    "render_outline_to_pptxgenjs",
    "render_payload_to_pptxgenjs",
    "render_plans_to_pptxgenjs",
]
