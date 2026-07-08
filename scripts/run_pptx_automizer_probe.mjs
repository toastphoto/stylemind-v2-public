#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Automizer, ModifyImageHelper } from "pptx-automizer";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MANIFEST = path.join(ROOT, "reference_samples/brand_campaign_ingest/reference_manifest.json");
const OUT_DIR = path.join(ROOT, ".pytest_tmp/automizer_probe");
const PROBE_IMAGE = "automizer-probe-image.png";
const OUTPUT_NAME = "stylemind_automizer_probe.pptx";
const REPORT_NAME = "pptx_automizer_probe_report.json";

const GENERIC_NAME_RE = /^(文本框|图片|矩形|组合|object|picture|textbox|shape|freeform|placeholder)\s*\d+$/i;
const PLACEHOLDER_NAME_RE = /(title|subtitle|body|copy|text|hero|image|picture|metric|evidence|logo|placeholder|标题|副标题|正文|主图|图片占位|证据|指标)/i;
const PROBE_TEXT = "StyleMind Automizer Probe\n模板页文本已被 RenderPlan 数据替换";
const RED_PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mP8z8AARQABywH8GQAAAABJRU5ErkJggg==";

function readManifest() {
  if (!fs.existsSync(MANIFEST)) {
    throw new Error(`reference manifest not found: ${MANIFEST}`);
  }
  return JSON.parse(fs.readFileSync(MANIFEST, "utf8"));
}

function safeElementText(element) {
  try {
    return typeof element.getText === "function" ? element.getText().join(" ").trim() : "";
  } catch {
    return "";
  }
}

function summarizeElement(element) {
  return {
    name: element.name,
    type: element.type,
    visualType: element.visualType,
    creationId: element.creationId || "",
    hasTextBody: Boolean(element.hasTextBody),
    text: safeElementText(element).slice(0, 120),
  };
}

function semanticNameCount(elements) {
  return elements.filter((element) => element.name && !GENERIC_NAME_RE.test(element.name)).length;
}

function placeholderNameCount(elements) {
  return elements.filter((element) => element.name && PLACEHOLDER_NAME_RE.test(element.name) && !GENERIC_NAME_RE.test(element.name)).length;
}

function slideStats(slide) {
  const elements = slide.elements || [];
  return {
    number: slide.number,
    id: slide.id,
    elementCount: elements.length,
    textCount: elements.filter((element) => element.hasTextBody).length,
    pictureCount: elements.filter((element) => element.type === "pic" || element.visualType === "picture").length,
    creationIdCount: elements.filter((element) => element.creationId).length,
    semanticNameCount: semanticNameCount(elements),
    sampleElements: elements.slice(0, 8).map(summarizeElement),
  };
}

function templateReadiness(templateName, slides) {
  const allElements = slides.flatMap((slide) => slide.elements || []);
  const semanticNames = semanticNameCount(allElements);
  const placeholderNames = placeholderNameCount(allElements);
  const creationIds = allElements.filter((element) => element.creationId).length;
  const total = allElements.length;
  const quality = placeholderNames >= 3 || creationIds >= Math.max(4, total * 0.25) ? "candidate" : "weak";
  return {
    templateName,
    slides: slides.length,
    elements: total,
    semanticNameCount: semanticNames,
    placeholderNameCount: placeholderNames,
    creationIdCount: creationIds,
    placeholderQuality: quality,
  };
}

function chooseCandidate(templateReports) {
  const sorted = [...templateReports].sort((a, b) => {
    const score = (report) => {
      const slide = report.slides.find((item) => item.textCount > 0 && item.pictureCount > 0);
      return (slide ? 1000 : 0) - report.file.length + (report.readiness.semanticNameCount || 0);
    };
    return score(b) - score(a);
  });

  for (const report of sorted) {
    const slide = report.rawSlides.find((item) => {
      const elements = item.elements || [];
      return elements.some((element) => element.hasTextBody && element.visualType === "textBox") && elements.some((element) => element.type === "pic" || element.visualType === "picture");
    });
    if (!slide) continue;
    const textElement = slide.elements.find((element) => element.hasTextBody && element.visualType === "textBox");
    const pictureElement = slide.elements.find((element) => element.type === "pic" || element.visualType === "picture");
    if (textElement && pictureElement) {
      return { report, slide, textElement, pictureElement };
    }
  }
  return null;
}

