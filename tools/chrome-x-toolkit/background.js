/**
 * 后台：LLM 评论生成
 */

const DEFAULT_LLM = {
  apiKey: '',
  apiBase: 'http://127.0.0.1:11434/v1',
  model: 'gemma-uncensored',
  count: 4,
  rolePrompt: '你是 X/Twitter 上的真实用户，口语自然，短句为主，可接梗但不低俗，不超过 280 字。',
};

async function loadLlmSettings() {
  const data = await chrome.storage.local.get(DEFAULT_LLM);
  return { ...DEFAULT_LLM, ...data };
}

function buildCommentPrompt(ctx, settings) {
  const lines = [
    `请基于以下 X 贴文详情，写 ${settings.count} 条「回复主贴」的评论候选。`,
    '',
    '要求：',
    '1. 已阅读主贴与前几条现有回复，避免重复，可顺势接话或补充新角度。',
    '2. 像真人，口语自然，单条 ≤280 字。',
    '3. 不要编号、不要 markdown，严格输出 JSON 字符串数组：',
    '["评论1","评论2",...]',
    '',
    `角色：${settings.rolePrompt}`,
    '',
    `主贴作者：${ctx.mainAuthor || '未知'}`,
    `主贴正文：\n${ctx.mainText || ''}`,
  ];
  if (ctx.replies?.length) {
    lines.push('', '前几条回复：');
    ctx.replies.forEach((r) => lines.push(`${r.index}. ${r.author}: ${r.text}`));
  }
  return lines.join('\n');
}

function parseComments(raw) {
  const text = String(raw || '').trim();
  const start = text.indexOf('[');
  const end = text.lastIndexOf(']');
  if (start >= 0 && end > start) {
    try {
      const arr = JSON.parse(text.slice(start, end + 1));
      if (Array.isArray(arr)) return arr.map((x) => String(x).trim()).filter(Boolean);
    } catch (_) {
      /* fallthrough */
    }
  }
  return [];
}

async function callLlm(prompt, settings) {
  const url = `${String(settings.apiBase || '').replace(/\/$/, '')}/chat/completions`;
  const headers = { 'Content-Type': 'application/json' };
  if (settings.apiKey) headers.Authorization = `Bearer ${settings.apiKey}`;
  const resp = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model: settings.model,
      temperature: 0.85,
      messages: [
        {
          role: 'system',
          content: '你是社交媒体评论写手，只输出 JSON 评论数组。',
        },
        { role: 'user', content: prompt },
      ],
    }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data?.error?.message || data?.message || `HTTP ${resp.status}`);
  }
  const content = data?.choices?.[0]?.message?.content;
  if (!content) throw new Error('模型未返回内容');
  return content;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    if (msg.type !== 'GENERATE_COMMENTS') return;
    try {
      const settings = await loadLlmSettings();
      const prompt = buildCommentPrompt(msg.payload || {}, settings);
      const raw = await callLlm(prompt, settings);
      const items = parseComments(raw).slice(0, settings.count);
      if (!items.length) throw new Error('未能解析评论');
      sendResponse({ ok: true, items });
    } catch (e) {
      sendResponse({ ok: false, error: String(e.message || e) });
    }
  })();
  return true;
});

chrome.runtime.onInstalled.addListener(() => {
  console.log('X 工具箱已安装');
});
