#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import PptxGenJS from "pptxgenjs";

const SLIDE_W = 13.333;
const SLIDE_H = 7.5;
const PNG_1X1 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO9WZ0kAAAAASUVORK5CYII=";

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return fallback;
}

function hex(color, fallback = "1E293B") {
  const raw = String(color || fallback).trim().replace(/^#/, "");
  return /^[0-9a-fA-F]{6}$/.test(raw) ? raw.toUpperCase() : fallback;
}

function mixHex(color, amount = 0.82) {
  const raw = hex(color);
  const channels = [raw.slice(0, 2), raw.slice(2, 4), raw.slice(4, 6)].map((part) => parseInt(part, 16));
  return channels.map((channel) => Math.round(channel + (255 - channel) * amount).toString(16).padStart(2, "0")).join("").toUpperCase();
}

function darkenHex(color, amount = 0.28) {
  const raw = hex(color);
  const channels = [raw.slice(0, 2), raw.slice(2, 4), raw.slice(4, 6)].map((part) => parseInt(part, 16));
  return channels.map((channel) => Math.max(0, Math.round(channel * (1 - amount))).toString(16).padStart(2, "0")).join("").toUpperCase();
}

function escapeXml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function svgDataUri(svg) {
  return `data:image/svg+xml;base64,${Buffer.from(svg, "utf8").toString("base64")}`;
}

function fontFace(plan, role = "body") {
  const profile = plan.intent?.font_profile || {};
  if (role === "title") return profile.title_font || profile.east_asian_font || profile.body_font || "Microsoft YaHei";
  return profile.body_font || profile.east_asian_font || "Microsoft YaHei";
}

function addText(slide, text, box, opts = {}) {
  const [x, y, w, h] = box;
  slide.addText(String(text || ""), {
    x, y, w, h,
    margin: 0.08,
    fit: "shrink",
    valign: "top",
    breakLine: false,
    fontFace: opts.fontFace || "Microsoft YaHei",
    fontSize: opts.fontSize || 14,
    bold: Boolean(opts.bold),
    color: hex(opts.color || "1E293B"),
    align: opts.align || "left",
    transparency: opts.transparency,
    hyperlink: opts.hyperlink ? { url: opts.hyperlink } : undefined,
  });
}

function addRect(slide, box, opts = {}) {
  const [x, y, w, h] = box;
  slide.addShape("rect", {
    x, y, w, h,
    fill: { color: hex(opts.fill || "FFFFFF"), transparency: opts.transparency ?? 0 },
    line: { color: hex(opts.line || opts.fill || "FFFFFF"), transparency: opts.lineTransparency ?? 0 },
    radius: opts.radius || 0,
    shadow: opts.shadow,
  });
}

function addEllipse(slide, box, opts = {}) {
  const [x, y, w, h] = box;
  slide.addShape("ellipse", {
    x, y, w, h,
    fill: { color: hex(opts.fill || "FFFFFF"), transparency: opts.transparency ?? 0 },
    line: { color: hex(opts.line || opts.fill || "FFFFFF"), transparency: opts.lineTransparency ?? 0 },
  });
}

function addLine(slide, x1, y1, x2, y2, color, opts = {}) {
  slide.addShape("line", {
    x: x1,
    y: y1,
    w: x2 - x1,
    h: y2 - y1,
    line: { color: hex(color), width: opts.width || 1.1, transparency: opts.transparency ?? 0 },
  });
}

function archetype(plan) {
  return plan.visual_profile?.archetype || "";
}

function componentSpec(plan) {
  return plan?.component_spec && typeof plan.component_spec === "object" ? plan.component_spec : {};
}

function renderHint(plan, key, fallback = true) {
  const hints = componentSpec(plan).render_hints;
  if (!hints || typeof hints !== "object") return fallback;
  return Object.prototype.hasOwnProperty.call(hints, key) ? hints[key] : fallback;
}

function textLines(plan, limit = 4) {
  return (plan.body_lines || []).filter(Boolean).slice(0, limit).join("\n");
}

function isDarkPoster(plan) {
  const id = plan.visual_profile?.reference_style_id || "";
  const type = archetype(plan);
  return id === "evidence_wall" || ["hero_photo_claim", "section_divider", "video_material_board"].includes(type);
}

function campaignTone(plan) {
  const type = archetype(plan);
  const id = plan.visual_profile?.reference_style_id || "";
  const accent = hex(plan.accent || "2563EB");
  if (id === "summer_home_campaign") {
    return {
      deep: "0A3552",
      mid: "1B75D0",
      soft: "CFEAF7",
      warm: "F7C9C4",
      paper: "F8FBFF",
      imageA: "BFE9F5",
      imageB: "2E86C1",
      imageC: "F5B7A6",
    };
  }
  if (id === "evidence_wall" || type === "evidence_wall") {
    return {
      deep: "4A1110",
      mid: "D7332F",
      soft: "F2E6D8",
      warm: "F6B66A",
      paper: "FAF7F1",
      imageA: "F6D5B8",
      imageB: "AC2D2A",
      imageC: "36100F",
    };
  }
  if (id === "city_travel_photo") {
    return {
      deep: "123C35",
      mid: "2F6B4F",
      soft: "DCE8D8",
      warm: "EFCB86",
      paper: "F2F6F2",
      imageA: "D6E7D2",
      imageB: "42866B",
      imageC: "F1C784",
    };
  }
  if (id === "xhs_lifestyle_grid" || id === "ip_sticker_system") {
    return {
      deep: "671626",
      mid: "EF6F83",
      soft: "F8DDE4",
      warm: "FFD6A5",
      paper: "FFF7F7",
      imageA: "FFE3E8",
      imageB: "EF6F83",
      imageC: "FFB86B",
    };
  }
  if (type === "metric_dashboard" || type === "step_flow" || type === "campaign_timeline") {
    return {
      deep: darkenHex(accent, 0.55),
      mid: accent,
      soft: mixHex(accent, 0.82),
      warm: "F7C76A",
      paper: "F8FAFC",
      imageA: mixHex(accent, 0.86),
      imageB: accent,
      imageC: "FFFFFF",
    };
  }
  return {
    deep: darkenHex(accent, 0.5),
    mid: accent,
    soft: hex(plan.soft || mixHex(accent, 0.82)),
    warm: "F4C06A",
    paper: hex(plan.paper || "F8FAFC"),
    imageA: mixHex(accent, 0.86),
    imageB: accent,
    imageC: "FFFFFF",
  };
}

function generatedMoodSvg(plan, label = "StyleMind visual asset") {
  const tone = campaignTone(plan);
  const type = archetype(plan);
  const title = escapeXml(String(plan.title || label).slice(0, 34));
  const glowOpacity = type === "evidence_wall" ? 0.68 : 0.48;
  return svgDataUri(`
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="860" viewBox="0 0 1280 860">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#${tone.imageA}"/>
      <stop offset="48%" stop-color="#${tone.imageB}"/>
      <stop offset="100%" stop-color="#${tone.deep}"/>
    </linearGradient>
    <radialGradient id="glow" cx="30%" cy="28%" r="75%">
      <stop offset="0%" stop-color="#${tone.warm}" stop-opacity="${glowOpacity}"/>
      <stop offset="100%" stop-color="#${tone.deep}" stop-opacity="0"/>
    </radialGradient>
    <filter id="softNoise">
      <feTurbulence type="fractalNoise" baseFrequency="0.012 0.02" numOctaves="3" seed="${(plan.index || 1) * 7}"/>
      <feColorMatrix type="saturate" values="0.18"/>
      <feComponentTransfer><feFuncA type="table" tableValues="0 0.14"/></feComponentTransfer>
    </filter>
  </defs>
  <rect width="1280" height="860" fill="url(#bg)"/>
  <rect width="1280" height="860" fill="url(#glow)"/>
  <rect width="1280" height="860" filter="url(#softNoise)" opacity="0.55"/>
  <circle cx="965" cy="188" r="210" fill="#${tone.warm}" opacity="0.36"/>
  <circle cx="1015" cy="545" r="320" fill="#${tone.deep}" opacity="0.28"/>
  <path d="M-80 680 C210 560 360 740 640 612 C880 502 980 330 1360 390 L1360 900 L-80 900Z" fill="#${tone.deep}" opacity="0.38"/>
  <path d="M84 84 L1194 84 L1194 776 L84 776Z" fill="none" stroke="#FFFFFF" stroke-width="2" opacity="0.22"/>
  <path d="M112 112 L520 112" stroke="#FFFFFF" stroke-width="16" stroke-linecap="round" opacity="0.42"/>
  <path d="M112 146 L408 146" stroke="#FFFFFF" stroke-width="8" stroke-linecap="round" opacity="0.26"/>
  <g opacity="0.28">
    <rect x="780" y="124" width="310" height="198" rx="42" fill="#FFFFFF"/>
    <rect x="860" y="380" width="250" height="150" rx="34" fill="#FFFFFF"/>
    <rect x="700" y="572" width="420" height="110" rx="34" fill="#FFFFFF"/>
  </g>
  <text x="108" y="744" fill="#FFFFFF" opacity="0.24" font-family="Arial, sans-serif" font-size="30" font-weight="700">${title}</text>
</svg>`);
}

function visualGeometry(plan) {
  const spec = plan.layout_spec;
  const type = archetype(plan);
  const dark = isDarkPoster(plan);
  const base = {
    titleBox: spec.title_box,
    bodyBox: spec.body_box,
    imageBox: spec.image_box,
    titleSize: 30,
    bodySize: spec.body_font_size || 16,
    titleColor: dark ? "FFFFFF" : "0F172A",
    bodyColor: type === "evidence_wall" ? "233044" : dark ? "F8FAFC" : "233044",
  };

  if (type === "hero_photo_claim") {
    return {
      ...base,
      titleBox: [0.72, 0.82, 6.72, 1.72],
      bodyBox: [0.88, 2.92, 5.82, 1.82],
      imageBox: [6.9, 0.54, 5.86, 5.96],
      titleSize: 43,
      bodySize: 16,
    };
  }
  if (type === "section_divider") {
    return {
      ...base,
      titleBox: [0.94, 2.0, 8.9, 1.48],
      bodyBox: [1.02, 3.72, 6.7, 0.86],
      titleSize: 44,
      bodySize: 15,
    };
  }
  if (type === "strategy_claim_collage") {
    return {
      ...base,
      titleBox: [0.78, 0.58, 6.42, 1.22],
      bodyBox: [0.9, 2.06, 5.28, 2.96],
      imageBox: [6.45, 1.02, 5.92, 4.86],
      titleSize: 34,
      bodySize: 15,
    };
  }
  if (type === "metric_dashboard") {
    return {
      ...base,
      titleBox: [0.78, 0.54, 8.4, 0.82],
      bodyBox: [0.98, 5.66, 10.9, 0.8],
      titleSize: 30,
      bodySize: 12,
    };
  }
  if (type === "evidence_wall") {
    return {
      ...base,
      titleBox: [0.76, 0.52, 8.15, 0.92],
      bodyBox: [7.02, 1.58, 4.92, 4.08],
      imageBox: [0.74, 1.28, 5.98, 5.02],
      titleSize: 30,
      bodySize: 13,
    };
  }
  if (type === "campaign_timeline" || type === "step_flow") {
    return {
      ...base,
      titleBox: [0.76, 0.54, 8.4, 0.82],
      bodyBox: [0.9, 1.56, 11.1, 0.96],
      titleSize: 27,
      bodySize: 13,
    };
  }
  if (type === "video_material_board") {
    return {
      ...base,
      titleBox: [0.76, 0.54, 7.1, 0.86],
      bodyBox: [7.18, 1.58, 4.65, 3.28],
      imageBox: [0.76, 1.3, 6.05, 4.32],
      titleSize: 27,
      bodySize: 13,
    };
  }
  if (type === "editorial_content_bridge") {
    return {
      ...base,
      titleBox: [0.78, 0.54, 7.5, 0.92],
      bodyBox: [0.9, 1.72, 6.55, 4.55],
      imageBox: spec.image_box ? [8.25, 1.36, 3.95, 4.25] : null,
      titleSize: 27,
      bodySize: 14,
    };
  }
  return base;
}

function addBackground(slide, plan, baseDir) {
  const backgroundSource = plan.background_sources?.[0] || "";
  const tone = campaignTone(plan);
  const type = archetype(plan);
  const dark = isDarkPoster(plan);
  if (backgroundSource) {
    addImageOrPlaceholder(
      slide,
      { ...plan, image_sources: [backgroundSource], image_label: "背景素材图" },
      [0, 0, SLIDE_W, SLIDE_H],
      baseDir,
    );
  }
  addRect(slide, [0, 0, SLIDE_W, SLIDE_H], {
    fill: dark ? tone.deep : tone.paper,
    line: dark ? tone.deep : tone.paper,
    transparency: backgroundSource ? 20 : 0,
  });
  if (!backgroundSource && ["hero_photo_claim", "section_divider", "video_material_board"].includes(type)) {
    slide.addImage({ data: generatedMoodSvg(plan, "page background"), x: 6.56, y: 0, w: 6.78, h: 7.5, transparency: 8 });
    addRect(slide, [0, 0, 7.4, SLIDE_H], { fill: tone.deep, line: tone.deep, transparency: 4 });
    addRect(slide, [6.0, 0, 2.2, SLIDE_H], { fill: tone.deep, line: tone.deep, transparency: 26 });
  }
  if (!backgroundSource && type === "section_divider") {
    slide.addImage({ data: generatedMoodSvg(plan, "section visual"), x: 0.42, y: 0.38, w: 12.1, h: 6.54, transparency: 22 });
    addRect(slide, [0, 0, SLIDE_W, SLIDE_H], { fill: tone.deep, line: tone.deep, transparency: 12 });
  }
  if (renderHint(plan, "show_left_rail", true)) {
    addRect(slide, [0, 0, 0.12, SLIDE_H], { fill: tone.mid, line: tone.mid, transparency: dark ? 18 : 0 });
  }
  addEllipse(slide, [9.72, -0.84, 3.4, 2.32], { fill: tone.soft, line: tone.soft, transparency: dark ? 58 : 30 });
  addEllipse(slide, [-0.74, 5.88, 2.72, 2.28], { fill: tone.warm, line: tone.warm, transparency: dark ? 64 : 52 });
  if (plan.grid) {
    [1.2, 2.4, 3.6, 4.8, 6.0, 7.2, 8.4, 9.6, 10.8, 12.0].forEach((x) => addLine(slide, x, 0.24, x, 7.2, tone.soft, { width: 0.4, transparency: 78 }));
    [1.2, 2.4, 3.6, 4.8, 6.0].forEach((y) => addLine(slide, 0.42, y, 12.68, y, tone.soft, { width: 0.4, transparency: 78 }));
  }
}

function addCampaignBackdrop(slide, plan) {
  const type = archetype(plan);
  const tone = campaignTone(plan);
  const soft = tone.soft || plan.soft || mixHex(plan.accent, 0.84);
  if (["hero_photo_claim", "strategy_claim_collage", "video_material_board"].includes(type)) {
    addRect(slide, [6.5, 0.46, 6.12, 5.96], { fill: soft, line: soft, transparency: isDarkPoster(plan) ? 70 : 28 });
    addRect(slide, [0, 6.46, 13.333, 1.04], { fill: tone.mid, line: tone.mid, transparency: isDarkPoster(plan) ? 32 : 48 });
    addRect(slide, [10.54, 0.38, 1.72, 0.12], { fill: tone.mid, line: tone.mid, transparency: 16 });
    addRect(slide, [10.9, 0.66, 0.86, 0.1], { fill: tone.warm, line: tone.warm, transparency: 22 });
  } else if (type === "section_divider") {
    addRect(slide, [9.82, 0.68, 1.42, 5.96], { fill: tone.mid, line: tone.mid, transparency: 0 });
    addRect(slide, [11.42, 0.68, 0.24, 5.96], { fill: tone.warm, line: tone.warm, transparency: 0 });
    addText(slide, String(plan.index || "").padStart(2, "0"), [10.14, 1.08, 0.86, 0.5], {
      fontFace: fontFace(plan, "title"),
      fontSize: 17,
      bold: true,
      color: "FFFFFF",
      align: "center",
    });
  } else if (type === "metric_dashboard") {
    addRect(slide, [0.72, 1.42, 11.86, 3.56], { fill: mixHex(tone.mid, 0.9), line: mixHex(tone.mid, 0.72), transparency: 18 });
    addRect(slide, [0.72, 4.92, 11.86, 0.1], { fill: tone.mid, line: tone.mid, transparency: 24 });
  } else if (type === "evidence_wall") {
    addRect(slide, [0.66, 1.16, 6.2, 5.32], { fill: tone.deep, line: tone.mid, transparency: 8 });
    addRect(slide, [7.0, 1.22, 5.14, 5.18], { fill: "FFFFFF", line: mixHex(tone.mid, 0.58), transparency: 2 });
  } else if (type === "campaign_timeline" || type === "step_flow") {
    addRect(slide, [0.72, 3.1, 11.92, 2.88], { fill: mixHex(tone.mid, 0.92), line: mixHex(tone.mid, 0.8), transparency: 18 });
    addRect(slide, [0.72, 2.96, 2.2, 0.1], { fill: tone.mid, line: tone.mid, transparency: 8 });
  }
}

function addSkillTag(slide, plan) {
  const tone = campaignTone(plan);
  addRect(slide, [0.72, 0.3, 1.38, 0.28], { fill: tone.mid, line: tone.mid, transparency: isDarkPoster(plan) ? 8 : 0 });
  addText(slide, plan.layout_spec.label, [0.76, 0.335, 1.28, 0.18], {
    fontFace: fontFace(plan, "title"),
    fontSize: 8,
    bold: true,
    color: "FFFFFF",
    align: "center",
  });
}

function addCard(slide, plan, box, title, body) {
  const [x, y, w, h] = box;
  const tone = campaignTone(plan);
  addRect(slide, [x + 0.05, y + 0.06, w, h], { fill: darkenHex(tone.deep, 0.05), line: darkenHex(tone.deep, 0.05), transparency: 86 });
  addRect(slide, box, { fill: "FFFFFF", line: mixHex(tone.mid, 0.38), transparency: 3 });
  addRect(slide, [x, y, 0.08, h], { fill: tone.mid, line: tone.mid });
  addText(slide, title, [x + 0.22, y + 0.16, w - 0.42, 0.34], {
    fontFace: fontFace(plan, "title"),
    fontSize: 13,
    bold: true,
    color: tone.mid,
  });
  addText(slide, body, [x + 0.22, y + 0.58, w - 0.42, Math.max(0.2, h - 0.72)], {
    fontFace: fontFace(plan),
    fontSize: 11,
    color: "475569",
  });
}

function addMetricCard(slide, plan, box, text, idx) {
  const label = String(text || "").split(/[:：\s]+/, 1)[0] || `指标 ${idx + 1}`;
  const value = extractMetricValue(text);
  const [x, y, w, h] = box;
  const tone = campaignTone(plan);
  const fill = idx === 0 ? tone.deep : "FFFFFF";
  const textColor = idx === 0 ? "FFFFFF" : "475569";
  addRect(slide, [x + 0.06, y + 0.08, w, h], { fill: tone.deep, line: tone.deep, transparency: 88 });
  addRect(slide, box, { fill, line: idx === 0 ? tone.deep : tone.mid, transparency: idx === 0 ? 0 : 2 });
  addRect(slide, [x, y, w, 0.12], { fill: tone.mid, line: tone.mid });
  addText(slide, label.slice(0, 12), [x + 0.18, y + 0.24, w - 0.36, 0.36], {
    fontFace: fontFace(plan, "title"),
    fontSize: 11,
    bold: true,
    color: textColor,
  });
  addText(slide, value, [x + 0.18, y + 0.82, w - 0.36, Math.max(0.6, h - 1.04)], {
    fontFace: fontFace(plan, "title"),
    fontSize: w < 1.6 ? 24 : 34,
    bold: true,
    color: idx === 0 ? tone.warm : tone.mid,
  });
}

function resolveImagePath(imageSource, baseDir) {
  if (!imageSource || imageSource.startsWith("data:image")) return "";
  const candidates = [imageSource];
  if (imageSource.startsWith("/api/generated/")) {
    const rel = imageSource.split("/api/generated/", 1)[1];
    candidates.push(path.join(process.cwd(), "web_ui", "static", "generated", rel));
    candidates.push(path.join(process.cwd(), "web_ui", "static", rel));
  }
  if (!path.isAbsolute(imageSource)) {
    candidates.push(path.join(baseDir, imageSource));
    candidates.push(path.join(process.cwd(), imageSource));
  }
  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) return candidate;
  }
  return "";
}

