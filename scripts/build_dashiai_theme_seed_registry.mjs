#!/usr/bin/env node
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const THEME_METADATA = path.join(
  ROOT,
  'third_party/dashiai-ppt-skill/project/src/components/themes/generated-metadata.js',
);
const OUT_FILE = path.join(
  ROOT,
  'reference_samples/dashiai_theme_seed/stylemind_dashiai_theme_seed_registry.json',
);

const STYLEMIND_ROLE_RULES = [
  {
    role: '开场定调',
    terms: ['封面', 'cover', '开场', '发布', '品牌', '主张'],
    pageNumberMax: 5,
  },
  {
    role: '章节转场',
    terms: ['章节', '目录', '转场', 'section', 'chapter', 'part'],
  },
  {
    role: '内容承接',
    terms: ['摘要', 'overview', 'report', '洞察', '复盘', '观察', '承接'],
  },
  {
    role: '创意主张',
    terms: ['金句', 'statement', 'quote', '概念', '主张', 'slogan', 'claim'],
  },
  {
    role: '执行打法',
    terms: ['策略', 'strategy', '路线图', 'roadmap', '流程', 'process', '行动', 'workflow'],
  },
  {
    role: '案例证据',
    terms: ['案例', 'case', '证据', 'evidence', 'spotlight', '峰值', '聚焦'],
  },
  {
    role: '数据结果',
    terms: ['指标', 'metrics', '数据', 'data', '趋势', 'trend', '对比', 'delta', 'scorecard', '大数字'],
  },
  {
    role: '视频素材',
    terms: ['视频', 'video', 'media', 'image', '图片', '照片', '素材'],
    requireMedia: true,
  },
];

const MODULE_TAG_RULES = [
  ['metric_dashboard', ['指标', 'metrics', 'scorecard', '大数字', 'gauge', 'delta']],
  ['comparison_matrix', ['对比', 'compare', 'matrix', 'scorecard', 'delta']],
  ['case_evidence', ['案例', 'case', 'evidence', 'spotlight', 'peak']],
  ['process_roadmap', ['路线图', 'roadmap', '流程', 'workflow', 'process']],
  ['statement_quote', ['金句', 'statement', 'quote', 'claim']],
  ['cover_hero', ['封面', 'cover']],
  ['media_collage', ['image', '图片', '照片', 'media', '视频']],
];

const FEIBO_OVERLAY = {
  aestheticSource: 'Feibo reference decks/PDFs first',
  rewritePolicy: [
    'remove fixed corner labels unless the reference page needs them',
    'replace default palettes with Feibo-derived typography, spacing, image crop rhythm, and campaign backgrounds',
    'keep DashiAI controls as component logic, not as final visual identity',
    'use uploaded or image-2 generated page assets as replaceable picture objects',
  ],
};

const { GENERATED_THEME_PACKS, GENERATED_THEME_PAGES } = await import(
  pathToFileURL(THEME_METADATA).href
);

const themes = GENERATED_THEME_PACKS.map(theme => ({
  key: theme.key,
  displayName: theme.displayName || theme.name || theme.key,
  scenario: theme.scenario || '',
  audience: theme.audience || '',
  pageCount: theme.pageCount || 0,
}));

