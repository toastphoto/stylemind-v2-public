#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Automizer } from "pptx-automizer";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_MANIFEST = path.join(ROOT, "reference_samples/brand_campaign_ingest/reference_manifest.json");
const DEFAULT_OUTPUT = path.join(ROOT, "reference_samples/brand_campaign_ingest/template_registry.json");
const SLIDE_W = 12192000;
const SLIDE_H = 6858000;
const SLIDE_AREA = SLIDE_W * SLIDE_H;

const ARCHETYPES = [
  "hero_photo_claim",
  "section_divider",
  "strategy_claim_collage",
  "metric_dashboard",
  "evidence_wall",
  "campaign_timeline",
  "step_flow",
  "editorial_content_bridge",
  "video_material_board",
];

const GENERIC_NAME_RE = /^(文本框|图片|矩形|组合|object|picture|textbox|shape|freeform|placeholder)\s*\d+$/i;
const PLACEHOLDER_NAME_RE = /(title|subtitle|body|copy|text|hero|image|picture|metric|evidence|logo|placeholder|标题|副标题|正文|主图|图片占位|证据|指标)/i;
const METRIC_RE = /(\d+[,.]?\d*%|\d+[,.]?\d*\s*(万|亿|k|K|w|W|人|篇|次|倍|元|¥|￥)|\+\d+)/;
const TIMELINE_RE = /(节奏|阶段|预热|爆发|持续|上线|时间|timeline|phase|step|week|month|月|日)/i;
const STEP_RE = /(step|步骤|打法|动作|策略|目的|执行|链路|路径|方式|机制)/i;
const VIDEO_RE = /(视频|素材|片子|短片|tvc|video|reels|直播|达人)/i;

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

