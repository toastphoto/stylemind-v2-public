#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";
import { Automizer } from "pptx-automizer";
import JSZip from "jszip";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MANIFEST = path.join(ROOT, "reference_samples/brand_campaign_ingest/reference_manifest.json");
const DEFAULT_TEMPLATE_REGISTRY = path.join(ROOT, "reference_samples/brand_campaign_ingest/template_registry.json");
const DEFAULT_CLEANED_REGISTRY = path.join(ROOT, "reference_samples/curated_templates/stylemind_cleaned_reference_templates_registry.json");
const DEFAULT_INPUT = path.join(ROOT, ".pytest_tmp/midea_social_render_plan.json");
const DEFAULT_OUTPUT = path.join(ROOT, ".pytest_tmp/reference_template_probe/stylemind_reference_template_match.pptx");
const DEFAULT_REPORT = path.join(ROOT, ".pytest_tmp/reference_template_probe/reference_template_match_report.json");

const PPTX_HOME = "20240221-小红书《哇塞！生活家》招商通案.pptx";
const PPTX_CNY = "20241227-2025年小红书CNY【大家的春节】SS级专项招商方案.pptx";
const PPTX_SLOW = "2024小红书慢人节招商方案.pptx";
const CLEANED_TEMPLATE_KEY = "__cleaned_reference_templates__";

const ARCHETYPE_RECIPES = {
  hero_photo_claim: { file: PPTX_SLOW, slide: 1 },
  section_divider: { file: PPTX_SLOW, slide: 2 },
  strategy_claim_collage: { file: PPTX_HOME, slide: 2 },
  metric_dashboard: { file: PPTX_CNY, slide: 5 },
  evidence_wall: { file: PPTX_HOME, slide: 5 },
  campaign_timeline: { file: PPTX_CNY, slide: 2 },
  step_flow: { file: PPTX_HOME, slide: 2 },
  editorial_content_bridge: { file: PPTX_SLOW, slide: 2 },
  video_material_board: { file: PPTX_HOME, slide: 2 },
};

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