function imageSourceExists(plan, baseDir) {
  const imageSource = plan.image_sources?.[0] || "";
  if (!imageSource) return false;
  if (imageSource.startsWith("data:image")) return true;
  return Boolean(resolveImagePath(imageSource, baseDir));
}

function addImageOrPlaceholder(slide, plan, box, baseDir) {
  const imageSource = plan.image_sources?.[0] || "";
  if (imageSource.startsWith("data:image")) {
    slide.addImage({ data: imageSource, x: box[0], y: box[1], w: box[2], h: box[3] });
    return;
  }
  const imgPath = resolveImagePath(imageSource, baseDir);
  if (imgPath) {
    slide.addImage({ path: imgPath, x: box[0], y: box[1], w: box[2], h: box[3] });
    return;
  }

  // Keep the contract: image slots are always replaceable picture objects,
  // even when the source asset is missing during a renderer spike.
  const tone = campaignTone(plan);
  slide.addImage({ data: generatedMoodSvg(plan, plan.image_label || "visual asset"), x: box[0], y: box[1], w: box[2], h: box[3] });
  addRect(slide, [box[0], box[1], box[2], box[3]], { fill: tone.deep, line: tone.mid, transparency: 86, lineTransparency: 22 });
  addRect(slide, [box[0] + 0.22, box[1] + box[3] - 0.52, Math.max(0.3, box[2] - 0.44), 0.18], { fill: "FFFFFF", line: "FFFFFF", transparency: 48 });
  addRect(slide, [box[0] + 0.22, box[1] + box[3] - 0.28, Math.max(0.3, box[2] * 0.42), 0.08], { fill: tone.warm, line: tone.warm, transparency: 28 });
}

