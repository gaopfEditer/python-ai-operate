/**
 * 评论角度助手 - popup
 * 多平台：X / 币安 Square / OKX / Bitget / Reddit
 */

const { PLATFORMS, ROLE_PRESETS, rolesForPlatform, getPlatformMeta } = PlatformKit;

const DEFAULTS = {
  apiKey: '',
  apiBase: 'http://127.0.0.1:11434/v1',
  model: 'gemma-uncensored',
  count: 4,
  rolePreset: 'rational',
  roleCustom: ROLE_PRESETS.find((r) => r.id === 'rational')?.prompt || '',
  lastPlatform: 'generic',
};

function isLocalOllama(apiBase) {
  const b = (apiBase || '').toLowerCase();
  return (
    b.includes('127.0.0.1:11434') ||
    b.includes('localhost:11434') ||
    (b.includes('11434') && b.includes('/v1'))
  );
}

const els = {
  settingsPanel: document.getElementById('settingsPanel'),
  btnSettings: document.getElementById('btnSettings'),
  btnSaveSettings: document.getElementById('btnSaveSettings'),
  btnCloseSettings: document.getElementById('btnCloseSettings'),
  apiKey: document.getElementById('apiKey'),
  apiBase: document.getElementById('apiBase'),
  model: document.getElementById('model'),
  count: document.getElementById('count'),
  platformBadge: document.getElementById('platformBadge'),
  rolePreset: document.getElementById('rolePreset'),
  roleCustom: document.getElementById('roleCustom'),
  context: document.getElementById('context'),
  btnRefreshCtx: document.getElementById('btnRefreshCtx'),
  btnGenerate: document.getElementById('btnGenerate'),
  status: document.getElementById('status'),
  results: document.getElementById('results'),
  resultMeta: document.getElementById('resultMeta'),
  btnCopy: document.getElementById('btnCopy'),
  btnInsert: document.getElementById('btnInsert'),
};

/** @type {string[]} */
let candidates = [];
let selectedIndex = -1;
let currentPlatform = 'generic';
let currentPlatformMeta = null;

function setStatus(text, kind = '') {
  els.status.textContent = text || '';
  els.status.className = 'status' + (kind ? ` ${kind}` : '');
}

function updatePlatformBadge(platformId, platformName) {
  currentPlatform = platformId || 'generic';
  currentPlatformMeta = getPlatformMeta(currentPlatform);
  if (!els.platformBadge) return;
  const name = platformName || currentPlatformMeta?.name || '通用站点';
  els.platformBadge.textContent = name;
  els.platformBadge.dataset.platform = currentPlatform;
  els.platformBadge.className = 'platform-badge' + (currentPlatform !== 'generic' ? ` p-${currentPlatform}` : '');
}

async function loadSettings() {
  const data = await chrome.storage.local.get(DEFAULTS);
  els.apiKey.value = data.apiKey || '';
  els.apiBase.value = data.apiBase || DEFAULTS.apiBase;
  els.model.value = data.model || DEFAULTS.model;
  els.count.value = String(data.count || DEFAULTS.count);
  updatePlatformBadge(data.lastPlatform || 'generic');
  return data;
}

async function saveSettings() {
  const payload = {
    apiKey: (els.apiKey.value || '').trim(),
    apiBase: (els.apiBase.value || '').trim().replace(/\/$/, ''),
    model: (els.model.value || '').trim(),
    count: Math.min(8, Math.max(2, Number(els.count.value) || 4)),
    rolePreset: els.rolePreset.value,
    roleCustom: (els.roleCustom.value || '').trim(),
    lastPlatform: currentPlatform,
  };
  els.count.value = String(payload.count);
  await chrome.storage.local.set(payload);
  setStatus('设置已保存', 'ok');
  return payload;
}

function fillRoleSelect(platformId) {
  const roles = rolesForPlatform(platformId || 'generic');
  const generic = roles.filter((r) => r.platforms.includes('*') && r.id !== 'custom');
  const specific = roles.filter((r) => !r.platforms.includes('*'));
  let html = '';
  if (specific.length) {
    const meta = getPlatformMeta(platformId);
    html += `<optgroup label="${meta?.name || platformId} 专用">`;
    html += specific.map((r) => `<option value="${r.id}">${r.name}</option>`).join('');
    html += '</optgroup>';
  }
  html += `<optgroup label="通用角度">`;
  html += generic.map((r) => `<option value="${r.id}">${r.name}</option>`).join('');
  html += `<option value="custom">完全自定义</option>`;
  html += '</optgroup>';
  els.rolePreset.innerHTML = html;
}

function pickDefaultRoleForPlatform(platformId) {
  const roles = rolesForPlatform(platformId);
  const preferred = {
    twitter: 'twitter_short',
    binance: 'binance_square',
    okx: 'okx_pro',
    bitget: 'bitget_trader',
    reddit: 'reddit_casual',
  };
  const id = preferred[platformId];
  if (id && roles.some((r) => r.id === id)) return id;
  return 'rational';
}