function numberArg(name, fallback) {
  const value = Number(argValue(name, String(fallback)));
  return Number.isFinite(value) && value > 0 ? value : fallback;
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

function isGroup(element) {
  return element.type === "grpSp" || element.visualType === "group";
}

function isWritableText(element) {
  return Boolean(
    element.hasTextBody &&
      element.type === "sp" &&
      ["textBox", "rectangle", "shape"].includes(element.visualType || "textBox"),
  );
}

function elementArea(element) {
  const pos = element.position || {};
  return Math.max(0, Number(pos.cx || 0)) * Math.max(0, Number(pos.cy || 0));
}

function isBigPicture(element) {
  return isPicture(element) && elementArea(element) >= SLIDE_AREA * 0.18;
}

function isFullBleedCandidate(element) {
  const pos = element.position || {};
  return (
    isPicture(element) &&
    Number(pos.x || 0) <= SLIDE_W * 0.04 &&
    Number(pos.y || 0) <= SLIDE_H * 0.04 &&
    Number(pos.cx || 0) >= SLIDE_W * 0.72 &&
    Number(pos.cy || 0) >= SLIDE_H * 0.72
  );
}

function semanticNameCount(elements) {
  return elements.filter((element) => element.name && !GENERIC_NAME_RE.test(element.name)).length;
}

function placeholderNameCount(elements) {
  return elements.filter((element) => element.name && PLACEHOLDER_NAME_RE.test(element.name) && !GENERIC_NAME_RE.test(element.name)).length;
}

function summarizeTextElements(elements) {
  return elements
    .filter((element) => element.hasTextBody)
    .map((element) => ({
      name: element.name || "",
      visualType: element.visualType || "",
      text: safeElementText(element).slice(0, 120),
      writable: isWritableText(element),
    }))
    .filter((item) => item.text)
    .slice(0, 8);
}

function readiness(metrics) {
  if (metrics.placeholder_name_count >= 3 || metrics.creation_id_count >= 4) return "named_or_id_ready";
  if (metrics.writable_text_count >= 1 && metrics.picture_count >= 1 && metrics.text_char_count <= 420) return "curation_candidate";
  if (metrics.writable_text_count >= 1) return "needs_manual_cleanup";
  return "weak";
}

function archetypeScores(metrics, sampleText) {
  const scores = Object.fromEntries(ARCHETYPES.map((item) => [item, 0]));
  const text = cleanText(sampleText);

  if (metrics.picture_count >= 1) {
    scores.editorial_content_bridge += 16;
    scores.strategy_claim_collage += 8;
  }
  if (metrics.big_picture_count >= 1) {
    scores.hero_photo_claim += 28;
    scores.section_divider += 22;
    scores.editorial_content_bridge += 8;
  }
  if (metrics.full_bleed_picture_count >= 1) {
    scores.hero_photo_claim += 22;
    scores.section_divider += 22;
  }
  if (metrics.text_element_count <= 3) {
    scores.hero_photo_claim += 18;
    scores.section_divider += 16;
  }
  if (metrics.text_element_count >= 2 && metrics.picture_count >= 2) {
    scores.strategy_claim_collage += 28;
    scores.evidence_wall += 14;
  }
  if (metrics.picture_count >= 4) {
    scores.evidence_wall += 28;
    scores.video_material_board += 22;
    scores.strategy_claim_collage += 10;
  }
  if (metrics.text_element_count >= 5 || METRIC_RE.test(text)) {
    scores.metric_dashboard += 30;
  }
  if (TIMELINE_RE.test(text)) {
    scores.campaign_timeline += 34;
  }
  if (STEP_RE.test(text) || (metrics.text_element_count >= 4 && metrics.picture_count <= 3)) {
    scores.step_flow += 28;
  }
  if (VIDEO_RE.test(text)) {
    scores.video_material_board += 34;
  }
  if (metrics.text_char_count > 700) {
    scores.hero_photo_claim -= 20;
    scores.section_divider -= 18;
    scores.strategy_claim_collage -= 8;
  }
  if (metrics.group_count > 2) {
    scores.metric_dashboard -= 5;
    scores.step_flow -= 5;
  }

  return Object.fromEntries(
    Object.entries(scores).map(([key, value]) => [key, Math.max(0, Math.round(value))]),
  );
}

function slideCandidate(file, alias, slide, deckEntry) {
  const elements = slide.elements || [];
  const textElements = elements.filter((element) => element.hasTextBody);
  const texts = textElements.map(safeElementText).filter(Boolean);
  const sampleText = cleanText(texts.join(" "));
  const metrics = {
    element_count: elements.length,
    text_element_count: textElements.length,
    writable_text_count: elements.filter(isWritableText).length,
    picture_count: elements.filter(isPicture).length,
    big_picture_count: elements.filter(isBigPicture).length,
    full_bleed_picture_count: elements.filter(isFullBleedCandidate).length,
    group_count: elements.filter(isGroup).length,
    creation_id_count: elements.filter((element) => element.creationId).length,
    semantic_name_count: semanticNameCount(elements),
    placeholder_name_count: placeholderNameCount(elements),
    text_char_count: sampleText.length,
  };
  const scores = archetypeScores(metrics, sampleText);
  const replaceabilityScore =
    metrics.writable_text_count * 8 +
    metrics.picture_count * 5 +
    metrics.big_picture_count * 8 +
    metrics.placeholder_name_count * 20 +
    metrics.creation_id_count * 3 -
    metrics.group_count * 3 -
    Math.floor(metrics.text_char_count / 120);
  const visualScore =
    metrics.picture_count * 7 +
    metrics.big_picture_count * 16 +
    metrics.full_bleed_picture_count * 18 +
    Math.max(0, 12 - Math.abs(metrics.text_element_count - 3) * 2) -
    Math.max(0, metrics.text_char_count - 420) / 80;
  const totalScore = Math.round(Math.max(0, replaceabilityScore) + Math.max(0, visualScore));
  const recommendedArchetypes = Object.entries(scores)
    .filter(([, score]) => score >= 24)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([archetype, score]) => ({ archetype, score }));

  return {
    id: `${alias}_s${slide.number}`,
    file,
    alias,
    slide: slide.number,
    deck_pages: deckEntry.pages || null,
    readiness: readiness(metrics),
    score: totalScore,
    replaceability_score: Math.round(replaceabilityScore),
    visual_score: Math.round(visualScore),
    metrics,
    archetype_scores: scores,
    recommended_archetypes: recommendedArchetypes,
    sample_text: sampleText.slice(0, 240),
    sample_text_elements: summarizeTextElements(elements),
  };
}