function addPhotoField(slide, plan, box, baseDir, label, evidenceGrid = false) {
  const [x, y, w, h] = box;
  const hasRealImage = imageSourceExists(plan, baseDir);
  const tone = campaignTone(plan);
  addRect(slide, [x + 0.08, y + 0.1, w, h], { fill: tone.deep, line: tone.deep, transparency: 84 });
  addRect(slide, box, { fill: mixHex(tone.mid, 0.84), line: tone.mid, transparency: 18 });
  addImageOrPlaceholder(slide, { ...plan, image_label: label }, [x + 0.1, y + 0.1, Math.max(0.2, w - 0.2), Math.max(0.2, h - 0.2)], baseDir);
  addRect(slide, box, { fill: "FFFFFF", line: tone.mid, transparency: 100, lineTransparency: 18 });

  if (evidenceGrid && !hasRealImage) {
    const cardW = Math.max(0.7, (w - 0.64) / 2);
    const cardH = Math.max(0.48, (h - 0.74) / 2);
    for (let row = 0; row < 2; row += 1) {
      for (let col = 0; col < 2; col += 1) {
        const cx = x + 0.22 + col * (cardW + 0.2);
        const cy = y + 0.24 + row * (cardH + 0.18);
        addRect(slide, [cx, cy, cardW, cardH], { fill: "FFFFFF", line: tone.mid, transparency: 12 });
        addRect(slide, [cx + 0.12, cy + 0.13, Math.max(0.1, cardW - 0.24), 0.12], { fill: mixHex(tone.mid, 0.64), line: mixHex(tone.mid, 0.64), transparency: 10 });
        addRect(slide, [cx + 0.12, cy + cardH - 0.2, Math.max(0.1, cardW - 0.24), 0.04], { fill: tone.warm, line: tone.warm, transparency: 18 });
      }
    }
  }
}