function onRolePresetChange() {
  const preset = ROLE_PRESETS.find((r) => r.id === els.rolePreset.value);
  if (!preset) return;
  if (preset.id !== 'custom') {
    els.roleCustom.value = preset.prompt;
  }
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function refreshContext() {
  setStatus('正在读取当前页…');
  const tab = await getActiveTab();
  if (!tab?.id) {
    setStatus('找不到当前页签', 'err');
    return;
  }
  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: 'extractContext' });
    if (!res?.ok) throw new Error(res?.error || '读取失败');
    const platform = res.platform || res.site || 'generic';
    updatePlatformBadge(platform, res.platformName);
    fillRoleSelect(platform);
    const saved = await chrome.storage.local.get(['rolePreset', 'lastPlatform']);
    const defaultRole = pickDefaultRoleForPlatform(platform);
    if (saved.lastPlatform !== platform || !rolesForPlatform(platform).some((r) => r.id === saved.rolePreset)) {
      els.rolePreset.value = defaultRole;
      onRolePresetChange();
    } else {
      els.rolePreset.value = saved.rolePreset || defaultRole;
      onRolePresetChange();
    }
    await chrome.storage.local.set({ lastPlatform: platform, rolePreset: els.rolePreset.value });

    const parts = [];
    if (res.platformName) parts.push(`平台：${res.platformName}`);
    if (res.title) parts.push(`标题：${res.title}`);
    if (res.author) parts.push(`作者：${res.author}`);
    if (res.subreddit) parts.push(`版块：r/${res.subreddit}`);
    if (res.url) parts.push(`链接：${res.url}`);
    if (res.selection) parts.push(`选中内容：\n${res.selection}`);
    if (res.body) parts.push(`正文：\n${res.body}`);
    els.context.value = parts.join('\n\n').trim();
    const hint = currentPlatformMeta?.hint ? ` · ${currentPlatformMeta.hint}` : '';
    setStatus(
      els.context.value ? `已读取 [${res.platformName || platform}]${hint}` : '未读到有效内容，请手动粘贴',
      els.context.value ? 'ok' : 'err'
    );
  } catch (e) {
    setStatus(`读取失败：${e.message || e}（可手动粘贴）`, 'err');
  }
}

function buildPrompt(context, role, count, platformMeta) {
  const maxLen = platformMeta?.maxLen || 500;
  const platformHint = platformMeta?.hint || '';
  const lines = [
    `请基于以下贴文上下文，以指定角色角度写 ${count} 条评论候选。`,
    '',
    '要求：',
    '1. 每条独立成段，像真人会发的评论，口语自然。',
    '2. 紧扣贴文，不要空洞套话；不要标题党；不要表情刷屏。',
    `3. 单条建议不超过 ${maxLen} 字（该平台风格）。`,
    '4. 不要编号说明、不要引号包裹整段、不要输出分析过程。',
    '5. 严格按下面 JSON 数组输出，仅含字符串，不要 markdown：',
    '["评论1","评论2",...]',
  ];
  if (platformHint) {
    lines.push('', `平台风格：${platformHint}`);
  }
  lines.push('', `角色角度：${role}`, '', '贴文上下文：', context.slice(0, 6000));
  return lines.join('\n');
}

function parseComments(raw) {
  const text = (raw || '').trim();
  const start = text.indexOf('[');
  const end = text.lastIndexOf(']');
  if (start >= 0 && end > start) {
    try {
      const arr = JSON.parse(text.slice(start, end + 1));
      if (Array.isArray(arr)) {
        return arr.map((x) => String(x).trim()).filter(Boolean);
      }
    } catch (_) {
      /* fallthrough */
    }
  }
  return text
    .split(/\n+/)
    .map((line) => line.replace(/^\s*[\d]+[\.\)、]\s*/, '').replace(/^[-*]\s*/, '').trim())
    .filter((line) => line && !line.startsWith('{') && !line.startsWith('['));
}

async function callChatCompletions({ apiKey, apiBase, model, prompt }) {
  const url = `${apiBase.replace(/\/$/, '')}/chat/completions`;
  /** @type {Record<string, string>} */
  const headers = { 'Content-Type': 'application/json' };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  const resp = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model,
      temperature: 0.85,
      stream: false,
      messages: [
        {
          role: 'system',
          content:
            '你是社交媒体评论写手，熟悉 X、币安 Square、OKX、Bitget、Reddit 社区语气。只输出用户要求的 JSON 评论数组。',
        },
        { role: 'user', content: prompt },
      ],
    }),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const msg = data?.error?.message || data?.message || JSON.stringify(data).slice(0, 200);
    throw new Error(msg || `HTTP ${resp.status}`);
  }
  const content = data?.choices?.[0]?.message?.content;
  if (!content) throw new Error('模型未返回内容');
  return content;
}