function setRawText(text) {
  return (element) => {
    const textNodes = element.getElementsByTagName("a:t");
    if (!textNodes || textNodes.length === 0) {
      throw new Error("target element does not contain a:t text nodes");
    }
    for (let idx = 0; idx < textNodes.length; idx += 1) {
      const node = textNodes.item(idx);
      if (idx === 0) {
        node.textContent = text;
      } else {
        node.textContent = "";
      }
    }
  };
}

async function loadTemplateInfo(sourceDir, file) {
  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(" "));
  try {
    const automizer = new Automizer({
      templateDir: sourceDir,
      outputDir: OUT_DIR,
      removeExistingSlides: true,
      autoImportSlideMasters: true,
      cleanup: false,
      compression: 0,
      verbosity: 0,
    });
    const pres = automizer.loadRoot(file).load(file, "template");
    const info = await pres.getInfo();
    const rawSlides = info.slidesByTemplate("template");
    return {
      file,
      warnings,
      readiness: templateReadiness(file, rawSlides),
      slides: rawSlides.map(slideStats),
      rawSlides,
    };
  } finally {
    console.warn = originalWarn;
  }
}

async function runProbe(sourceDir, candidate) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const probeImagePath = path.join(OUT_DIR, PROBE_IMAGE);
  fs.writeFileSync(probeImagePath, Buffer.from(RED_PNG_1X1, "base64"));

  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(" "));
  try {
    const automizer = new Automizer({
      templateDir: sourceDir,
      outputDir: OUT_DIR,
      mediaDir: OUT_DIR,
      removeExistingSlides: true,
      autoImportSlideMasters: true,
      cleanup: false,
      compression: 0,
      verbosity: 0,
    });
    const pres = automizer
      .loadRoot(candidate.report.file)
      .load(candidate.report.file, "template")
      .loadMedia([PROBE_IMAGE]);

    pres.addSlide("template", candidate.slide.number, (slide) => {
      slide.modifyElement(candidate.textElement.name, setRawText(PROBE_TEXT));
      slide.modifyElement(candidate.pictureElement.name, [
        ModifyImageHelper.setRelationTarget(PROBE_IMAGE),
      ]);
    });

    const summary = await pres.write(OUTPUT_NAME);
    return {
      output: path.join(OUT_DIR, OUTPUT_NAME),
      probeImage: probeImagePath,
      probeText: PROBE_TEXT,
      writeSummary: summary,
      warnings,
    };
  } finally {
    console.warn = originalWarn;
  }
}

async function main() {
  const manifest = readManifest();
  const sourceDir = manifest.source_dir;
  const pptxEntries = (manifest.entries || []).filter((entry) => entry.kind === "pptx");
  if (!pptxEntries.length) {
    throw new Error("no PPTX entries in reference manifest");
  }

  fs.mkdirSync(OUT_DIR, { recursive: true });
  const templateReports = [];
  for (const entry of pptxEntries) {
    templateReports.push(await loadTemplateInfo(sourceDir, entry.file));
  }

  const candidate = chooseCandidate(templateReports);
  if (!candidate) {
    throw new Error("no template slide with both text and picture elements");
  }

  const probe = await runProbe(sourceDir, candidate);
  const report = {
    status: "ok",
    library: "pptx-automizer",
    libraryVersion: "0.8.2",
    sourceDir,
    outputDir: OUT_DIR,
    selected: {
      template: candidate.report.file,
      slideNumber: candidate.slide.number,
      textElement: summarizeElement(candidate.textElement),
      pictureElement: summarizeElement(candidate.pictureElement),
      placeholderQuality: candidate.report.readiness.placeholderQuality,
    },
    probe,
    templates: templateReports.map((report) => ({
      file: report.file,
      readiness: report.readiness,
      warnings: report.warnings.slice(0, 8),
      slides: report.slides.slice(0, 6),
    })),
  };

  const reportPath = path.join(OUT_DIR, REPORT_NAME);
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify({ status: "ok", report: reportPath, output: probe.output }));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