function elevatedImageBox(plan) {
  return visualGeometry(plan).imageBox || plan.layout_spec.image_box;
}

function extractMetricValue(text) {
  const match = String(text || "").match(/([+-]?\d+(?:\.\d+)?\s*%|[+-]?\d+(?:\.\d+)?\s*(?:万|亿|k|K|w|W)?)/);
  return match ? match[1].replace(/\s+/g, "") : String(text || "").slice(0, 14);
}

function addNumberedDot(slide, plan, x, y, number) {
  const tone = campaignTone(plan);
  addEllipse(slide, [x, y, 0.34, 0.34], { fill: tone.mid, line: tone.mid });
  addText(slide, String(number), [x + 0.045, y + 0.055, 0.25, 0.18], {
    fontFace: fontFace(plan, "title"),
    fontSize: 8,
    bold: true,
    color: "FFFFFF",
    align: "center",
  });
}

function addStepFlowCards(slide, plan) {
  const tone = campaignTone(plan);
  const centers = [];
  const boxes = [
    [0.9, 3.28, 2.55, 2.18],
    [3.88, 3.28, 2.55, 2.18],
    [6.86, 3.28, 2.55, 2.18],
    [9.84, 3.28, 2.55, 2.18],
  ];
  boxes.forEach((box, idx) => {
    const [x, y, w, h] = box;
    const text = plan.card_texts?.[idx % Math.max(1, plan.card_texts.length)] || plan.layout_spec.label;
    addRect(slide, [x + 0.05, y + 0.08, w, h], { fill: tone.deep, line: tone.deep, transparency: 88 });
    addRect(slide, box, { fill: "FFFFFF", line: mixHex(tone.mid, 0.32), transparency: 2 });
    addNumberedDot(slide, plan, x + 0.2, y + 0.2, idx + 1);
    addText(slide, String(text).slice(0, 120), [x + 0.64, y + 0.18, Math.max(0.2, w - 0.82), Math.max(0.3, h - 0.34)], {
      fontFace: fontFace(plan),
      fontSize: 11,
      bold: idx === 0,
      color: idx === 0 ? tone.mid : "334155",
    });
    centers.push([x + w / 2, y + h / 2]);
  });
  centers.slice(0, -1).forEach((center, idx) => {
    const next = centers[idx + 1];
    addLine(slide, center[0] + 1.25, center[1], next[0] - 1.25, next[1], tone.mid, { width: 1.4 });
  });
}

