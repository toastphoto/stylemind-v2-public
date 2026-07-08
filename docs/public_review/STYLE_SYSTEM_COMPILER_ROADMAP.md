# StyleMind Public Review Roadmap

Last updated: 2026-07-08

## What This Public Repo Is For

This public repository is a sanitized review mirror for GPT Pro and external architecture review. The private repository remains the source of truth for implementation, private reference decks, cleaned template libraries, visual QA outputs, and local project memory.

The public repo intentionally excludes:

- API keys and local config.
- private Feibo/reference decks and PDFs.
- cleaned private template PPTX files.
- local generated QA contact sheets.
- internal project memory.
- third-party experiment dumps pending license review.

## Current Architectural Direction

The project should not treat high-quality PPT references as text knowledge alone. The target is a design-system compiler:

```text
brief
-> ContentPlan
-> PageRoleClassifier
-> StylePack / TemplateRegistry retrieval
-> TemplateSelector
-> LayoutSolver
-> RenderPlan
-> HTML preview + editable PPTX renderer
-> Visual QA loop
```

The AI should not freely design every page. It should select and fill controlled design systems:

- StylePacks encode visual tokens, composition, capacity rules, and negative fit rules.
- TemplateSkills map page roles to reusable editable placeholders.
- RenderPlan is the source of truth consumed by both HTML preview and PPTX export.
- Reference-template-first remains the quality route when good editable templates exist.
- PptxGenJS/python-pptx remain fallback or adapter routes, not product-facing design modes.

Private implementation progress on 2026-07-08:

- The private repo now has a first StylePack seed-library builder.
- The private seed library links curated company reference sample pages, cleaned TemplateSkill candidates, and supplemental DashiAI-style component seeds.
- The Agent workbench receives per-page StylePack matches in its planning payload.
- The private Agent API now has an initial content-only ContentPlan layer for per-page message, slots, density, asset needs, and fit warnings before visual selection.
- The private workbench Page Manifest now shows ContentPlan and StylePack planning fields as separate layers.
- The private workbench now has initial lockable StylePack and TemplateSkill planning controls with deterministic fit scoring.
- The private reference-template export path now consumes locked TemplateSkill choices when they map to the cleaned template registry and reports lock consumption for QA.
- The private workbench now has a selected-page rendered QA path for locked TemplateSkill choices, returning a contact sheet and report for human visual review.
- The private workbench now persists selected-page rendered QA state back to the page/session and surfaces it in the planning manifest.
- The private reference-template renderer now compacts orphan template slides/media after PPTX generation so template-copy outputs do not carry inactive source assets.
- A live private smoke test confirmed selected-page QA can write back to a temporary outline session and reappear in the Agent planning payload; the same smoke confirmed the export path is not using a full-slide image-generation model for the QA state.
- Persisted rendered QA is now compiled into a visual-review signal used by private TemplateSkill fit scoring and surfaced in the workbench manifest.
- The public repo does not include the private seed JSON or private reference assets.

## Main Decisions

### 1. Split Content From Visual Planning

ContentPlan should only contain message, slots, evidence, density, and asset needs. It should not pick concrete layout.

Visual planning should choose StylePack and TemplateSkill based on page role, content density, and asset needs.

### 2. Replace Text-RAG Style Learning With StylePacks

RAG can keep content knowledge, but visual quality needs structured design extraction:

- slide size.
- shape bboxes.
- text font/size/color/weight.
- image bboxes and crop.
- z-order.
- background treatment.
- whitespace ratio.
- dominant visual area.
- editable placeholder semantics.
- page capacity rules and negative fit rules.

### 3. Keep HTML As Workbench, Not The Only Source

HTML is the preview and control surface. RenderPlan is the source of truth. PPTX export must consume the same RenderPlan.

Complex aesthetics may be baked into replaceable background/image layers when necessary, while headline/body/key business content stays editable.

### 4. Make Contact Sheets A Visual Gate

Visual changes should be reviewed through side-by-side outputs:

- reference archetype sample.
- HTML preview.
- rendered PPTX.
- object counts and full-slide fallback counts.
- text overflow / image coverage / palette / alignment checks where feasible.

## Next Small Build Targets

1. Aggregate visual-review status across the deck and use it to guide TemplateSkill selection and QA prioritization.
2. Mature ContentPlan fit scoring against real reference templates without letting it choose visual templates directly.
3. Promote template selection from scripts into the main workbench planning path.
4. Improve visual fit and placeholder-capacity scoring using rendered QA evidence.
5. Keep public repo updates sanitized and review-oriented.

## Review Boundary

This public repo can be used to review structure and code direction. It cannot validate final Feibo-level visual quality unless private reference assets are replaced with public-safe samples or explicitly approved for release.
