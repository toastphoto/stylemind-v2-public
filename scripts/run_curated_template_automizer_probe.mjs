#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { Automizer, ModifyImageHelper } from "pptx-automizer";

const TEMPLATE_DIR = "reference_samples/curated_templates";
const TEMPLATE_FILE = "stylemind_named_placeholder_templates.pptx";
const OUT_DIR = ".pytest_tmp/curated_template_probe";
const OUT_FILE = "stylemind_curated_template_probe.pptx";
const PROBE_IMAGE = "curated-probe-image.png";
const PROBE_TEXT = {
  title: "StyleMind Curated Template",
  body: "命名占位符已被 Automizer 按 RenderPlan 数据替换，模板页仍保持可编辑。",
  tagline: "named placeholders / automizer ready",
};
const BLUE_PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mNk+M8AAwUBAcfCdTQAAAAASUVORK5CYII=";

function setRawText(text) {
  return (element) => {
    const textNodes = element.getElementsByTagName("a:t");
    if (!textNodes || textNodes.length === 0) {
      throw new Error("target element does not contain a:t text nodes");
    }
    for (let idx = 0; idx < textNodes.length; idx += 1) {
      const node = textNodes.item(idx);
      node.textContent = idx === 0 ? text : "";
    }
  };
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(path.join(OUT_DIR, PROBE_IMAGE), Buffer.from(BLUE_PNG_1X1, "base64"));

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

  const pres = automizer
    .loadRoot(TEMPLATE_FILE)
    .load(TEMPLATE_FILE, "curated")
    .loadMedia([PROBE_IMAGE]);

  const info = await pres.getInfo();
  const firstSlide = info.slideByNumber("curated", 1);
  const names = firstSlide.elements.map((element) => element.name);
  for (const required of ["title", "body", "tagline", "hero_image"]) {
    if (!names.includes(required)) {
      throw new Error(`missing curated placeholder: ${required}`);
    }
  }

  pres.addSlide("curated", 1, (slide) => {
    slide.modifyElement("title", setRawText(PROBE_TEXT.title));
    slide.modifyElement("body", setRawText(PROBE_TEXT.body));
    slide.modifyElement("tagline", setRawText(PROBE_TEXT.tagline));
    slide.modifyElement("hero_image", [ModifyImageHelper.setRelationTarget(PROBE_IMAGE)]);
  });

  await pres.write(OUT_FILE);
  console.log(JSON.stringify({
    status: "ok",
    output: path.resolve(OUT_DIR, OUT_FILE),
    probeImage: path.resolve(OUT_DIR, PROBE_IMAGE),
    probeText: PROBE_TEXT,
    placeholders: names,
  }));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