function addCampaignTimeline(slide, plan) {
  const tone = campaignTone(plan);
  const y = 5.84;
  const boxes = [
    [0.95, 3.34, 2.7, 1.9],
    [3.92, 3.06, 2.7, 1.9],
    [6.9, 3.34, 2.7, 1.9],
    [9.88, 3.06, 2.4, 1.9],
  ];
  addLine(slide, 1.22, y, 11.96, y, tone.mid, { width: 1.4 });
  boxes.forEach((box, idx) => {
    const [x, cardY, w, h] = box;
    const cx = x + w / 2;
    const text = plan.card_texts?.[idx % Math.max(1, plan.card_texts.length)] || plan.layout_spec.label;
    addEllipse(slide, [cx - 0.08, y - 0.08, 0.16, 0.16], { fill: tone.mid, line: tone.mid });
    addRect(slide, [x + 0.04, cardY + 0.06, w, h], { fill: tone.deep, line: tone.deep, transparency: 88 });
    addRect(slide, box, { fill: "FFFFFF", line: tone.mid, transparency: 2 });
    addText(slide, `阶段 ${idx + 1}`, [x + 0.18, cardY + 0.18, w - 0.36, 0.28], {
      fontFace: fontFace(plan, "title"),
      fontSize: 11,
      bold: true,
      color: tone.mid,
    });
    addText(slide, String(text).slice(0, 110), [x + 0.18, cardY + 0.56, w - 0.36, h - 0.72], {
      fontFace: fontFace(plan),
      fontSize: 11,
      color: "334155",
    });
  });
}