function renderResults() {
  els.results.innerHTML = '';
  if (!candidates.length) {
    els.results.innerHTML = '<p class="empty">尚未生成</p>';
    els.btnCopy.disabled = true;
    els.btnInsert.disabled = true;
    els.resultMeta.textContent = '';
    return;
  }
  const maxLen = currentPlatformMeta?.maxLen;
  els.resultMeta.textContent = `${candidates.length} 条${maxLen ? ` · 建议 ≤${maxLen} 字` : ''}`;
  candidates.forEach((text, i) => {
    const item = document.createElement('label');
    item.className = 'candidate' + (i === selectedIndex ? ' selected' : '');
    const over = maxLen && text.length > maxLen;
    item.innerHTML = `
      <input type="radio" name="pick" value="${i}" ${i === selectedIndex ? 'checked' : ''} />
      <div>
        <div class="idx">候选 ${i + 1}${over ? ` · ${text.length} 字` : ''}</div>
        <div class="body"></div>
      </div>
    `;
    item.querySelector('.body').textContent = text;
    item.querySelector('input').addEventListener('change', () => {
      selectedIndex = i;
      renderResults();
    });
    item.addEventListener('click', (e) => {
      if (e.target.tagName === 'INPUT') return;
      selectedIndex = i;
      renderResults();
    });
    els.results.appendChild(item);
  });
  els.btnCopy.disabled = selectedIndex < 0;
  els.btnInsert.disabled = selectedIndex < 0;
}

async function generate() {
  const settings = await saveSettings();
  const useOllama = isLocalOllama(settings.apiBase);
  if (!settings.apiKey && !useOllama) {
    els.settingsPanel.classList.remove('hidden');
    setStatus('请先填写 API Key，或改用 Ollama Base', 'err');
    return;
  }
  const context = (els.context.value || '').trim();
  if (!context) {
    setStatus('请先提供贴文上下文', 'err');
    return;
  }
  const role = (els.roleCustom.value || '').trim() || '普通读者，自然评论';
  const count = settings.count;
  const prompt = buildPrompt(context, role, count, currentPlatformMeta);

  els.btnGenerate.disabled = true;
  setStatus(`正在生成（${useOllama ? 'Ollama' : currentPlatformMeta?.short || currentPlatform}）…`);
  try {
    const raw = await callChatCompletions({
      apiKey: settings.apiKey,
      apiBase: settings.apiBase,
      model: settings.model,
      prompt,
    });
    candidates = parseComments(raw).slice(0, count);
    if (!candidates.length) throw new Error('未能解析出评论，请重试');
    selectedIndex = 0;
    renderResults();
    setStatus(`已生成 ${candidates.length} 条，请选择一条`, 'ok');
  } catch (e) {
    setStatus(`生成失败：${e.message || e}`, 'err');
  } finally {
    els.btnGenerate.disabled = false;
  }
}

async function copySelected() {
  if (selectedIndex < 0 || !candidates[selectedIndex]) return;
  const text = candidates[selectedIndex];
  try {
    await navigator.clipboard.writeText(text);
    setStatus('已复制到剪贴板', 'ok');
  } catch (_) {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    setStatus('已复制到剪贴板', 'ok');
  }
}

async function insertSelected() {
  if (selectedIndex < 0 || !candidates[selectedIndex]) return;
  const text = candidates[selectedIndex];
  const tab = await getActiveTab();
  if (!tab?.id) {
    setStatus('找不到当前页签', 'err');
    return;
  }
  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: 'insertComment', text });
    if (!res?.ok) throw new Error(res?.error || '未找到评论输入框');
    const plat = res.platform ? ` [${res.platform}]` : '';
    setStatus(
      res.method === 'copied' ? `未定位到输入框${plat}，已改为复制` : `已填入评论框${plat}`,
      'ok'
    );
  } catch (e) {
    await copySelected();
    setStatus(`填入失败，已复制：${e.message || e}`, 'err');
  }
}

els.btnSettings.addEventListener('click', () => {
  els.settingsPanel.classList.toggle('hidden');
});
els.btnCloseSettings.addEventListener('click', () => {
  els.settingsPanel.classList.add('hidden');
});
els.btnSaveSettings.addEventListener('click', () => saveSettings());
els.rolePreset.addEventListener('change', onRolePresetChange);
els.btnRefreshCtx.addEventListener('click', refreshContext);
els.btnGenerate.addEventListener('click', generate);
els.btnCopy.addEventListener('click', copySelected);
els.btnInsert.addEventListener('click', insertSelected);

fillRoleSelect('generic');
loadSettings().then(async (data) => {
  const preset = ROLE_PRESETS.find((r) => r.id === (data.rolePreset || els.rolePreset.value));
  if (preset && preset.id !== 'custom' && !(els.roleCustom.value || '').trim()) {
    els.roleCustom.value = preset.prompt;
  }
  await refreshContext();
});