function hasFlag(name) {
  return process.argv.includes(name);
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

function setRawText(text) {
  return (element) => {
    const textNodes = element.getElementsByTagName("a:t");
    if (!textNodes || textNodes.length === 0) return;
    for (let idx = 0; idx < textNodes.length; idx += 1) {
      textNodes.item(idx).textContent = idx === 0 ? text : "";
    }
  };
}

function positionArea(element) {
  const pos = element.position || {};
  return Math.max(0, Number(pos.cx || 0)) * Math.max(0, Number(pos.cy || 0));
}

function yPosition(element) {
  return Number(element.position?.y || 0);
}

function isTextCandidate(element) {
  const text = safeElementText(element);
  return Boolean(text && element.hasTextBody);
}

function isWritableTextSlot(element) {
  return Boolean(
    isTextCandidate(element) &&
      element.type === "sp" &&
      ["textBox", "rectangle", "shape"].includes(element.visualType || "textBox"),
  );
}

function selectTextTargets(slideInfo) {
  const all = (slideInfo.elements || []).filter(isTextCandidate);
  const writable = all.filter(isWritableTextSlot);
  const titleCandidates = [...writable].sort((a, b) => {
    const aScore = positionArea(a) / 1e10 - yPosition(a) / 1e6 + Math.min(safeElementText(a).length, 48);
    const bScore = positionArea(b) / 1e10 - yPosition(b) / 1e6 + Math.min(safeElementText(b).length, 48);
    return bScore - aScore;
  });
  const title = titleCandidates[0] || writable[0];
  const body = [...writable]
    .filter((element) => element !== title)
    .sort((a, b) => {
      const aScore = safeElementText(a).length * 2 + positionArea(a) / 1e10;
      const bScore = safeElementText(b).length * 2 + positionArea(b) / 1e10;
      return bScore - aScore;
    })[0];
  return { title, body, all };
}

function pageBody(plan) {
  const lines = (plan.body_lines || []).filter(Boolean).slice(0, 4);
  if (lines.length) return lines.join("\n");
  return cleanText(plan.intent?.brief || plan.title || "");
}

function titleText(plan) {
  const archetype = planArchetype(plan);
  const maxLen = {
    hero_photo_claim: 22,
    section_divider: 18,
    metric_dashboard: 24,
    evidence_wall: 26,
    campaign_timeline: 22,
    step_flow: 22,
  }[archetype] || 30;
  const text = cleanText(plan.title);
  return text.length > maxLen ? `${text.slice(0, maxLen)}...` : text;
}

function shouldWriteBody(plan) {
  return ["strategy_claim_collage", "evidence_wall", "editorial_content_bridge", "video_material_board"].includes(planArchetype(plan));
}

function isTemplatePlaceholderText(text) {
  const value = cleanText(text);
  return (
    value.includes("{{") ||
    value.includes("}}") ||
    /^\{+[^{}]{1,48}\}+$/.test(value) ||
    /^请输入/.test(value)
  );
}

function planArchetype(plan) {
  return plan.visual_profile?.archetype || "editorial_content_bridge";
}

function selectedPlans(payload, maxPages, selectionMode) {
  const plans = payload.plans || [];
  if (selectionMode === "all") return plans;
  if (selectionMode === "first-pages") return plans.slice(0, maxPages);
  const seen = new Set();
  const selected = [];
  for (const plan of plans) {
    const archetype = planArchetype(plan);
    if (seen.has(archetype)) continue;
    seen.add(archetype);
    selected.push(plan);
    if (selected.length >= maxPages) break;
  }
  return selected;
}

function summarizeElement(element) {
  return element
    ? {
        name: element.name,
        type: element.type,
        visualType: element.visualType,
        text: safeElementText(element).slice(0, 100),
        position: element.position || null,
      }
    : null;
}

function scoreFallbackSlide(slideInfo, plan) {
  const elements = slideInfo.elements || [];
  const pictureCount = elements.filter((element) => element.type === "pic" || element.visualType === "picture").length;
  const textCount = elements.filter((element) => element.hasTextBody && safeElementText(element)).length;
  const archetype = planArchetype(plan);
  let score = textCount * 2 + pictureCount * 5;
  if (["hero_photo_claim", "strategy_claim_collage", "evidence_wall", "video_material_board"].includes(archetype)) score += pictureCount * 8;
  if (archetype === "metric_dashboard" && textCount >= 5) score += 12;
  if (archetype === "section_divider" && textCount <= 4) score += 8;
  return score;
}

function registryCandidateMap(registry) {
  return new Map((registry?.candidates || []).map((candidate) => [candidate.id, candidate]));
}

function rotated(items, start) {
  if (!items.length) return [];
  const offset = start % items.length;
  return [...items.slice(offset), ...items.slice(0, offset)];
}

function registryRecipe(registry, candidateMap, archetype, occurrenceIndex, usedCandidateIds) {
  const ids = registry?.by_archetype?.[archetype] || [];
  let candidate = null;
  const ordered = rotated(ids, occurrenceIndex);
  for (const id of ordered) {
    const item = candidateMap.get(id);
    if (!item) continue;
    if (item.readiness === "weak") continue;
    if (!usedCandidateIds.has(id) || ids.length === 1) {
      candidate = item;
      break;
    }
  }
  if (!candidate) {
    for (const id of ordered) {
      const item = candidateMap.get(id);
      if (!item || item.readiness === "weak") continue;
      candidate = item;
      break;
    }
  }
  if (!candidate) {
    const recipe = registry?.selected_recipes?.[archetype];
    candidate = recipe?.candidate_id ? candidateMap.get(recipe.candidate_id) : null;
  }
  if (!candidate || !candidate.file || !candidate.slide) return null;
  return {
    file: candidate.file,
    slide: candidate.slide,
    source: "registry",
    candidateId: candidate.id || "",
    readiness: candidate.readiness || "",
  };
}

function cleanedEntriesByArchetype(cleanedRegistry) {
  const result = new Map();
  for (const entry of cleanedRegistry?.entries || []) {
    for (const archetype of entry.archetypes || []) {
      if (!result.has(archetype)) result.set(archetype, []);
      result.get(archetype).push(entry);
    }
  }
  return result;
}

function cleanedEntryMetrics(entry) {
  const metrics = entry.metrics || {};
  const placeholders = entry.placeholders || {};
  return {
    pictureCount: Number(metrics.picture_count ?? placeholders.pictures?.length ?? 0) || 0,
    bigPictureCount: Number(metrics.big_picture_count ?? 0) || 0,
    fullBleedPictureCount: Number(metrics.full_bleed_picture_count ?? 0) || 0,
    writableTextCount: Number(metrics.writable_text_count ?? placeholders.text?.length ?? 0) || 0,
    textCharCount: Number(metrics.text_char_count ?? 0) || 0,
    groupCount: Number(metrics.group_count ?? 0) || 0,
    sourceScore: Number(entry.source_score ?? entry.score ?? 0) || 0,
  };
}

function cleanedEntryFitScore(entry, archetype, plan, usedSlides) {
  const metrics = cleanedEntryMetrics(entry);
  const hasCurrentAssets = planAssetSources(plan).length > 0;
  const qualityTags = new Set(entry.quality_tags || []);
  let score = 1000;
  if (!entry.archetypes?.includes(archetype)) score -= 80;
  if (usedSlides.has(String(entry.template_slide))) score -= 160;

  if (hasCurrentAssets) {
    score += metrics.sourceScore / 12;
    score += Math.min(metrics.pictureCount, 8) * 7;
    score += metrics.bigPictureCount * 6;
    score += metrics.fullBleedPictureCount * 4;
    score += Math.min(metrics.writableTextCount, 8) * 3;
    if (qualityTags.has("photo_led")) score += 18;
    if (qualityTags.has("heavy_legacy_structure")) score -= 18;
  } else {
    score += metrics.sourceScore / 40;
    score += Math.min(metrics.writableTextCount, 8) * 4;
    score -= metrics.pictureCount * 8;
    score -= metrics.bigPictureCount * 12;
    score -= metrics.fullBleedPictureCount * 18;
    score -= metrics.groupCount * 6;
    score -= Math.max(0, metrics.textCharCount - 140) * 0.22;
    if (qualityTags.has("no_asset_friendly")) score += 44;
    if (qualityTags.has("asset_sensitive")) score -= 36;
    if (qualityTags.has("heavy_legacy_structure")) score -= 44;
    if (qualityTags.has("hard_red_chrome")) score -= 260;
    if (qualityTags.has("black_red_commercial_shell")) score -= 90;
    if (qualityTags.has("dark_ui_theme")) score -= 30;
    if (qualityTags.has("automizer_copy_unsafe")) score -= 420;
    if (["metric_dashboard", "step_flow", "campaign_timeline"].includes(archetype)) {
      score -= metrics.fullBleedPictureCount * 18;
      score -= Math.max(0, metrics.pictureCount - 4) * 6;
    }
    if (["hero_photo_claim", "section_divider"].includes(archetype)) {
      score -= Math.max(0, metrics.pictureCount - 4) * 8;
    }
  }
  return Math.round(score * 10) / 10;
}

function cleanedRecipe(cleanedByArchetype, archetype, plan, occurrenceIndex, usedSlides) {
  const entries = cleanedByArchetype.get(archetype) || [];
  if (!entries.length) return null;
  const ranked = rotated(entries, occurrenceIndex)
    .map((entry) => ({ entry, fitScore: cleanedEntryFitScore(entry, archetype, plan, usedSlides) }))
    .sort((a, b) => b.fitScore - a.fitScore);
  const bestUsed = ranked.find(({ entry }) => usedSlides.has(String(entry.template_slide)));
  const bestUnused = ranked.find(({ entry }) => !usedSlides.has(String(entry.template_slide)));
  const selected =
    entries.length === 1
      ? ranked[0]
      : bestUsed && (!bestUnused || bestUsed.fitScore - bestUnused.fitScore >= 60)
        ? bestUsed
        : bestUnused || ranked[0];
  if (!selected?.entry?.template_slide) return null;
  return {
    file: CLEANED_TEMPLATE_KEY,
    slide: selected.entry.template_slide,
    source: "cleaned-library",
    candidateId: selected.entry.source_candidate_id || "",
    readiness: selected.entry.readiness || "cleaned_named_placeholders",
    cleanedEntry: selected.entry,
    fitScore: selected.fitScore,
  };
}

function findSlide(infosByFile, recipe, plan) {
  if (recipe && infosByFile.has(recipe.file)) {
    const exact = infosByFile.get(recipe.file).slides.find((slide) => slide.number === recipe.slide);
    if (exact) {
      return {
        file: recipe.file,
        alias: infosByFile.get(recipe.file).alias,
        slide: exact,
        source: recipe.source || "recipe",
        candidateId: recipe.candidateId || "",
        readiness: recipe.readiness || "",
        cleanedEntry: recipe.cleanedEntry || null,
        fitScore: recipe.fitScore ?? null,
      };
    }
  }
  let best = null;
  for (const [file, info] of infosByFile.entries()) {
    for (const slide of info.slides) {
      const score = scoreFallbackSlide(slide, plan);
      if (!best || score > best.score) best = { file, alias: info.alias, slide, score, source: "fallback" };
    }
  }
  return best;
}

function selectNamedTargets(slideInfo) {
  const all = (slideInfo.elements || []).filter(isTextCandidate);
  const title = all.find((element) => element.name === "title");
  const body = all.find((element) => element.name === "body");
  return { title, body, all };
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function parsePresentationSlideTargets(presentationXml, relsXml) {
  const rels = new Map();
  const attr = (tag, name) => {
    const match = new RegExp(`${name}="([^"]+)"`).exec(tag);
    return match ? match[1] : "";
  };
  const relRe = /<Relationship\b[^>]*>/g;
  let relMatch;
  while ((relMatch = relRe.exec(relsXml))) {
    const tag = relMatch[0];
    const id = attr(tag, "Id");
    const target = attr(tag, "Target").replace(/^\.\.\//, "");
    if (id && target) rels.set(id, target);
  }
  const targets = [];
  const slideRe = /<p:sldId\b[^>]*>/g;
  let slideMatch;
  while ((slideMatch = slideRe.exec(presentationXml))) {
    const target = rels.get(attr(slideMatch[0], "r:id"));
    if (target && target.startsWith("slides/")) targets.push(`ppt/${target}`);
  }
  return targets;
}

function slideRelsPath(slidePath) {
  return `ppt/slides/_rels/${path.basename(slidePath)}.rels`;
}

function normalizeImageExtension(value) {
  const raw = String(value || "").toLowerCase().replace(/^\./, "");
  if (raw === "jpeg" || raw === "jpg") return "jpg";
  if (raw === "png") return "png";
  if (raw === "webp") return "webp";
  return "png";
}

function imageContentType(ext) {
  return {
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    webp: "image/webp",
  }[ext] || "image/png";
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(buffer) {
  let c = 0xffffffff;
  for (const byte of buffer) {
    c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBuffer = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
  return Buffer.concat([length, typeBuffer, data, crc]);
}

function parseHexColor(value, fallback) {
  const raw = String(value || "").trim().replace(/^#/, "");
  const hex = /^[0-9a-fA-F]{6}$/.test(raw) ? raw : String(fallback || "f8fbff").replace(/^#/, "");
  return [
    Number.parseInt(hex.slice(0, 2), 16),
    Number.parseInt(hex.slice(2, 4), 16),
    Number.parseInt(hex.slice(4, 6), 16),
  ];
}

function mixColor(a, b, t) {
  return [
    Math.round(a[0] * (1 - t) + b[0] * t),
    Math.round(a[1] * (1 - t) + b[1] * t),
    Math.round(a[2] * (1 - t) + b[2] * t),
  ];
}

function hashString(value) {
  let hash = 2166136261;
  for (const char of String(value || "")) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function encodePngRgba(width, height, paint) {
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y += 1) {
    const rowStart = y * (width * 4 + 1);
    raw[rowStart] = 0;
    for (let x = 0; x < width; x += 1) {
      const [r, g, b, a = 255] = paint(x, y, width, height);
      const idx = rowStart + 1 + x * 4;
      raw[idx] = r;
      raw[idx + 1] = g;
      raw[idx + 2] = b;
      raw[idx + 3] = a;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", zlib.deflateSync(raw, { level: 7 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function slideColorProfile(slideXml) {
  const profile = {
    colorCount: 0,
    redCount: 0,
    brightCount: 0,
    darkCount: 0,
    blackCount: 0,
    whiteCount: 0,
  };
  for (const match of slideXml.matchAll(/<a:srgbClr\b[^>]*\bval="([0-9A-Fa-f]{6})"/g)) {
    const value = match[1].toUpperCase();
    const r = Number.parseInt(value.slice(0, 2), 16);
    const g = Number.parseInt(value.slice(2, 4), 16);
    const b = Number.parseInt(value.slice(4, 6), 16);
    const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    profile.colorCount += 1;
    if (r >= 190 && g <= 90 && b <= 100) profile.redCount += 1;
    if (luminance >= 220) profile.brightCount += 1;
    if (luminance <= 70) profile.darkCount += 1;
    if (value === "000000") profile.blackCount += 1;
    if (value === "FFFFFF") profile.whiteCount += 1;
  }
  return profile;
}

function placeholderToneForSlide(slideXml) {
  const profile = slideColorProfile(slideXml);
  if (profile.brightCount >= 6 && (profile.blackCount >= 2 || profile.darkCount >= 8 || profile.redCount >= 10)) {
    return { tone: "dark", profile };
  }
  if (profile.whiteCount >= 4 && profile.redCount >= 8) return { tone: "dark", profile };
  return { tone: "light", profile };
}

function generatedPlaceholderAsset(plan, placeholderIdx, tone = "light") {
  const tokens = plan.style_tokens || {};
  const visual = plan.visual_profile || {};
  const archetype = planArchetype(plan);
  const seed = hashString(`${plan.title || ""}|${archetype}|${placeholderIdx}`);
  const paper = tone === "dark" ? parseHexColor("#141820", "#141820") : parseHexColor(tokens.paper, "#F8FBFF");
  const soft = tone === "dark" ? parseHexColor("#263142", "#263142") : parseHexColor(tokens.soft, "#D7ECF5");
  const accent = parseHexColor(tokens.accent, tone === "dark" ? "#FF405A" : "#1B75D0");
  const warm = tone === "dark"
    ? parseHexColor("#3E2831", "#3E2831")
    : archetype.includes("evidence") || archetype.includes("video") || archetype.includes("claim")
      ? parseHexColor("#FFE4D6", "#FFE4D6")
      : parseHexColor("#FFFFFF", "#FFFFFF");
  const width = 960;
  const height = 540;
  const cx1 = 0.18 + ((seed & 0xff) / 255) * 0.22;
  const cy1 = 0.18 + (((seed >>> 8) & 0xff) / 255) * 0.24;
  const cx2 = 0.72 + (((seed >>> 16) & 0xff) / 255) * 0.18;
  const cy2 = 0.62 + (((seed >>> 24) & 0xff) / 255) * 0.22;
  const buffer = encodePngRgba(width, height, (x, y, w, h) => {
    const nx = x / Math.max(1, w - 1);
    const ny = y / Math.max(1, h - 1);
    let base = mixColor(paper, soft, Math.min(1, nx * 0.38 + ny * 0.28));
    const d1 = Math.hypot(nx - cx1, ny - cy1);
    const d2 = Math.hypot(nx - cx2, ny - cy2);
    const glow1 = Math.max(0, 1 - d1 / 0.44);
    const glow2 = Math.max(0, 1 - d2 / 0.36);
    base = mixColor(base, warm, glow1 * 0.42);
    base = mixColor(base, accent, glow2 * 0.22);
    const line = Math.sin((nx * 3.2 + ny * 4.6 + (seed % 17)) * Math.PI);
    const veil = line > 0.86 ? 0.08 : 0;
    base = mixColor(base, [255, 255, 255], veil);
    const grain = (((x * 73856093) ^ (y * 19349663) ^ seed) & 0xff) / 255;
    const g = (grain - 0.5) * 5;
    return [
      Math.max(0, Math.min(255, base[0] + g)),
      Math.max(0, Math.min(255, base[1] + g)),
      Math.max(0, Math.min(255, base[2] + g)),
      255,
    ];
  });
  return {
    source: "generated_current_page_placeholder",
    tone,
    ext: "png",
    buffer,
  };
}

function ensureContentType(zip, ext) {
  const file = zip.file("[Content_Types].xml");
  if (!file) return Promise.resolve();
  return file.async("string").then((xml) => {
    if (new RegExp(`<Default\\b[^>]*\\bExtension="${escapeRegExp(ext)}"`).test(xml)) return;
    const entry = `<Default Extension="${ext}" ContentType="${imageContentType(ext)}"/>`;
    zip.file("[Content_Types].xml", xml.replace("</Types>", `${entry}</Types>`));
  });
}

function localPathForAssetSource(source) {
  const value = String(source || "").trim();
  if (!value || value.startsWith("data:")) return null;
  let pathname = value;
  try {
    const parsed = new URL(value);
    pathname = parsed.pathname;
  } catch {
    pathname = value;
  }
  if (pathname.startsWith("/api/generated/")) {
    return path.join(ROOT, "web_ui/static/generated", pathname.slice("/api/generated/".length));
  }
  if (pathname.startsWith("/static/")) {
    return path.join(ROOT, "web_ui/static", pathname.slice("/static/".length));
  }
  if (path.isAbsolute(pathname)) return pathname;
  const candidates = [
    path.resolve(ROOT, pathname),
    path.resolve(ROOT, "web_ui/static", pathname),
    path.resolve(ROOT, "web_ui/static/generated", pathname),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function readAssetSource(source) {
  const value = String(source || "").trim();
  const dataMatch = /^data:image\/([a-zA-Z0-9.+-]+);base64,(.+)$/s.exec(value);
  if (dataMatch) {
    const ext = normalizeImageExtension(dataMatch[1]);
    return {
      source: value.slice(0, 80),
      ext,
      buffer: Buffer.from(dataMatch[2], "base64"),
    };
  }
  const localPath = localPathForAssetSource(value);
  if (localPath && fs.existsSync(localPath)) {
    const ext = normalizeImageExtension(path.extname(localPath));
    return {
      source: value,
      ext,
      buffer: fs.readFileSync(localPath),
    };
  }
  return null;
}

function planAssetSources(plan) {
  return [
    ...(plan.background_sources || []),
    ...(plan.image_sources || []),
  ].filter(Boolean);
}

function pictureRelationIdsByName(slideXml, placeholderName) {
  const ids = [];
  for (const entry of pictureRelationEntries(slideXml)) {
    if (entry.name === placeholderName) ids.push(entry.relId);
  }
  return ids;
}

function pictureRelationEntries(slideXml) {
  const entries = [];
  const picRe = /<p:pic\b[\s\S]*?<\/p:pic>/g;
  let match;
  while ((match = picRe.exec(slideXml))) {
    const block = match[0];
    const nameMatch = /<p:cNvPr\b[^>]*\bname="([^"]+)"/.exec(block);
    const relMatch = /<a:blip\b[^>]*(?:r:embed|r:link)="([^"]+)"/.exec(block);
    if (relMatch) entries.push({ name: nameMatch ? nameMatch[1] : "", relId: relMatch[1] });
  }
  return entries;
}

function replaceRelationshipTarget(relsXml, relId, target) {
  const relRe = new RegExp(`<Relationship\\b(?=[^>]*\\bId="${escapeRegExp(relId)}")[^>]*>`, "g");
  return relsXml.replace(relRe, (tag) => {
    let updated = tag.replace(/\sTarget="[^"]*"/, ` Target="${target}"`);
    updated = updated.replace(/\sTargetMode="External"/, "");
    return updated;
  });
}

async function replaceNamedPicturePlaceholders(pptxPath, selected, warnings) {
  const raw = fs.readFileSync(pptxPath);
  const zip = await JSZip.loadAsync(raw);
  const presentationXml = await zip.file("ppt/presentation.xml").async("string");
  const relsXml = await zip.file("ppt/_rels/presentation.xml.rels").async("string");
  const slideTargets = parsePresentationSlideTargets(presentationXml, relsXml);
  const reports = [];

  for (const [idx, item] of selected.entries()) {
    const slidePath = slideTargets[idx];
    const placeholders = item.match.cleanedEntry?.placeholders?.pictures || [];
    const assetSources = planAssetSources(item.plan);
    const currentAssets = assetSources.map(readAssetSource).filter(Boolean);
    const report = {
      slidePath,
      placeholderCount: placeholders.length,
      currentAssetCount: currentAssets.length,
      generatedFallbackAssetCount: 0,
      generatedFallbackTone: "",
      assetCount: 0,
      replacements: 0,
      extraPictureReplacements: 0,
      replacedPictureNames: [],
      skipped: "",
    };
    if (!slidePath) {
      report.skipped = "slide_path_missing";
      reports.push(report);
      continue;
    }
    const slideFile = zip.file(slidePath);
    const relFile = zip.file(slideRelsPath(slidePath));
    if (!slideFile || !relFile) {
      report.skipped = "slide_or_relationship_file_missing";
      reports.push(report);
      continue;
    }
    const slideXml = await slideFile.async("string");
    const allPictureEntries = pictureRelationEntries(slideXml);
    const fallbackTone = placeholderToneForSlide(slideXml);
    const fallbackAssetCount = Math.max(placeholders.length, allPictureEntries.length, 1);
    const loadedAssets = currentAssets.length
      ? currentAssets
      : Array.from({ length: fallbackAssetCount }, (_, placeholderIdx) =>
          generatedPlaceholderAsset(item.plan, placeholderIdx, fallbackTone.tone),
        );
    report.generatedFallbackAssetCount = currentAssets.length ? 0 : loadedAssets.length;
    report.generatedFallbackTone = currentAssets.length ? "" : fallbackTone.tone;
    report.generatedFallbackColorProfile = currentAssets.length ? null : fallbackTone.profile;
    report.assetCount = loadedAssets.length;
    if (!placeholders.length && !allPictureEntries.length) {
      report.skipped = "no_picture_relationships";
      reports.push(report);
      continue;
    }
    let slideRelsXml = await relFile.async("string");
    const mediaNames = [];
    for (const [assetIdx, asset] of loadedAssets.entries()) {
      const prefix = asset.source === "generated_current_page_placeholder" ? "stylemind_generated_placeholder" : "stylemind_page_asset";
      const mediaName = `${prefix}_${idx + 1}_${assetIdx + 1}.${asset.ext}`;
      mediaNames.push(mediaName);
      zip.file(`ppt/media/${mediaName}`, asset.buffer);
      await ensureContentType(zip, asset.ext);
    }

    const replacedRelIds = new Set();
    for (const [placeholderIdx, placeholderName] of placeholders.entries()) {
      const relIds = pictureRelationIdsByName(slideXml, placeholderName);
      if (!relIds.length) continue;
      const mediaName = mediaNames[placeholderIdx % mediaNames.length];
      for (const relId of relIds) {
        slideRelsXml = replaceRelationshipTarget(slideRelsXml, relId, `../media/${mediaName}`);
        report.replacements += 1;
        replacedRelIds.add(relId);
      }
      report.replacedPictureNames.push(placeholderName);
    }
    for (const [pictureIdx, entry] of allPictureEntries.entries()) {
      if (replacedRelIds.has(entry.relId)) continue;
      const mediaName = mediaNames[pictureIdx % mediaNames.length];
      slideRelsXml = replaceRelationshipTarget(slideRelsXml, entry.relId, `../media/${mediaName}`);
      report.replacements += 1;
      report.extraPictureReplacements += 1;
      replacedRelIds.add(entry.relId);
      if (entry.name) report.replacedPictureNames.push(entry.name);
    }
    zip.file(slideRelsPath(slidePath), slideRelsXml);
    reports.push(report);
    if (!report.replacements) warnings.push(`No picture relationships replaced for ${slidePath}`);
  }

  const updated = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
  fs.writeFileSync(pptxPath, updated);
  return reports;
}

async function loadTemplateInfos(automizer, manifest) {
  const pptxEntries = (manifest.entries || []).filter((entry) => entry.kind === "pptx");
  const infosByFile = new Map();
  const info = await automizer.getInfo();
  pptxEntries.forEach((entry, idx) => {
    const alias = `tpl${idx}`;
    infosByFile.set(entry.file, {
      alias,
      slides: info.slidesByTemplate(alias),
      entry,
    });
  });
  try {
    const cleanedSlides = info.slidesByTemplate("cleaned");
    if (cleanedSlides && cleanedSlides.length) {
      infosByFile.set(CLEANED_TEMPLATE_KEY, {
        alias: "cleaned",
        slides: cleanedSlides,
        entry: { file: CLEANED_TEMPLATE_KEY, kind: "pptx" },
      });
    }
  } catch {
    // Cleaned template library is optional.
  }
  return infosByFile;
}

async function main() {
  const input = path.resolve(argValue("--input", DEFAULT_INPUT));
  const output = path.resolve(argValue("--output", DEFAULT_OUTPUT));
  const reportPath = path.resolve(argValue("--report", DEFAULT_REPORT));
  const registryPath = path.resolve(argValue("--template-registry", DEFAULT_TEMPLATE_REGISTRY));
  const cleanedRegistryPath = path.resolve(argValue("--cleaned-registry", DEFAULT_CLEANED_REGISTRY));
  const maxPages = Math.max(1, Number(argValue("--max-pages", "9")) || 9);
  const selectionMode = hasFlag("--all-pages")
    ? "all"
    : hasFlag("--first-pages")
      ? "first-pages"
      : "one-per-archetype";
  const useRegistry = !hasFlag("--no-template-registry") && fs.existsSync(registryPath);
  const useCleanedLibrary = !hasFlag("--no-cleaned-library") && fs.existsSync(cleanedRegistryPath);

  if (!fs.existsSync(input)) throw new Error(`RenderPlan input not found: ${input}`);
  if (!fs.existsSync(MANIFEST)) throw new Error(`reference manifest not found: ${MANIFEST}`);

  const payload = readJson(input);
  if (payload.schema !== "stylemind.render_plan.v1") throw new Error(`Unsupported schema: ${payload.schema}`);
  const manifest = readJson(MANIFEST);
  const templateRegistry = useRegistry ? readJson(registryPath) : null;
  const cleanedRegistry = useCleanedLibrary ? readJson(cleanedRegistryPath) : null;
  const pptxEntries = (manifest.entries || []).filter((entry) => entry.kind === "pptx");
  if (!pptxEntries.length) throw new Error("No editable PPTX entries in reference manifest");

  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  const outputDir = path.dirname(output);
  const outputName = path.basename(output);

  const cleanedTemplatePath = cleanedRegistry?.template_file ? path.join(ROOT, cleanedRegistry.template_file) : null;
  const rootFile = cleanedTemplatePath && fs.existsSync(cleanedTemplatePath)
    ? cleanedTemplatePath
    : path.join(manifest.source_dir, pptxEntries[0].file);
  const automizer = new Automizer({
    templateDir: "/",
    outputDir,
    removeExistingSlides: true,
    autoImportSlideMasters: true,
    cleanup: false,
    compression: 0,
    verbosity: 0,
  });

  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(" "));
  try {
    automizer.loadRoot(rootFile);
    if (cleanedTemplatePath && fs.existsSync(cleanedTemplatePath)) {
      automizer.load(cleanedTemplatePath, "cleaned");
    }
    for (const [idx, entry] of pptxEntries.entries()) {
      automizer.load(path.join(manifest.source_dir, entry.file), `tpl${idx}`);
    }

    const infosByFile = await loadTemplateInfos(automizer, manifest);
    const pages = selectedPlans(payload, maxPages, selectionMode);
    const selected = [];
    const candidateMap = registryCandidateMap(templateRegistry);
    const cleanedByArchetype = cleanedEntriesByArchetype(cleanedRegistry);
    const usedRegistryCandidates = new Set();
    const usedCleanedSlides = new Set();
    const archetypeOccurrences = new Map();

    for (const plan of pages) {
      const archetype = planArchetype(plan);
      const occurrenceIndex = archetypeOccurrences.get(archetype) || 0;
      archetypeOccurrences.set(archetype, occurrenceIndex + 1);
      const match = findSlide(
        infosByFile,
        cleanedRecipe(cleanedByArchetype, archetype, plan, occurrenceIndex, usedCleanedSlides) ||
          registryRecipe(templateRegistry, candidateMap, archetype, occurrenceIndex, usedRegistryCandidates) ||
          ARCHETYPE_RECIPES[archetype],
        plan,
      );
      if (!match) throw new Error(`No template slide matched for ${archetype}`);
      if (match.source === "registry" && match.candidateId) usedRegistryCandidates.add(match.candidateId);
      if (match.source === "cleaned-library") usedCleanedSlides.add(String(match.slide.number));
      const targets = match.source === "cleaned-library" ? selectNamedTargets(match.slide) : selectTextTargets(match.slide);
      selected.push({ plan, match, targets });

      automizer.addSlide(match.alias, match.slide.number, (slide) => {
        const written = new Set();
        if (targets.title) {
          slide.modifyElement(targets.title.name, setRawText(titleText(plan)));
          written.add(targets.title.name);
        }
        if (targets.body && shouldWriteBody(plan)) {
          slide.modifyElement(targets.body.name, setRawText(pageBody(plan).slice(0, 260)));
          written.add(targets.body.name);
        }
        for (const element of targets.all) {
          if (written.has(element.name)) continue;
          const oldText = safeElementText(element);
          if (!oldText || oldText.length <= 2) continue;
          if (isTemplatePlaceholderText(oldText) || match.source !== "cleaned-library") {
            slide.modifyElement(element.name, setRawText(""));
          }
        }
      });
    }

    const summary = await automizer.write(outputName);
    const pictureReplacementReports = await replaceNamedPicturePlaceholders(output, selected, warnings);
    const report = {
      status: "ok",
      strategy: "reference_template_first",
      input,
      output,
      sourceDir: manifest.source_dir,
      selectionMode,
      templateRegistry: useRegistry ? registryPath : null,
      registryUsed: useRegistry,
      cleanedRegistry: useCleanedLibrary ? cleanedRegistryPath : null,
      cleanedLibraryUsed: useCleanedLibrary,
      pageCount: pages.length,
      writeSummary: summary,
      pictureReplacementMode: "current_page_assets_or_generated_placeholders_cycle_named_placeholders",
      pictureReplacementSummary: {
        slidesWithAssets: pictureReplacementReports.filter((item) => item.currentAssetCount > 0).length,
        slidesWithGeneratedFallbacks: pictureReplacementReports.filter((item) => item.generatedFallbackAssetCount > 0).length,
        totalReplacements: pictureReplacementReports.reduce((sum, item) => sum + item.replacements, 0),
        generatedFallbackAssets: pictureReplacementReports.reduce((sum, item) => sum + item.generatedFallbackAssetCount, 0),
      },
      warnings: warnings.slice(0, 40),
      selected: selected.map(({ plan, match, targets }, idx) => ({
        pageIndex: plan.index,
        title: plan.title,
        pageRole: plan.intent?.page_role || "",
        archetype: planArchetype(plan),
        template: match.file,
        templateAlias: match.alias,
        templateSlide: match.slide.number,
        matchSource: match.source,
        registryCandidateId: match.candidateId || "",
        templateReadiness: match.readiness || "",
        cleanedTemplateSlide: match.cleanedEntry?.template_slide || null,
        templateFitScore: match.fitScore,
        templateQualityTags: match.cleanedEntry?.quality_tags || [],
        templateMetrics: match.cleanedEntry ? cleanedEntryMetrics(match.cleanedEntry) : null,
        titleElement: summarizeElement(targets.title),
        bodyElement: summarizeElement(targets.body),
        textElementsTouched: targets.all.length,
        pictureCount: (match.slide.elements || []).filter((element) => element.type === "pic" || element.visualType === "picture").length,
        picturePlaceholders: match.cleanedEntry?.placeholders?.pictures || [],
        assetSources: planAssetSources(plan),
        pictureReplacement: pictureReplacementReports[idx],
      })),
    };
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
    console.log(JSON.stringify({ status: "ok", output, report: reportPath, pageCount: pages.length }));
  } finally {
    console.warn = originalWarn;
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