function addSectionMarks(slide, plan) {
  const tone = campaignTone(plan);
  const boxes = [[9.9, 0.72, 1.34, 5.94], [11.42, 0.72, 0.24, 5.94]];
  boxes.forEach((box, idx) => {
    const [x, y, w, h] = box;
    const fill = idx === 0 ? tone.mid : tone.warm;
    addRect(slide, box, { fill, line: tone.mid, transparency: idx === 0 ? 0 : 14 });
    if (idx === 0) {
      addText(slide, String(plan.intent?.layout_label || "").slice(0, 28), [x + 0.18, y + 0.24, Math.max(0.2, w - 0.36), 0.86], {
        fontFace: fontFace(plan, "title"),
        fontSize: 10,
        bold: true,
        color: "FFFFFF",
      });
    }
  });
}

function addMetricDashboardCards(slide, plan) {
  const boxes = [
    [0.96, 1.66, 2.78, 2.86],
    [4.08, 1.66, 2.78, 2.86],
    [7.2, 1.66, 2.78, 2.86],
    [10.32, 1.66, 1.76, 2.86],
  ];
  boxes.forEach((box, idx) => {
    const text = plan.card_texts?.[idx % Math.max(1, plan.card_texts.length)] || plan.layout_spec.label;
    addMetricCard(slide, plan, box, text, idx);
  });
}

