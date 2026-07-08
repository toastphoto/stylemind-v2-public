#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import PptxGenJS from "pptxgenjs";

const SLIDE_W = 13.333;
const SLIDE_H = 7.5;
const PNG_1X1 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO9WZ0kAAAAASUVORK5CYII=";
const OUT_DIR = "reference_samples/curated_templates";
const OUT_FILE = path.join(OUT_DIR, "stylemind_named_placeholder_templates.pptx");

function addRect(slide, box, fill, line = fill, transparency = 0, objectName = undefined) {
  const [x, y, w, h] = box;
  slide.addShape("rect", {
    x, y, w, h,
    objectName,
    fill: { color: fill, transparency },
    line: { color: line, transparency: line ? 0 : 100 },
  });
}

function addText(slide, text, box, opts = {}) {
  const [x, y, w, h] = box;
  slide.addText(text, {
    x, y, w, h,
    objectName: opts.objectName,
    fontFace: opts.fontFace || "Microsoft YaHei",
    fontSize: opts.fontSize || 16,
    bold: Boolean(opts.bold),
    color: opts.color || "111827",
    margin: opts.margin ?? 0.08,
    fit: "shrink",
    valign: opts.valign || "top",
    align: opts.align || "left",
    fill: opts.fill ? { color: opts.fill, transparency: opts.fillTransparency ?? 0 } : undefined,
    line: opts.line ? { color: opts.line } : { transparency: 100 },
  });
}

function addImagePlaceholder(slide, box, name, label, accent) {
  const [x, y, w, h] = box;
  slide.addImage({ data: PNG_1X1, x, y, w, h, transparency: 100, objectName: name, altText: name });
  addRect(slide, box, "EDF2F7", accent, 0, `${name}_frame`);
  slide.addShape("line", { x, y, w, h, line: { color: "CBD5E1", width: 1 } });
  slide.addShape("line", { x, y: y + h, w, h: -h, line: { color: "CBD5E1", width: 1 } });
  addText(slide, label, [x + 0.18, y + 0.16, w - 0.36, 0.36], {
    objectName: `${name}_label`,
    fontSize: 11,
    bold: true,
    color: accent,
  });
}

function addTemplateNotes(slide, archetype, placeholders) {
  if (typeof slide.addNotes === "function") {
    slide.addNotes([
      `StyleMind curated template: ${archetype}`,
      `Placeholders: ${placeholders.join(", ")}`,
      "Used by pptx-automizer only after placeholder audit.",
    ].join("\n"));
  }
}

function addHeroTemplate(pptx) {
  const slide = pptx.addSlide();
  addRect(slide, [0, 0, SLIDE_W, SLIDE_H], "F8E7EB", "F8E7EB");
  addRect(slide, [0, 0, 0.18, SLIDE_H], "E11D48", "E11D48");
  addRect(slide, [7.0, 0.62, 5.62, 5.88], "F9C8D2", "E11D48", 0, "hero_background_panel");
  addImagePlaceholder(slide, [7.32, 0.96, 4.96, 4.92], "hero_image", "hero_image", "E11D48");
  addText(slide, "{{title}}", [0.82, 0.9, 5.8, 1.4], { objectName: "title", fontSize: 38, bold: true, color: "111827" });
  addText(slide, "{{body}}", [0.92, 2.62, 5.42, 2.08], { objectName: "body", fontSize: 17, color: "374151" });
  addText(slide, "{{tagline}}", [0.94, 5.9, 4.62, 0.52], { objectName: "tagline", fontSize: 15, bold: true, color: "E11D48", fill: "FFFFFF" });
  addTemplateNotes(slide, "hero_photo_claim", ["title", "body", "tagline", "hero_image"]);
}

function addMetricTemplate(pptx) {
  const slide = pptx.addSlide();
  addRect(slide, [0, 0, SLIDE_W, SLIDE_H], "F5FBFE", "F5FBFE");
  addRect(slide, [0, 0, 0.18, SLIDE_H], "0891B2", "0891B2");
  addText(slide, "{{title}}", [0.76, 0.54, 8.4, 0.82], { objectName: "title", fontSize: 28, bold: true, color: "0F172A" });
  addText(slide, "{{body}}", [0.96, 5.72, 10.8, 0.74], { objectName: "body", fontSize: 13, color: "334155" });
  [
    ["metric_1", 0.96],
    ["metric_2", 4.08],
    ["metric_3", 7.2],
    ["metric_4", 10.32],
  ].forEach(([name, x], idx) => {
    const w = idx === 3 ? 1.76 : 2.78;
    addRect(slide, [x, 1.66, w, 2.86], "FFFFFF", "0891B2", 0, `${name}_card`);
    addText(slide, `{{${name}_label}}`, [x + 0.18, 1.9, w - 0.36, 0.36], { objectName: `${name}_label`, fontSize: 11, bold: true, color: "475569" });
    addText(slide, `{{${name}_value}}`, [x + 0.18, 2.48, w - 0.36, 1.2], { objectName: `${name}_value`, fontSize: idx === 3 ? 24 : 34, bold: true, color: "0891B2" });
  });
  addTemplateNotes(slide, "metric_dashboard", ["title", "body", "metric_1_label", "metric_1_value", "metric_2_label", "metric_2_value", "metric_3_label", "metric_3_value", "metric_4_label", "metric_4_value"]);
}

function addEvidenceTemplate(pptx) {
  const slide = pptx.addSlide();
  addRect(slide, [0, 0, SLIDE_W, SLIDE_H], "F8FAFC", "F8FAFC");
  addRect(slide, [0, 0, 0.18, SLIDE_H], "2563EB", "2563EB");
  addText(slide, "{{title}}", [0.76, 0.54, 8.0, 0.84], { objectName: "title", fontSize: 28, bold: true, color: "0F172A" });
  addText(slide, "{{body}}", [7.06, 1.6, 4.78, 4.22], { objectName: "body", fontSize: 13, color: "334155" });
  [
    ["evidence_image_1", 0.84, 1.36],
    ["evidence_image_2", 3.78, 1.36],
    ["evidence_image_3", 0.84, 3.74],
    ["evidence_image_4", 3.78, 3.74],
  ].forEach(([name, x, y]) => addImagePlaceholder(slide, [x, y, 2.54, 1.88], name, name, "2563EB"));
  addTemplateNotes(slide, "evidence_wall", ["title", "body", "evidence_image_1", "evidence_image_2", "evidence_image_3", "evidence_image_4"]);
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const pptx = new PptxGenJS();
  pptx.author = "StyleMind";
  pptx.subject = "Curated named placeholder templates for pptx-automizer";
  pptx.company = "StyleMind";
  pptx.lang = "zh-CN";
  pptx.defineLayout({ name: "STYLEMIND_WIDE", width: SLIDE_W, height: SLIDE_H });
  pptx.layout = "STYLEMIND_WIDE";
  pptx.theme = {
    headFontFace: "Microsoft YaHei",
    bodyFontFace: "Microsoft YaHei",
    lang: "zh-CN",
  };
  addHeroTemplate(pptx);
  addMetricTemplate(pptx);
  addEvidenceTemplate(pptx);
  await pptx.writeFile({ fileName: OUT_FILE });
  console.log(JSON.stringify({ status: "ok", output: path.resolve(OUT_FILE), slides: 3 }));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
