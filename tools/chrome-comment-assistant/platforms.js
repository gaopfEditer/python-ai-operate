/**
 * 平台检测、角色预设、评论框选择器（popup + content 共用）
 */
/* global self */

const PLATFORMS = {
  twitter: {
    id: 'twitter',
    name: 'X / Twitter',
    short: 'X',
    hosts: ['x.com', 'twitter.com', 'mobile.twitter.com'],
    pathTest: () => true,
    maxLen: 280,
    hint: '短句、口语，避免长段；可带 0~1 个相关 emoji，不 spam。',
  },
  binance: {
    id: 'binance',
    name: '币安 Square',
    short: '币安',
    hosts: ['binance.com', 'www.binance.com'],
    pathTest: (p) => /\/square/i.test(p),
    maxLen: 500,
    hint: '社区广场语气，可谈行情/策略但避免喊单；不写具体杠杆建议。',
  },
  okx: {
    id: 'okx',
    name: 'OKX 社区',
    short: 'OKX',
    hosts: ['okx.com', 'www.okx.com'],
    pathTest: (p) => /\/(community|feed|post|learn)/i.test(p) || /\/cn\//i.test(p),
    maxLen: 500,
    hint: '偏专业社区口吻，逻辑清晰，少标题党。',
  },
  bitget: {
    id: 'bitget',
    name: 'Bitget 社区',
    short: 'Bitget',
    hosts: ['bitget.com', 'www.bitget.com'],
    pathTest: (p) => /\/(community|square|feed|post|insights)/i.test(p),
    maxLen: 500,
    hint: '合约/现货社区读者，强调风险与可验证信息。',
  },
  reddit: {
    id: 'reddit',
    name: 'Reddit',
    short: 'Reddit',
    hosts: ['reddit.com', 'old.reddit.com', 'www.reddit.com'],
    pathTest: (p) => /\/comments\//i.test(p) || /\/r\//i.test(p),
    maxLen: 800,
    hint: '英文或中英混合均可；Reddit 风格自然，可适度 casual，避免像 bot。',
  },
};

/** @type {{ id: string; name: string; platforms: string[]; prompt: string }[]} */
const ROLE_PRESETS = [
  {
    id: 'rational',
    name: '理性分析',
    platforms: ['*'],
    prompt: '你是理性读者，评论侧重逻辑、证据与风险，语气克制，不吹不黑，不灌鸡汤。',
  },
  {
    id: 'friendly',
    name: '友善互动',
    platforms: ['*'],
    prompt: '你是友善网友，语气轻松自然，先认同再补充一点个人感受，避免尴尬捧杀。',
  },
  {
    id: 'skeptic',
    name: '质疑追问',
    platforms: ['*'],
    prompt: '你是审慎质疑者，礼貌提出关键疑点或未说明的前提，不做人身攻击。',
  },
  {
    id: 'practitioner',
    name: '实操经验',
    platforms: ['*'],
    prompt: '你是有实操经验的人，结合可落地的细节或踩坑提醒，短句为主。',
  },
  {
    id: 'humor',
    name: '轻度幽默',
    platforms: ['*'],
    prompt: '你带一点轻松幽默，但不玩梗过度，不冒犯作者，保持与贴文相关。',
  },
  {
    id: 'twitter_short',
    name: 'X·短句互动',
    platforms: ['twitter'],
    prompt: '你是 X 用户，评论 1~2 句，口语、有观点，可反问或补充角度，不超过 200 字。',
  },
  {
    id: 'twitter_crypto',
    name: 'X·加密圈讨论',
    platforms: ['twitter'],
    prompt: '你是加密圈参与者，评论紧扣行情/项目/宏观，不喊单，可提风险与数据，语气像 timeline 真人。',
  },
  {
    id: 'binance_square',
    name: '币安·广场互动',
    platforms: ['binance'],
    prompt: '你是币安 Square 活跃用户，评论像广场跟帖：有观点、可分享观察，不承诺收益，不写「必涨必跌」。',
  },
  {
    id: 'binance_risk',
    name: '币安·风险提示',
    platforms: ['binance'],
    prompt: '你从风控角度跟评：提醒波动、杠杆、信息源可靠性，语气专业克制。',
  },
  {
    id: 'okx_pro',
    name: 'OKX·专业跟评',
    platforms: ['okx'],
    prompt: '你是 OKX 社区读者，评论偏专业：结构清晰，可引用逻辑链，避免空洞看多/看空。',
  },
  {
    id: 'bitget_trader',
    name: 'Bitget·交易员视角',
    platforms: ['bitget'],
    prompt: '你是 Bitget 社区交易者，评论可谈仓位思路/纪律/复盘，强调止损与计划，不诱导跟单。',
  },
  {
    id: 'reddit_casual',
    name: 'Reddit·自然跟帖',
    platforms: ['reddit'],
    prompt: 'You write like a real Redditor: casual, specific, maybe a short personal take. English preferred unless post is Chinese.',
  },
  {
    id: 'reddit_helpful',
    name: 'Reddit·补充信息',
    platforms: ['reddit'],
    prompt: 'You add helpful context, a source, or a polite counterpoint. Reddit tone, not corporate.',
  },
  {
    id: 'custom',
    name: '完全自定义',
    platforms: ['*'],
    prompt: '',
  },
];

