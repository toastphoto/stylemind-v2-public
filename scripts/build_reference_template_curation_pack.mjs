#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Automizer } from "pptx-automizer";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_REGISTRY = path.join(ROOT, "reference_samples/brand_campaign_ingest/template_registry.json");
const DEFAULT_MANIFEST = path.join(ROOT, "reference_samples/brand_campaign_ingest/reference_manifest.json");
const DEFAULT_OUT_DIR = path.join(ROOT, ".pytest_tmp/reference_template_curation_pack");
const DEFAULT_OUTPUT = path.join(DEFAULT_OUT_DIR, "reference_template_curation_pack.pptx");
const DEFAULT_PLAN = path.join(ROOT, "reference_samples/curated_templates/reference_template_curation_plan.json");

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

function numberArg(name, fallback) {
  const raw = Number(argValue(name, String(fallback)));
  return Number.isFinite(raw) && raw > 0 ? raw : fallback;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function safeElementText(element) {
  try {
    return typeof element.getText === "function" ? cleanText(element.getText().join(" ")) : "";
  } catch {
    return "";
  }
}

function isPicture(element) {
  return element.type === "pic" || element.visualType === "picture";
}

function isWritableText(element) {
  return Boolean(
    element.hasTextBody &&
      element.type === "sp" &&
      ["textBox", "rectangle", "shape"].includes(element.visualType || "textBox"),
  );
}

function area(element) {
  const pos = element.position || {};
  return Math.max(0, Number(pos.cx || 0)) * Math.max(0, Number(pos.cy || 0));
}

function top(element) {
  return Number(element.position?.y || 0);
}

function summarizeElement(element) {
  return {
    name: element.name || "",
    type: element.type || "",
    visualType: element.visualType || "",
    creationId: element.creationId || "",
    text: safeElementText(element).slice(0, 180),
    position: element.position || null,
  };
}

function textRoleFor(element, index) {
  if (index === 0) return "title";
  if (index === 1) return "body";
  return "clear_or_optional_text";
}

function pictureRoleFor(archetypes, index) {
  if (index === 0 && archetypes.some((item) => ["hero_photo_claim", "section_divider", "editorial_content_bridge"].includes(item))) {
    return "hero_image";
  }
  if (archetypes.includes("evidence_wall")) return `evidence_image_${index + 1}`;
  if (archetypes.includes("video_material_board")) return `video_image_${index + 1}`;
  return `image_${index + 1}`;
}

function suggestedPlaceholders(slideInfo, archetypes) {
  const writableTexts = (slideInfo.elements || [])
    .filter((element) => isWritableText(element) && safeElementText(element))
    .sort((a, b) => {
      const aScore = area(a) / 1e10 - top(a) / 1e6 + Math.min(safeElementText(a).length, 80);
      const bScore = area(b) / 1e10 - top(b) / 1e6 + Math.min(safeElementText(b).length, 80);
      return bScore - aScore;
    });
  const pictures = (slideInfo.elements || [])
    .filter(isPicture)
    .sort((a, b) => area(b) - area(a));

  return {
    text_targets: writableTexts.slice(0, 10).map((element, index) => ({
      suggested_role: textRoleFor(element, index),
      suggested_placeholder_name: textRoleFor(element, index) === "clear_or_optional_text" ? `optional_text_${index - 1}` : textRoleFor(element, index),
      ...summarizeElement(element),
    })),
    picture_targets: pictures.slice(0, 10).map((element, index) => ({
      suggested_role: pictureRoleFor(archetypes, index),
      suggested_placeholder_name: pictureRoleFor(archetypes, index),
      ...summarizeElement(element),
    })),
  };
}

function selectCandidates(registry, perArchetype, maxSlides) {
  const byId = new Map((registry.candidates || []).map((candidate) => [candidate.id, candidate]));
  const selected = new Map();
  for (const archetype of registry.archetypes || []) {
    let count = 0;
    for (const id of registry.by_archetype?.[archetype] || []) {
      const candidate = byId.get(id);
      if (!candidate || candidate.readiness === "weak") continue;
      if (!selected.has(id)) {
        if (selected.size >= maxSlides) break;
        selected.set(id, { ...candidate, archetypes: [] });
      }
      const record = selected.get(id);
      if (!record.archetypes.includes(archetype)) record.archetypes.push(archetype);
      count += 1;
      if (count >= perArchetype) break;
    }
  }
  return [...selected.values()].sort((a, b) => {
    const aFirst = a.archetypes[0] || "";
    const bFirst = b.archetypes[0] || "";
    if (aFirst !== bFirst) return String(aFirst).localeCompare(String(bFirst));
    return b.score - a.score;
  });
}

async function loadAutomizer(manifest, outputDir) {
  const pptxEntries = (manifest.entries || []).filter((entry) => entry.kind === "pptx");
  if (!pptxEntries.length) throw new Error("no editable PPTX entries in manifest");
  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(" "));
  try {
    const automizer = new Automizer({
      templateDir: manifest.source_dir,
      outputDir,
      removeExistingSlides: true,
      autoImportSlideMasters: true,
      cleanup: false,
      compression: 0,
      verbosity: 0,
    });
    automizer.loadRoot(pptxEntries[0].file);
    for (const [idx, entry] of pptxEntries.entries()) {
      automizer.load(entry.file, `tpl${idx}`);
    }
    const info = await automizer.getInfo();
    return { automizer, info, warnings };
  } finally {
    console.warn = originalWarn;
  }
}

