/**
 * X 工具箱 content script：注入 hook、消息路由
 */
/* global XApi, CommentPanel, BatchOverlay */

(function () {
  function injectHook() {
    if (document.documentElement.dataset.xToolkitInject) return;
    document.documentElement.dataset.xToolkitInject = '1';
    const s = document.createElement('script');
    s.src = chrome.runtime.getURL('inject.js');
    s.onload = () => s.remove();
    (document.head || document.documentElement).appendChild(s);
  }

  injectHook();

  window.addEventListener('message', (ev) => {
    if (ev.source !== window) return;
    const msg = ev.data;
    if (!msg || msg.source !== 'x-toolkit-inject' || msg.type !== 'API_CAPTURE') return;
    XApi.mergeCreds(msg.payload || {});
    chrome.storage.local.set({ xApiCapture: msg.payload || {} });
  });

  chrome.storage.local.get(['xApiCapture'], (data) => {
    if (data.xApiCapture) XApi.mergeCreds(data.xApiCapture);
  });

  function bootUi() {
    try {
      CommentPanel.init();
    } catch (e) {
      console.warn('[x-toolkit] comment panel', e);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootUi);
  } else {
    bootUi();
  }

  // SPA 路由变化
  let lastPath = location.pathname;
  setInterval(() => {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      bootUi();
    }
  }, 1200);

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    (async () => {
      try {
        if (msg.type === 'GET_API_STATUS') {
          const c = XApi.creds || {};
          sendResponse({
            ok: true,
            hasAuth: Boolean(c.authorization),
            hasCsrf: Boolean(c.csrf || document.cookie.includes('ct0=')),
            queryIds: Object.keys(c.queryIds || {}),
          });
          return;
        }
        if (msg.type === 'SCAN_CLEANUP') {
          const data = await BatchOverlay.runScan(msg.payload || {});
          sendResponse({ ok: true, ...data });
          return;
        }
        if (msg.type === 'RUN_CLEANUP') {
          const res = await BatchOverlay.runDelete(msg.items || [], msg.delayMs || 1200);
          sendResponse({ ok: true, ...res });
          return;
        }
        if (msg.type === 'EXTRACT_STATUS') {
          sendResponse({ ok: true, ctx: CommentPanel.extractStatusContext?.() });
          return;
        }
        sendResponse({ ok: false, error: 'unknown' });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  });
})();
