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
REFERENCE_TEMPLATE_SCRIPT = ROOT / "scripts" / "run_reference_template_matcher_probe.mjs"

KNOWN_LIMITATIONS = [
    "cleaned reference templates are still production_safe=false until visual QA is complete",
    "pages without current background_images or fixed_images receive generated neutral placeholders and still need final visual assets",
    "some source text may be baked into images or grouped artwork",
]


@dataclass(frozen=True)
class ReferenceTemplateRenderResult:
    output_path: str
    render_plan_path: str
    report_path: str
    page_count: int
    selected_count: int
    strategy: str = "reference_template_first"
    known_limitations: tuple[str, ...] = tuple(KNOWN_LIMITATIONS)
    stdout: str = ""
    stderr: str = ""


class ReferenceTemplateRendererError(RuntimeError):
    """Raised when the reference-template renderer cannot produce a PPTX."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def _default_render_plan_path() -> Path:
    DEFAULT_RENDER_PLAN_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_RENDER_PLAN_DIR / f"reference_template_render_plan_{int(time.time())}_{uuid.uuid4().hex[:8]}.json"


def _default_report_path(output_path: Path) -> Path:
    DEFAULT_RENDER_PLAN_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_RENDER_PLAN_DIR / f"{output_path.stem}_reference_template_report.json"


def _validate_payload(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema")
    if schema != "stylemind.render_plan.v1":
        raise ValueError(f"unsupported RenderPlan schema: {schema}")
    if not isinstance(payload.get("plans"), list):
        raise ValueError("RenderPlan payload must include a plans list")
    if not REFERENCE_TEMPLATE_SCRIPT.exists():
        raise ReferenceTemplateRendererError(f"reference-template script missing: {REFERENCE_TEMPLATE_SCRIPT}")


def _report_url_path(path: str | Path) -> str | None:
    try:
        rel = Path(path).resolve().relative_to((WEB_UI_DIR / "static" / "generated").resolve())
    except Exception:
        return None
    return f"/api/generated/{rel.as_posix()}"


def render_payload_to_reference_template(
    payload: Mapping[str, Any],
    output_path: str | Path,
    *,
    render_plan_path: str | Path | None = None,
    report_path: str | Path | None = None,
    timeout: int = 240,
    max_pages: int | None = None,
) -> ReferenceTemplateRenderResult:
    """Render a serialized RenderPlan by copying matched reference PPTX template slides."""
    _validate_payload(payload)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    plan_path = Path(render_plan_path) if render_plan_path else _default_render_plan_path()
    report = Path(report_path) if report_path else _default_report_path(output)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        "node",
        str(REFERENCE_TEMPLATE_SCRIPT),
        "--input",
        str(plan_path),
        "--output",
        str(output),
        "--report",
        str(report),
    ]
    if max_pages:
        cmd.extend(["--first-pages", "--max-pages", str(max_pages)])
    else:
        cmd.append("--all-pages")

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(ROOT),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ReferenceTemplateRendererError("Node.js is required for the reference-template renderer") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise ReferenceTemplateRendererError(
            f"Reference-template renderer failed: {detail[:800]}",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ReferenceTemplateRendererError(
            f"Reference-template renderer timed out after {timeout}s",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        ) from exc

    if not output.exists() or output.stat().st_size == 0:
        raise ReferenceTemplateRendererError("Reference-template renderer did not create a PPTX file")
    if not report.exists() or report.stat().st_size == 0:
        raise ReferenceTemplateRendererError("Reference-template renderer did not create a report file")

    try:
        report_data = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReferenceTemplateRendererError(f"Reference-template report is invalid JSON: {report}") from exc

    return ReferenceTemplateRenderResult(
        output_path=str(output),
        render_plan_path=str(plan_path),
        report_path=str(report),
        page_count=int(report_data.get("pageCount") or len(payload.get("plans") or [])),
        selected_count=len(report_data.get("selected") or []),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def render_outline_to_reference_template(
    outline: Mapping[str, Any],
    output_path: str | Path,
    *,
    render_plan_path: str | Path | None = None,
    report_path: str | Path | None = None,
    timeout: int = 240,
    max_pages: int | None = None,
) -> ReferenceTemplateRenderResult:
    """Build the shared RenderPlan from an outline, then render matched reference templates."""
    return render_payload_to_reference_template(
        deck_render_plan_to_dict(dict(outline)),
        output_path,
        render_plan_path=render_plan_path,
        report_path=report_path,
        timeout=timeout,
        max_pages=max_pages,
    )


def render_plans_to_reference_template(
    plans: Sequence[SlideRenderPlan],
    output_path: str | Path,
    *,
    render_plan_path: str | Path | None = None,
    report_path: str | Path | None = None,
    timeout: int = 240,
    max_pages: int | None = None,
) -> ReferenceTemplateRenderResult:
    """Render existing SlideRenderPlan objects through matched reference templates."""
    payload = {
        "schema": "stylemind.render_plan.v1",
        "page_count": len(plans),
        "plans": [render_plan_to_dict(plan) for plan in plans],
    }
    return render_payload_to_reference_template(
        payload,
        output_path,
        render_plan_path=render_plan_path,
        report_path=report_path,
        timeout=timeout,
        max_pages=max_pages,
    )


__all__ = [
    "KNOWN_LIMITATIONS",
    "ReferenceTemplateRendererError",
    "ReferenceTemplateRenderResult",
    "render_outline_to_reference_template",
    "render_payload_to_reference_template",
    "render_plans_to_reference_template",
]