function readinessBonus(candidate) {
  if (candidate.readiness === "named_or_id_ready") return 35;
  if (candidate.readiness === "curation_candidate") return 18;
  if (candidate.readiness === "needs_manual_cleanup") return 6;
  return -18;
}

function archetypeFitScore(candidate, archetype) {
  const m = candidate.metrics;
  const text = candidate.sample_text || "";
  const base = candidate.archetype_scores[archetype] * 8 + readinessBonus(candidate);
  const textCount = m.text_element_count;
  const picCount = m.picture_count;
  const compactTextPenalty = Math.max(0, textCount - 4) * 14 + Math.max(0, m.text_char_count - 220) / 8;
  const densePenalty = Math.max(0, m.element_count - 48) * 2 + m.group_count * 4;

  if (archetype === "hero_photo_claim") {
    return (
      base +
      m.big_picture_count * 38 +
      m.full_bleed_picture_count * 34 +
      (picCount >= 1 ? 24 : -80) +
      (textCount <= 4 ? 52 : -compactTextPenalty) -
      densePenalty
    );
  }
  if (archetype === "section_divider") {
    return (
      base +
      m.big_picture_count * 28 +
      m.full_bleed_picture_count * 30 +
      (textCount <= 4 ? 48 : -compactTextPenalty) +
      (m.text_char_count <= 220 ? 20 : -20) -
      densePenalty
    );
  }
  if (archetype === "strategy_claim_collage") {
    return (
      base +
      Math.min(picCount, 8) * 22 +
      (textCount >= 2 && textCount <= 14 ? 34 : -Math.abs(textCount - 8) * 4) +
      m.big_picture_count * 14 -
      m.group_count * 3
    );
  }
  if (archetype === "metric_dashboard") {
    return (
      base +
      (METRIC_RE.test(text) ? 96 : -30) +
      (textCount >= 5 ? 28 : -20) +
      Math.min(textCount, 18) * 4 -
      Math.max(0, picCount - 12) * 5
    );
  }
  if (archetype === "evidence_wall") {
    return (
      base +
      (picCount >= 4 ? 72 : picCount * 12 - 20) +
      Math.min(picCount, 12) * 10 +
      (textCount >= 2 ? 18 : 0) -
      Math.max(0, m.text_char_count - 520) / 12
    );
  }
  if (archetype === "campaign_timeline") {
    return (
      base +
      (TIMELINE_RE.test(text) ? 110 : -35) +
      (textCount >= 3 ? 24 : -12) +
      Math.min(textCount, 16) * 4 -
      Math.max(0, picCount - 18) * 3
    );
  }
  if (archetype === "step_flow") {
    return (
      base +
      (STEP_RE.test(text) ? 92 : -22) +
      (textCount >= 4 ? 26 : -14) +
      Math.min(textCount, 14) * 4 -
      Math.max(0, picCount - 8) * 4
    );
  }
  if (archetype === "editorial_content_bridge") {
    return (
      base +
      (picCount >= 1 ? 34 : -48) +
      (textCount >= 2 && textCount <= 9 ? 42 : -Math.abs(textCount - 5) * 5) +
      m.big_picture_count * 18 -
      Math.max(0, m.text_char_count - 520) / 10
    );
  }
  if (archetype === "video_material_board") {
    return (
      base +
      (VIDEO_RE.test(text) ? 106 : 0) +
      (picCount >= 4 ? 54 : picCount * 9 - 18) +
      Math.min(picCount, 12) * 7 -
      Math.max(0, m.text_char_count - 480) / 12
    );
  }
  return base + candidate.score;
}

