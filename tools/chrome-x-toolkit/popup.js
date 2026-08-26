/**
 * X 工具箱 popup
 */

let scanItems = [];

const els = {
  apiStatus: document.getElementById('apiStatus'),
  startDate: document.getElementById('startDate'),
  endDate: document.getElementById('endDate'),
  typePosts: document.getElementById('typePosts'),
  typeReplies: document.getElementById('typeReplies'),
  typeRetweets: document.getElementById('typeRetweets'),
  typeLikes: document.getElementById('typeLikes'),
  delayMs: document.getElementById('delayMs'),
  btnScan: document.getElementById('btnScan'),
  btnRun: document.getElementById('btnRun'),
  scanResult: document.getElementById('scanResult'),
  status: document.getElementById('status'),
  settingsPanel: document.getElementById('settingsPanel'),
  btnSettings: document.getElementById('btnSettings'),
  btnSaveSettings: document.getElementById('btnSaveSettings'),
  btnCloseSettings: document.getElementById('btnCloseSettings'),
  apiBase: document.getElementById('apiBase'),
  apiKey: document.getElementById('apiKey'),
  model: document.getElementById('model'),
  count: document.getElementById('count'),
  rolePrompt: document.getElementById('rolePrompt'),
  btnOpenStatus: document.getElementById('btnOpenStatus'),
};

const DEFAULTS = {
  apiBase: 'http://127.0.0.1:11434/v1',
  apiKey: '',
  model: 'gemma-uncensored',
  count: 4,
  rolePrompt:
    '你是 X/Twitter 上的真实用户，口语自然，短句为主，可接梗但不低俗，不超过 280 字。',
  startDate: '',
  endDate: '',
};

function setStatus(text, kind) {
  els.status.textContent = text || '';
  els.status.className = 'status' + (kind ? ` ${kind}` : '');
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoISO(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

async function getXTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.url && /x\.com|twitter\.com/i.test(tab.url)) return tab;
  const tabs = await chrome.tabs.query({ url: ['https://x.com/*', 'https://twitter.com/*'] });
  return tabs[0] || tab;
}

async function ensureXTab() {
  let tab = await getXTab();
  if (tab?.id && /x\.com|twitter\.com/i.test(tab.url || '')) return tab;
  tab = await chrome.tabs.create({ url: 'https://x.com/home', active: true });
  await new Promise((r) => setTimeout(r, 2500));
  return tab;
}

async function refreshApiStatus() {
  const tab = await getXTab();
  if (!tab?.id) {
    els.apiStatus.textContent = '请先打开 x.com';
    els.apiStatus.className = 'api-status err';
    return;
  }
  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: 'GET_API_STATUS' });
    if (!res?.ok) throw new Error(res?.error || '无响应');
    const q = (res.queryIds || []).length;
    if (res.hasAuth && res.hasCsrf) {
      els.apiStatus.textContent = `凭据 OK · 已捕获 ${q} 个 GraphQL 操作`;
      els.apiStatus.className = 'api-status ok';
    } else {
      els.apiStatus.textContent = '凭据不完整：请在 X 上刷新并滚动时间线';
      els.apiStatus.className = 'api-status err';
    }
  } catch (_) {
    els.apiStatus.textContent = '未连接 content script，请刷新 X 页面';
    els.apiStatus.className = 'api-status err';
  }
}

function getCleanupOptions() {
  return {
    startDate: els.startDate.value || daysAgoISO(7),
    endDate: els.endDate.value || todayISO(),
    types: {
      posts: els.typePosts.checked,
      replies: els.typeReplies.checked,
      retweets: els.typeRetweets.checked,
      likes: els.typeLikes.checked,
    },
    delayMs: Math.max(500, Number(els.delayMs.value) || 1500),
  };
}

