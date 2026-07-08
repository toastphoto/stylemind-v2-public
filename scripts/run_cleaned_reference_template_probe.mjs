#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { Automizer } from "pptx-automizer";

const TEMPLATE_DIR = "reference_samples/curated_templates";
const TEMPLATE_FILE = "stylemind_cleaned_reference_templates.pptx";
const REGISTRY_FILE = "stylemind_cleaned_reference_templates_registry.json";
const OUT_DIR = ".pytest_tmp/cleaned_reference_template_probe";
const OUT_FILE = "stylemind_cleaned_reference_template_probe.pptx";
const PROBE_IMAGE = "cleaned-reference-probe-image.png";
const GREEN_PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mNk+M8ABYwCAV0BVqsAAAAASUVORK5CYII=";
const PROBE_TEXT = {
  title: "StyleMind Cleaned Reference Template",
  body: "语义占位符已替换；参考页质感保留，文字保持可编辑。",
};

function setRawText(text) {
  return (element) => {
    const textNodes = element.getElementsByTagName("a:t");
    if (!textNodes || textNodes.length === 0) {
      throw new Error("target element does not contain a:t text nodes");
    }
    for (let idx = 0; idx < textNodes.length; idx += 1) {
      textNodes.item(idx).textContent = idx === 0 ? text : "";
    }
  };
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(path.join(OUT_DIR, PROBE_IMAGE), Buffer.from(GREEN_PNG_1X1, "base64"));
  const registry = JSON.parse(fs.readFileSync(path.join(TEMPLATE_DIR, REGISTRY_FILE), "utf8"));
  const first = registry.entries?.[0];
  if (!first) throw new Error("cleaned template registry has no entries");
  const picturePlaceholder = first.placeholders?.pictures?.[0];
  if (!picturePlaceholder) throw new Error("first cleaned template entry has no picture placeholder");

  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args.join(" "));
  try {
    const automizer = new Automizer({
      templateDir: TEMPLATE_DIR,
      outputDir: OUT_DIR,
      mediaDir: OUT_DIR,
      removeExistingSlides: true,
      autoImportSlideMasters: true,
      cleanup: false,
      compression: 0,
      verbosity: 0,
    });
    const pres = automizer.loadRoot(TEMPLATE_FILE).load(TEMPLATE_FILE, "cleaned");

    const info = await pres.getInfo();
    const firstSlide = info.slideByNumber("cleaned", first.template_slide);
    const names = firstSlide.elements.map((element) => element.name);
    for (const required of ["title", "body", picturePlaceholder]) {
      if (!names.includes(required)) throw new Error(`missing cleaned placeholder: ${required}`);
    }

    pres.addSlide("cleaned", first.template_slide, (slide) => {
      slide.modifyElement("title", setRawText(PROBE_TEXT.title));
      slide.modifyElement("body", setRawText(PROBE_TEXT.body));
    });
    await pres.write(OUT_FILE);
  } finally {
    console.warn = originalWarn;
  }
  console.log(JSON.stringify({
    status: "ok",
    output: path.resolve(OUT_DIR, OUT_FILE),
    probeImage: path.resolve(OUT_DIR, PROBE_IMAGE),
    probeText: PROBE_TEXT,
    picturePlaceholder,
    templateSlide: first.template_slide,
    warnings: warnings.slice(0, 20),
  }));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