async function loadCandidates(manifest) {
  const pptxEntries = (manifest.entries || []).filter((entry) => entry.kind === "pptx");
  if (!pptxEntries.length) throw new Error("no PPTX entries in reference manifest");

  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(" "));
  try {
    const automizer = new Automizer({
      templateDir: manifest.source_dir,
      outputDir: path.join(ROOT, ".pytest_tmp/reference_template_registry"),
      removeExistingSlides: true,
      autoImportSlideMasters: true,
      cleanup: false,
      compression: 0,
      verbosity: 0,
    });
    automizer.loadRoot(pptxEntries[0].file);
    pptxEntries.forEach((entry, idx) => automizer.load(entry.file, `tpl${idx}`));
    const info = await automizer.getInfo();

    const candidates = [];
    pptxEntries.forEach((entry, idx) => {
      const alias = `tpl${idx}`;
      const slides = info.slidesByTemplate(alias);
      for (const slide of slides) {
        candidates.push(slideCandidate(entry.file, alias, slide, entry));
      }
    });
    return { candidates, warnings };
  } finally {
    console.warn = originalWarn;
  }
}

function buildByArchetype(candidates, topPerArchetype) {
  const byArchetype = {};
  const selectedRecipes = {};
  for (const archetype of ARCHETYPES) {
    const ranked = candidates
      .filter((candidate) => candidate.archetype_scores[archetype] > 0)
      .map((candidate) => ({
        ...candidate,
        archetype_match_score: candidate.archetype_scores[archetype],
        archetype_total_score: Math.round(archetypeFitScore(candidate, archetype)),
      }))
      .sort((a, b) => {
        if (b.archetype_total_score !== a.archetype_total_score) return b.archetype_total_score - a.archetype_total_score;
        return b.score - a.score;
      })
      .slice(0, topPerArchetype);
    byArchetype[archetype] = ranked.map((candidate) => candidate.id);
    if (ranked[0]) {
      selectedRecipes[archetype] = {
        candidate_id: ranked[0].id,
        file: ranked[0].file,
        slide: ranked[0].slide,
        readiness: ranked[0].readiness,
        score: ranked[0].score,
        archetype_match_score: ranked[0].archetype_match_score,
      };
    }
  }
  return { byArchetype, selectedRecipes };
}

async function main() {
  const manifestPath = path.resolve(argValue("--manifest", DEFAULT_MANIFEST));
  const outputPath = path.resolve(argValue("--output", DEFAULT_OUTPUT));
  const topPerArchetype = numberArg("--top-per-archetype", 5);

  if (!fs.existsSync(manifestPath)) throw new Error(`manifest not found: ${manifestPath}`);
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const { candidates, warnings } = await loadCandidates(manifest);
  const rankedCandidates = [...candidates].sort((a, b) => b.score - a.score);
  const { byArchetype, selectedRecipes } = buildByArchetype(rankedCandidates, topPerArchetype);
  const registry = {
    schema: "stylemind.reference_template_registry.v1",
    generated_by: "scripts/build_reference_template_registry.mjs",
    source_manifest: path.relative(ROOT, manifestPath),
    source_dir: manifest.source_dir,
    generated_at: new Date().toISOString(),
    archetypes: ARCHETYPES,
    candidate_count: rankedCandidates.length,
    warnings: warnings.slice(0, 60),
    selected_recipes: selectedRecipes,
    by_archetype: byArchetype,
    candidates: rankedCandidates,
  };
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(registry, null, 2), "utf8");
  console.log(
    JSON.stringify({
      status: "ok",
      output: outputPath,
      candidate_count: rankedCandidates.length,
      selected_archetypes: Object.keys(selectedRecipes).length,
    }),
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
