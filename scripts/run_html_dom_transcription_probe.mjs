#!/usr/bin/env node
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_SKILL_ROOT = process.env.DASHIAI_PPT_SKILL_ROOT || "";
const DEFAULT_OUT_DIR = path.join(ROOT, ".pytest_tmp", "html_dom_transcription_probe");

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return fallback;
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function isWritableTempDir(dir) {
  if (!dir) return false;
  try {
    ensureDir(dir);
    const probeDir = fs.mkdtempSync(path.join(dir, "stylemind-tmp-check-"));
    fs.rmSync(probeDir, { recursive: true, force: true });
    return true;
  } catch {
    return false;
  }
}

function ensureRuntimeTempDir() {
  const current = os.tmpdir();
  if (isWritableTempDir(current)) return current;
  const fallback = ensureDir(path.join(ROOT, ".pytest_tmp", "html_dom_runtime_tmp"));
  process.env.TMPDIR = fallback;
  process.env.TMP = fallback;
  process.env.TEMP = fallback;
  return fallback;
}

function assertFile(file, label) {
  if (!fs.existsSync(file)) throw new Error(`${label} not found: ${file}`);
  return file;
}

function htmlEscape(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fixtureSlides() {
  return [
    {
      theme: "hero",
      title: "美的夏日生活方式提案",
      kicker: "StyleMind HTML DOM Probe",
      body: "HTML 工作台预览应能转写成可编辑 PPTX，而不是整页 PNG。",
      metric: "95%",
      note: "目标质感：飞博参考优先",
    },
    {
      theme: "data",
      title: "传播结果需要先看主指标",
      kicker: "数据结果",
      body: "保留 DashiAI 的指标结构能力，但用飞博式留白、轻支撑块和原生文字重绘。",
      metric: "3.8x",
      note: "互动效率提升",
    },
    {
      theme: "evidence",
      title: "案例证据必须保留素材层",
      kicker: "案例证据",
      body: "复杂视觉可以局部截图保真，但标题、正文、数据与说明必须从 DOM 重新抽出为可编辑对象。",
      metric: "12",
      note: "素材位与文案分离",
    },
  ];
}

function slidesFromRenderPlan(payload) {
  const plans = Array.isArray(payload?.plans) ? payload.plans : [];
  return plans.map((plan, index) => {
    const role = plan.intent?.page_role || plan.layout_spec?.label || "StyleMind";
    const archetype = plan.visual_profile?.archetype || "";
    const moduleKey = plan.component_spec?.modules?.[0]?.key || "";
    const cardTexts = Array.isArray(plan.card_texts) ? plan.card_texts : [];
    const bodyLines = Array.isArray(plan.body_lines) ? plan.body_lines : [];
    const metricSource = cardTexts[0] || bodyLines.find(line => /[0-9]/.test(String(line || ""))) || `${index + 1}`;
    const metricMatch = String(metricSource).match(/([+-]?\d+(?:\.\d+)?\s*%|[+-]?\d+(?:\.\d+)?\s*(?:万|亿|k|K|w|W)?)/);
    let theme = "hero";
    if (archetype === "metric_dashboard" || moduleKey === "feibo_metric_result_strip") theme = "data";
    if (archetype === "evidence_wall" || moduleKey === "feibo_evidence_wall") theme = "evidence";
    if (archetype === "campaign_timeline" || archetype === "step_flow" || moduleKey === "feibo_process_rhythm") theme = "data";
    return {
      theme,
      title: plan.title || `StyleMind page ${index + 1}`,
      kicker: role,
      body: bodyLines.slice(0, 3).join(" / ") || plan.intent?.brief || "HTML DOM 转写保持原生文字可编辑。",
      metric: metricMatch ? metricMatch[1].replace(/\s+/g, "") : String(index + 1).padStart(2, "0"),
      note: plan.component_spec?.modules?.[0]?.label || plan.visual_profile?.reference_style_label || "Feibo reference first",
      layoutKey: `${archetype || "stylemind"}_${index + 1}`,
    };
  });
}

function probeHtml(renderPlanPayload = null) {
  const slides = renderPlanPayload ? slidesFromRenderPlan(renderPlanPayload) : fixtureSlides();
  const slideMarkup = slides.map((slide, index) => `
    <section class="slide ${index === 0 ? "active" : ""} ${slide.theme}" data-layout-key="${htmlEscape(slide.layoutKey || `stylemind_html_dom_${index + 1}`)}" ${index === 0 ? "data-deck-active" : ""}>
      <div class="visual-field" data-editable-pptx-material-background>
        <div class="noise"></div>
        <div class="halo"></div>
      </div>
      <div class="copy">
        <p class="kicker">${htmlEscape(slide.kicker)}</p>
        <h1>${htmlEscape(slide.title)}</h1>
        <p class="body">${htmlEscape(slide.body)}</p>
      </div>
      <div class="metric-panel">
        <span class="metric">${htmlEscape(slide.metric)}</span>
        <span class="metric-note">${htmlEscape(slide.note)}</span>
      </div>
      <div class="support-grid">
        <div><b>结构</b><span>DOM text</span></div>
        <div><b>图片</b><span>replaceable layer</span></div>
        <div><b>导出</b><span>editable PPTX</span></div>
      </div>
    </section>
  `).join("\n");

  return `<!doctype html>
<html lang="zh-CN" data-theme-pack="stylemind-html-dom-probe">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>StyleMind HTML DOM Probe</title>
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; width: 100%; height: 100%; background: #111827; font-family: "PingFang SC", "Microsoft YaHei", Arial, sans-serif; }
    #deck-viewport { width: 100vw; height: 100vh; display: grid; place-items: center; overflow: hidden; }
    #deck { position: relative; width: min(100vw, 177.777vh); aspect-ratio: 16 / 9; background: #f8fafc; overflow: hidden; }
    .slide { position: absolute; inset: 0; display: none; padding: 86px 94px; background: #f8fafc; color: #0f172a; overflow: hidden; }
    .slide.active, .slide[data-deck-active] { display: block; }
    .visual-field { position: absolute; inset: 0; overflow: hidden; background:
      radial-gradient(circle at 78% 18%, rgba(255, 198, 133, .7), transparent 24%),
      radial-gradient(circle at 14% 82%, rgba(38, 103, 255, .28), transparent 26%),
      linear-gradient(135deg, #f8fafc 0%, #eaf2ff 48%, #fff2ed 100%); }
    .data .visual-field { background:
      linear-gradient(90deg, rgba(38,103,255,.08) 1px, transparent 1px),
      linear-gradient(0deg, rgba(38,103,255,.06) 1px, transparent 1px),
      linear-gradient(135deg, #f8fbff 0%, #dce7ff 52%, #fff8ec 100%); background-size: 96px 96px, 96px 96px, auto; }
    .evidence .visual-field { background:
      radial-gradient(circle at 22% 16%, rgba(215,51,47,.4), transparent 22%),
      linear-gradient(135deg, #faf7f1 0%, #f2e6d8 44%, #fff 100%); }
    .noise { position: absolute; inset: -20%; background-image: repeating-linear-gradient(135deg, rgba(15, 23, 42, .06) 0 1px, transparent 1px 14px); opacity: .42; transform: rotate(-4deg); }
    .halo { position: absolute; right: 86px; top: 68px; width: 560px; height: 420px; border-radius: 48px; background: rgba(255,255,255,.44); border: 1px solid rgba(255,255,255,.65); box-shadow: 0 40px 90px rgba(38,103,255,.14); }
    .copy { position: relative; z-index: 2; width: 780px; padding-top: 32px; }
    .kicker { margin: 0 0 28px; font-size: 24px; font-weight: 700; color: #2667ff; letter-spacing: 0; }
    h1 { margin: 0; font-size: 78px; line-height: .98; max-width: 780px; letter-spacing: 0; }
    .body { margin: 38px 0 0; width: 650px; font-size: 29px; line-height: 1.45; color: #334155; letter-spacing: 0; }
    .metric-panel { position: absolute; z-index: 3; right: 96px; bottom: 86px; width: 390px; min-height: 210px; padding: 34px 36px; background: rgba(255,255,255,.76); border: 1px solid rgba(226,232,240,.9); border-radius: 26px; box-shadow: 0 28px 80px rgba(15,23,42,.09); }
    .metric { display: block; font-size: 82px; line-height: .9; font-weight: 800; color: #2667ff; letter-spacing: 0; }
    .metric-note { display: block; margin-top: 22px; font-size: 25px; color: #334155; font-weight: 700; letter-spacing: 0; }
    .support-grid { position: absolute; z-index: 3; left: 96px; bottom: 78px; display: grid; grid-template-columns: repeat(3, 190px); gap: 18px; }
    .support-grid div { min-height: 92px; padding: 18px 20px; background: rgba(255,255,255,.62); border: 1px solid rgba(226,232,240,.86); border-radius: 18px; }
    .support-grid b { display: block; font-size: 20px; color: #0f172a; }
    .support-grid span { display: block; margin-top: 10px; font-size: 17px; color: #64748b; }
  </style>
</head>
<body>
  <main id="deck-viewport">
    <div id="deck">
      ${slideMarkup}
    </div>
  </main>
  <script>
    window.go = function(index) {
      const slides = [...document.querySelectorAll('#deck > .slide')];
      slides.forEach((slide, i) => {
        const active = i === Number(index || 0);
        slide.classList.toggle('active', active);
        if (active) slide.setAttribute('data-deck-active', '');
        else slide.removeAttribute('data-deck-active');
      });
    };
    window.__getVisibleSlides = function() {
      return [...document.querySelectorAll('#deck > .slide')];
    };
    window.__layoutDeck = function() {};
    window.__finishEditablePptxAnimations = function() {};
  </script>
</body>
</html>`;
}

function contentType(file) {
  if (file.endsWith(".html")) return "text/html;charset=utf-8";
  if (file.endsWith(".js")) return "text/javascript;charset=utf-8";
  if (file.endsWith(".css")) return "text/css;charset=utf-8";
  if (file.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

function startStaticServer(rootDir) {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url || "/", "http://127.0.0.1");
    const rel = decodeURIComponent(url.pathname === "/" ? "/index.html" : url.pathname);
    const file = path.resolve(rootDir, `.${rel}`);
    if (!file.startsWith(rootDir) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404, { "content-type": "text/plain;charset=utf-8" });
      res.end("not found");
      return;
    }
    res.writeHead(200, { "content-type": contentType(file), "cache-control": "no-store" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({ server, url: `http://127.0.0.1:${address.port}/` });
    });
  });
}