function drawArchetypeNativeObjects(slide, plan, baseDir) {
  const spec = plan.layout_spec;
  const type = archetype(plan);
  let handledImage = false;
  let handledCards = false;

  if (["hero_photo_claim", "strategy_claim_collage", "video_material_board", "editorial_content_bridge"].includes(type) && elevatedImageBox(plan)) {
    const label = type === "video_material_board" ? "视频缩略图 / DEMO" : "主视觉素材";
    addPhotoField(slide, plan, elevatedImageBox(plan), baseDir, label);
    handledImage = true;
    if (type === "strategy_claim_collage") {
      [0.42, 0.32, 0.24].forEach((size, idx) => addRect(slide, [10.7 + idx * 0.48, 0.82 + idx * 0.34, size, size], { fill: plan.soft || "E2E8F0", line: plan.accent }));
    }
  }

  if (type === "evidence_wall" && elevatedImageBox(plan)) {
    addPhotoField(slide, plan, elevatedImageBox(plan), baseDir, "证据截图 / 素材占位", true);
    handledImage = true;
  }

  if (type === "metric_dashboard") {
    addMetricDashboardCards(slide, plan);
    handledCards = true;
  } else if (type === "step_flow") {
    addStepFlowCards(slide, plan);
    handledCards = true;
  } else if (type === "campaign_timeline") {
    addCampaignTimeline(slide, plan);
    handledCards = true;
  } else if (type === "section_divider") {
    addSectionMarks(slide, plan);
    handledCards = true;
  }

  return { handledImage, handledCards };
}

