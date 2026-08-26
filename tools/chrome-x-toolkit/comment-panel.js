/**
 * 贴文详情页：提取主贴 + 前几条评论 → AI 生成回复候选
 */
/* global XApi */

const CommentPanel = (() => {
  const PANEL_ID = 'x-toolkit-comment-panel';
  let candidates = [];
  let selected = 0;

  function clean(s) {
    return String(s || '').replace(/\s+/g, ' ').trim();
  }

  function isStatusPage() {
    return /\/status\/\d+/i.test(location.pathname);
  }

  function extractStatusContext() {
    const articles = [...document.querySelectorAll('article[data-testid="tweet"]')];
    if (!articles.length) return null;

    const main = articles[0];
    const mainText = [...main.querySelectorAll('[data-testid="tweetText"]')]
      .map((n) => n.innerText.trim())
      .join('\n\n');
    const mainAuthor =
      clean(main.querySelector('[data-testid="User-Name"] span')?.textContent) ||
      clean(main.querySelector('a[role="link"] span')?.textContent);

    const replies = articles.slice(1, 6).map((a, i) => {
      const author =
        clean(a.querySelector('[data-testid="User-Name"] span')?.textContent) ||
        clean(a.querySelector('a[role="link"] span')?.textContent);
      const text = [...a.querySelectorAll('[data-testid="tweetText"]')]
        .map((n) => n.innerText.trim())
        .join('\n\n');
      return { index: i + 1, author, text: text.slice(0, 500) };
    }).filter((r) => r.text);

    return {
      url: location.href,
      mainAuthor,
      mainText: mainText.slice(0, 2000),
      replies,
    };
  }

  function findReplyBox() {
    const sels = [
      'div[data-testid="tweetTextarea_0"]',
      'div[role="textbox"][data-testid^="tweetTextarea"]',
      'div[contenteditable="true"][data-testid="tweetTextarea_0_label"]',
    ];
    for (const sel of sels) {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) return el;
    }
    return document.querySelector('div[contenteditable="true"]');
  }

  async function insertReply(text) {
    const el = findReplyBox();
    if (!el) {
      await navigator.clipboard.writeText(text);
      return { ok: true, method: 'copied' };
    }
    el.focus();
    el.scrollIntoView({ block: 'nearest' });
    if (el.isContentEditable) {
      el.textContent = '';
      document.execCommand('selectAll', false, null);
      const ok = document.execCommand('insertText', false, text);
      if (!ok) {
        el.textContent = text;
        el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text, inputType: 'insertText' }));
      }
      return { ok: true, method: 'contenteditable' };
    }
    return { ok: false, error: '未找到回复框' };
  }

  function ensurePanel() {
    let panel = document.getElementById(PANEL_ID);
    if (panel) return panel;

    panel = document.createElement('div');
    panel.id = PANEL_ID;
    panel.className = 'x-toolkit-panel x-toolkit-comment';
    panel.innerHTML = `
      <div class="x-toolkit-head">
        <strong>评论助手</strong>
        <button type="button" class="x-toolkit-close" title="关闭">×</button>
      </div>
      <div class="x-toolkit-body">
        <p class="x-toolkit-hint">基于主贴与前几条回复生成候选（需在 popup 配置 LLM）</p>
        <div class="x-toolkit-actions">
          <button type="button" id="x-toolkit-gen-comment" class="x-toolkit-btn primary">生成评论</button>
          <button type="button" id="x-toolkit-refresh-ctx" class="x-toolkit-btn">刷新上下文</button>
        </div>
        <pre id="x-toolkit-ctx-preview" class="x-toolkit-pre"></pre>
        <div id="x-toolkit-comment-status" class="x-toolkit-status"></div>
        <div id="x-toolkit-comment-list" class="x-toolkit-list"></div>
        <div class="x-toolkit-foot">
          <button type="button" id="x-toolkit-insert-comment" class="x-toolkit-btn primary" disabled>填入回复框</button>
          <button type="button" id="x-toolkit-copy-comment" class="x-toolkit-btn" disabled>复制</button>
        </div>
      </div>
    `;
    document.body.appendChild(panel);

    panel.querySelector('.x-toolkit-close').addEventListener('click', () => panel.classList.add('hidden'));
    panel.querySelector('#x-toolkit-refresh-ctx').addEventListener('click', refreshPreview);
    panel.querySelector('#x-toolkit-gen-comment').addEventListener('click', generate);
    panel.querySelector('#x-toolkit-insert-comment').addEventListener('click', () => insertSelected());
    panel.querySelector('#x-toolkit-copy-comment').addEventListener('click', () => copySelected());

    return panel;
  }

  function setStatus(text, kind) {
    const el = document.getElementById('x-toolkit-comment-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'x-toolkit-status' + (kind ? ` ${kind}` : '');
  }

  function refreshPreview() {
    const ctx = extractStatusContext();
    const pre = document.getElementById('x-toolkit-ctx-preview');
    if (!pre) return ctx;
    if (!ctx?.mainText) {
      pre.textContent = '未读到主贴，请等待页面加载完成';
      return null;
    }
    const lines = [`主贴 @${ctx.mainAuthor || '?'}`, ctx.mainText];
    if (ctx.replies.length) {
      lines.push('', '前几条回复：');
      ctx.replies.forEach((r) => lines.push(`${r.index}. ${r.author}: ${r.text.slice(0, 120)}`));
    }
    pre.textContent = lines.join('\n');
    return ctx;
  }

  function renderList() {
    const box = document.getElementById('x-toolkit-comment-list');
    const btnI = document.getElementById('x-toolkit-insert-comment');
    const btnC = document.getElementById('x-toolkit-copy-comment');
    if (!box) return;
    if (!candidates.length) {
      box.innerHTML = '<p class="x-toolkit-empty">尚无候选</p>';
      btnI.disabled = true;
      btnC.disabled = true;
      return;
    }
    box.innerHTML = candidates
      .map(
        (t, i) => `
      <label class="x-toolkit-candidate${i === selected ? ' selected' : ''}">
        <input type="radio" name="x-comment-pick" value="${i}" ${i === selected ? 'checked' : ''} />
        <span>${escapeHtml(t)}</span>
      </label>`
      )
      .join('');
    box.querySelectorAll('input').forEach((inp) => {
      inp.addEventListener('change', () => {
        selected = Number(inp.value);
        renderList();
      });
    });
    btnI.disabled = false;
    btnC.disabled = false;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  async function generate() {
    const ctx = refreshPreview();
    if (!ctx?.mainText) {
      setStatus('请先打开贴文详情页', 'err');
      return;
    }
    setStatus('生成中…');
    try {
      const res = await chrome.runtime.sendMessage({
        type: 'GENERATE_COMMENTS',
        payload: ctx,
      });
      if (!res?.ok) throw new Error(res?.error || '生成失败');
      candidates = res.items || [];
      selected = 0;
      renderList();
      setStatus(`已生成 ${candidates.length} 条`, 'ok');
    } catch (e) {
      setStatus(String(e.message || e), 'err');
    }
  }

  async function insertSelected() {
    if (!candidates[selected]) return;
    const r = await insertReply(candidates[selected]);
    setStatus(r.method === 'copied' ? '已复制（未找到回复框）' : '已填入回复框', 'ok');
  }

  async function copySelected() {
    if (!candidates[selected]) return;
    await navigator.clipboard.writeText(candidates[selected]);
    setStatus('已复制', 'ok');
  }

  function ensureFab() {
    if (document.getElementById('x-toolkit-comment-fab')) return;
    const fab = document.createElement('button');
    fab.id = 'x-toolkit-comment-fab';
    fab.className = 'x-toolkit-fab';
    fab.type = 'button';
    fab.title = '评论助手';
    fab.textContent = '💬';
    fab.addEventListener('click', () => {
      const panel = ensurePanel();
      panel.classList.remove('hidden');
      refreshPreview();
    });
    document.body.appendChild(fab);
  }

  function init() {
    if (!isStatusPage()) return;
    ensureFab();
    ensurePanel();
    refreshPreview();
  }

  return { init, extractStatusContext, insertReply, isStatusPage };
})();

if (typeof window !== 'undefined') window.CommentPanel = CommentPanel;