const COMMENT_SELECTORS = {
  twitter: [
    'div[data-testid="tweetTextarea_0"]',
    'div[contenteditable="true"][data-testid="tweetTextarea_0_label"]',
    'div.public-DraftEditor-content[contenteditable="true"]',
    'div[aria-label*="Post text" i][contenteditable="true"]',
    'div[aria-label*="Tweet text" i][contenteditable="true"]',
    'div[aria-label*="回复" i][contenteditable="true"]',
    'div[aria-label*="Reply" i][contenteditable="true"]',
  ],
  binance: [
    'textarea[placeholder*="评论" i]',
    'textarea[placeholder*="comment" i]',
    'textarea[placeholder*="说点什么" i]',
    'div[contenteditable="true"].ProseMirror',
    'div.ProseMirror[contenteditable="true"]',
    '[class*="comment"] textarea',
    '[class*="Comment"] textarea',
    '[class*="reply"] [contenteditable="true"]',
    '[class*="Reply"] [contenteditable="true"]',
    'textarea',
  ],
  okx: [
    'textarea[placeholder*="评论" i]',
    'textarea[placeholder*="comment" i]',
    'textarea[placeholder*="回复" i]',
    'div[contenteditable="true"]',
    '[class*="comment"] textarea',
    '[class*="Comment"] textarea',
    'textarea',
  ],
  bitget: [
    'textarea[placeholder*="评论" i]',
    'textarea[placeholder*="comment" i]',
    'textarea[placeholder*="回复" i]',
    'div[contenteditable="true"]',
    '[class*="comment"] textarea',
    'textarea',
  ],
  reddit: [
    'textarea[name="body"]',
    'textarea[placeholder*="comment" i]',
    'textarea[placeholder*="thought" i]',
    'div[contenteditable="true"][data-lexical-editor="true"]',
    'div[contenteditable="true"][role="textbox"]',
    'shreddit-composer textarea',
    'faceplate-textarea-input textarea',
    'div[contenteditable="true"]',
  ],
  generic: [
    'textarea[placeholder*="评论"]',
    'textarea[placeholder*="留言"]',
    'textarea[placeholder*="说点什么"]',
    'textarea[placeholder*="comment" i]',
    'div[role="textbox"][contenteditable="true"]',
    'textarea',
  ],
};

function detectPlatformFromLocation(href, hostname) {
  const host = (hostname || '').toLowerCase();
  const path = (() => {
    try {
      return new URL(href || `https://${host}/`).pathname;
    } catch (_) {
      return '';
    }
  })();
  for (const p of Object.values(PLATFORMS)) {
    if (!p.hosts.some((h) => host === h || host.endsWith('.' + h) || host.includes(h))) continue;
    if (p.pathTest(path)) return p.id;
  }
  if (host.includes('x.com') || host.includes('twitter.com')) return 'twitter';
  if (host.includes('reddit.com')) return 'reddit';
  if (host.includes('binance.com')) return 'binance';
  if (host.includes('okx.com')) return 'okx';
  if (host.includes('bitget.com')) return 'bitget';
  return 'generic';
}

function getPlatformMeta(platformId) {
  return PLATFORMS[platformId] || null;
}

function rolesForPlatform(platformId) {
  return ROLE_PRESETS.filter(
    (r) => r.platforms.includes('*') || r.platforms.includes(platformId)
  );
}

function selectorsForPlatform(platformId) {
  const specific = COMMENT_SELECTORS[platformId] || [];
  const generic = COMMENT_SELECTORS.generic || [];
  return [...specific, ...generic];
}

const PlatformKit = {
  PLATFORMS,
  ROLE_PRESETS,
  COMMENT_SELECTORS,
  detectPlatformFromLocation,
  getPlatformMeta,
  rolesForPlatform,
  selectorsForPlatform,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = PlatformKit;
}
if (typeof self !== 'undefined') {
  self.PlatformKit = PlatformKit;
}