async function main() {
  ensureRuntimeTempDir();
  const skillRoot = path.resolve(argValue("--skill-root", process.env.DASHIAI_PPT_SKILL_ROOT || DEFAULT_SKILL_ROOT));
  const skillProject = path.join(skillRoot, "project");
  const htmlToPptxEntry = assertFile(
    path.join(skillProject, "packages", "html-deck-to-pptx", "src", "editable.mjs"),
    "DashiAI html-deck-to-pptx editable entry",
  );
  const chromePathEntry = assertFile(path.join(skillProject, "scripts", "chrome-path.mjs"), "DashiAI chrome-path script");
  assertFile(path.join(skillProject, "node_modules", "playwright-core", "package.json"), "DashiAI playwright-core dependency");

  const outDir = ensureDir(path.resolve(argValue("--out-dir", DEFAULT_OUT_DIR)));
  const deckDir = ensureDir(path.resolve(argValue("--deck-dir", path.join(outDir, "deck"))));
  const output = path.resolve(argValue("--output", path.join(outDir, "stylemind_html_dom_probe.pptx")));
  const report = path.resolve(argValue("--report", path.join(outDir, "stylemind_html_dom_probe.report.json")));
  const inputPath = argValue("--input", "");
  const renderPlanPayload = inputPath ? JSON.parse(fs.readFileSync(path.resolve(inputPath), "utf8")) : null;
  fs.writeFileSync(path.join(deckDir, "index.html"), probeHtml(renderPlanPayload), "utf8");

  const skillRequire = createRequire(path.join(skillProject, "package.json"));
  const { chromium } = skillRequire("playwright-core");
  const { getChromeExecutablePath } = await import(pathToFileURL(chromePathEntry).href);
  const { exportEditablePptxFromUrl } = await import(pathToFileURL(htmlToPptxEntry).href);

  const { server, url } = await startStaticServer(deckDir);
  let browser = null;
  try {
    browser = await chromium.launch({ headless: true, executablePath: getChromeExecutablePath() });
    const result = await exportEditablePptxFromUrl(browser, url, {
      outFile: output,
      reportFile: report,
      title: "StyleMind HTML DOM Transcription Probe",
      timeout: 60000,
    });
    const summary = {
      status: "ok",
      renderer: "html-dom",
      source: "dashiai-html-deck-to-pptx",
      deckDir,
      output,
      report,
      previewUrl: url,
      input: inputPath ? path.resolve(inputPath) : "",
      slideCount: result.slideCount,
      textObjects: result.textObjects,
      shapeObjects: result.shapeObjects,
      imageObjects: result.imageObjects,
      warningCount: Array.isArray(result.warnings) ? result.warnings.length : 0,
    };
    console.log(JSON.stringify(summary, null, 2));
  } finally {
    if (browser) await browser.close().catch(() => {});
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => {
  console.error(`[html-dom probe] ${error?.stack || error?.message || error}`);
  process.exit(1);
});