function slideInfoFor(info, candidate) {
  const slides = info.slidesByTemplate(candidate.alias) || [];
  return slides.find((slide) => slide.number === candidate.slide);
}

async function main() {
  const registryPath = path.resolve(argValue("--registry", DEFAULT_REGISTRY));
  const manifestPath = path.resolve(argValue("--manifest", DEFAULT_MANIFEST));
  const outputPath = path.resolve(argValue("--output", DEFAULT_OUTPUT));
  const planPath = path.resolve(argValue("--plan", DEFAULT_PLAN));
  const perArchetype = numberArg("--per-archetype", 3);
  const maxSlides = numberArg("--max-slides", 27);

  if (!fs.existsSync(registryPath)) throw new Error(`template registry not found: ${registryPath}`);
  if (!fs.existsSync(manifestPath)) throw new Error(`reference manifest not found: ${manifestPath}`);
  const registry = readJson(registryPath);
  const manifest = readJson(manifestPath);
  const outputDir = path.dirname(outputPath);
  fs.mkdirSync(outputDir, { recursive: true });
  fs.mkdirSync(path.dirname(planPath), { recursive: true });

  const selected = selectCandidates(registry, perArchetype, maxSlides);
  const { automizer, info, warnings } = await loadAutomizer(manifest, outputDir);
  const planEntries = [];
  let deckSlide = 0;
  for (const candidate of selected) {
    const slideInfo = slideInfoFor(info, candidate);
    if (!slideInfo) continue;
    deckSlide += 1;
    automizer.addSlide(candidate.alias, candidate.slide);
    const placeholders = suggestedPlaceholders(slideInfo, candidate.archetypes);
    planEntries.push({
      deck_slide: deckSlide,
      candidate_id: candidate.id,
      file: candidate.file,
      source_alias: candidate.alias,
      source_slide: candidate.slide,
      archetypes: candidate.archetypes,
      readiness: candidate.readiness,
      score: candidate.score,
      metrics: candidate.metrics,
      curation_status: "needs_named_placeholder_cleanup",
      required_cleanup: [
        "remove or replace old source copy",
        "rename safe text targets to semantic placeholders",
        "rename safe picture targets to semantic placeholders",
        "render and inspect before production use",
      ],
      suggested_placeholders: placeholders,
      sample_text: candidate.sample_text,
    });
  }

  if (!planEntries.length) throw new Error("no curation candidates selected");
  const outputName = path.basename(outputPath);
  const writeSummary = await automizer.write(outputName);
  const plan = {
    schema: "stylemind.reference_template_curation_plan.v1",
    generated_by: "scripts/build_reference_template_curation_pack.mjs",
    source_registry: path.relative(ROOT, registryPath),
    source_manifest: path.relative(ROOT, manifestPath),
    output_deck: path.relative(ROOT, outputPath),
    generated_at: new Date().toISOString(),
    per_archetype: perArchetype,
    max_slides: maxSlides,
    selected_count: planEntries.length,
    production_safe: false,
    quality_route: "reference_template_first",
    warnings: warnings.slice(0, 80),
    notes: [
      "This deck is a curation work pack, not a production template library.",
      "Promote slides only after old text is removed and placeholders are named semantically.",
    ],
    write_summary: writeSummary,
    selected: planEntries,
  };
  fs.writeFileSync(planPath, JSON.stringify(plan, null, 2), "utf8");
  console.log(JSON.stringify({ status: "ok", output: outputPath, plan: planPath, slides: planEntries.length }));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
