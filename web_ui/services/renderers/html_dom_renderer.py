from __future__ import annotations

import json
import os
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
HTML_DOM_SCRIPT = ROOT / "scripts" / "run_html_dom_transcription_probe.mjs"

KNOWN_LIMITATIONS = [
    "html-dom transcription is experimental and depends on the installed DashiAI skill runtime",
    "complex CSS backgrounds and effects may be preserved as PPTX picture objects",
    "this route prioritizes HTML visual fidelity plus editable text, not all-native shape reconstruction",
]


@dataclass(frozen=True)
class HtmlDomRenderResult:
    output_path: str
    render_plan_path: str
    report_path: str
    deck_dir: str
    page_count: int
    text_objects: int
    shape_objects: int
    image_objects: int
    strategy: str = "html_dom_transcription"
    known_limitations: tuple[str, ...] = tuple(KNOWN_LIMITATIONS)
    stdout: str = ""
    stderr: str = ""


class HtmlDomRendererError(RuntimeError):
    """Raised when the HTML DOM renderer cannot produce a PPTX."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def _default_render_plan_path() -> Path:
    DEFAULT_RENDER_PLAN_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_RENDER_PLAN_DIR / f"html_dom_render_plan_{int(time.time())}_{uuid.uuid4().hex[:8]}.json"


def _default_report_path(output_path: Path) -> Path:
    DEFAULT_RENDER_PLAN_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_RENDER_PLAN_DIR / f"{output_path.stem}_html_dom_report.json"


def _default_deck_dir(output_path: Path) -> Path:
    DEFAULT_RENDER_PLAN_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_RENDER_PLAN_DIR / f"{output_path.stem}_html_dom_deck"


def _validate_payload(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema")
    if schema != "stylemind.render_plan.v1":
        raise ValueError(f"unsupported RenderPlan schema: {schema}")
    if not isinstance(payload.get("plans"), list):
        raise ValueError("RenderPlan payload must include a plans list")
    if not HTML_DOM_SCRIPT.exists():
        raise HtmlDomRendererError(f"HTML DOM renderer script missing: {HTML_DOM_SCRIPT}")


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    runtime_tmp = ROOT / ".pytest_tmp" / "html_dom_runtime_tmp"
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    for key in ("TMPDIR", "TMP", "TEMP"):
        env[key] = str(runtime_tmp)
    return env


def _report_url_path(path: str | Path) -> str | None:
    try:
        rel = Path(path).resolve().relative_to((WEB_UI_DIR / "static" / "generated").resolve())
    except Exception:
        return None
    return f"/api/generated/{rel.as_posix()}"


def render_payload_to_html_dom(
    payload: Mapping[str, Any],
    output_path: str | Path,
    *,
    render_plan_path: str | Path | None = None,
    report_path: str | Path | None = None,
    deck_dir: str | Path | None = None,
    timeout: int = 180,
) -> HtmlDomRenderResult:
    """Render a serialized StyleMind RenderPlan through a browser DOM -> PPTX pass."""
    _validate_payload(payload)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    plan_path = Path(render_plan_path) if render_plan_path else _default_render_plan_path()
    report = Path(report_path) if report_path else _default_report_path(output)
    deck = Path(deck_dir) if deck_dir else _default_deck_dir(output)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    deck.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        "node",
        str(HTML_DOM_SCRIPT),
        "--input",
        str(plan_path),
        "--deck-dir",
        str(deck),
        "--output",
        str(output),
        "--report",
        str(report),
    ]

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(ROOT),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=_subprocess_env(),
        )
    except FileNotFoundError as exc:
        raise HtmlDomRendererError("Node.js is required for the HTML DOM renderer") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise HtmlDomRendererError(
            f"HTML DOM renderer failed: {detail[:800]}",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HtmlDomRendererError(
            f"HTML DOM renderer timed out after {timeout}s",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        ) from exc

    if not output.exists() or output.stat().st_size == 0:
        raise HtmlDomRendererError("HTML DOM renderer did not create a PPTX file")
    if not report.exists() or report.stat().st_size == 0:
        raise HtmlDomRendererError("HTML DOM renderer did not create a report file")

    try:
        report_data = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HtmlDomRendererError(f"HTML DOM renderer report is invalid JSON: {report}") from exc

    return HtmlDomRenderResult(
        output_path=str(output),
        render_plan_path=str(plan_path),
        report_path=str(report),
        deck_dir=str(deck),
        page_count=int(report_data.get("slideCount") or len(payload.get("plans") or [])),
        text_objects=int(report_data.get("textObjects") or 0),
        shape_objects=int(report_data.get("shapeObjects") or 0),
        image_objects=int(report_data.get("imageObjects") or 0),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def render_outline_to_html_dom(
    outline: Mapping[str, Any],
    output_path: str | Path,
    *,
    render_plan_path: str | Path | None = None,
    report_path: str | Path | None = None,
    deck_dir: str | Path | None = None,
    timeout: int = 180,
) -> HtmlDomRenderResult:
    """Build the shared RenderPlan from an outline, then render through HTML DOM transcription."""
    return render_payload_to_html_dom(
        deck_render_plan_to_dict(dict(outline)),
        output_path,
        render_plan_path=render_plan_path,
        report_path=report_path,
        deck_dir=deck_dir,
        timeout=timeout,
    )


def render_plans_to_html_dom(
    plans: Sequence[SlideRenderPlan],
    output_path: str | Path,
    *,
    render_plan_path: str | Path | None = None,
    report_path: str | Path | None = None,
    deck_dir: str | Path | None = None,
    timeout: int = 180,
) -> HtmlDomRenderResult:
    """Render existing SlideRenderPlan objects through HTML DOM transcription."""
    payload = {
        "schema": "stylemind.render_plan.v1",
        "page_count": len(plans),
        "plans": [render_plan_to_dict(plan) for plan in plans],
    }
    return render_payload_to_html_dom(
        payload,
        output_path,
        render_plan_path=render_plan_path,
        report_path=report_path,
        deck_dir=deck_dir,
        timeout=timeout,
    )


__all__ = [
    "KNOWN_LIMITATIONS",
    "HtmlDomRendererError",
    "HtmlDomRenderResult",
    "render_outline_to_html_dom",
    "render_payload_to_html_dom",
    "render_plans_to_html_dom",
    "_report_url_path",
]