async function scan() {
  els.btnScan.disabled = true;
  els.btnRun.disabled = true;
  scanItems = [];
  setStatus('扫描中…');
  els.scanResult.hidden = false;
  els.scanResult.textContent = '正在打开 X 并扫描…';
  try {
    const tab = await ensureXTab();
    const opts = getCleanupOptions();
    const stored = await chrome.storage.local.get(['xApiCapture']);
    const res = await chrome.tabs.sendMessage(tab.id, {
      type: 'SCAN_CLEANUP',
      payload: { ...opts, creds: stored.xApiCapture || {} },
    });
    if (!res?.ok) throw new Error(res?.error || '扫描失败');
    scanItems = res.items || [];
    const preview = scanItems
      .slice(0, 30)
      .map(
        (it, i) =>
          `${i + 1}. [${it.kind}/${it.action}] ${it.createdAt?.slice(0, 16) || ''} ${it.text.slice(0, 50)}`
      )
      .join('\n');
    els.scanResult.textContent =
      `共 ${scanItems.length} 条\n` +
      (preview || '（无匹配项）') +
      (scanItems.length > 30 ? `\n… 另有 ${scanItems.length - 30} 条` : '');
    els.btnRun.disabled = !scanItems.length;
    setStatus(`扫描完成：${scanItems.length} 条`, scanItems.length ? 'ok' : '');
  } catch (e) {
    els.scanResult.textContent = String(e.message || e);
    setStatus(String(e.message || e), 'err');
  } finally {
    els.btnScan.disabled = false;
  }
}

async function runCleanup() {
  if (!scanItems.length) return;
  if (
    !confirm(
      `确定删除 ${scanItems.length} 项？\n此操作不可撤销，建议先小范围试跑。`
    )
  ) {
    return;
  }
  els.btnRun.disabled = true;
  setStatus('执行中…');
  try {
    const tab = await ensureXTab();
    const opts = getCleanupOptions();
    const res = await chrome.tabs.sendMessage(tab.id, {
      type: 'RUN_CLEANUP',
      items: scanItems,
      delayMs: opts.delayMs,
    });
    setStatus(`完成：成功 ${res.ok} · 失败 ${res.fail}`, res.fail ? 'err' : 'ok');
    scanItems = [];
    els.btnRun.disabled = true;
  } catch (e) {
    setStatus(String(e.message || e), 'err');
  } finally {
    els.btnRun.disabled = !scanItems.length;
  }
}

async function loadSettings() {
  const data = await chrome.storage.local.get(DEFAULTS);
  els.apiBase.value = data.apiBase || DEFAULTS.apiBase;
  els.apiKey.value = data.apiKey || '';
  els.model.value = data.model || DEFAULTS.model;
  els.count.value = String(data.count || DEFAULTS.count);
  els.rolePrompt.value = data.rolePrompt || DEFAULTS.rolePrompt;
  els.startDate.value = data.startDate || daysAgoISO(7);
  els.endDate.value = data.endDate || todayISO();
}

async function saveSettings() {
  await chrome.storage.local.set({
    apiBase: els.apiBase.value.trim(),
    apiKey: els.apiKey.value.trim(),
    model: els.model.value.trim(),
    count: Math.min(8, Math.max(2, Number(els.count.value) || 4)),
    rolePrompt: els.rolePrompt.value.trim(),
    startDate: els.startDate.value,
    endDate: els.endDate.value,
  });
  setStatus('设置已保存', 'ok');
}

document.querySelectorAll('.tab').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-cleanup').classList.toggle('hidden', btn.dataset.tab !== 'cleanup');
    document.getElementById('tab-comment').classList.toggle('hidden', btn.dataset.tab !== 'comment');
  });
});

els.btnSettings.addEventListener('click', () => els.settingsPanel.classList.remove('hidden'));
els.btnCloseSettings.addEventListener('click', () => els.settingsPanel.classList.add('hidden'));
els.btnSaveSettings.addEventListener('click', saveSettings);
els.btnScan.addEventListener('click', scan);
els.btnRun.addEventListener('click', runCleanup);
els.btnOpenStatus.addEventListener('click', async () => {
  const tab = await getXTab();
  if (!tab?.id) {
    setStatus('请先打开 X', 'err');
    return;
  }
  await chrome.tabs.sendMessage(tab.id, { type: 'EXTRACT_STATUS' });
  setStatus('请在页面右下角点击 💬 打开评论面板', 'ok');
});

loadSettings().then(refreshApiStatus);
