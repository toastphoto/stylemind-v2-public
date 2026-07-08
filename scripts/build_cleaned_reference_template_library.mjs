#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Automizer } from "pptx-automizer";
import JSZip from "jszip";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_PLAN = path.join(ROOT, "reference_samples/curated_templates/reference_template_curation_plan.json");
const DEFAULT_OUTPUT = path.join(ROOT, "reference_samples/curated_templates/stylemind_cleaned_reference_templates.pptx");
const DEFAULT_REGISTRY = path.join(ROOT, "reference_samples/curated_templates/stylemind_cleaned_reference_templates_registry.json");
const KEEP_TEXT_ROLES = new Set(["title", "body"]);
const COPY_UNSAFE_CANDIDATE_IDS = new Set(["tpl2_s48"]);

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

function numberArg(name, fallback) {
  const raw = Number(argValue(name, String(fallback)));
  return Number.isFinite(raw) && raw > 0 ? raw : fallback;
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

function isWritableText(element) {
  return Boolean(
    element.hasTextBody &&
      element.type === "sp" &&
      ["textBox", "rectangle", "shape"].includes(element.visualType || "textBox"),
  );
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

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function selectedRows(plan, maxSlides) {
  return (plan.selected || [])
    .filter((row) => row.readiness !== "weak")
    .slice(0, maxSlides)
    .map((row, idx) => ({ ...row, library_slide: idx + 1 }));
}

function textTargetMap(row) {
  const map = new Map();
  for (const target of row.suggested_placeholders?.text_targets || []) {
    const role = target.suggested_role;
    if (KEEP_TEXT_ROLES.has(role) && target.name) {
      map.set(target.name, { placeholderName: role, placeholderText: `{{${role}}}` });
    } else if (target.name) {
      map.set(target.name, { placeholderName: target.suggested_placeholder_name || "optional_text", placeholderText: "" });
    }
  }
  return map;
}

function pictureTargetMap(row) {
  const map = new Map();
  for (const target of row.suggested_placeholders?.picture_targets || []) {
    if (target.name) {
      map.set(target.name, target.suggested_placeholder_name || "image");
    }
  }
  return map;
}

async function loadAutomizer(plan, outputDir) {
  const referenceManifest = readJson(path.join(ROOT, plan.source_manifest || "reference_samples/brand_campaign_ingest/reference_manifest.json"));
  const sourceDir = referenceManifest.source_dir;
  const pptxFiles = [...new Set((plan.selected || []).map((row) => row.file))];
  if (!pptxFiles.length) throw new Error("curation plan has no source PPTX files");

  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(" "));
  try {
    const automizer = new Automizer({
      templateDir: referenceManifest.source_dir,
      outputDir,
      removeExistingSlides: true,
      autoImportSlideMasters: true,
      cleanup: false,
      compression: 0,
      verbosity: 0,
    });
    automizer.loadRoot(pptxFiles[0]);
    for (const [idx, file] of pptxFiles.entries()) {
      automizer.load(file, `src${idx}`);
    }
    const info = await automizer.getInfo();
    const aliasesByFile = new Map(pptxFiles.map((file, idx) => [file, `src${idx}`]));
    return { automizer, info, aliasesByFile, warnings, sourceDir };
  } finally {
    console.warn = originalWarn;
  }
}

function findSlide(info, alias, slideNo) {
  return (info.slidesByTemplate(alias) || []).find((slide) => slide.number === slideNo);
}

function buildRenameMap(row) {
  const renames = {};
  for (const [oldName, item] of textTargetMap(row).entries()) {
    if (oldName) renames[oldName] = item.placeholderName;
  }
  for (const [oldName, placeholderName] of pictureTargetMap(row).entries()) {
    if (oldName) renames[oldName] = placeholderName;
  }
  return renames;
}

function colorProfileFromXml(xml) {
  const profile = {
    color_count: 0,
    red_count: 0,
    bright_count: 0,
    dark_count: 0,
    black_count: 0,
    white_count: 0,
  };
  for (const match of xml.matchAll(/<a:srgbClr\b[^>]*\bval="([0-9A-Fa-f]{6})"/g)) {
    const value = match[1].toUpperCase();
    const r = Number.parseInt(value.slice(0, 2), 16);
    const g = Number.parseInt(value.slice(2, 4), 16);
    const b = Number.parseInt(value.slice(4, 6), 16);
    const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    profile.color_count += 1;
    if (r >= 190 && g <= 90 && b <= 100) profile.red_count += 1;
    if (luminance >= 220) profile.bright_count += 1;
    if (luminance <= 70) profile.dark_count += 1;
    if (value === "000000") profile.black_count += 1;
    if (value === "FFFFFF") profile.white_count += 1;
  }
  return profile;
}

function templateQualityTags(metrics = {}, colorProfile = {}, candidateId = "") {
  const tags = [];
  const pictureCount = Number(metrics.picture_count || 0);
  const bigPictureCount = Number(metrics.big_picture_count || 0);
  const fullBleedPictureCount = Number(metrics.full_bleed_picture_count || 0);
  const writableTextCount = Number(metrics.writable_text_count || 0);
  const textCharCount = Number(metrics.text_char_count || 0);
  const groupCount = Number(metrics.group_count || 0);
  if (pictureCount >= 10 || fullBleedPictureCount > 0) tags.push("asset_sensitive");
  if (bigPictureCount >= 2 || fullBleedPictureCount >= 2) tags.push("photo_led");
  if (writableTextCount >= 12 || textCharCount >= 220 || groupCount >= 5) tags.push("heavy_legacy_structure");
  if (pictureCount <= 4 && textCharCount <= 180) tags.push("no_asset_friendly");
  if (Number(colorProfile.red_count || 0) >= 12 && pictureCount <= 4) tags.push("hard_red_chrome");
  if (Number(colorProfile.black_count || 0) >= 2 || Number(colorProfile.dark_count || 0) >= 8) tags.push("dark_ui_theme");
  if (Number(colorProfile.red_count || 0) >= 10 && (Number(colorProfile.black_count || 0) >= 2 || pictureCount >= 10)) {
    tags.push("black_red_commercial_shell");
  }
  if (COPY_UNSAFE_CANDIDATE_IDS.has(candidateId)) tags.push("automizer_copy_unsafe");
  return tags;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeXml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
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
  const name = path.basename(slidePath);
  return `ppt/slides/_rels/${name}.rels`;
}

function mediaTargetsFromRelsXml(relsXml) {
  const targets = [];
  const relRe = /<Relationship\b[^>]*>/g;
  const attr = (tag, name) => {
    const match = new RegExp(`${name}="([^"]+)"`).exec(tag);
    return match ? match[1] : "";
  };
  let relMatch;
  while ((relMatch = relRe.exec(relsXml))) {
    const target = attr(relMatch[0], "Target");
    if (target.startsWith("../media/")) targets.push(target);
  }
  return targets;
}

async function repairMissingSlideMedia(zip, slidePath, row, sourceDir, warnings) {
  const relPath = slideRelsPath(slidePath);
  const relFile = zip.file(relPath);
  if (!relFile || !row?.file) return;
  const sourcePath = path.join(sourceDir, row.file);
  if (!fs.existsSync(sourcePath)) {
    warnings.push(`Cannot repair media for ${slidePath}: source missing ${sourcePath}`);
    return;
  }
  const relsXml = await relFile.async("string");
  const targets = mediaTargetsFromRelsXml(relsXml);
  if (!targets.length) return;
  const sourceZip = await JSZip.loadAsync(fs.readFileSync(sourcePath));
  for (const target of targets) {
    const outputMediaPath = `ppt/${target.replace(/^\.\.\//, "")}`;
    if (zip.file(outputMediaPath)) continue;
    const sourceMedia = sourceZip.file(outputMediaPath);
    if (!sourceMedia) {
      warnings.push(`Missing media could not be repaired: ${slidePath} -> ${outputMediaPath}`);
      continue;
    }
    zip.file(outputMediaPath, await sourceMedia.async("nodebuffer"));
    warnings.push(`Repaired missing media: ${slidePath} -> ${outputMediaPath}`);
  }
}

async function renameShapeNamesAndRepairMedia(pptxPath, rows, sourceDir, warnings) {
  const raw = fs.readFileSync(pptxPath);
  const zip = await JSZip.loadAsync(raw);
  const presentationXml = await zip.file("ppt/presentation.xml").async("string");
  const relsXml = await zip.file("ppt/_rels/presentation.xml.rels").async("string");
  const slideTargets = parsePresentationSlideTargets(presentationXml, relsXml);
  const slideNumbers = [];
  const colorProfiles = [];
  for (const [idx, row] of rows.entries()) {
    const slidePath = slideTargets[idx];
    const file = slidePath ? zip.file(slidePath) : null;
    if (!file) continue;
    const numberMatch = /slide(\d+)\.xml$/.exec(slidePath);
    slideNumbers[idx] = numberMatch ? Number(numberMatch[1]) : idx + 1;
    let xml = await file.async("string");
    colorProfiles[idx] = colorProfileFromXml(xml);
    const renames = buildRenameMap(row);
    for (const [oldName, newName] of Object.entries(renames)) {
      const re = new RegExp(`(<p:cNvPr\\b[^>]*\\bname=")${escapeRegExp(escapeXml(oldName))}(")`, "g");
      xml = xml.replace(re, `$1${escapeXml(newName)}$2`);
    }
    xml = xml.replace(/<a:t>(.*?)<\/a:t>/g, (match, text) => {
      const clean = String(text || "").trim();
      return clean === "{{title}}" || clean === "{{body}}" ? match : "<a:t></a:t>";
    });
    zip.file(slidePath, xml);
    await repairMissingSlideMedia(zip, slidePath, row, sourceDir, warnings);
  }
  const updated = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
  fs.writeFileSync(pptxPath, updated);
  return { slideNumbers, colorProfiles };
}

async function main() {
  const planPath = path.resolve(argValue("--plan", DEFAULT_PLAN));
  const outputPath = path.resolve(argValue("--output", DEFAULT_OUTPUT));
  const registryPath = path.resolve(argValue("--registry", DEFAULT_REGISTRY));
  const maxSlides = numberArg("--max-slides", 20);
  if (!fs.existsSync(planPath)) throw new Error(`curation plan not found: ${planPath}`);

  const plan = readJson(planPath);
  const rows = selectedRows(plan, maxSlides);
  if (!rows.length) throw new Error("no curation rows available for cleaned template library");
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.mkdirSync(path.dirname(registryPath), { recursive: true });

  const { automizer, info, aliasesByFile, warnings, sourceDir } = await loadAutomizer(plan, path.dirname(outputPath));
  const registryEntries = [];

  for (const row of rows) {
    const alias = aliasesByFile.get(row.file);
    if (!alias) continue;
    const slideInfo = findSlide(info, alias, row.source_slide);
    if (!slideInfo) continue;
    const textTargets = textTargetMap(row);
    const sourceTextNames = new Set((slideInfo.elements || []).filter((element) => element.hasTextBody).map((element) => element.name));
    automizer.addSlide(alias, row.source_slide, (slide) => {
      for (const name of sourceTextNames) {
        const target = textTargets.get(name);
        slide.modifyElement(name, setRawText(target ? target.placeholderText : ""));
      }
    });
    registryEntries.push({
      deck_order: registryEntries.length + 1,
      template_slide: registryEntries.length + 1,
      source_candidate_id: row.candidate_id,
      source_file: row.file,
      source_slide: row.source_slide,
      archetypes: row.archetypes,
      readiness: "cleaned_named_placeholders",
      original_readiness: row.readiness,
      source_score: row.score || 0,
      metrics: row.metrics || {},
      quality_tags: templateQualityTags(row.metrics || {}, {}, row.candidate_id),
      placeholders: {
        text: [...textTargets.values()].map((item) => item.placeholderName),
        pictures: [...pictureTargetMap(row).values()],
      },
      production_notes: [
        "Editable text has been replaced with placeholders or cleared.",
        "Picture placeholder names are OOXML shape names; images are still inherited from the reference slide.",
        "Baked text inside images or grouped artwork may remain and must be visually reviewed.",
      ],
    });
  }

  if (!registryEntries.length) throw new Error("no slides were added to cleaned template library");
  await automizer.write(path.basename(outputPath));
  const { slideNumbers, colorProfiles } = await renameShapeNamesAndRepairMedia(
    outputPath,
    rows.slice(0, registryEntries.length),
    sourceDir,
    warnings,
  );
  registryEntries.forEach((entry, idx) => {
    if (slideNumbers[idx]) entry.template_slide = slideNumbers[idx];
    entry.color_profile = colorProfiles[idx] || {};
    entry.quality_tags = templateQualityTags(entry.metrics || {}, entry.color_profile, entry.source_candidate_id);
  });

  const registry = {
    schema: "stylemind.cleaned_reference_template_library.v1",
    generated_by: "scripts/build_cleaned_reference_template_library.mjs",
    source_plan: path.relative(ROOT, planPath),
    template_file: path.relative(ROOT, outputPath),
    generated_at: new Date().toISOString(),
    production_safe: false,
    entry_count: registryEntries.length,
    warnings: warnings.slice(0, 80),
    entries: registryEntries,
  };
  fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2), "utf8");
  console.log(JSON.stringify({ status: "ok", output: outputPath, registry: registryPath, slides: registryEntries.length }));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
