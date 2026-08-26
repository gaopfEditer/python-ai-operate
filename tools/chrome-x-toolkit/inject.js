/**
 * 注入 MAIN world：拦截 X 站内 fetch，捕获 Bearer / CSRF / GraphQL queryId
 */
(function () {
  if (window.__XToolkitInjected) return;
  window.__XToolkitInjected = true;

  const STORE_KEY = '__x_toolkit_api_capture';
  const OP_RE = /\/i\/api\/graphql\/([^/]+)\/(\w+)/;

  function loadStore() {
    try {
      return JSON.parse(sessionStorage.getItem(STORE_KEY) || '{}') || {};
    } catch (_) {
      return {};
    }
  }

  function saveStore(patch) {
    const prev = loadStore();
    const next = { ...prev, ...patch, updatedAt: Date.now() };
    if (patch.queryIds) {
      next.queryIds = { ...(prev.queryIds || {}), ...patch.queryIds };
    }
    try {
      sessionStorage.setItem(STORE_KEY, JSON.stringify(next));
    } catch (_) {
      /* ignore quota */
    }
    window.postMessage({ source: 'x-toolkit-inject', type: 'API_CAPTURE', payload: next }, '*');
    return next;
  }

  function pickHeaders(h) {
    if (!h) return {};
    const get = (k) => (typeof h.get === 'function' ? h.get(k) : h[k]);
    const out = {};
    const auth = get('authorization') || get('Authorization');
    const csrf = get('x-csrf-token') || get('X-Csrf-Token');
    const guest = get('x-guest-token') || get('X-Guest-Token');
    if (auth) out.authorization = auth;
    if (csrf) out.csrf = csrf;
    if (guest) out.guestToken = guest;
    return out;
  }

  function captureFromRequest(url, headers) {
    const u = String(url || '');
    if (!u.includes('/i/api/')) return;
    const patch = pickHeaders(headers);
    const m = u.match(OP_RE);
    if (m) {
      patch.queryIds = { [m[2]]: m[1] };
    }
    if (Object.keys(patch).length) saveStore(patch);
  }

  const origFetch = window.fetch;
  window.fetch = async function (input, init) {
    try {
      const url = typeof input === 'string' ? input : input?.url;
      const headers = init?.headers || (input instanceof Request ? input.headers : null);
      captureFromRequest(url, headers);
    } catch (_) {
      /* ignore */
    }
    return origFetch.apply(this, arguments);
  };

  const XHROpen = XMLHttpRequest.prototype.open;
  const XHRSend = XMLHttpRequest.prototype.send;
  const XHRSetHeader = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__xToolkitUrl = url;
    this.__xToolkitHeaders = {};
    return XHROpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
    this.__xToolkitHeaders[k.toLowerCase()] = v;
    return XHRSetHeader.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    try {
      captureFromRequest(this.__xToolkitUrl, this.__xToolkitHeaders);
    } catch (_) {
      /* ignore */
    }
    return XHRSend.apply(this, arguments);
  };

  // 初始广播
  const existing = loadStore();
  if (Object.keys(existing).length) {
    window.postMessage({ source: 'x-toolkit-inject', type: 'API_CAPTURE', payload: existing }, '*');
  }
})();