function renderPlan(pptx, plan, baseDir) {
  const slide = pptx.addSlide();
  const spec = plan.layout_spec;
  const geom = visualGeometry(plan);
  const tone = campaignTone(plan);
  addBackground(slide, plan, baseDir);
  addCampaignBackdrop(slide, plan);
  if (renderHint(plan, "show_fixed_tag", true)) {
    addSkillTag(slide, plan);
  }
  if (renderHint(plan, "show_generic_separator", true)) {
    addLine(slide, geom.titleBox[0], geom.titleBox[1] + geom.titleBox[3] + 0.14, geom.titleBox[0] + 2.7, geom.titleBox[1] + geom.titleBox[3] + 0.14, isDarkPoster(plan) ? tone.warm : tone.mid, { width: 1.4 });
  }

  if (isDarkPoster(plan) && archetype(plan) !== "evidence_wall") {
    addRect(slide, [geom.bodyBox[0] - 0.12, geom.bodyBox[1] - 0.1, geom.bodyBox[2] + 0.22, geom.bodyBox[3] + 0.18], {
      fill: tone.deep,
      line: tone.deep,
      transparency: 36,
    });
  }

  addText(slide, plan.title, geom.titleBox, {
    fontFace: fontFace(plan, "title"),
    fontSize: geom.titleSize,
    bold: true,
    color: geom.titleColor,
  });
  addText(slide, textLines(plan, archetype(plan) === "metric_dashboard" ? 2 : 5), geom.bodyBox, {
    fontFace: fontFace(plan),
    fontSize: geom.bodySize,
    color: geom.bodyColor,
  });

  const handled = drawArchetypeNativeObjects(slide, plan, baseDir);

  if (geom.imageBox && !handled.handledImage) addImageOrPlaceholder(slide, plan, geom.imageBox, baseDir);

  (spec.card_boxes || []).forEach((box, idx) => {
    if (handled.handledCards) return;
    const text = plan.card_texts?.[idx % Math.max(1, plan.card_texts.length)] || spec.label;
    if (spec.label === "数据结果") addMetricCard(slide, plan, box, text, idx);
    else addCard(slide, plan, box, `${spec.label} ${idx + 1}`, String(text).slice(0, 72));
  });

  if (plan.video_links?.[0]) {
    addText(slide, "打开视频素材链接", [spec.label === "视频素材" ? 7.16 : 9.28, 6.48, 3.1, 0.32], {
      fontFace: fontFace(plan, "title"),
      fontSize: 12,
      bold: true,
      color: plan.accent,
      hyperlink: plan.video_links[0],
    });
  }
  if (Array.isArray(plan.notes) && typeof slide.addNotes === "function") {
    slide.addNotes(plan.notes.join("\n"));
  }
}

async function main() {
  const input = argValue("--input", ".pytest_tmp/stylemind_render_plan_fixture.json");
  const output = argValue("--output", ".pytest_tmp/stylemind_pptxgenjs_spike.pptx");
  const payload = JSON.parse(fs.readFileSync(input, "utf8"));
  if (payload.schema !== "stylemind.render_plan.v1") {
    throw new Error(`Unsupported render-plan schema: ${payload.schema}`);
  }

  const pptx = new PptxGenJS();
  pptx.author = "StyleMind";
  pptx.subject = "PptxGenJS render-plan spike";
  pptx.company = "StyleMind";
  pptx.lang = "zh-CN";
  pptx.defineLayout({ name: "STYLEMIND_WIDE", width: SLIDE_W, height: SLIDE_H });
  pptx.layout = "STYLEMIND_WIDE";
  pptx.theme = {
    headFontFace: "Microsoft YaHei",
    bodyFontFace: "Microsoft YaHei",
    lang: "zh-CN",
  };

  const baseDir = path.dirname(path.resolve(input));
  payload.plans.forEach((plan) => renderPlan(pptx, plan, baseDir));
  await pptx.writeFile({ fileName: output });
  console.log(JSON.stringify({ output, page_count: payload.plans.length, renderer: "pptxgenjs" }));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