const candidates = [];
for (const page of GENERATED_THEME_PAGES) {
  const text = normalizedText([
    page.key,
    page.themeKey,
    page.label,
    page.slot,
    page.layout,
    JSON.stringify(page.defaultProps || {}),
    JSON.stringify((page.controls || []).map(control => control.label || control.key)),
  ]);
  const mediaLike = hasMediaSignal(page);
  const stylemindRoles = STYLEMIND_ROLE_RULES
    .map(rule => {
      let score = 0;
      for (const term of rule.terms) {
        if (text.includes(term.toLowerCase())) score += 2;
      }
      if (rule.pageNumberMax && Number(page.pageNumber || 0) <= rule.pageNumberMax) score += 5;
      if (rule.requireMedia && mediaLike) score += 5;
      if (rule.requireMedia && !mediaLike) score -= 5;
      return { role: rule.role, score };
    })
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score);
  if (!stylemindRoles.length) continue;

  const moduleTags = MODULE_TAG_RULES
    .filter(([, terms]) => terms.some(term => text.includes(term.toLowerCase())))
    .map(([tag]) => tag);
  const controls = (page.controls || []).map(control => ({
    key: control.publicKey || control.key,
    sourceKey: control.key,
    label: control.label || control.key,
    type: normalizeControlType(control.type),
    default: control.default,
    min: control.min,
    max: control.max,
    desc: control.desc || '',
  }));

  candidates.push({
    key: page.key,
    themeKey: page.themeKey,
    themeName: themeName(page.themeKey),
    pageNumber: page.pageNumber,
    label: page.label,
    slot: page.slot,
    layout: page.layout,
    stylemindRoles,
    primaryStylemindRole: stylemindRoles[0].role,
    moduleTags,
    hasMediaSlots: mediaLike,
    controlCount: controls.length,
    controls,
    defaultCopyKeys: Object.keys(page.defaultProps || {}).filter(key => {
      const value = page.defaultProps[key];
      return typeof value === 'string' || typeof value === 'number';
    }).slice(0, 24),
    adaptation: {
      status: 'seed_needs_feibo_restyle',
      visualSource: 'DashiAI vendored theme',
      targetVisualSource: 'Feibo reference',
    },
  });
}

const byRole = {};
for (const role of STYLEMIND_ROLE_RULES.map(rule => rule.role)) {
  byRole[role] = candidates
    .filter(candidate => candidate.stylemindRoles.some(item => item.role === role))
    .sort((a, b) => {
      const as = a.stylemindRoles.find(item => item.role === role)?.score || 0;
      const bs = b.stylemindRoles.find(item => item.role === role)?.score || 0;
      return bs - as || Number(a.pageNumber || 0) - Number(b.pageNumber || 0);
    })
    .slice(0, 36)
    .map(candidate => candidate.key);
}

const registry = {
  schema: 'stylemind.dashiai_theme_seed_registry.v1',
  generatedAt: new Date().toISOString(),
  source: {
    vendorPath: 'third_party/dashiai-ppt-skill',
    metadataPath: 'third_party/dashiai-ppt-skill/project/src/components/themes/generated-metadata.js',
    license: 'AGPL-3.0',
  },
  feiboOverlay: FEIBO_OVERLAY,
  themes,
  roleMap: STYLEMIND_ROLE_RULES.map(({ role, terms, requireMedia, pageNumberMax }) => ({
    role,
    terms,
    requireMedia: Boolean(requireMedia),
    pageNumberMax: pageNumberMax || null,
  })),
  counts: {
    themes: themes.length,
    sourcePages: GENERATED_THEME_PAGES.length,
    candidates: candidates.length,
  },
  byRole,
  candidates,
};

mkdirSync(path.dirname(OUT_FILE), { recursive: true });
writeFileSync(OUT_FILE, `${JSON.stringify(registry, null, 2)}\n`);
console.log(`Wrote ${path.relative(ROOT, OUT_FILE)} with ${candidates.length} candidate(s).`);

function normalizedText(parts) {
  return parts
    .filter(value => value !== null && value !== undefined)
    .join(' ')
    .toLowerCase();
}

function hasMediaSignal(page) {
  const controls = page.controls || [];
  const props = page.defaultProps || {};
  return controls.some(control => /media|image|图片|照片|视频/.test(`${control.key} ${control.label || ''}`.toLowerCase()))
    || Array.isArray(props.images)
    || Array.isArray(props.media)
    || Array.isArray(props.photos)
    || Object.keys(props).some(key => /image|media|photo|video|图片|照片|视频/.test(key.toLowerCase()));
}

function normalizeControlType(type) {
  if (type === 'number') return 'range';
  if (type === 'boolean') return 'toggle';
  if (type === 'enum' || type === 'color') return 'select';
  return type || 'control';
}

function themeName(themeKey) {
  const theme = GENERATED_THEME_PACKS.find(item => item.key === themeKey);
  return theme?.displayName || theme?.name || themeKey;
}
