const $ = (sel) => document.querySelector(sel);

const state = {
  lastCreate: { title: "", content: "", path: "" },
  listTarget: "signals",
  knownTags: [],
  counts: { all: 0, active: 0, archived: 0, watch_later: 0, tagged: 0 },
  platforms: [],
  newsPlatform: "",
  historyPlatform: "",
  taskStatus: "all",
  corpusSelected: new Set(),
  corpusItems: [],
  labFormula: localStorage.getItem("labFormula") || "contrarian",
  labProfile: localStorage.getItem("labProfile") || "general",
  labMaterialCategory: localStorage.getItem("labMaterialCategory") || "all",
  labMaterialCategories: [],
  labContentMix: [],
  labCategoryTemplates: [],
  labTagFilter: "",
  labVariants: [],
  labActiveVariant: null,
  labImagePick: new Set(),
  labMode: localStorage.getItem("appLabMode") || "lab",
  memosItems: [],
  memosPick: new Set(),
  memosNextPageToken: "",
  memosTags: [],
  memosEditIndex: -1,
  memosBaseUrl: "",
  labConfigActiveTab: "general",
  labConfigProfiles: [],
  sigMode: "list",
  sigConfig: {},
};

const APP_MAIN_TAB_LS = "appMainTab";
const APP_SIG_MODE_LS = "appSigMode";
const LAB_SESSION_KEY = "pai_lab_session";
const LAB_SESSION_MAX_BYTES = 2.5 * 1024 * 1024;
function readLabSession() {
  try {
    const raw = localStorage.getItem(LAB_SESSION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : null;
  } catch (_) {
    return null;
  }
}

function _labSlimCorpusItem(it) {
  if (!it || typeof it !== "object") return null;
  const factors = it.factors && typeof it.factors === "object" ? it.factors : {};
  return {
    id: it.id,
    source_title: it.source_title || "",
    hooks: it.hooks || "",
    pattern: it.pattern || "",
    emotion: it.emotion || "",
    tension: it.tension || "",
    keywords: Array.isArray(it.keywords) ? it.keywords.slice(0, 12) : [],
    tags: Array.isArray(it.tags) ? it.tags.slice(0, 12) : [],
    status: it.status || "active",
    factors: {
      material_category: factors.material_category || "",
      is_category_template: !!factors.is_category_template,
      narrative_type: factors.narrative_type || "",
      use_case: factors.use_case || "",
      hook: factors.hook || "",
    },
    raw_text: String(it.raw_text || "").slice(0, 1200),
  };
}

function _labSlimVariant(v) {
  if (!v || typeof v !== "object") return null;
  return {
    id: v.id || "",
    label: v.label || "",
    hook: String(v.hook || "").slice(0, 400),
    content: String(v.content || "").slice(0, 6000),
    featured: !!v.featured,
    generation_id: v.generation_id,
    images: Array.isArray(v.images)
      ? v.images.slice(0, 4).map((im) => ({ url: im?.url || "" }))
      : [],
  };
}

function snapshotLabSession() {
  try {
    const activeIdx = Math.max(
      0,
      (state.labVariants || []).indexOf(state.labActiveVariant)
    );
    const payload = {
      saved_at: Date.now(),
      tabs: {
        labMode: state.labMode || "lab",
        materialCategory: state.labMaterialCategory || "all",
        formula: state.labFormula || "contrarian",
        profile: state.labProfile || "general",
        corpusStatus: $("#corpusStatus")?.value ?? "active",
        tagFilter: state.labTagFilter || "",
      },
      forms: {
        topic: $("#regenTopic")?.value || "",
        prompt: $("#regenPrompt")?.value || "",
        style: $("#regenStyle")?.value || "X/Twitter",
        keyword: $("#corpusKeyword")?.value || "",
        capture: $("#labCaptureInput")?.value || "",
        xgrowthLimit: $("#xgrowthLimit")?.value || "8",
        xgrowthMinVel: $("#xgrowthMinVel")?.value || "0",
        xgrowthPotential: !!$("#xgrowthPotential")?.checked,
        xgrowthOpenTweet: !!$("#xgrowthOpenTweet")?.checked,
      },
      results: {
        selectedIds: [...(state.corpusSelected || [])].map(Number).filter(Boolean).slice(0, 3),
        corpusItems: (state.corpusItems || [])
          .slice(0, 80)
          .map(_labSlimCorpusItem)
          .filter(Boolean),
        variants: (state.labVariants || []).map(_labSlimVariant).filter(Boolean),
        activeVariantIdx: activeIdx,
        imagePick: [...(state.labImagePick || [])].map(Number).filter((i) => i >= 0),
        cot: Array.isArray(state.labCot) ? state.labCot.slice(0, 20).map(String) : [],
        promptSnippets: Array.isArray(state.labPromptSnippets)
          ? state.labPromptSnippets.slice(0, 12)
          : [],
        path: state.labPath || null,
      },
    };
    let raw = JSON.stringify(payload);
    if (raw.length > LAB_SESSION_MAX_BYTES) {
      payload.results.corpusItems = payload.results.corpusItems.slice(0, 30);
      payload.results.variants = (payload.results.variants || []).map((v) => ({
        ...v,
        content: String(v.content || "").slice(0, 2500),
      }));
      raw = JSON.stringify(payload);
    }
    localStorage.setItem(LAB_SESSION_KEY, raw);
    localStorage.setItem("labProfile", payload.tabs.profile);
    localStorage.setItem("labMaterialCategory", payload.tabs.materialCategory);
    localStorage.setItem("labFormula", payload.tabs.formula);
    localStorage.setItem("appLabMode", payload.tabs.labMode);
  } catch (_) {
    /* quota / private mode */
  }
}

let _labSessionSaveTimer = null;
function scheduleLabSessionSave() {
  if (_labSessionSaveTimer) clearTimeout(_labSessionSaveTimer);
  _labSessionSaveTimer = setTimeout(() => {
    _labSessionSaveTimer = null;
    snapshotLabSession();
  }, 280);
}

function restoreLabSessionTabsAndForms(cached) {
  const c = cached || readLabSession();
  if (!c) return null;
  const tabs = c.tabs || {};
  const forms = c.forms || {};
  if (tabs.labMode) state.labMode = tabs.labMode === "memos" ? "memos" : "lab";
  if (tabs.materialCategory) state.labMaterialCategory = String(tabs.materialCategory);
  if (tabs.formula) state.labFormula = String(tabs.formula);
  if (tabs.profile) state.labProfile = String(tabs.profile);
  if (tabs.tagFilter != null) state.labTagFilter = String(tabs.tagFilter || "");
  if ($("#corpusStatus") && tabs.corpusStatus != null) {
    $("#corpusStatus").value = tabs.corpusStatus;
  }
  if ($("#regenTopic") && forms.topic != null) $("#regenTopic").value = forms.topic;
  if ($("#regenPrompt") && forms.prompt != null) $("#regenPrompt").value = forms.prompt;
  if ($("#regenStyle") && forms.style) $("#regenStyle").value = forms.style;
  if ($("#corpusKeyword") && forms.keyword != null) $("#corpusKeyword").value = forms.keyword;
  if ($("#labCaptureInput") && forms.capture != null) $("#labCaptureInput").value = forms.capture;
  if ($("#xgrowthLimit") && forms.xgrowthLimit != null) $("#xgrowthLimit").value = forms.xgrowthLimit;
  if ($("#xgrowthMinVel") && forms.xgrowthMinVel != null) $("#xgrowthMinVel").value = forms.xgrowthMinVel;
  if ($("#xgrowthPotential") && forms.xgrowthPotential != null) {
    $("#xgrowthPotential").checked = !!forms.xgrowthPotential;
  }
  if ($("#xgrowthOpenTweet") && forms.xgrowthOpenTweet != null) {
    $("#xgrowthOpenTweet").checked = !!forms.xgrowthOpenTweet;
  }
  return c;
}

function restoreLabSessionResults(cached) {
  const c = cached || readLabSession();
  if (!c?.results) return false;
  const r = c.results;
  if (Array.isArray(r.corpusItems) && r.corpusItems.length) {
    // 仅在当前列表为空时用缓存结果垫底，避免覆盖刚拉到的新数据
    if (!(state.corpusItems || []).length) {
      state.corpusItems = r.corpusItems;
    }
  }
  if (Array.isArray(r.selectedIds) && r.selectedIds.length) {
    const alive = new Set((state.corpusItems || []).map((x) => Number(x.id)));
    const ids = r.selectedIds
      .map(Number)
      .filter((id) => alive.has(id) || !(state.corpusItems || []).length)
      .slice(0, 3);
    if (ids.length) state.corpusSelected = new Set(ids);
  }
  if (Array.isArray(r.variants) && r.variants.length) {
    const idx = Number(r.activeVariantIdx);
    if (Array.isArray(r.imagePick)) {
      state.labImagePick = new Set(r.imagePick.map(Number).filter((i) => i >= 0));
    }
    renderLabVariants(r.variants, Number.isFinite(idx) ? idx : 0);
  }
  if (Array.isArray(r.cot) && r.cot.length) {
    state.labCot = r.cot;
    renderLabCot(r.cot);
  }
  if (Array.isArray(r.promptSnippets) && r.promptSnippets.length) {
    state.labPromptSnippets = r.promptSnippets;
    renderLabPromptSnippets(r.promptSnippets);
  }
  if (r.path) {
    state.labPath = r.path;
    renderPathView(r.path);
  }
  renderCorpusItems(state.corpusItems || []);
  syncCorpusSelectionInput();
  if (typeof updateLabSteps === "function") updateLabSteps();
  return true;
}

function hydrateLabSessionOnEnter() {
  const cached = restoreLabSessionTabsAndForms();
  applyLabMode(state.labMode || "lab");
  return cached;
}

const APP_MAIN_TABS = [
  "signals",
  "realtime",
  "tweetcards",
  "corpus",
  "create",
  "publish",
];

/** CDP 发布页展示顺序与默认全选 */
const PUBLISH_PLATFORM_ORDER = [
  { id: "binance_square", name: "币安广场" },
  { id: "okx", name: "OKX" },
  { id: "bitget", name: "Bitget" },
  { id: "reddit", name: "Reddit" },
  { id: "x", name: "X / Twitter" },
];
const PUBLISH_PLATFORM_DEFAULT_IDS = PUBLISH_PLATFORM_ORDER.map((p) => p.id);

function platformMeta(pid) {
  const id = String(pid || "").toLowerCase();
  if (id === "x-cdp" || id === "x" || id === "twitter") {
    return { cls: "src-x", label: "X", tip: "来自 X / Twitter" };
  }
  if (id === "reddit") {
    return { cls: "src-reddit", label: "Reddit", tip: "来自 Reddit" };
  }
  if (id === "telegram" || id === "tg") {
    return { cls: "src-telegram", label: "Telegram", tip: "来自 Telegram" };
  }
  return { cls: "src-other", label: pid || "未知", tip: `来源 ${pid || "未知"}` };
}

function renderPlatformBadge(it) {
  const meta = platformMeta(it.platform_id);
  const label = it.platform_name || it.source || meta.label;
  const extra =
    it.subreddit
      ? ` · r/${escapeHtml(it.subreddit)}`
      : it.chat
        ? ` · ${escapeHtml(it.chat)}`
        : "";
  return `<span class="source-badge ${meta.cls}" title="${escapeAttr(meta.tip)}">来源 ${escapeHtml(label)}${extra}</span>`;
}

function platformBarModel(platforms) {
  const list = Array.isArray(platforms) ? platforms : [];
  const total = list.reduce((s, p) => s + Number(p.count || 0), 0);
  const known = [
    { id: "x-cdp", name: "X" },
    { id: "reddit", name: "Reddit" },
    { id: "telegram", name: "Telegram" },
  ];
  const byId = Object.fromEntries(list.map((p) => [String(p.id), p]));
  const items = [
    { id: "", name: "全部", count: total, cls: "" },
  ];
  known.forEach((k) => {
    const hit = byId[k.id] || list.find((p) => platformMeta(p.id).label === k.name);
    const id = hit ? hit.id : k.id;
    items.push({
      id,
      name: k.name,
      count: hit ? Number(hit.count || 0) : 0,
      cls: platformMeta(id).cls,
    });
  });
  list.forEach((p) => {
    if (known.some((k) => k.id === p.id || platformMeta(p.id).label === k.name)) return;
    items.push({
      id: p.id,
      name: p.name || p.id,
      count: Number(p.count || 0),
      cls: platformMeta(p.id).cls,
    });
  });
  return items;
}

function renderPlatformBar(containerId, platforms, activeId, onPick) {
  const box = $(containerId);
  if (!box) return;
  const items = platformBarModel(platforms);
  const sig = items.map((x) => x.id).join("|");
  // 结构未变：只改数字/选中态，避免整段重绘导致框宽来回跳
  if (box.dataset.sig === sig && box.querySelector("[data-platform]")) {
    items.forEach((it) => {
      const key = String(it.id ?? "");
      const btn = [...box.querySelectorAll("[data-platform]")].find(
        (el) => (el.getAttribute("data-platform") || "") === key
      );
      if (!btn) return;
      const em = btn.querySelector("em");
      if (em && em.textContent !== String(it.count)) em.textContent = String(it.count);
      btn.classList.toggle("on", String(activeId || "") === key);
      btn.classList.toggle("empty", !it.count && key !== "");
    });
    return;
  }
  box.dataset.sig = sig;
  box.innerHTML = items
    .map((it) => {
      const on = String(activeId || "") === String(it.id || "") ? " on" : "";
      const empty = !it.count && it.id !== "" ? " empty" : "";
      return `<button type="button" class="platform-chip ${it.cls}${on}${empty}" data-platform="${escapeAttr(it.id)}"><span class="chip-label">${escapeHtml(it.name)}</span><em>${it.count}</em></button>`;
    })
    .join("");
  box.querySelectorAll("[data-platform]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = btn.getAttribute("data-platform") || "";
      onPick(pid);
    });
  });
}

function setStatus(el, text, kind) {
  if (!el) return;
  el.textContent = text || "";
  el.style.color =
    kind === "error" ? "var(--danger)" : kind === "ok" ? "var(--ok)" : "var(--muted)";
}

function toast(text, kind) {
  let el = $("#toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = text || "";
  el.className = `toast show${kind ? ` ${kind}` : ""}`;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    el.classList.remove("show");
  }, 2200);
}

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
  } catch (e) {
    return { success: false, error: `网络错误: ${e?.message || e}` };
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok && data && !data.error) {
    data.error = `HTTP ${res.status}`;
  }
  return data;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function normalizeSigImgUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  if (!/twimg\.com|pbs\./i.test(raw)) return raw;
  try {
    const u = new URL(raw);
    if (!u.searchParams.get("format")) {
      const path = u.pathname.toLowerCase();
      let fmt = "jpg";
      if (path.endsWith(".png")) fmt = "png";
      else if (path.endsWith(".webp")) fmt = "webp";
      else if (path.endsWith(".gif")) fmt = "gif";
      u.searchParams.set("format", fmt);
    }
    u.searchParams.set("name", "large");
    return u.href;
  } catch (_) {
    return raw.includes("?") ? raw : `${raw}?format=jpg&name=large`;
  }
}

function sigImgSrc(im) {
  if (!im || typeof im !== "object") return "";
  if (im.rel) return `/api/signals/media?rel=${encodeURIComponent(im.rel)}`;
  return normalizeSigImgUrl(im.url || "");
}

function encodeData(s) {
  return encodeURIComponent(String(s || ""));
}

function decodeData(s) {
  try {
    return decodeURIComponent(String(s || ""));
  } catch (e) {
    return String(s || "");
  }
}

function updateCounts(counts, tags, platforms) {
  if (counts && typeof counts === "object") {
    state.counts = { ...state.counts, ...counts };
  }
  if (Array.isArray(tags)) {
    state.knownTags = tags;
  }
  if (Array.isArray(platforms)) {
    state.platforms = platforms;
  }
  const setCount = (id, n) => {
    const el = $(id);
    if (el) el.textContent = String(n || 0);
  };
  if (state.counts.corpus != null) setCount("#countCorpus", state.counts.corpus);
}

function refreshTagDatalist() {
  /* 资讯标签已下线 */
}

function renderTagCloud() {
  const box = $("#tagCloud");
  if (!box) return;
  const tags = state.knownTags || [];
  const active = ($("#tagsFilter")?.value || "").trim().toLowerCase();
  if (!tags.length) {
    box.dataset.sig = "";
    box.innerHTML = `<p class="muted">还没有标签。在资讯条目里点「添加标签」即可创建。</p>`;
    return;
  }
  const names = tags.map((t) => String(t.name || t));
  const sig = names.join("\0");
  if (box.dataset.sig === sig && box.querySelector("[data-filter-tag]")) {
    tags.forEach((t) => {
      const name = String(t.name || t);
      const btn = [...box.querySelectorAll("[data-filter-tag]")].find(
        (el) => el.getAttribute("data-filter-tag") === name
      );
      if (!btn) return;
      const em = btn.querySelector("em");
      if (em) em.textContent = String(t.count || 0);
      btn.classList.toggle("on", !!active && name.toLowerCase() === active);
    });
    return;
  }
  box.dataset.sig = sig;
  box.innerHTML = tags
    .map((t) => {
      const name = t.name || t;
      const count = t.count || 0;
      const on = active && String(name).toLowerCase() === active ? " on" : "";
      return `<button type="button" class="tag-chip cloud${on}" data-filter-tag="${escapeAttr(name)}">${escapeHtml(name)} <em>${count}</em></button>`;
    })
    .join("");
  box.querySelectorAll("[data-filter-tag]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.getAttribute("data-filter-tag") || "";
      if ($("#tagsFilter")) $("#tagsFilter").value = name;
      loadLibrary("tags");
    });
  });
}

function renderItemTags(tags, platformId, key, href) {
  const list = Array.isArray(tags) ? tags.filter(Boolean) : [];
  const chips = list
    .map(
      (t) =>
        `<button type="button" class="tag-chip" data-remove-tag="${escapeAttr(t)}" title="移除标签">${escapeHtml(t)} ×</button>`
    )
    .join("");
  return `
    <div class="tag-editor" data-platform-id="${encodeData(platformId)}" data-key="${encodeData(key)}" data-href="${encodeData(href)}">
      <div class="tag-row">${chips || `<span class="tag-empty">暂无标签</span>`}</div>
      <form class="tag-add-form">
        <input type="text" class="tag-input" list="knownTagsList" placeholder="输入标签，回车添加（可用逗号多个）" maxlength="40" />
        <button class="btn ghost btn-sm" type="submit">添加</button>
      </form>
    </div>`;
}

function renderItems(container, items, opts = {}) {
  if (!container) return;
  if (!items || !items.length) {
    container.innerHTML = `<div class="item"><h3>暂无数据</h3><p class="snippet newsList-item-snippet">${escapeHtml(opts.empty || "这里还没有内容。")}</p></div>`;
    return;
  }
  container.innerHTML = items
    .map((it) => {
      const stars = Number(it.star || 0);
      const useful = it.isUseful ? "有用" : "";
      const summary = (it.summary || "").trim();
      const snippet = summary || (it.content || it.raw || "").slice(0, 220);
      const isSummary = Boolean(summary);
      const archived = !!it.archived;
      const later = !!it.watch_later;
      const tags = Array.isArray(it.tags) ? it.tags : [];
      const pid = it.platform_id || "";
      const key = it.key || "";
      const href = it.href || key;
      return `
        <article class="item${archived ? " is-archived" : ""}${later ? " is-later" : ""}"
          data-platform-id="${encodeData(pid)}"
          data-key="${encodeData(key)}"
          data-href="${encodeData(href)}">
          <div class="item-head">
            ${renderPlatformBadge(it)}
            <h3>${escapeHtml(it.title || "(无标题)")}</h3>
          </div>
          <div class="meta">
            ${it.author ? `<span>@${escapeHtml(String(it.author).replace(/^@/, ""))}</span>` : ""}
            <span>${escapeHtml(it.fetched_at || "")}</span>
            ${useful ? `<span>${useful}</span>` : ""}
            ${stars ? `<span>★ ${stars}</span>` : ""}
            ${isSummary ? `<span>中文摘要</span>` : ""}
            ${archived ? `<span class="badge badge-archive">已归档${it.archived_at ? " · " + escapeHtml(it.archived_at) : ""}</span>` : ""}
            ${later ? `<span class="badge badge-later">稍后观看${it.watch_later_at ? " · " + escapeHtml(it.watch_later_at) : ""}</span>` : ""}
            ${href ? `<a href="${escapeAttr(href)}" target="_blank" rel="noreferrer">打开原文</a>` : ""}
          </div>
          ${
            snippet
              ? `<p class="snippet newsList-item-snippet">${escapeHtml(snippet)}</p>`
              : `<p class="snippet newsList-item-snippet muted">暂无摘要</p>`
          }
          ${renderItemTags(tags, pid, key, href)}
          <div class="item-actions">
            <button class="btn ghost btn-sm${archived ? " on" : ""}" type="button" data-action="toggle_archive">${archived ? "取消归档" : "归档"}</button>
            <button class="btn ghost btn-sm${later ? " on" : ""}" type="button" data-action="toggle_watch_later">${later ? "取消稍后" : "稍后观看"}</button>
            <button class="btn ghost btn-sm" type="button" data-action="deconstruct">拆解入库</button>
            <button class="btn ghost btn-sm" type="button" data-action="pick_synth">${(state.newsPicked || new Set()).has(`${pid}||${key}`) ? "已选合成" : "选入合成"}</button>
            <button class="btn ghost btn-sm" type="button" data-use-topic="${escapeAttr(it.title || "")}">用作创作主题</button>
          </div>
        </article>`;
    })
    .join("");

  bindItemActions(container);
}

function itemIdsFromEl(el) {
  const root = el.closest("[data-key]") || el;
  return {
    platform_id: decodeData(root.getAttribute("data-platform-id")),
    key: decodeData(root.getAttribute("data-key")),
    href: decodeData(root.getAttribute("data-href")),
  };
}

async function postMeta(payload) {
  return api("/api/posts/meta", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

function bindItemActions(container) {
  container.querySelectorAll("[data-use-topic]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const topic = btn.getAttribute("data-use-topic") || "";
      $("#createTopic").value = topic;
      switchTab("create");
    });
  });

  container.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ids = itemIdsFromEl(btn);
      const action = btn.getAttribute("data-action") || "";
      if (!ids.key || !action) return;
      btn.disabled = true;
      try {
        if (action === "deconstruct") {
          setStatus($("#crawlStatus"), "正在拆解入库…");
          const data = await api("/api/corpus/deconstruct", {
            method: "POST",
            body: JSON.stringify({
              platform_id: ids.platform_id,
              key: ids.key,
              href: ids.href,
            }),
          });
          if (!data.success) {
            toast(data.error || "拆解失败", "error");
            return;
          }
          const tid = data.template?.id;
          toast(tid ? `已入库模板 #${tid}` : "拆解完成", "ok");
          await refreshCorpusStats();
          return;
        }
        if (action === "pick_synth") {
          if (!state.newsPicked) state.newsPicked = new Set();
          const token = `${ids.platform_id || ""}||${ids.key || ""}`;
          if (state.newsPicked.has(token)) state.newsPicked.delete(token);
          else state.newsPicked.add(token);
          btn.textContent = state.newsPicked.has(token) ? "已选合成" : "选入合成";
          btn.classList.toggle("on", state.newsPicked.has(token));
          const n = state.newsPicked.size;
          setStatus($("#crawlStatus"), n ? `已选 ${n} 条待合成（去语料库点「合成已选帖」）` : "已清空合成选中", "ok");
          const badge = $("#synthPickedCount");
          if (badge) badge.textContent = String(n);
          return;
        }
        const data = await postMeta({ ...ids, action });
        if (!data.success) {
          toast(data.error || "操作失败", "error");
          return;
        }
        updateCounts(data.counts, data.tags);
        const item = data.item || {};
        if (action === "toggle_archive") {
          toast(item.archived ? "已归档" : "已取消归档", "ok");
        } else if (action === "toggle_watch_later") {
          toast(item.watch_later ? "已加入稍后观看" : "已取消稍后观看", "ok");
        }
        await reloadCurrentList();
      } catch (e) {
        toast(String(e), "error");
      } finally {
        btn.disabled = false;
      }
    });
  });

  container.querySelectorAll(".tag-add-form").forEach((form) => {
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const editor = form.closest(".tag-editor");
      const input = form.querySelector(".tag-input");
      const ids = itemIdsFromEl(editor);
      const raw = (input?.value || "").trim();
      if (!raw) return;
      const tags = raw
        .split(/[,，;；|]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      if (!tags.length) return;
      const submitBtn = form.querySelector("button[type=submit]");
      if (submitBtn) submitBtn.disabled = true;
      try {
        const data = await postMeta({
          ...ids,
          action: "add_tags",
          tags,
        });
        if (!data.success) {
          toast(data.error || "添加标签失败", "error");
          return;
        }
        if (input) input.value = "";
        updateCounts(data.counts, data.tags);
        toast(`已添加标签：${tags.join("、")}`, "ok");
        await reloadCurrentList();
      } catch (e) {
        toast(String(e), "error");
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  });

  container.querySelectorAll("[data-remove-tag]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ids = itemIdsFromEl(btn);
      const tag = btn.getAttribute("data-remove-tag") || "";
      if (!ids.key || !tag) return;
      btn.disabled = true;
      try {
        const data = await postMeta({
          ...ids,
          action: "remove_tags",
          tags: [tag],
        });
        if (!data.success) {
          toast(data.error || "移除失败", "error");
          return;
        }
        updateCounts(data.counts, data.tags);
        toast(`已移除标签：${tag}`, "ok");
        await reloadCurrentList();
      } catch (e) {
        toast(String(e), "error");
      } finally {
        btn.disabled = false;
      }
    });
  });
}

function switchTab(name) {
  if (!APP_MAIN_TABS.includes(name)) return;
  document.querySelectorAll(".tab").forEach((tab) => {
    const on = tab.dataset.tab === name;
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".panel").forEach((panel) => {
    const on = panel.id === `panel-${name}`;
    panel.classList.toggle("active", on);
    panel.hidden = !on;
  });
  try {
    localStorage.setItem(APP_MAIN_TAB_LS, name);
  } catch (_) {
    /* ignore quota */
  }
  if (name === "corpus") {
    const cached = hydrateLabSessionOnEnter();
    loadLabMaterials().then(() => {
      renderLabMaterialTabs();
      renderLabContentMix();
    });
    loadLabFormulas();
    if (cached) restoreLabSessionResults(cached);
    loadCorpus().then(() => {
      if (cached) {
        const r = cached.results || {};
        if (Array.isArray(r.selectedIds) && r.selectedIds.length) {
          const alive = new Set((state.corpusItems || []).map((x) => Number(x.id)));
          const ids = r.selectedIds.map(Number).filter((id) => alive.has(id)).slice(0, 3);
          if (ids.length) {
            state.corpusSelected = new Set(ids);
            renderCorpusItems(state.corpusItems || []);
            syncCorpusSelectionInput();
          }
        }
        if (Array.isArray(r.variants) && r.variants.length && !(state.labVariants || []).length) {
          restoreLabSessionResults(cached);
        }
      }
      scheduleLabSessionSave();
    });
    loadGenerations();
  }
  if (name === "signals") {
    restoreSigModeFromStorage();
    loadSignalsPanel();
  }
  if (name === "realtime") {
    loadRealtimePanel();
  }
  if (name === "tweetcards") { loadTweetCards(); }
  if (name === "publish") {
    loadPublishPlatforms(loadPublishPrefs().platforms || undefined);
    restorePublishPrefsFields();
    restorePublishWorkbenchMode();
  }
}

async function refreshHealth() {
  try {
    const data = await api("/api/health");
    $("#healthDot").className = "dot " + (data.ok ? "ok" : "bad");
    $("#healthText").textContent = data.ok
      ? `在线 · ${data.time || ""}`
      : "服务异常";
  } catch (e) {
    $("#healthDot").className = "dot bad";
    $("#healthText").textContent = "无法连接后端";
  }
}

async function refreshStats() {
  /* 资讯入库已下线 */
}

async function loadPosts(keyword, platform, target, view, tag) {
  const qs = new URLSearchParams();
  if (keyword) qs.set("keyword", keyword);
  if (platform) qs.set("platform", platform);
  if (view) qs.set("view", view);
  if (tag) qs.set("tag", tag);
  qs.set("limit", "120");
  const data = await api(`/api/posts?${qs.toString()}`);
  if (!data.success) {
    const statusEl =
      target === "history"
        ? $("#historyMeta")
        : target === "later"
          ? $("#laterMeta")
          : target === "archived"
            ? $("#archivedMeta")
            : target === "tags"
              ? $("#tagsMeta")
              : $("#crawlStatus");
    setStatus(statusEl, data.error || "加载失败", "error");
    return;
  }
  state.listTarget = target;
  updateCounts(data.counts, data.tags, data.platforms || data.matched_platforms);

  const metaMap = {
    history: $("#historyMeta"),
    later: $("#laterMeta"),
    archived: $("#archivedMeta"),
    tags: $("#tagsMeta"),
    news: $("#crawlStatus"),
  };
  const listMap = {
    history: $("#historyList"),
    later: $("#laterList"),
    archived: $("#archivedList"),
    tags: $("#tagsList"),
    news: $("#newsList"),
  };
  const emptyMap = {
    later: "还没有稍后观看的内容，在资讯条目点「稍后观看」。",
    archived: "还没有归档内容。",
    tags: tag ? `没有带「${tag}」标签的帖子。` : "选择一个标签查看对应帖子。",
    history: platform
      ? `当前来源暂无匹配内容。若 Reddit/Telegram 为 0，请检查代理或 Telegram 会话后重新抓取。`
      : "换个关键词，或先执行一次抓取。",
    news: platform
      ? `当前来源暂无匹配内容。点「全部」可看其它平台；Reddit 需可用代理，Telegram 需登录会话。`
      : "换个关键词，或先勾选平台后执行抓取。",
  };

  const platText = (data.matched_platforms || [])
    .map((p) => `${p.name}:${p.count}`)
    .join(" · ");
  const label =
    target === "news"
      ? `匹配 ${data.total} 条${platText ? `（${platText}）` : ""}`
      : `共 ${data.total} 条${platText ? `（${platText}）` : ""}` +
        (data.generated_at ? ` · 缓存 ${data.generated_at}` : "");
  setStatus(metaMap[target], label, "ok");
  renderItems(listMap[target], data.items, { empty: emptyMap[target] });
}

async function loadLibrary(kind) {
  if (kind === "later") {
    await loadPosts($("#laterKeyword")?.value.trim() || "", "", "later", "watch_later", "");
  } else if (kind === "archived") {
    await loadPosts(
      $("#archivedKeyword")?.value.trim() || "",
      "",
      "archived",
      "archived",
      ""
    );
  } else if (kind === "tags") {
    const tag = $("#tagsFilter")?.value.trim() || "";
    await refreshStats();
    if (!tag) {
      state.listTarget = "tags";
      setStatus($("#tagsMeta"), "点击上方标签筛选，或输入标签后回车", "ok");
      renderItems($("#tagsList"), [], { empty: "选择一个标签查看对应帖子。" });
      return;
    }
    await loadPosts("", "", "tags", "all", tag);
  }
}

const LAYER_LABEL = {
  collect: "采集",
  deconstruct: "拆解",
  store: "入库",
  generate: "再生成",
};

const LAB_FORMULAS_FALLBACK = [
  { id: "contrarian", label: "反常识批判风", emoji: "⚡", blurb: "否定直觉 → 隐藏代价 → 底层解法" },
  { id: "build_public", label: "Build in Public 复盘", emoji: "🧪", blurb: "踩坑数据 → 实验对比 → 通用经验" },
  { id: "absurd", label: "荒诞讽刺风", emoji: "🎭", blurb: "严肃日常 → 荒谬反转 → 时代痛点" },
  { id: "checklist", label: "硬核极简清单", emoji: "🛠️", blurb: "痛点 → 3点建议 → 落地指令" },
];

const LAB_PROFILE_MATERIAL_MAP = {
  general: "x_hot",
  technical: "market",
  longform_video: "thread",
};

const LAB_PROFILES_FALLBACK = [
  {
    id: "general",
    label: "通用短贴",
    emoji: "📝",
    blurb: "归纳可复用提示词 + A/B/C 三版短贴",
    variant_hint: "A 刺眼 · B 干货 · C 故事",
  },
  {
    id: "technical",
    label: "行情/宏观技术分析",
    emoji: "📊",
    blurb: "技术面 · 宏观 · 交易计划（美联储/数据）",
    variant_hint: "A 技术面 · B 宏观 · C 交易计划",
  },
  {
    id: "longform_video",
    label: "结构化长文·转视频",
    emoji: "🎬",
    blurb: "口播大纲 · 分镜 · 完整视频稿",
    variant_hint: "A 口播大纲 · B 分镜 · C 完整稿",
  },
];

function updateLabSteps() {
  const steps = document.querySelectorAll("#labSteps [data-step]");
  if (!steps.length) return;
  const hasCards = (state.corpusSelected || new Set()).size > 0;
  const hasTopic = Boolean($("#regenTopic")?.value.trim());
  const hasVariants = Boolean((state.labVariants || []).length);
  const hasPick = Boolean(state.labActiveVariant?.content);
  const active = hasPick ? 4 : hasVariants ? 4 : hasTopic && hasCards ? 3 : hasTopic || hasCards ? 2 : 1;
  steps.forEach((el) => {
    const n = Number(el.getAttribute("data-step"));
    el.classList.toggle("on", n === active);
    el.classList.toggle("done", n < active);
  });
}

function syncCorpusSelectionInput() {
  const ids = [...(state.corpusSelected || [])].sort((a, b) => a - b);
  const el = $("#regenTemplateIds");
  if (el) el.value = ids.join(", ");
  renderLabBlocks();
  const badge = $("#labTrayBadge");
  if (badge) badge.textContent = `已选 ${ids.length}/3`;
  const meta = $("#corpusMeta");
  if (meta) meta.textContent = `${(state.corpusItems || []).length} 张语料`;
  if (typeof updateLabSteps === "function") updateLabSteps();
  scheduleLabSessionSave();
}

function renderLabBlocks() {
  const box = $("#labBlocks");
  const hint = $("#labBlocksHint");
  if (!box) return;
  const ids = [...(state.corpusSelected || [])];
  if (!ids.length) {
    box.innerHTML = "";
    if (hint) hint.hidden = false;
    return;
  }
  if (hint) hint.hidden = true;
  box.innerHTML = ids
    .map((id) => {
      const it = (state.corpusItems || []).find((x) => Number(x.id) === id) || { id };
      const factors = it.factors || {};
      const hook = it.hooks || factors.hook || it.pattern || "";
      const narrative = factors.narrative_type || it.emotion || "灵感";
      return `<div class="lab-block" data-id="${escapeAttr(String(id))}">
        <span class="lab-block-badge">${escapeHtml(String(narrative).slice(0, 8))}</span>
        <p>${escapeHtml(String(hook).slice(0, 72))}</p>
        <button type="button" class="lab-block-x" data-remove-block="${escapeAttr(String(id))}" title="移除">×</button>
      </div>`;
    })
    .join("");
  box.querySelectorAll("[data-remove-block]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.getAttribute("data-remove-block"));
      state.corpusSelected.delete(id);
      renderCorpusItems(state.corpusItems || []);
      syncCorpusSelectionInput();
    });
  });
}

function renderLabFormulas(items) {
  const box = $("#labFormulas");
  if (!box) return;
  const list = items && items.length ? items : LAB_FORMULAS_FALLBACK;
  if (!state.labFormula) state.labFormula = list[0].id;
  box.innerHTML = list
    .map((f) => {
      const on = state.labFormula === f.id ? " on" : "";
      return `<button type="button" class="lab-formula${on}" data-formula="${escapeAttr(f.id)}">
        <strong>${escapeHtml((f.emoji || "") + " " + (f.label || f.id))}</strong>
        <span>${escapeHtml(f.blurb || "")}</span>
      </button>`;
    })
    .join("");
  box.querySelectorAll("[data-formula]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.labFormula = btn.getAttribute("data-formula");
      box.querySelectorAll(".lab-formula").forEach((b) => b.classList.toggle("on", b === btn));
      scheduleLabSessionSave();
    });
  });
}

async function loadLabFormulas() {
  try {
    const [formulas, profiles] = await Promise.all([
      api("/api/corpus/lab/formulas"),
      api("/api/corpus/lab/profiles"),
    ]);
    renderLabFormulas(formulas.items || LAB_FORMULAS_FALLBACK);
    renderLabProfiles(profiles.items || LAB_PROFILES_FALLBACK);
    syncLabConfigCustomHint(profiles.customized);
  } catch (e) {
    renderLabFormulas(LAB_FORMULAS_FALLBACK);
    renderLabProfiles(LAB_PROFILES_FALLBACK);
  }
}

function labProfileMaterialCategory(profileId) {
  return LAB_PROFILE_MATERIAL_MAP[String(profileId || "").trim()] || "all";
}

function applyLabProfileMaterialFilter({ reload = true } = {}) {
  const cat = labProfileMaterialCategory(state.labProfile);
  const prev = state.labMaterialCategory || "all";
  if (cat === prev) {
    if (reload) loadCategoryTemplates();
    return false;
  }
  state.labMaterialCategory = cat;
  localStorage.setItem("labMaterialCategory", cat);
  state.corpusSelected = new Set();
  renderLabMaterialTabs();
  if (reload) loadCorpus();
  return true;
}

function renderLabProfiles(items) {
  const box = $("#labProfiles");
  if (!box) return;
  const list = items && items.length ? items : LAB_PROFILES_FALLBACK;
  if (!state.labProfile) state.labProfile = list[0].id;
  box.innerHTML = list
    .map((p) => {
      const on = state.labProfile === p.id ? " on" : "";
      return `<button type="button" class="lab-profile${on}" data-profile="${escapeAttr(p.id)}" title="${escapeAttr(p.blurb || "")}">
        <strong>${escapeHtml((p.emoji || "") + " " + (p.label || p.id))}</strong>
        <span>${escapeHtml(p.blurb || "")}</span>
      </button>`;
    })
    .join("");
  box.querySelectorAll("[data-profile]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.labProfile = btn.getAttribute("data-profile");
      localStorage.setItem("labProfile", state.labProfile || "general");
      box.querySelectorAll(".lab-profile").forEach((b) => b.classList.toggle("on", b === btn));
      syncLabProfileHint(list);
      applyLabProfileMaterialFilter({ reload: true });
      scheduleLabSessionSave();
    });
  });
  syncLabProfileHint(list);
}

function syncLabProfileHint(list) {
  const hint = $("#labProfileHint");
  const variantHint = $("#labVariantHint");
  const profiles = list || LAB_PROFILES_FALLBACK;
  const p = profiles.find((x) => x.id === state.labProfile) || profiles[0];
  const mat = labProfileMaterialCategory(state.labProfile);
  const matLabel = mat !== "all" ? materialCategoryLabel(mat) : "";
  if (hint && p) {
    hint.textContent = matLabel
      ? `${p.blurb || ""} · 左侧语料：${matLabel}`
      : p.blurb || "";
  }
  if (variantHint && p?.variant_hint) variantHint.textContent = p.variant_hint;
}

function syncLabConfigCustomHint(customized) {
  const el = $("#labConfigCustomHint");
  const btn = $("#btnLabProfileConfig");
  if (el) {
    el.textContent = customized
      ? "当前使用自定义配置（config/lab_prompt_profiles.yaml）"
      : "当前为内置默认；保存后将写入 config/lab_prompt_profiles.yaml";
  }
  if (btn) btn.classList.toggle("is-custom", !!customized);
}

function renderLabProfileConfigForm(profiles) {
  const tabs = $("#labConfigTabs");
  const panels = $("#labConfigPanels");
  if (!tabs || !panels) return;
  const list = profiles?.length
    ? profiles
    : LAB_PROFILES_FALLBACK.map((p) => ({
        ...p,
        system: "",
        max_tokens: 2200,
        temperature: 0.8,
        output_extra: [],
      }));
  if (!list.find((p) => p.id === state.labConfigActiveTab)) {
    state.labConfigActiveTab = list[0]?.id || "general";
  }
  tabs.innerHTML = list
    .map((p) => {
      const active = p.id === state.labConfigActiveTab;
      return `<button type="button" class="lab-config-tab${active ? " on" : ""}" data-config-tab="${escapeAttr(p.id)}" role="tab" aria-selected="${active ? "true" : "false"}" aria-controls="lab-config-panel-${escapeAttr(p.id)}">${escapeHtml(`${p.emoji || ""} ${p.label || p.id}`.trim())}</button>`;
    })
    .join("");
  panels.innerHTML = list
    .map((p) => {
      const active = p.id === state.labConfigActiveTab;
      const extra = (p.output_extra || []).join(", ");
      return `<div id="lab-config-panel-${escapeAttr(p.id)}" class="lab-config-panel${active ? " is-active" : ""}" data-config-panel="${escapeAttr(p.id)}" role="tabpanel"${active ? "" : " hidden"}>
        <div class="form-grid lab-config-grid">
          <label class="field"><span>名称</span><input type="text" data-f="label" value="${escapeAttr(p.label || "")}" /></label>
          <label class="field"><span>Emoji</span><input type="text" data-f="emoji" value="${escapeAttr(p.emoji || "")}" maxlength="8" /></label>
          <label class="field full"><span>简介</span><input type="text" data-f="blurb" value="${escapeAttr(p.blurb || "")}" /></label>
          <label class="field full"><span>三版说明</span><input type="text" data-f="variant_hint" value="${escapeAttr(p.variant_hint || "")}" placeholder="A xxx · B xxx · C xxx" /></label>
          <label class="field"><span>max_tokens</span><input type="number" data-f="max_tokens" min="500" max="12000" step="100" value="${escapeAttr(String(p.max_tokens || 2200))}" /></label>
          <label class="field"><span>temperature</span><input type="number" data-f="temperature" min="0" max="2" step="0.05" value="${escapeAttr(String(p.temperature ?? 0.8))}" /></label>
          <label class="field full"><span>额外输出字段</span><input type="text" data-f="output_extra" value="${escapeAttr(extra)}" placeholder="如 prompt_snippets 或 video_meta，逗号分隔" /></label>
          <label class="field full lab-config-system"><span>System Prompt</span><textarea data-f="system" rows="16" spellcheck="false">${escapeHtml(p.system || "")}</textarea></label>
        </div>
      </div>`;
    })
    .join("");
}

function switchLabConfigTab(tabId) {
  if (!tabId) return;
  state.labConfigActiveTab = tabId;
  const tabs = $("#labConfigTabs");
  const panels = $("#labConfigPanels");
  tabs?.querySelectorAll("[data-config-tab]").forEach((btn) => {
    const on = btn.getAttribute("data-config-tab") === tabId;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  panels?.querySelectorAll("[data-config-panel]").forEach((panel) => {
    const on = panel.getAttribute("data-config-panel") === tabId;
    panel.hidden = !on;
    panel.classList.toggle("is-active", on);
  });
}

function bindLabConfigTabs() {
  const tabs = $("#labConfigTabs");
  if (!tabs || tabs.dataset.bound === "1") return;
  tabs.dataset.bound = "1";
  tabs.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-config-tab]");
    if (!btn) return;
    e.preventDefault();
    const id = btn.getAttribute("data-config-tab");
    if (!id || id === state.labConfigActiveTab) return;
    collectLabConfigDraft();
    switchLabConfigTab(id);
  });
}

function collectLabConfigDraft() {
  const panels = $("#labConfigPanels");
  if (!panels) return;
  const next = [];
  panels.querySelectorAll("[data-config-panel]").forEach((panel) => {
    const id = panel.getAttribute("data-config-panel");
    const item = { id };
    panel.querySelectorAll("[data-f]").forEach((el) => {
      item[el.getAttribute("data-f")] = el.value;
    });
    next.push(item);
  });
  if (next.length) state.labConfigProfiles = next;
}

function collectLabConfigProfiles() {
  collectLabConfigDraft();
  return (state.labConfigProfiles || []).map((p) => ({
    id: p.id,
    label: p.label,
    emoji: p.emoji,
    blurb: p.blurb,
    variant_hint: p.variant_hint,
    max_tokens: Number(p.max_tokens),
    temperature: Number(p.temperature),
    output_extra: String(p.output_extra || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    system: p.system,
  }));
}

async function openLabProfileConfig() {
  const dlg = $("#labProfileConfigDialog");
  if (!dlg) return;
  setStatus($("#labConfigStatus"), "加载中…");
  try {
    const data = await api("/api/corpus/lab/profiles/config");
    state.labConfigProfiles = data.items || [];
    syncLabConfigCustomHint(data.customized);
    renderLabProfileConfigForm(state.labConfigProfiles);
    bindLabConfigTabs();
    setStatus($("#labConfigStatus"), "");
    if (typeof dlg.showModal === "function") dlg.showModal();
  } catch (e) {
    toast(String(e), "error");
    setStatus($("#labConfigStatus"), "");
  }
}

async function saveLabProfileConfig(e) {
  e.preventDefault();
  const profiles = collectLabConfigProfiles();
  setStatus($("#labConfigStatus"), "保存中…");
  try {
    const data = await api("/api/corpus/lab/profiles/config", {
      method: "POST",
      body: JSON.stringify({ profiles }),
    });
    if (!data.success) {
      setStatus($("#labConfigStatus"), data.error || "保存失败", "error");
      return;
    }
    state.labConfigProfiles = data.items || profiles;
    syncLabConfigCustomHint(data.customized);
    await loadLabFormulas();
    toast("Prompt 配置已保存", "ok");
    $("#labProfileConfigDialog")?.close();
  } catch (err) {
    setStatus($("#labConfigStatus"), String(err), "error");
  }
}

async function resetLabProfileConfig() {
  if (!confirm("确定恢复为内置默认 Prompt？自定义文件将被删除。")) return;
  setStatus($("#labConfigStatus"), "恢复中…");
  try {
    const data = await api("/api/corpus/lab/profiles/config", {
      method: "POST",
      body: JSON.stringify({ reset: true }),
    });
    if (!data.success) {
      setStatus($("#labConfigStatus"), data.error || "恢复失败", "error");
      return;
    }
    state.labConfigProfiles = data.items || [];
    syncLabConfigCustomHint(false);
    renderLabProfileConfigForm(state.labConfigProfiles);
    bindLabConfigTabs();
    switchLabConfigTab(state.labConfigActiveTab);
    await loadLabFormulas();
    toast("已恢复默认 Prompt", "ok");
    setStatus($("#labConfigStatus"), "已恢复内置默认", "ok");
  } catch (err) {
    setStatus($("#labConfigStatus"), String(err), "error");
  }
}

function renderLabPromptSnippets(snippets) {
  const box = $("#labPromptSnippetsBox");
  const list = $("#labPromptSnippets");
  if (!box || !list) return;
  const arr = Array.isArray(snippets) ? snippets.filter(Boolean) : [];
  state.labPromptSnippets = arr;
  if (!arr.length) {
    box.hidden = true;
    list.innerHTML = "";
    return;
  }
  box.hidden = false;
  box.open = true;
  list.innerHTML = arr.map((s) => `<li>${escapeHtml(String(s))}</li>`).join("");
}

function renderLabTagCloud(items) {
  const box = $("#labTagCloud");
  if (!box) return;
  const counts = {};
  (items || []).forEach((it) => {
    (it.tags || []).forEach((t) => {
      const k = String(t || "").trim();
      if (!k) return;
      counts[k] = (counts[k] || 0) + 1;
    });
  });
  const top = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);
  if (!top.length) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = top
    .map(
      ([t, n]) =>
        `<button type="button" class="lab-tag${state.labTagFilter === t ? " on" : ""}" data-lab-tag="${escapeAttr(t)}">#${escapeHtml(t)} <em>${n}</em></button>`
    )
    .join("");
  box.querySelectorAll("[data-lab-tag]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const t = btn.getAttribute("data-lab-tag");
      state.labTagFilter = state.labTagFilter === t ? "" : t;
      if ($("#corpusKeyword")) {
        $("#corpusKeyword").value = state.labTagFilter ? `#${state.labTagFilter}` : "";
      }
      scheduleLabSessionSave();
      loadCorpus();
    });
  });
}

function renderPathView(pathObj) {
  const el = $("#corpusPathView");
  if (!el) return;
  state.labPath = pathObj || null;
  const steps = Array.isArray(pathObj?.steps) ? pathObj.steps : [];
  if (!steps.length) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.className = "path-view";
  el.innerHTML = `<ol class="path-flow">${steps
    .slice(-6)
    .map((s) => {
      const layer = LAYER_LABEL[s.layer] || s.layer || "";
      return `<li class="path-step" data-layer="${escapeAttr(s.layer || "")}"><span class="path-layer">${escapeHtml(layer)}</span></li>`;
    })
    .join("")}</ol>`;
}

function materialCategoryLabel(id) {
  const cid = String(id || "").trim();
  if (!cid || cid === "uncategorized") return "未分类";
  const hit = (state.labMaterialCategories || []).find((c) => c.id === cid);
  return hit?.label || cid;
}

function corpusMaterialCategory(it) {
  const factors = it?.factors || {};
  return String(factors.material_category || "").trim();
}

function isCorpusCategoryTemplate(it) {
  return !!(it?.factors || {}).is_category_template;
}

async function loadLabMaterials() {
  try {
    const data = await api("/api/corpus/lab/materials");
    state.labMaterialCategories = data.categories || [];
    state.labContentMix = data.content_mix || [];
    renderLabMaterialTabs();
    renderLabContentMix();
  } catch (_) {
    state.labMaterialCategories = [];
    state.labContentMix = [];
    renderLabMaterialTabs();
    renderLabContentMix();
  }
}

function renderLabContentMix() {
  const box = $("#labContentMix");
  if (!box) return;
  const mix = state.labContentMix || [];
  const cat = state.labMaterialCategory || "all";
  if (!mix.length || (cat && cat !== "all")) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  box.hidden = false;
  box.innerHTML =
    `<div class="lab-mix-head"><span>内容配比建议</span><em class="muted">立体交易员/投研人设</em></div>` +
    `<div class="lab-mix-bars">` +
    mix
      .map((row) => {
        const pct = Number(row.pct || 0);
        return `<button type="button" class="lab-mix-row" data-lab-mix="${escapeAttr(row.category || "")}" title="${escapeAttr(row.role || "")}">
          <span class="lab-mix-label">${escapeHtml(row.emoji || "")} ${escapeHtml(row.label || row.category || "")}</span>
          <span class="lab-mix-track"><i style="width:${pct}%"></i></span>
          <span class="lab-mix-pct">${pct}%</span>
        </button>`;
      })
      .join("") +
    `</div>`;
  box.querySelectorAll("[data-lab-mix]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-lab-mix") || "";
      if (!id) return;
      const tab = $(`#labMaterialTabs [data-lab-material="${CSS.escape(id)}"]`);
      if (tab) tab.click();
    });
  });
}

function renderLabMaterialTabs() {
  const box = $("#labMaterialTabs");
  if (!box) return;
  const cur = state.labMaterialCategory || "all";
  const cats = state.labMaterialCategories || [];
  const tabs = [
    { id: "all", label: "全部", emoji: "📚", count: cats.reduce((s, c) => s + Number(c.count || 0), 0) },
    ...cats.filter((c) => c.id !== "uncategorized" || Number(c.count || 0) > 0),
  ];
  box.innerHTML = tabs
    .map((c) => {
      const on = cur === c.id ? " on" : "";
      const tpl = Number(c.template_count || 0);
      const tplHint = tpl > 0 ? ` · 模板${tpl}` : "";
      return `<button type="button" class="lab-material-tab${on}" data-lab-material="${escapeAttr(c.id)}">${escapeHtml(c.emoji || "")} ${escapeHtml(c.label || c.id)}<em>${Number(c.count || 0)}${tplHint}</em></button>`;
    })
    .join("");
  box.querySelectorAll("[data-lab-material]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-lab-material") || "all";
      if (state.labMaterialCategory === id) return;
      state.labMaterialCategory = id;
      localStorage.setItem("labMaterialCategory", id);
      state.corpusSelected = new Set();
      state.labTagFilter = "";
      if ($("#corpusKeyword")) $("#corpusKeyword").value = "";
      renderLabMaterialTabs();
      renderLabContentMix();
      syncLabProfileHint();
      loadCorpus();
      scheduleLabSessionSave();
    });
  });
  fillCorpusMaterialSelect();
}

function fillCorpusMaterialSelect() {
  const sel = $("#editCorpusMaterial");
  if (!sel) return;
  const cur = sel.value;
  const opts = [
    `<option value="">（未分类）</option>`,
    ...(state.labMaterialCategories || [])
      .filter((c) => c.id !== "uncategorized")
      .map((c) => `<option value="${escapeAttr(c.id)}">${escapeHtml(c.label || c.id)}</option>`),
  ];
  sel.innerHTML = opts.join("");
  if (cur) sel.value = cur;
}

async function loadCategoryTemplates() {
  const cat = state.labMaterialCategory || "all";
  const wrap = $("#labCategoryTemplates");
  const list = $("#labCategoryTemplateList");
  if (!wrap || !list) return;
  if (!cat || cat === "all") {
    wrap.hidden = true;
    state.labCategoryTemplates = [];
    return;
  }
  try {
    const qs = new URLSearchParams({
      material_category: cat,
      category_template: "1",
      status: "active",
      limit: "24",
    });
    const data = await api(`/api/corpus/templates?${qs.toString()}`);
    state.labCategoryTemplates = data.items || [];
  } catch (_) {
    state.labCategoryTemplates = [];
  }
  const items = state.labCategoryTemplates || [];
  if (!items.length) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  list.innerHTML = items
    .map((it) => {
      const factors = it.factors || {};
      const title = it.source_title || "";
      const hook = it.hooks || factors.hook || it.pattern || title || "";
      const ex = factors.example && typeof factors.example === "object" ? factors.example : null;
      const exHook = ex?.hook || "";
      const exBody = ex?.body || "";
      const struct = Array.isArray(factors.structure) ? factors.structure : [];
      const structLine = struct.length
        ? `<div class="lab-tpl-struct">${escapeHtml(struct.map((s) => String(s)).join(" → ").slice(0, 160))}</div>`
        : "";
      const exBlock =
        exHook || exBody
          ? `<details class="lab-tpl-example"><summary>案例</summary>
              <p class="lab-tpl-ex-hook">${escapeHtml(String(exHook).slice(0, 160))}</p>
              <pre class="lab-tpl-ex-body">${escapeHtml(String(exBody).slice(0, 600))}</pre>
            </details>`
          : "";
      return `<div class="lab-category-template-item" data-tpl-id="${escapeAttr(String(it.id))}">
        <div class="lab-tpl-title"><strong>#${escapeHtml(String(it.id))}</strong> ${escapeHtml(String(title).replace(/^【模板】/, "").slice(0, 40))}</div>
        <div class="lab-tpl-hook">${escapeHtml(String(hook).slice(0, 120))}</div>
        ${structLine}${exBlock}
      </div>`;
    })
    .join("");
}

function narrativeBadge(it) {
  const factors = it.factors || {};
  return factors.narrative_type || it.emotion || "灵感";
}

function renderCorpusItems(items) {
  const box = $("#corpusList");
  if (!box) return;
  if (!state.corpusSelected) state.corpusSelected = new Set();
  let list = items || [];
  const cat = state.labMaterialCategory || "all";
  if (cat && cat !== "all") {
    list = list.filter((it) => {
      const mc = corpusMaterialCategory(it) || "uncategorized";
      return mc === cat;
    });
  }
  if (state.labTagFilter) {
    const tag = state.labTagFilter.toLowerCase();
    list = list.filter((it) => (it.tags || []).some((t) => String(t).toLowerCase() === tag));
  }
  if (!list.length) {
    const catLabel = cat && cat !== "all" ? materialCategoryLabel(cat) : "";
    box.innerHTML = `<div class="lab-empty">暂无${catLabel ? `「${escapeHtml(catLabel)}」` : ""}语料卡。切换素材类目、快捕或导入。</div>`;
    syncCorpusSelectionInput();
    return;
  }
  box.innerHTML = list
    .map((it) => {
      const factors = it.factors || {};
      const selected = state.corpusSelected.has(Number(it.id));
      const hook = it.hooks || factors.hook || it.pattern || it.source_title || "";
      const narrative = narrativeBadge(it);
      const mat = corpusMaterialCategory(it);
      const matBadge = mat
        ? `<span class="lab-material-badge">${escapeHtml(materialCategoryLabel(mat))}</span>`
        : "";
      const tplBadge = isCorpusCategoryTemplate(it)
        ? `<span class="lab-template-badge">类目模板</span>`
        : "";
      const tags = (it.tags || [])
        .slice(0, 3)
        .map((t) => `<span class="chip tag">#${escapeHtml(t)}</span>`)
        .join("");
      const tplAction = isCorpusCategoryTemplate(it)
        ? `<button type="button" data-corpus="unset_template">取消类目模板</button>`
        : `<button type="button" data-corpus="set_template">设为类目模板</button>`;
      return `
        <article class="lab-card${selected ? " is-selected" : ""}${isCorpusCategoryTemplate(it) ? " is-template" : ""}" data-id="${escapeAttr(String(it.id))}" data-corpus-card>
          <details class="lab-card-menu" onclick="event.stopPropagation()">
            <summary title="更多">···</summary>
            <div class="lab-card-menu-list">
              <button type="button" data-corpus="edit">编辑</button>
              ${tplAction}
              <button type="button" data-corpus="delete">删除</button>
            </div>
          </details>
          <div class="lab-card-badges">${tplBadge}${matBadge}<span class="lab-narrative">${escapeHtml(String(narrative).slice(0, 10))}</span></div>
          <p class="lab-hook">${escapeHtml(String(hook).slice(0, 140))}</p>
          <div class="chip-row">${tags}</div>
        </article>`;
    })
    .join("");

  const toggleCard = (id) => {
    if (!id) return;
    if (state.corpusSelected.has(id)) state.corpusSelected.delete(id);
    else {
      if (state.corpusSelected.size >= 3) {
        toast("最多选 3 张", "error");
        return;
      }
      state.corpusSelected.add(id);
    }
    renderCorpusItems(state.corpusItems || []);
    syncCorpusSelectionInput();
  };
  box.querySelectorAll("[data-corpus-card]").forEach((card) => {
    card.addEventListener("click", (e) => {
      if (e.target.closest("[data-corpus], .lab-card-menu")) return;
      toggleCard(Number(card.getAttribute("data-id") || 0));
    });
  });
  box.querySelectorAll("[data-corpus]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const root = btn.closest(".lab-card");
      const id = Number(root?.getAttribute("data-id") || 0);
      const action = btn.getAttribute("data-corpus");
      if (!id || !action) return;
      const item = (state.corpusItems || []).find((x) => Number(x.id) === id);
      if (action === "edit") {
        openCorpusEdit(item || { id });
        return;
      }
      if (action === "set_template") {
        const cat = state.labMaterialCategory;
        if (!cat || cat === "all") {
          toast("请先选择具体素材类目", "error");
          return;
        }
        await api(`/api/corpus/templates/${id}`, {
          method: "POST",
          body: JSON.stringify({
            action: "set_category_template",
            enabled: true,
            material_category: cat,
          }),
        });
        toast("已设为类目结构模板", "ok");
        await loadLabMaterials();
        await loadCorpus();
        return;
      }
      if (action === "unset_template") {
        await api(`/api/corpus/templates/${id}`, {
          method: "POST",
          body: JSON.stringify({ action: "set_category_template", enabled: false }),
        });
        toast("已取消类目模板", "ok");
        await loadLabMaterials();
        await loadCorpus();
        return;
      }
      if (action === "delete") {
        if (!window.confirm(`删除卡片 #${id}？`)) return;
        await api(`/api/corpus/templates/${id}`, {
          method: "POST",
          body: JSON.stringify({ action: "delete" }),
        });
        state.corpusSelected.delete(id);
        toast("已删除", "ok");
        await loadCorpus();
      }
    });
  });
  renderLabTagCloud(state.corpusItems || []);
  syncCorpusSelectionInput();
}

function openCorpusEdit(item) {
  const dlg = $("#corpusEditDialog");
  if (!dlg || !item) return;
  $("#editCorpusId").value = String(item.id || "");
  $("#editCorpusTitle").value = item.source_title || "";
  $("#editCorpusPattern").value = item.pattern || "";
  $("#editCorpusEmotion").value = item.emotion || "";
  $("#editCorpusTension").value = item.tension || "";
  $("#editCorpusKeywords").value = (item.keywords || []).join(", ");
  $("#editCorpusHooks").value = item.hooks || "";
  $("#editCorpusTags").value = (item.tags || []).join(", ");
  const matSel = $("#editCorpusMaterial");
  if (matSel) matSel.value = corpusMaterialCategory(item) || "";
  if (typeof dlg.showModal === "function") dlg.showModal();
  else dlg.setAttribute("open", "true");
}

function splitCsv(s) {
  return String(s || "")
    .split(/[,，]/)
    .map((x) => x.trim())
    .filter(Boolean);
}

async function saveCorpusEdit(ev) {
  if (ev) ev.preventDefault();
  const dlg = $("#corpusEditDialog");
  const id = Number($("#editCorpusId")?.value || 0);
  if (!id) return;
  const payload = {
    action: "update",
    source_title: $("#editCorpusTitle")?.value.trim() || "",
    pattern: $("#editCorpusPattern")?.value.trim() || "",
    emotion: $("#editCorpusEmotion")?.value.trim() || "",
    tension: $("#editCorpusTension")?.value.trim() || "",
    keywords: splitCsv($("#editCorpusKeywords")?.value),
    hooks: $("#editCorpusHooks")?.value.trim() || "",
    tags: splitCsv($("#editCorpusTags")?.value),
  };
  try {
    const data = await api(`/api/corpus/templates/${id}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!data.success) {
      toast(data.error || "保存失败", "error");
      return;
    }
    toast("已保存", "ok");
    if (dlg?.close) dlg.close();
    else dlg?.removeAttribute("open");
    await api(`/api/corpus/templates/${id}`, {
      method: "POST",
      body: JSON.stringify({
        action: "set_material_category",
        material_category: $("#editCorpusMaterial")?.value.trim() || "",
      }),
    });
    await loadLabMaterials();
    await loadCorpus();
  } catch (e) {
    toast(String(e), "error");
  }
}

async function createManualCorpus() {
  const pattern = window.prompt("句式模板", "关于【话题】，其实【反转】");
  if (!pattern) return;
  await api("/api/corpus/templates", {
    method: "POST",
    body: JSON.stringify({
      source_platform: "manual",
      source_key: `manual-${Date.now()}`,
      source_title: pattern.slice(0, 40),
      pattern,
      emotion: "共鸣",
      tension: "预期违背",
      tags: ["手动"],
    }),
  });
  await loadCorpus();
}

async function runLabCapture(ev) {
  if (ev) ev.preventDefault();
  const input = $("#labCaptureInput");
  const text = input?.value.trim() || "";
  if (!text) return;
  input.disabled = true;
  try {
    const data = await api("/api/corpus/capture", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    if (!data.success) {
      toast(data.error || "快捕失败", "error");
      return;
    }
    toast(data.message || "已入库", "ok");
    input.value = "";
    if (data.template) {
      const tid = Number(data.template.id);
      const cat = state.labMaterialCategory;
      if (tid && cat && cat !== "all") {
        try {
          await api(`/api/corpus/templates/${tid}`, {
            method: "POST",
            body: JSON.stringify({ action: "set_material_category", material_category: cat }),
          });
          data.template.factors = { ...(data.template.factors || {}), material_category: cat };
        } catch (_) {
          /* ignore */
        }
      }
      state.corpusItems = [data.template, ...(state.corpusItems || [])];
      state.corpusSelected.add(Number(data.template.id));
      // 保持最多 3 张选中
      const sel = [...state.corpusSelected];
      if (sel.length > 3) state.corpusSelected = new Set(sel.slice(0, 3));
      renderCorpusItems(state.corpusItems);
      syncCorpusSelectionInput();
      refreshCorpusStats();
    } else {
      await loadCorpus();
    }
  } catch (e) {
    toast(String(e), "error");
  } finally {
    input.disabled = false;
    input.focus();
  }
}

async function runCorpusSynthesizeRandom() {
  const btn = $("#btnSynthRandom");
  if (btn) btn.disabled = true;
  setStatus($("#synthStatus"), "随机合成中…");
  try {
    const data = await api("/api/corpus/synthesize", {
      method: "POST",
      body: JSON.stringify({ mode: "random", count: Number($("#synthCount")?.value || 3) }),
    });
    if (!data.success) {
      setStatus($("#synthStatus"), data.error || "失败", "error");
      return;
    }
    setStatus($("#synthStatus"), `已入库 #${data.template?.id}`, "ok");
    toast("合成完成", "ok");
    await loadCorpus();
  } catch (e) {
    setStatus($("#synthStatus"), String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runCorpusSynthesizePicked() {
  const picked = [...(state.newsPicked || [])];
  if (!picked.length) {
    setStatus($("#synthStatus"), "请先在资讯列表点「选入合成」", "error");
    return;
  }
  const btn = $("#btnSynthPicked");
  if (btn) btn.disabled = true;
  try {
    const refs = picked.map((token) => {
      const [platform_id, key] = String(token).split("||");
      return { platform_id, key };
    });
    const data = await api("/api/corpus/synthesize", {
      method: "POST",
      body: JSON.stringify({ mode: "specified", refs }),
    });
    if (!data.success) {
      setStatus($("#synthStatus"), data.error || "失败", "error");
      return;
    }
    state.newsPicked = new Set();
    const badge = $("#synthPickedCount");
    if (badge) badge.textContent = "0";
    toast("指定帖合成完成", "ok");
    await loadCorpus();
  } catch (e) {
    setStatus($("#synthStatus"), String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function refreshCorpusStats() {
  try {
    const data = await api("/api/corpus/stats");
    if (!data.success) return;
    state.counts.corpus = data.active ?? data.total ?? 0;
    const el = $("#countCorpus");
    if (el) el.textContent = String(state.counts.corpus);
    return data;
  } catch (e) {
    return null;
  }
}

async function loadCorpus() {
  const qs = new URLSearchParams();
  let kw = $("#corpusKeyword")?.value.trim() || "";
  if (kw.startsWith("#")) kw = kw.slice(1);
  const quality = $("#corpusQuality")?.value || "";
  const status = $("#corpusStatus")?.value ?? "active";
  const cat = state.labMaterialCategory || "all";
  if (kw) qs.set("keyword", kw);
  if (quality) qs.set("quality", quality);
  if (status) qs.set("status", status);
  if (cat && cat !== "all") qs.set("material_category", cat);
  qs.set("limit", "100");
  try {
    const data = await api(`/api/corpus/templates?${qs.toString()}`);
    if (!data.success) {
      toast(data.error || "加载失败", "error");
      return;
    }
    state.corpusItems = data.items || [];
    const alive = new Set(state.corpusItems.map((x) => Number(x.id)));
    state.corpusSelected = new Set([...(state.corpusSelected || [])].filter((id) => alive.has(id)));
    renderCorpusItems(state.corpusItems);
    const meta = $("#corpusMeta");
    if (meta) {
      const catLabel =
        cat && cat !== "all" ? materialCategoryLabel(cat) : "全部素材";
      meta.textContent = `${catLabel} · ${(state.corpusItems || []).length} 张语料 · 已选 ${(state.corpusSelected || new Set()).size}/3`;
    }
    await loadCategoryTemplates();
    await refreshCorpusStats();
    await loadGenerations();
    scheduleLabSessionSave();
  } catch (e) {
    toast(String(e), "error");
  }
}

async function loadGenerations() {
  const box = $("#corpusGenList");
  if (!box) return;
  try {
    const data = await api("/api/corpus/generations?featured=1&limit=20");
    const items = data.items || [];
    state.corpusGenerations = items;
    if (!items.length) {
      box.innerHTML = `<p class="lab-hist-empty muted">还没有精选。在版本预览点「★ 精选留存」可保存完整正文与要素细节。</p>`;
      return;
    }
    box.innerHTML = items
      .map((g) => {
        const el = g.meta?.elements || {};
        const label =
          g.meta?.variant_label || el.variant_label || g.meta?.variant_id || "精选";
        const hook = el.hook || String(g.content || "").split("\n")[0] || "";
        const cards = Array.isArray(el.source_cards) ? el.source_cards : [];
        const chips = [];
        if (el.formula) chips.push(`配方:${el.formula}`);
        if (g.meta?.variant_id) chips.push(`变体${g.meta.variant_id}`);
        cards.slice(0, 3).forEach((c) => {
          if (c.emotion) chips.push(c.emotion);
          if (c.tension) chips.push(String(c.tension).slice(0, 16));
          (c.keywords || []).slice(0, 2).forEach((k) => chips.push(k));
        });
        const uniqChips = [...new Set(chips)].slice(0, 8);
        const cardBits = cards
          .slice(0, 3)
          .map(
            (c) =>
              `<div class="lab-hist-card">
                <strong>${escapeHtml(c.title || c.hook || `#${c.id}`)}</strong>
                <span>${escapeHtml((c.pattern || c.raw_text || "").slice(0, 120))}</span>
                <em>${escapeHtml([c.emotion, c.tension].filter(Boolean).join(" · "))}</em>
              </div>`
          )
          .join("");
        return `<article class="lab-hist-item" data-gen-id="${escapeAttr(String(g.id))}">
          <button type="button" class="lab-hist-sum" data-gen-toggle="${escapeAttr(String(g.id))}">
            <span class="lab-hist-badge">★ ${escapeHtml(String(label))}</span>
            <strong>${escapeHtml((g.topic || "").slice(0, 28))}</strong>
            <span class="lab-hist-hook">${escapeHtml(hook.slice(0, 80))}</span>
            <span class="lab-hist-meta muted">#${g.id} · ${(g.created_at || "").slice(0, 16)}</span>
          </button>
          <div class="lab-hist-detail" hidden data-gen-detail="${escapeAttr(String(g.id))}">
            <div class="lab-hist-chips">${uniqChips
              .map((c) => `<span class="chip">${escapeHtml(String(c))}</span>`)
              .join("")}</div>
            ${cardBits ? `<div class="lab-hist-cards">${cardBits}</div>` : ""}
            <pre class="lab-hist-body">${escapeHtml(g.content || "")}</pre>
            <div class="lab-hist-actions">
              <button type="button" class="btn ghost xs" data-gen-use="${escapeAttr(String(g.id))}">载入预览</button>
              <button type="button" class="btn ghost xs" data-gen-copy="${escapeAttr(String(g.id))}">复制全文</button>
            </div>
          </div>
        </article>`;
      })
      .join("");

    box.querySelectorAll("[data-gen-toggle]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-gen-toggle");
        const detail = box.querySelector(`[data-gen-detail="${id}"]`);
        if (!detail) return;
        detail.hidden = !detail.hidden;
        btn.classList.toggle("open", !detail.hidden);
      });
    });
    box.querySelectorAll("[data-gen-use]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const g = (state.corpusGenerations || []).find(
          (x) => Number(x.id) === Number(btn.getAttribute("data-gen-use"))
        );
        if (!g) return;
        const el = g.meta?.elements || {};
        state.labActiveVariant = {
          id: g.meta?.variant_id || "★",
          label: g.meta?.variant_label || el.variant_label || "精选历史",
          content: g.content,
          hook: el.hook || String(g.content || "").split("\n")[0],
          generation_id: g.id,
          featured: true,
        };
        state.lastCreate = { title: g.topic || "", content: g.content || "", path: "" };
        renderLabVariants([state.labActiveVariant], 0);
        toast("已载入精选全文", "ok");
      });
    });
    box.querySelectorAll("[data-gen-copy]").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const g = (state.corpusGenerations || []).find(
          (x) => Number(x.id) === Number(btn.getAttribute("data-gen-copy"))
        );
        if (!g?.content) return;
        try {
          await navigator.clipboard.writeText(g.content);
          toast("已复制全文", "ok");
        } catch (e) {
          toast("复制失败", "error");
        }
      });
    });
  } catch (e) {
    box.innerHTML = `<p class="muted">精选历史加载失败</p>`;
  }
}

function collectTrayElements() {
  const ids = new Set([...(state.corpusSelected || [])].map(Number));
  return (state.corpusItems || [])
    .filter((t) => ids.has(Number(t.id)))
    .map((t) => {
      const factors = t.factors && typeof t.factors === "object" ? t.factors : {};
      return {
        id: t.id,
        title: t.source_title || "",
        hook: t.hooks || factors.hook || "",
        pattern: t.pattern || "",
        emotion: t.emotion || "",
        tension: t.tension || "",
        keywords: t.keywords || [],
        tags: t.tags || [],
        core_concept: factors.core_concept || "",
        narrative_type: factors.narrative_type || "",
        use_case: factors.use_case || "",
        raw_text: String(t.raw_text || "").slice(0, 4000),
        factors,
      };
    });
}

async function loadTemplateHistory(templateId) {
  /* kept for API compat; history lives in edit flow */
  void templateId;
}

function showLabSkeleton(loading) {
  const box = $("#labVariants");
  if (!box) return;
  if (loading) state.labImagePick = new Set();
  box.innerHTML = `<div class="lab-skel${loading ? " is-loading" : ""}" aria-hidden="true">
    <div class="lab-skel-card"><div class="sk-line w40"></div><div class="sk-line"></div><div class="sk-line"></div><div class="sk-line w70"></div></div>
    <div class="lab-skel-card"><div class="sk-line w40"></div><div class="sk-line"></div><div class="sk-line"></div><div class="sk-line w70"></div></div>
    <div class="lab-skel-card"><div class="sk-line w40"></div><div class="sk-line"></div><div class="sk-line"></div><div class="sk-line w70"></div></div>
  </div>`;
  if ($("#labResultBar")) $("#labResultBar").hidden = true;
  if ($("#labTweaks")) $("#labTweaks").hidden = true;
  if ($("#labImageBar")) $("#labImageBar").hidden = true;
}

function labSelectedImageIndices() {
  return [...(state.labImagePick || [])].sort((a, b) => a - b);
}

function syncLabImagePickAll() {
  const all = $("#labImagePickAll");
  const variants = state.labVariants || [];
  if (!all) return;
  const picked = labSelectedImageIndices();
  all.indeterminate = picked.length > 0 && picked.length < variants.length;
  all.checked = variants.length > 0 && picked.length === variants.length;
}

function renderLabVariants(variants, activeIdx) {
  const box = $("#labVariants");
  if (!box) return;
  if (!variants || !variants.length) {
    showLabSkeleton(false);
    return;
  }
  const prevPick = state.labImagePick || new Set();
  state.labVariants = variants;
  if (!prevPick.size) {
    state.labImagePick = new Set(variants.map((_, i) => i));
  } else {
    state.labImagePick = new Set([...prevPick].filter((i) => i >= 0 && i < variants.length));
  }
  const idx = activeIdx == null ? 0 : activeIdx;
  state.labActiveVariant = variants[idx];
  box.innerHTML = variants
    .map((v, i) => {
      const on = i === idx ? " on" : "";
      const starred = v.featured ? " starred" : "";
      const checked = state.labImagePick.has(i) ? " checked" : "";
      const imgs = (v.images || [])
        .map(
          (im) =>
            `<img class="lab-vimg" src="${escapeHtml(im.url || "")}" alt="配图" loading="lazy" />`
        )
        .join("");
      return `<article class="lab-variant${on}${starred}" data-vidx="${i}">
        <header>
          <label class="lab-vpick" title="勾选以批量生成配图">
            <input type="checkbox" class="lab-vpick-cb" data-vpick="${i}"${checked} />
          </label>
          <span class="lab-vid">${escapeHtml(v.id || String.fromCharCode(65 + i))}</span>
          <strong>${escapeHtml(v.label || "变体")}</strong>
          <button type="button" class="lab-vstar" data-feature-idx="${i}" title="精选留存完整正文与要素">★</button>
        </header>
        <p class="lab-vhook">${escapeHtml(v.hook || "")}</p>
        <pre class="lab-vbody">${escapeHtml(v.content || "")}</pre>
        ${imgs ? `<div class="lab-vimgs">${imgs}</div>` : ""}
      </article>`;
    })
    .join("");
  box.querySelectorAll(".lab-variant").forEach((el) => {
    el.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-feature-idx], .lab-vpick")) return;
      const i = Number(el.getAttribute("data-vidx"));
      renderLabVariants(state.labVariants, i);
    });
  });
  box.querySelectorAll("[data-feature-idx]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const i = Number(btn.getAttribute("data-feature-idx"));
      labSaveFeatured(i);
    });
  });
  box.querySelectorAll(".lab-vpick-cb").forEach((cb) => {
    cb.addEventListener("change", (ev) => {
      ev.stopPropagation();
      const i = Number(cb.getAttribute("data-vpick"));
      if (cb.checked) state.labImagePick.add(i);
      else state.labImagePick.delete(i);
      syncLabImagePickAll();
    });
  });
  if ($("#labResultBar")) $("#labResultBar").hidden = false;
  if ($("#labTweaks")) $("#labTweaks").hidden = false;
  if ($("#labImageBar")) $("#labImageBar").hidden = false;
  syncLabImagePickAll();
  const active = state.labActiveVariant;
  const draft = labBuildPublishDraft(active);
  state.lastCreate = {
    title: draft?.title || $("#regenTopic")?.value.trim() || "灵感碰撞",
    content: draft?.content || active?.content || "",
    path: "",
  };
  const out = $("#corpusRegenOut");
  if (out) out.textContent = active?.content || "";
  if (typeof updateLabSteps === "function") updateLabSteps();
  scheduleLabSessionSave();
}

function renderLabCot(steps) {
  const box = $("#labCotBox");
  const list = $("#labCotList");
  if (!box || !list) return;
  const arr = Array.isArray(steps) ? steps : [];
  if (!arr.length) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.open = true;
  list.innerHTML = arr.map((s) => `<li>${escapeHtml(String(s))}</li>`).join("");
}

async function runCorpusRegen({ explicit = false } = {}) {
  if (!explicit) return;
  const ids = [...(state.corpusSelected || [])];
  const topic = $("#regenTopic")?.value.trim() || "";
  if (!topic) {
    setStatus($("#corpusRegenStatus"), "先填热点主题（选卡可选）", "error");
    return;
  }
  $("#btnCorpusRegen").disabled = true;
  setStatus($("#corpusRegenStatus"), "生成中…");
  showLabSkeleton(true);
  const prof = LAB_PROFILES_FALLBACK.find((x) => x.id === state.labProfile) || LAB_PROFILES_FALLBACK[0];
  renderLabCot(["读取灵感卡骨架…", "注入热点变量…", `后处理：${prof.label}…`]);
  try {
    const data = await api("/api/corpus/generate", {
      method: "POST",
      body: JSON.stringify({
        lab: true,
        template_ids: ids,
        topic,
        formula: state.labFormula || "contrarian",
        prompt_profile: state.labProfile || "general",
        platform_style: $("#regenStyle")?.value.trim() || "X/Twitter",
        prompt: $("#regenPrompt")?.value.trim() || "",
        variant_count: 3,
        material_category:
          state.labMaterialCategory && state.labMaterialCategory !== "all"
            ? state.labMaterialCategory
            : labProfileMaterialCategory(state.labProfile) !== "all"
              ? labProfileMaterialCategory(state.labProfile)
              : "",
      }),
    });
    if (!data.success) {
      setStatus($("#corpusRegenStatus"), data.error || "生成失败", "error");
      return;
    }
    renderLabCot(data.cot || []);
    state.labCot = data.cot || [];
    if (data.prompt_profile?.variant_hint) syncLabProfileHint([data.prompt_profile]);
    state.labPromptSnippets = data.prompt_snippets || [];
    renderLabPromptSnippets(state.labPromptSnippets);
    renderLabVariants(data.variants || [], 0);
    state.labPath = data.path || null;
    renderPathView(state.labPath || {});
    setStatus(
      $("#corpusRegenStatus"),
      `完成 · ${data.provider || "ai"} · ${(data.variants || []).length} 个变体`,
      "ok"
    );
    await loadGenerations();
    scheduleLabSessionSave();
  } catch (e) {
    setStatus($("#corpusRegenStatus"), String(e), "error");
  } finally {
    $("#btnCorpusRegen").disabled = false;
  }
}

async function runLabTweak(tweakId) {
  const active = state.labActiveVariant;
  if (!active?.content) {
    toast("请先选一个变体", "error");
    return;
  }
  setStatus($("#corpusRegenStatus"), "微调中…");
  try {
    const data = await api("/api/corpus/lab/tweak", {
      method: "POST",
      body: JSON.stringify({
        content: active.content,
        tweak: tweakId,
        topic: $("#regenTopic")?.value.trim() || "",
      }),
    });
    if (!data.success) {
      toast(data.error || "微调失败", "error");
      return;
    }
    active.content = data.content;
    active.hook = data.hook || data.content.split("\n")[0];
    const idx = (state.labVariants || []).indexOf(active);
    renderLabVariants(state.labVariants, idx >= 0 ? idx : 0);
    setStatus($("#corpusRegenStatus"), "微调完成", "ok");
  } catch (e) {
    toast(String(e), "error");
  }
}

async function labCopyMarkdown() {
  const v = state.labActiveVariant;
  if (!v?.content) return;
  const md = `## ${v.label || "Post"}\n\n${v.content}\n`;
  try {
    await navigator.clipboard.writeText(md);
    toast("已复制 Markdown", "ok");
  } catch (e) {
    toast("复制失败", "error");
  }
}

function labBuildPublishDraft(variant) {
  const v = variant || state.labActiveVariant;
  if (!v?.content?.trim()) return null;
  const topic = $("#regenTopic")?.value.trim() || "灵感碰撞";
  const label = v.label || v.id || "变体";
  const title = label.includes(topic) ? label : `${topic} · ${label}`;
  const style = $("#regenStyle")?.value.trim() || "X/Twitter";
  const prof =
    LAB_PROFILES_FALLBACK.find((x) => x.id === state.labProfile) || LAB_PROFILES_FALLBACK[0];
  const tags = [topic, prof?.label].filter(Boolean).join(", ");
  const media_paths = (v.media_paths || []).length
    ? [...v.media_paths]
    : (v.images || []).map((im) => im.path).filter(Boolean);
  return {
    title,
    content: v.content,
    hook: v.hook || "",
    label,
    tags,
    style,
    media_paths,
  };
}

function labPlatformHintFromStyle(style) {
  const s = String(style || "").toLowerCase();
  if (s.includes("币安") || s.includes("binance")) return ["binance_square"];
  if (s.includes("reddit")) return ["reddit"];
  if (s.includes("okx")) return ["okx"];
  if (s.includes("bitget")) return ["bitget"];
  return ["x"];
}

function applyPublishPlatformHint(ids) {
  const box = $("#publishPlatformChecks");
  if (!box) return;
  const want = new Set(ids?.length ? ids : PUBLISH_PLATFORM_DEFAULT_IDS);
  box.querySelectorAll('input[type="checkbox"][data-platform]').forEach((el) => {
    el.checked = want.has(el.value);
  });
}

async function labPublishViaCdp() {
  const draft = labBuildPublishDraft();
  if (!draft?.content) {
    toast("请先生成并选中一条变体文案", "error");
    return;
  }
  const btn = $("#btnLabPublishPreview");
  const platforms = labPlatformHintFromStyle(draft.style);
  if (btn) btn.disabled = true;
  toast(`CDP 发布中 · ${platforms.join(", ")}…`);
  try {
    const data = await api("/api/publish", {
      method: "POST",
      body: JSON.stringify({
        title: draft.title,
        content: draft.content,
        tags: draft.tags || "",
        platforms,
        media_paths: draft.media_paths || [],
        use_cdp: true,
        debugger_url: $("#debuggerUrl")?.value.trim() || "127.0.0.1:9222",
        submit: !$("#publishDryRun")?.checked,
      }),
    });
    const okN = data.success_count || 0;
    const total = data.total || platforms.length;
    if (data.success) {
      toast(`CDP 发布完成 ${okN}/${total}`, "ok");
    } else {
      const err = data.error || data.results?.find((r) => r?.error)?.error || "发布失败";
      toast(`${err} (${okN}/${total})`, "error");
    }
  } catch (e) {
    toast(String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function labOpenPublishPreview() {
  const draft = labBuildPublishDraft();
  if (!draft) {
    toast("请先生成并选中一条变体文案", "error");
    return;
  }
  const dlg = $("#labPublishPreviewDialog");
  if (!dlg) {
    labSendToPublish(draft);
    return;
  }
  const meta = $("#labPublishPreviewMeta");
  const hook = $("#labPublishPreviewHook");
  const body = $("#labPublishPreviewBody");
  if (meta) meta.textContent = `${draft.title} · ${draft.style}`;
  if (hook) {
    hook.textContent = draft.hook || "";
    hook.hidden = !draft.hook;
  }
  if (body) body.textContent = draft.content;
  state.labPublishDraft = draft;
  dlg.showModal();
}

async function labSendToPublish(draft) {
  const d = draft || state.labPublishDraft || labBuildPublishDraft();
  if (!d?.content) {
    toast("无可用正文", "error");
    return;
  }
  state.lastCreate = { title: "", content: d.content, path: "" };
  if ($("#publishContent")) $("#publishContent").value = d.content;
  if (d.media_paths?.length) {
    publishServerMediaPaths = [...d.media_paths];
    publishServerMediaRels = [];
    renderMediaPreview();
  }
  await loadPublishPlatforms();
  applyPublishPlatformHint(labPlatformHintFromStyle(d.style));
  switchTab("publish");
  $("#publishContent")?.focus();
  toast(d.media_paths?.length ? "已带入 CDP 发布页（含配图）" : "已带入 CDP 发布页", "ok");
  state.labPublishDraft = null;
}

async function pollLabImageJob(jobId) {
  const statusEl = $("#labImageStatus");
  const btn = $("#btnLabGenImages");
  for (let i = 0; i < 240; i++) {
    const data = await api(`/api/jobs/${jobId}`);
    const job = data.job || {};
    const msg = job.message || job.status || "配图生成中…";
    if (statusEl) statusEl.textContent = msg;
    setStatus($("#corpusRegenStatus"), msg);
    if (job.status === "done" || job.status === "error") {
      const result = job.result || {};
      const rows = result.results || [];
      const variants = state.labVariants || [];
      let activeIdx = variants.indexOf(state.labActiveVariant);
      for (const row of rows) {
        if (!row.success) continue;
        const idx = Number(row.index);
        if (idx < 0 || idx >= variants.length) continue;
        const v = variants[idx];
        v.content = row.content || v.content;
        if (row.images?.length) {
          v.images = [...(v.images || []), ...row.images];
          v.media_paths = [...(v.media_paths || []), ...(row.media_paths || [])];
        }
        if (activeIdx < 0) activeIdx = idx;
      }
      if (variants.length) renderLabVariants(variants, activeIdx >= 0 ? activeIdx : 0);
      const okN = result.ok_count || 0;
      const total = result.total || rows.length;
      const failN = result.fail_count || 0;
      const finalMsg = failN
        ? `配图 ${okN}/${total} · 失败 ${failN}`
        : `配图完成 ${okN}/${total}`;
      if (statusEl) statusEl.textContent = finalMsg;
      setStatus($("#corpusRegenStatus"), finalMsg, failN && !okN ? "error" : "ok");
      if (failN) {
        const err = (result.failures || rows.filter((r) => !r.success))
          .map((r) => r.error || "失败")
          .slice(0, 2)
          .join("；");
        if (err) toast(err.slice(0, 180), "error");
      } else {
        toast(finalMsg, "ok");
      }
      if (btn) btn.disabled = false;
      return;
    }
    await new Promise((r) => setTimeout(r, 2500));
  }
  if (statusEl) statusEl.textContent = "配图超时，请稍后重试";
  setStatus($("#corpusRegenStatus"), "配图任务超时", "error");
  if (btn) btn.disabled = false;
}

async function runLabBatchImages() {
  const variants = state.labVariants || [];
  const indices = labSelectedImageIndices();
  if (!variants.length) {
    toast("请先生成变体", "error");
    return;
  }
  if (!indices.length) {
    toast("请勾选至少一个变体", "error");
    return;
  }
  const btn = $("#btnLabGenImages");
  const statusEl = $("#labImageStatus");
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = "提交配图任务…";
  setStatus($("#corpusRegenStatus"), `配图 0/${indices.length}…`);
  try {
    const payload = {
      indices,
      topic: $("#regenTopic")?.value.trim() || "",
      debugger_url: $("#debuggerUrl")?.value.trim() || "127.0.0.1:9222",
      variants: variants.map((v) => ({
        id: v.id,
        label: v.label,
        hook: v.hook,
        content: v.content,
      })),
    };
    const data = await api("/api/corpus/lab/images", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!data.success || !data.job_id) {
      toast(data.error || "提交失败", "error");
      if (btn) btn.disabled = false;
      return;
    }
    await pollLabImageJob(data.job_id);
  } catch (e) {
    toast(String(e), "error");
    if (btn) btn.disabled = false;
    if (statusEl) statusEl.textContent = "";
  }
}

const APP_LAB_MODE_LS = "appLabMode";

function applyLabMode(mode) {
  const m = mode === "memos" ? "memos" : "lab";
  state.labMode = m;
  document.querySelectorAll(".lab-mode-tab[data-lab-mode]").forEach((btn) => {
    const on = btn.getAttribute("data-lab-mode") === m;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  const labBox = $("#labModeLab");
  const memosBox = $("#labModeMemos");
  if (labBox) labBox.hidden = m !== "lab";
  if (memosBox) memosBox.hidden = m !== "memos";
  try {
    localStorage.setItem(APP_LAB_MODE_LS, m);
  } catch (_) {}
  scheduleLabSessionSave();
  if (m === "memos") {
    loadMemosConfig().then(() => {
      loadMemosTags();
      if (!(state.memosItems || []).length) return;
      renderMemosList(state.memosItems);
    });
  }
}

function switchLabMode(mode) {
  applyLabMode(mode);
  if (mode === "memos" && !(state.memosItems || []).length) {
    loadMemosConfig().then(() => loadMemosTags());
  }
}

function memosSelectedIndices() {
  return [...(state.memosPick || [])].sort((a, b) => a - b);
}

function syncMemosPickAll() {
  const all = $("#memosPickAll");
  const items = state.memosItems || [];
  if (!all) return;
  const picked = memosSelectedIndices();
  all.indeterminate = picked.length > 0 && picked.length < items.length;
  all.checked = items.length > 0 && picked.length === items.length;
}

/** 轻量 Markdown → HTML（标题/列表/代码/引用/链接/图片/加粗斜体） */
function renderMarkdown(src, opts) {
  const options = opts && typeof opts === "object" ? opts : {};
  const rewriteUrl =
    typeof options.rewriteUrl === "function" ? options.rewriteUrl : null;
  let text = String(src || "").replace(/\r\n/g, "\n");
  const blocks = [];
  text = text.replace(/```([\w-]*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const i = blocks.length;
    blocks.push(
      `<pre><code class="lang-${escapeHtml(lang || "")}">${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`
    );
    return `\u0000BLK${i}\u0000`;
  });

  const inline = (s) => {
    let t = escapeHtml(s);
    t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (_, alt, url) => {
      let u = String(url || "");
      if (rewriteUrl) u = rewriteUrl(u) || u;
      if (!/^(https?:|\/|data:image\/)/i.test(u)) return escapeHtml(`![${alt}](${url})`);
      return `<img src="${escapeHtml(u)}" alt="${escapeHtml(alt)}" loading="lazy" />`;
    });
    t = t.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (_, label, url) => {
      let u = String(url || "");
      if (rewriteUrl) u = rewriteUrl(u) || u;
      if (!/^(https?:|mailto:|\/)/i.test(u)) return escapeHtml(`[${label}](${url})`);
      return `<a href="${escapeHtml(u)}" target="_blank" rel="noopener">${label}</a>`;
    });
    t = t.replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`);
    t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    t = t.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    t = t.replace(/(^|[^_\w])_([^_\n]+)_(?!_)/g, "$1<em>$2</em>");
    return t;
  };

  const lines = text.split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const blk = line.match(/^\u0000BLK(\d+)\u0000$/);
    if (blk) {
      out.push(blocks[Number(blk[1])]);
      i += 1;
      continue;
    }
    if (/^\s*---+\s*$/.test(line) || /^\s*\*\*\*+\s*$/.test(line)) {
      out.push("<hr />");
      i += 1;
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.+)$/);
    if (h) {
      const lv = h[1].length;
      out.push(`<h${lv}>${inline(h[2])}</h${lv}>`);
      i += 1;
      continue;
    }
    if (/^\s*>\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      out.push(`<blockquote><p>${inline(buf.join(" "))}</p></blockquote>`);
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        buf.push(`<li>${inline(lines[i].replace(/^\s*[-*+]\s+/, ""))}</li>`);
        i += 1;
      }
      out.push(`<ul>${buf.join("")}</ul>`);
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        buf.push(`<li>${inline(lines[i].replace(/^\s*\d+\.\s+/, ""))}</li>`);
        i += 1;
      }
      out.push(`<ol>${buf.join("")}</ol>`);
      continue;
    }
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const buf = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|\s*[-*+]\s|\s*\d+\.\s|\s*>|\s*---+\s*$|\u0000BLK)/.test(lines[i])) {
      buf.push(lines[i]);
      i += 1;
    }
    out.push(`<p>${inline(buf.join("\n")).replace(/\n/g, "<br />")}</p>`);
  }
  return out.join("\n") || "<p class='muted'>（空）</p>";
}

function formatMemosTime(iso) {
  const s = String(iso || "").trim();
  if (!s) return "";
  try {
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return s;
    const pad = (n) => String(n).padStart(2, "0");
    // 北京时间展示
    const bj = new Date(d.getTime() + 8 * 3600 * 1000);
    return `${bj.getUTCFullYear()}-${pad(bj.getUTCMonth() + 1)}-${pad(bj.getUTCDate())} ${pad(bj.getUTCHours())}:${pad(bj.getUTCMinutes())}`;
  } catch (_) {
    return s;
  }
}

function applyMemosConfigForm(cfg) {
  if (!cfg) return;
  if ($("#memosBaseUrl") && cfg.base_url != null) $("#memosBaseUrl").value = cfg.base_url;
  if (cfg.base_url != null) state.memosBaseUrl = String(cfg.base_url || "").replace(/\/$/, "");
  if ($("#memosPageSize") && cfg.page_size != null) $("#memosPageSize").value = cfg.page_size;
  if ($("#memosFilter") && cfg.filter != null) $("#memosFilter").value = cfg.filter;
  const tok = $("#memosToken");
  if (tok && cfg.access_token) {
    if (!tok.value) tok.value = cfg.access_token;
    tok.placeholder = cfg.access_token_masked
      ? `已保存 ${cfg.access_token_masked}`
      : "Memos 设置里创建的 Token";
  }
}

function memosBaseUrl() {
  const fromInput = $("#memosBaseUrl")?.value.trim() || "";
  const base = (fromInput || state.memosBaseUrl || "").replace(/\/$/, "");
  if (base) state.memosBaseUrl = base;
  return base;
}

/** 把 Memos 相对附件路径转到 Console 代理，避免打到 8787 本域或丢 Token */
function resolveMemosMediaUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  if (/^data:/i.test(raw)) return raw;
  if (raw.startsWith("/api/corpus/memos/asset")) return raw;

  let path = "";
  if (/^https?:\/\//i.test(raw)) {
    try {
      const u = new URL(raw);
      const base = memosBaseUrl();
      if (base) {
        const b = new URL(base.includes("://") ? base : `https://${base}`);
        if (u.origin === b.origin && u.pathname.startsWith("/file/")) {
          path = u.pathname + (u.search || "");
        } else {
          return raw;
        }
      } else if (u.pathname.startsWith("/file/")) {
        path = u.pathname + (u.search || "");
      } else {
        return raw;
      }
    } catch (_) {
      return raw;
    }
  } else if (raw.startsWith("/file/")) {
    path = raw;
  } else if (raw.startsWith("/")) {
    // 其它相对站内路径也挂到 Memos（如历史绝对路径被写成相对）
    path = raw;
  } else {
    return raw;
  }

  if (!path.startsWith("/file/")) {
    const base = memosBaseUrl();
    return base ? `${base}${path}` : path;
  }
  return `/api/corpus/memos/asset?path=${encodeURIComponent(path)}`;
}

function renderMemosMarkdown(src) {
  return renderMarkdown(src, { rewriteUrl: resolveMemosMediaUrl });
}

function extractMemosContentImages(content) {
  const out = [];
  const re = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
  let m;
  const text = String(content || "");
  while ((m = re.exec(text))) {
    const src = resolveMemosMediaUrl(m[2]);
    if (!src || !/^(https?:|\/|data:)/i.test(src)) continue;
    out.push({ url: src, alt: m[1] || "配图" });
  }
  return out;
}

async function loadMemosConfig() {
  try {
    const data = await api("/api/corpus/memos/config");
    if (data.success) applyMemosConfigForm(data.config || {});
    return data.config || {};
  } catch (e) {
    return {};
  }
}

async function saveMemosConfig() {
  const status = $("#memosConfigStatus");
  try {
    const body = {
      base_url: $("#memosBaseUrl")?.value.trim() || "",
      page_size: Number($("#memosPageSize")?.value || 50),
      filter: $("#memosFilter")?.value.trim() || "",
    };
    const tok = $("#memosToken")?.value.trim();
    if (tok) body.access_token = tok;
    const data = await api("/api/corpus/memos/config", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!data.success) {
      if (status) status.textContent = data.error || "保存失败";
      toast(data.error || "保存失败", "error");
      return;
    }
    applyMemosConfigForm(data.config || {});
    if (status) status.textContent = "配置已保存";
    toast("Memos 配置已保存", "ok");
  } catch (e) {
    if (status) status.textContent = String(e);
    toast(String(e), "error");
  }
}

function syncMemosCustomRangeVis() {
  const custom = $("#memosCustomRange");
  if (!custom) return;
  custom.hidden = ($("#memosRange")?.value || "") !== "custom";
}

function renderMemosTagCloud(tags) {
  const box = $("#memosTagCloud");
  const list = $("#memosTagList");
  const arr = Array.isArray(tags) ? tags : [];
  state.memosTags = arr;
  if (list) {
    list.innerHTML = arr
      .map((t) => `<option value="${escapeHtml(t.tag || t)}"></option>`)
      .join("");
  }
  if (!box) return;
  const cur = ($("#memosTag")?.value || "").trim().replace(/^#/, "");
  box.innerHTML = arr
    .slice(0, 40)
    .map((t) => {
      const name = t.tag || t;
      const on = cur && cur === name ? " on" : "";
      const n = t.count != null ? ` ${t.count}` : "";
      return `<button type="button" class="memos-tag-chip${on}" data-memos-tag="${escapeHtml(name)}">#${escapeHtml(name)}${n}</button>`;
    })
    .join("");
  box.querySelectorAll("[data-memos-tag]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tag = btn.getAttribute("data-memos-tag") || "";
      const input = $("#memosTag");
      if (!input) return;
      input.value = input.value.trim().replace(/^#/, "") === tag ? "" : tag;
      renderMemosTagCloud(state.memosTags || []);
      fetchMemosList();
    });
  });
}

function harvestTagsFromItems(items) {
  const counts = {};
  for (const it of items || []) {
    for (const t of it.tags || []) {
      counts[t] = (counts[t] || 0) + 1;
    }
  }
  return Object.entries(counts)
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
}

async function loadMemosTags() {
  try {
    const data = await api("/api/corpus/memos/tags");
    if (data.success && data.tags?.length) {
      renderMemosTagCloud(data.tags);
      return;
    }
  } catch (_) {}
  renderMemosTagCloud(harvestTagsFromItems(state.memosItems || []));
}

let _appCtxMenuEl = null;
let _appCtxMenuCloser = null;

function hideAppCtxMenu() {
  if (_appCtxMenuCloser) {
    document.removeEventListener("pointerdown", _appCtxMenuCloser, true);
    document.removeEventListener("keydown", _appCtxMenuCloser, true);
    window.removeEventListener("blur", _appCtxMenuCloser);
    window.removeEventListener("resize", _appCtxMenuCloser);
    _appCtxMenuCloser = null;
  }
  if (_appCtxMenuEl) {
    _appCtxMenuEl.remove();
    _appCtxMenuEl = null;
  }
}

function showAppCtxMenu(clientX, clientY, items) {
  hideAppCtxMenu();
  const menu = document.createElement("div");
  menu.className = "app-ctx-menu";
  menu.setAttribute("role", "menu");
  (items || []).forEach((it) => {
    if (!it || !it.label) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("role", "menuitem");
    btn.textContent = it.label;
    if (it.danger) btn.classList.add("is-danger");
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      hideAppCtxMenu();
      try {
        it.action?.();
      } catch (e) {
        toast(String(e), "error");
      }
    });
    menu.appendChild(btn);
  });
  if (!menu.childElementCount) return;
  document.body.appendChild(menu);
  const pad = 8;
  const rect = menu.getBoundingClientRect();
  let left = Number(clientX) || 0;
  let top = Number(clientY) || 0;
  if (left + rect.width > window.innerWidth - pad) left = window.innerWidth - rect.width - pad;
  if (top + rect.height > window.innerHeight - pad) top = window.innerHeight - rect.height - pad;
  left = Math.max(pad, left);
  top = Math.max(pad, top);
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  _appCtxMenuEl = menu;
  _appCtxMenuCloser = (ev) => {
    if (ev.type === "keydown" && ev.key !== "Escape") return;
    if (ev.type === "pointerdown" && menu.contains(ev.target)) return;
    hideAppCtxMenu();
  };
  document.addEventListener("pointerdown", _appCtxMenuCloser, true);
  document.addEventListener("keydown", _appCtxMenuCloser, true);
  window.addEventListener("blur", _appCtxMenuCloser);
  window.addEventListener("resize", _appCtxMenuCloser);
}

function memosCollectMediaPaths(it) {
  if (!it || typeof it !== "object") return [];
  const fromPaths = Array.isArray(it.media_paths)
    ? it.media_paths.map(String).filter(Boolean)
    : [];
  if (fromPaths.length) return [...new Set(fromPaths)];
  const fromImgs = (it.images || [])
    .map((im) => im?.path || im?.media_path || "")
    .map(String)
    .filter(Boolean);
  return [...new Set(fromImgs)];
}

async function memosSendToPublish(idx) {
  const items = state.memosItems || [];
  const it = items[Number(idx)];
  if (!it) {
    toast("文章不存在", "error");
    return;
  }
  const content = String(it.content || "").trim();
  const media_paths = memosCollectMediaPaths(it);
  if (!content && !media_paths.length) {
    toast("该文章无正文与配图", "error");
    return;
  }
  const tags = Array.isArray(it.tags)
    ? it.tags.map(String).filter(Boolean).join(", ")
    : "";
  switchTab("publish");
  await loadPublishPlatforms();
  await loadQueueItemIntoPublishEditor(
    {
      id: it.id || "",
      title: it.title || it.label || "",
      content: content || it.content || "",
      tags,
      media_paths,
      platforms: [],
    },
    { switchMode: true }
  );
  applyPublishWorkbenchMode("publish");
  setStatus(
    $("#publishStatus"),
    `已从 Memos「${it.title || it.id || "文章"}」填入发布页，勾选平台后即可发布`,
    "ok"
  );
  $("#publishContent")?.focus();
  toast(media_paths.length ? "已带入 CDP 发布页（含配图）" : "已带入 CDP 发布页", "ok");
}

function renderMemosList(items, { selectAllIfEmpty = false } = {}) {
  const box = $("#memosList");
  if (!box) return;
  state.memosItems = items || [];
  const prev = state.memosPick || new Set();
  if (selectAllIfEmpty && !prev.size && state.memosItems.length) {
    state.memosPick = new Set(state.memosItems.map((_, i) => i));
  } else {
    state.memosPick = new Set(
      [...prev].filter((i) => i >= 0 && i < state.memosItems.length)
    );
  }
  if (!state.memosItems.length) {
    box.innerHTML = `<div class="muted" style="padding:24px;text-align:center">暂无文章，调整筛选后重新拉取</div>`;
    syncMemosPickAll();
    return;
  }
  box.innerHTML = state.memosItems
    .map((it, i) => {
      const checked = state.memosPick.has(i) ? " checked" : "";
      const tags = (it.tags || [])
        .slice(0, 8)
        .map((t) => `#${escapeHtml(String(t))}`)
        .join(" ");
      const contentImgs = extractMemosContentImages(it.content || "");
      const localImgs = it.images || [];
      const seen = new Set();
      const imgs = [...localImgs, ...contentImgs]
        .map((im) => {
          const src = resolveMemosMediaUrl(im.url || im.src || "");
          if (!src || seen.has(src)) return "";
          seen.add(src);
          return `<img class="lab-vimg" src="${escapeHtml(src)}" alt="${escapeHtml(
            im.alt || "配图"
          )}" loading="lazy" />`;
        })
        .filter(Boolean)
        .join("");
      const when = escapeHtml(formatMemosTime(it.display_time || it.create_time || it.update_time));
      return `<article class="memos-card" data-midx="${i}" title="双击编辑 · 右键发布到 CDP">
        <header>
          <label class="lab-vpick" title="勾选以批量生成配图">
            <input type="checkbox" class="memos-pick-cb" data-mpick="${i}"${checked} />
          </label>
          <strong>${escapeHtml(it.title || it.label || it.id || "无标题")}</strong>
        </header>
        <div class="memos-meta">${when}${tags ? " · " + tags : ""}${
        it.name ? ` · ${escapeHtml(it.name)}` : ""
      } · 双击编辑 · 右键发布</div>
        <div class="memos-md-preview">${renderMemosMarkdown(it.content || "")}</div>
        ${imgs ? `<div class="lab-vimgs">${imgs}</div>` : ""}
      </article>`;
    })
    .join("");
  box.querySelectorAll(".memos-pick-cb").forEach((cb) => {
    cb.addEventListener("change", () => {
      const i = Number(cb.getAttribute("data-mpick"));
      if (cb.checked) state.memosPick.add(i);
      else state.memosPick.delete(i);
      syncMemosPickAll();
    });
    cb.addEventListener("click", (e) => e.stopPropagation());
  });
  box.querySelectorAll(".memos-card").forEach((el) => {
    el.addEventListener("dblclick", (ev) => {
      if (ev.target.closest(".lab-vpick, a, button, input")) return;
      const i = Number(el.getAttribute("data-midx"));
      openMemosEditor(i);
    });
    el.addEventListener("contextmenu", (ev) => {
      if (ev.target.closest(".lab-vpick, a, button, input, textarea")) return;
      ev.preventDefault();
      const i = Number(el.getAttribute("data-midx"));
      showAppCtxMenu(ev.clientX, ev.clientY, [
        {
          label: "发布到 CDP",
          action: () => memosSendToPublish(i),
        },
        {
          label: "编辑 Markdown",
          action: () => openMemosEditor(i),
        },
      ]);
    });
  });
  syncMemosPickAll();
  const meta = $("#memosMeta");
  if (meta) {
    meta.textContent = `共 ${state.memosItems.length} 篇 · 已选 ${memosSelectedIndices().length} · 双击编辑 · 右键发布到 CDP`;
  }
  if (!(state.memosTags || []).length) {
    renderMemosTagCloud(harvestTagsFromItems(state.memosItems));
  }
}

function buildMemosQuery() {
  const qs = new URLSearchParams();
  const pageSize = Number($("#memosPageSize")?.value || 50);
  if (pageSize) qs.set("page_size", String(pageSize));
  const filter = $("#memosFilter")?.value.trim();
  if (filter) qs.set("filter", filter);
  const keyword = $("#memosKeyword")?.value.trim();
  if (keyword) qs.set("keyword", keyword);
  const tag = ($("#memosTag")?.value || "").trim().replace(/^#/, "");
  if (tag) qs.set("tag", tag);
  const range = $("#memosRange")?.value || "";
  if (range && range !== "custom") qs.set("range", range);
  if (range === "custom") {
    const since = $("#memosSince")?.value || "";
    const until = $("#memosUntil")?.value || "";
    if (since) qs.set("since", since);
    if (until) qs.set("until", until);
  }
  return qs;
}

async function fetchMemosList() {
  const status = $("#memosConfigStatus");
  const btn = $("#btnMemosFetch");
  if (btn) btn.disabled = true;
  if (status) status.textContent = "拉取中…";
  try {
    await saveMemosConfigQuiet();
    const qs = buildMemosQuery();
    const data = await api(`/api/corpus/memos?${qs.toString()}`);
    if (!data.success) {
      toast(data.error || "拉取失败", "error");
      if (status) status.textContent = data.error || "拉取失败";
      return;
    }
    state.memosPick = new Set();
    state.memosNextPageToken = data.next_page_token || "";
    renderMemosList(data.items || [], { selectAllIfEmpty: true });
    const hint = data.filter ? ` · filter: ${data.filter}` : "";
    if (status) status.textContent = `已拉取 ${data.count || 0} 篇${hint}`;
    toast(`已拉取 ${data.count || 0} 篇 Memos`, "ok");
  } catch (e) {
    toast(String(e), "error");
    if (status) status.textContent = String(e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function saveMemosConfigQuiet() {
  const body = {};
  const base = $("#memosBaseUrl")?.value.trim();
  if (base) body.base_url = base;
  const pageSize = Number($("#memosPageSize")?.value || 0);
  if (pageSize > 0) body.page_size = pageSize;
  const filter = $("#memosFilter")?.value.trim();
  if (filter != null && $("#memosFilter")) body.filter = filter;
  const tok = $("#memosToken")?.value.trim();
  if (tok) body.access_token = tok;
  if (!Object.keys(body).length) return;
  try {
    const data = await api("/api/corpus/memos/config", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (data.success) applyMemosConfigForm(data.config || {});
  } catch (_) {}
}

function setMemosEditView(mode) {
  const panes = $("#memosEditPanes");
  if (!panes) return;
  const m = ["split", "edit", "preview"].includes(mode) ? mode : "split";
  panes.setAttribute("data-view", m);
  document.querySelectorAll("[data-memos-view]").forEach((btn) => {
    btn.classList.toggle("on", btn.getAttribute("data-memos-view") === m);
  });
  if (m !== "edit") refreshMemosEditPreview();
}

function refreshMemosEditPreview() {
  const src = $("#memosEditSource")?.value || "";
  const box = $("#memosEditPreview");
  if (box) box.innerHTML = renderMemosMarkdown(src);
}

function openMemosEditor(idx) {
  const items = state.memosItems || [];
  const it = items[idx];
  if (!it) return;
  state.memosEditIndex = idx;
  const dlg = $("#memosEditDialog");
  const src = $("#memosEditSource");
  if (src) src.value = it.content || "";
  if ($("#memosEditTitle")) $("#memosEditTitle").textContent = it.title || "编辑 Memo";
  if ($("#memosEditMeta")) {
    $("#memosEditMeta").textContent = `${it.name || ""} · ${formatMemosTime(
      it.create_time || it.update_time
    )}${(it.tags || []).length ? " · #" + it.tags.join(" #") : ""}`;
  }
  if ($("#memosEditStatus")) {
    $("#memosEditStatus").textContent = "";
    $("#memosEditStatus").className = "status";
  }
  setMemosEditView("split");
  refreshMemosEditPreview();
  dlg?.showModal();
  src?.focus();
}

async function saveMemosEditor(e) {
  if (e) e.preventDefault();
  const idx = state.memosEditIndex;
  const items = state.memosItems || [];
  const it = items[idx];
  if (!it?.name) {
    toast("无效的 Memo", "error");
    return;
  }
  const content = $("#memosEditSource")?.value ?? "";
  const status = $("#memosEditStatus");
  const btn = $("#btnMemosEditSave");
  if (btn) btn.disabled = true;
  if (status) setStatus(status, "保存中…");
  try {
    const data = await api("/api/corpus/memos/update", {
      method: "POST",
      body: JSON.stringify({ name: it.name, content }),
    });
    if (!data.success) {
      setStatus(status, data.error || "保存失败", "error");
      toast(data.error || "保存失败", "error");
      return;
    }
    const updated = data.item || {};
    Object.assign(it, updated, {
      content,
      title: updated.title || it.title,
      tags: updated.tags || it.tags,
      images: it.images,
      media_paths: it.media_paths,
      dirty: false,
    });
    renderMemosList(items);
    setStatus(status, "已保存到 Memos", "ok");
    toast("已保存到 Memos", "ok");
    $("#memosEditDialog")?.close();
  } catch (err) {
    setStatus(status, String(err), "error");
    toast(String(err), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function pollMemosImageJob(jobId) {
  const statusEl = $("#memosImageStatus");
  const btn = $("#btnMemosGenImages");
  for (let i = 0; i < 240; i++) {
    const data = await api(`/api/jobs/${jobId}`);
    const job = data.job || {};
    const msg = job.message || job.status || "配图生成中…";
    if (statusEl) statusEl.textContent = msg;
    if (job.status === "done" || job.status === "error") {
      const result = job.result || {};
      const rows = result.results || [];
      const items = state.memosItems || [];
      for (const row of rows) {
        if (!row.success) continue;
        const idx = Number(row.index);
        if (idx < 0 || idx >= items.length) continue;
        const it = items[idx];
        it.content = row.content || it.content;
        if (row.images?.length) {
          it.images = [...(it.images || []), ...row.images];
          it.media_paths = [...(it.media_paths || []), ...(row.media_paths || [])];
        }
        it.dirty = !row.synced;
        if (row.synced) it.dirty = false;
      }
      renderMemosList(items);
      const okN = result.ok_count || 0;
      const total = result.total || rows.length;
      const failN = result.fail_count || 0;
      const syncOk = result.sync_ok;
      const syncFail = result.sync_fail || 0;
      let finalMsg = failN
        ? `配图 ${okN}/${total} · 失败 ${failN}`
        : `配图完成 ${okN}/${total}`;
      if (syncOk != null) {
        finalMsg += ` · 已写回 Memos ${syncOk}`;
        if (syncFail) finalMsg += ` · 写回失败 ${syncFail}`;
      }
      if (statusEl) statusEl.textContent = finalMsg;
      if (failN || syncFail) {
        const err = (result.failures || rows.filter((r) => !r.success || r.sync_error))
          .map((r) => r.sync_error || r.error || "失败")
          .slice(0, 2)
          .join("；");
        if (err) toast(err.slice(0, 180), "error");
        else toast(finalMsg, failN && !okN ? "error" : "ok");
      } else {
        toast(finalMsg, "ok");
      }
      if (btn) btn.disabled = false;
      return;
    }
    await new Promise((r) => setTimeout(r, 2500));
  }
  if (statusEl) statusEl.textContent = "配图超时，请稍后重试";
  if (btn) btn.disabled = false;
}

async function runMemosBatchImages() {
  const items = state.memosItems || [];
  const indices = memosSelectedIndices();
  if (!items.length) {
    toast("请先拉取 Memos 文章", "error");
    return;
  }
  if (!indices.length) {
    toast("请勾选至少一篇文章", "error");
    return;
  }
  const btn = $("#btnMemosGenImages");
  const statusEl = $("#memosImageStatus");
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = "提交配图任务…";
  try {
    const payload = {
      indices,
      topic: "Memos",
      sync_to_memos: true,
      debugger_url: $("#debuggerUrl")?.value.trim() || "127.0.0.1:9222",
      variants: items.map((it) => ({
        id: it.id || it.name,
        name: it.name || (it.id ? `memos/${it.id}` : ""),
        label: it.title || it.label || it.id,
        hook: it.hook || it.title || "",
        content: it.content || "",
      })),
    };
    const data = await api("/api/corpus/lab/images", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!data.success || !data.job_id) {
      toast(data.error || "提交失败", "error");
      if (btn) btn.disabled = false;
      return;
    }
    await pollMemosImageJob(data.job_id);
  } catch (e) {
    toast(String(e), "error");
    if (btn) btn.disabled = false;
    if (statusEl) statusEl.textContent = "";
  }
}

async function syncMemosImagesBack() {
  const items = state.memosItems || [];
  const indices = memosSelectedIndices();
  const payload = indices
    .map((i) => items[i])
    .filter((it) => it && it.name && (it.dirty || (it.images || []).length || (it.media_paths || []).length));
  if (!payload.length) {
    toast("勾选中没有已配图、可写回的文章", "error");
    return;
  }
  const btn = $("#btnMemosSync");
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/corpus/memos/sync", {
      method: "POST",
      body: JSON.stringify({
        items: payload.map((it) => ({
          name: it.name,
          content: it.content,
          media_paths: it.media_paths || [],
        })),
      }),
    });
    if (!data.success) {
      toast(data.error || "写回失败", "error");
      return;
    }
    for (const r of data.results || []) {
      if (!r.success) continue;
      const hit = items.find((x) => x.name === r.name);
      if (hit) {
        hit.dirty = false;
        if (r.item?.content) hit.content = r.item.content;
      }
    }
    renderMemosList(items);
    toast(`已写回 Memos ${data.ok_count}/${payload.length}`, data.fail_count ? "error" : "ok");
    const statusEl = $("#memosImageStatus");
    if (statusEl) {
      statusEl.textContent = `写回 ${data.ok_count}/${payload.length}${
        data.fail_count ? ` · 失败 ${data.fail_count}` : ""
      }`;
    }
  } catch (e) {
    toast(String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function labSaveFeatured(variantIdx) {
  const variants = state.labVariants || [];
  let v = state.labActiveVariant;
  if (variantIdx != null && variants[variantIdx]) {
    v = variants[variantIdx];
    state.labActiveVariant = v;
  }
  if (!v?.content) {
    toast("请先选一个变体", "error");
    return;
  }
  const data = await api("/api/corpus/lab/feature", {
    method: "POST",
    body: JSON.stringify({
      content: v.content,
      hook: v.hook || "",
      topic: $("#regenTopic")?.value.trim() || v.label || "精选变体",
      variant_id: v.id || "",
      variant_label: v.label || "",
      formula: state.labFormula || "",
      generation_id: v.generation_id || null,
      template_ids: [...(state.corpusSelected || [])],
      source_cards: collectTrayElements(),
      platform_style: $("#regenStyle")?.value.trim() || "X/Twitter",
      cot: state.labCot || [],
    }),
  });
  if (data.success) {
    v.featured = true;
    v.generation_id = data.generation?.id || v.generation_id;
    const idx = variants.indexOf(v);
    renderLabVariants(variants.length ? variants : [v], idx >= 0 ? idx : 0);
    toast(data.message || `已精选留存 #${data.generation?.id}`, "ok");
    await loadGenerations();
    await loadCorpus();
  } else toast(data.error || "留存失败", "error");
}

async function runXgrowthViral() {
  const btn = $("#btnXgrowthRun");
  const limit = Number($("#xgrowthLimit")?.value || 8);
  const minVel = Number($("#xgrowthMinVel")?.value || 0);
  if (btn) btn.disabled = true;
  setStatus($("#xgrowthStatus"), "已提交任务，CDP 抓取中…");
  const out = $("#xgrowthOut");
  if (out) {
    out.classList.add("muted");
    out.textContent = "排队…";
  }
  try {
    const start = await api("/api/corpus/xgrowth/run", {
      method: "POST",
      body: JSON.stringify({
        limit,
        min_velocity: minVel,
        include_potential: !!$("#xgrowthPotential")?.checked,
        open_tweet: !!$("#xgrowthOpenTweet")?.checked,
      }),
    });
    if (!start.success || !start.job_id) {
      setStatus($("#xgrowthStatus"), start.error || "启动失败", "error");
      return;
    }
    const jobId = start.job_id;
    for (;;) {
      await new Promise((r) => setTimeout(r, 1500));
      const data = await api(`/api/jobs/${jobId}`);
      const job = data.job || {};
      setStatus($("#xgrowthStatus"), job.message || job.status || "运行中…");
      if (out && job.message) out.textContent = job.message;
      if (job.status === "done" || job.status === "error") {
        const result = job.result || {};
        if (out) {
          out.classList.toggle("muted", job.status !== "done");
          out.textContent = JSON.stringify(result.items || result, null, 2);
        }
        setStatus(
          $("#xgrowthStatus"),
          job.status === "done"
            ? `完成：入库 ${result.ok || 0} 条`
            : job.message || "失败",
          job.status === "done" ? "ok" : "error"
        );
        if (job.status === "done") {
          toast(`xgrowth 拆解完成 ${result.ok || 0} 条`, "ok");
          await loadCorpus();
          await refreshCorpusStats();
        }
        break;
      }
    }
  } catch (e) {
    setStatus($("#xgrowthStatus"), String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function reloadCurrentList() {
  const t = state.listTarget;
  if (t === "history") {
    await loadPosts(
      $("#historyKeyword").value.trim(),
      state.historyPlatform || $("#historyPlatform").value.trim(),
      "history",
      $("#historyView")?.value || "all",
      $("#historyTag")?.value.trim() || ""
    );
  } else if (t === "later" || t === "archived" || t === "tags") {
    await loadLibrary(t);
  } else {
    await loadPosts(
      $("#newsKeyword").value.trim(),
      state.newsPlatform || "",
      "news",
      $("#newsView")?.value || "active",
      ""
    );
  }
  await refreshStats();
}

async function pollJob(jobId) {
  for (let i = 0; i < 180; i++) {
    const data = await api(`/api/jobs/${jobId}`);
    const job = data.job || {};
    setStatus($("#crawlStatus"), job.message || job.status || "运行中…");
    if (job.plan && job.plan.twitter_queries) {
      const box = $("#expandPreview");
      const body = $("#expandPreviewBody");
      if (box && body) {
        box.hidden = false;
        body.textContent = JSON.stringify(
          {
            provider: (job.expansion && job.expansion.provider) || "",
            seeds: job.plan.seeds,
            twitter_queries: job.plan.twitter_queries,
            reddit_queries: job.plan.reddit_queries,
            telegram_queries: job.plan.telegram_queries,
          },
          null,
          2
        );
      }
    }
    if (job.status === "done") {
      let doneMsg = job.message || "完成";
      const extra = job.extra || {};
      const errs = extra.errors || [];
      if (errs.length) {
        doneMsg += `｜${String(errs[0]).slice(0, 120)}`;
      }
      setStatus($("#crawlStatus"), doneMsg, errs.length ? "error" : "ok");
      if (errs.length) toast(String(errs[0]).slice(0, 180), "error");
      await loadPosts(
        $("#newsKeyword").value.trim(),
        state.newsPlatform || "",
        "news",
        $("#newsView")?.value || "active",
        ""
      );
      await refreshStats();
      await loadTasks();
      return;
    }
    if (job.status === "error") {
      setStatus($("#crawlStatus"), job.message || "抓取失败", "error");
      await loadTasks();
      return;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  setStatus($("#crawlStatus"), "等待超时，请稍后在历史缓存中查看", "error");
}

function selectedPlatforms() {
  const plats = [];
  if ($("#platX")?.checked) plats.push("x-cdp");
  if ($("#platReddit")?.checked) plats.push("reddit");
  if ($("#platTelegram")?.checked) plats.push("telegram");
  return plats.length ? plats : ["x-cdp"];
}

function taskCardHtml(t) {
  const enabled = !!t.enabled;
  const plats = (t.platforms || []).join(", ");
  // 状态文案长度固定，避免「执行中」闪现导致卡片宽度来回跳
  const statusText = enabled ? "运行中" : "已停止";
  const runFlag = t.running ? "执行中" : "";
  return `
        <article class="item${enabled ? "" : " is-archived"}" data-task-id="${escapeAttr(t.id)}" data-enabled="${enabled ? "1" : "0"}">
          <h3 data-k="title">${escapeHtml(t.name || t.keyword || "")}</h3>
          <div class="meta">
            <span class="badge ${enabled ? "badge-later" : "badge-archive"}" data-k="status">${statusText}</span>
            <span class="run-flag" data-k="runflag">${runFlag}</span>
            <span data-k="schedule">${escapeHtml(t.schedule_label || `每 ${t.interval_min} 分`)}</span>
            <span data-k="runcount">已跑 ${t.run_count || 0} 次</span>
            <span data-k="plats">${escapeHtml(plats)}</span>
            <span data-k="lastrun">${t.last_run_at ? `上次 ${escapeHtml(t.last_run_at)}` : ""}</span>
            <span data-k="nextrun">${t.next_run_at && enabled ? `下次 ${escapeHtml(t.next_run_at)}` : ""}</span>
            <span data-k="stopped">${t.stopped_at && !enabled ? `停止于 ${escapeHtml(t.stopped_at)}` : ""}</span>
          </div>
          <p class="snippet" data-k="msg">${escapeHtml(t.last_message || "")}</p>
          <p class="snippet muted" data-k="note"${t.note ? "" : " hidden"}>备注：${escapeHtml(t.note || "")}</p>
          <div class="item-actions">
            <button class="btn ghost btn-sm" type="button" data-task-action="toggle">${enabled ? "停止" : "启动"}</button>
            <button class="btn ghost btn-sm" type="button" data-task-action="run_now">立即执行</button>
            <button class="btn ghost btn-sm" type="button" data-task-action="fill">填回表单</button>
            <button class="btn ghost btn-sm" type="button" data-task-action="delete">删除</button>
          </div>
        </article>`;
}

function patchTaskCard(article, t) {
  const enabled = !!t.enabled;
  const set = (key, text, asHtml = false) => {
    const el = article.querySelector(`[data-k="${key}"]`);
    if (!el) return;
    const next = text || "";
    if (asHtml) {
      if (el.innerHTML !== next) el.innerHTML = next;
    } else if (el.textContent !== next) {
      el.textContent = next;
    }
  };
  article.classList.toggle("is-archived", !enabled);
  article.dataset.enabled = enabled ? "1" : "0";
  set("title", t.name || t.keyword || "");
  set("status", enabled ? "运行中" : "已停止");
  set("runflag", t.running ? "执行中" : "");
  set("schedule", t.schedule_label || `每 ${t.interval_min} 分`);
  set("runcount", `已跑 ${t.run_count || 0} 次`);
  set("plats", (t.platforms || []).join(", "));
  set("lastrun", t.last_run_at ? `上次 ${t.last_run_at}` : "");
  set("nextrun", t.next_run_at && enabled ? `下次 ${t.next_run_at}` : "");
  set("stopped", t.stopped_at && !enabled ? `停止于 ${t.stopped_at}` : "");
  set("msg", t.last_message || "");
  const noteEl = article.querySelector('[data-k="note"]');
  if (noteEl) {
    noteEl.hidden = !t.note;
    noteEl.textContent = t.note ? `备注：${t.note}` : "";
  }
  const badge = article.querySelector('[data-k="status"]');
  if (badge) {
    badge.className = `badge ${enabled ? "badge-later" : "badge-archive"}`;
  }
  const toggle = article.querySelector('[data-task-action="toggle"]');
  if (toggle) toggle.textContent = enabled ? "停止" : "启动";
}

function bindTaskActions(box, items) {
  box.querySelectorAll("[data-task-action]").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      const article = btn.closest("[data-task-id]");
      const id = article?.getAttribute("data-task-id") || "";
      const action = btn.getAttribute("data-task-action") || "";
      if (!id || !action) return;

      if (action === "fill") {
        const item = (state.taskItems || items).find((x) => x.id === id);
        if (!item) return;
        fillTaskToForm(item);
        toast("已填回表单，可修改后再次添加为周期任务", "ok");
        return;
      }
      if (action === "delete") {
        if (!window.confirm("确定从历史任务库永久删除该任务？")) return;
        const data2 = await api(`/api/crawl/tasks/${id}`, {
          method: "POST",
          body: JSON.stringify({ action: "delete" }),
        });
        if (!data2.success) {
          toast(data2.error || "删除失败", "error");
          return;
        }
        toast("已删除任务", "ok");
        await loadTasks();
        return;
      }
      if (action === "toggle" || action === "stop" || action === "start") {
        const enabled = article?.dataset.enabled === "1";
        if (action === "stop" || (action === "toggle" && enabled)) {
          await api(`/api/crawl/tasks/${id}`, { method: "DELETE" });
          toast("已停止（仍保留在任务库）", "ok");
          await loadTasks();
          return;
        }
        const data2 = await api(`/api/crawl/tasks/${id}`, {
          method: "POST",
          body: JSON.stringify({ action: "start", run_now: false }),
        });
        if (!data2.success) {
          toast(data2.error || "启动失败", "error");
          return;
        }
        toast("已启动周期任务", "ok");
        await loadTasks();
        return;
      }
      if (action === "run_now") {
        btn.disabled = true;
        try {
          const data2 = await api(`/api/crawl/tasks/${id}`, {
            method: "POST",
            body: JSON.stringify({ action: "run_now" }),
          });
          if (!data2.success) {
            toast(data2.error || "触发失败", "error");
            return;
          }
          toast("已触发立即执行", "ok");
          if (data2.job_id) await pollJob(data2.job_id);
          await loadTasks();
        } finally {
          btn.disabled = false;
        }
      }
    });
  });
}

async function loadTasks() {
  const status = state.taskStatus || "all";
  const data = await api(`/api/crawl/tasks?status=${encodeURIComponent(status)}`);
  const box = $("#taskList");
  const meta = $("#taskMeta");
  if (!box) return;
  const items = data.items || [];
  state.taskItems = items;
  const counts = data.counts || {};
  document.querySelectorAll("#taskStatusBar [data-task-status]").forEach((btn) => {
    btn.classList.toggle("on", btn.getAttribute("data-task-status") === status);
  });
  if (meta) {
    // 固定槽位宽度在 CSS；文案用等宽数字，避免 meta 行抖动
    setStatus(
      meta,
      `全部 ${counts.all || 0} · 运行中 ${counts.active || 0} · 已停止 ${counts.stopped || 0}`,
      "ok"
    );
  }

  if (!items.length) {
    box.dataset.sig = "";
    box.innerHTML = `<div class="item"><h3>暂无周期任务</h3><p class="snippet">勾选「添加为周期任务」后开始抓取，任务会进入此库并长期保留。</p></div>`;
    return;
  }

  const sig = items.map((t) => `${t.id}:${t.enabled ? 1 : 0}`).join("|");
  if (box.dataset.sig === sig && box.querySelector("[data-task-id]")) {
    items.forEach((t) => {
      const id = String(t.id);
      const article = [...box.querySelectorAll("[data-task-id]")].find(
        (el) => el.getAttribute("data-task-id") === id
      );
      if (article) patchTaskCard(article, t);
    });
    return;
  }

  box.dataset.sig = sig;
  box.innerHTML = items.map((t) => taskCardHtml(t)).join("");
  bindTaskActions(box, items);
}

function fillTaskToForm(task) {
  if ($("#newsKeyword")) $("#newsKeyword").value = task.keyword || "";
  if ($("#crawlScheduled")) $("#crawlScheduled").checked = true;
  if ($("#crawlExpand")) $("#crawlExpand").checked = !!task.expand;
  const mode = task.schedule_mode || "interval";
  if ($("#crawlScheduleMode")) $("#crawlScheduleMode").value = mode;
  if ($("#crawlInterval")) $("#crawlInterval").value = task.interval_min || 30;
  if ($("#crawlJitter")) $("#crawlJitter").value = task.jitter_min || 0;
  if ($("#crawlDailyHour")) $("#crawlDailyHour").value = task.daily_hour ?? 9;
  const plats = new Set(task.platforms || []);
  if ($("#platX")) $("#platX").checked = plats.has("x-cdp") || plats.has("x") || plats.has("twitter");
  if ($("#platReddit")) $("#platReddit").checked = plats.has("reddit");
  if ($("#platTelegram")) $("#platTelegram").checked = plats.has("telegram");
  syncScheduleModeUi();
  syncTaskUi();
}

function syncScheduleModeUi() {
  const mode = $("#crawlScheduleMode")?.value || "interval";
  const intervalField = $("#crawlIntervalField");
  const dailyField = $("#crawlDailyHourField");
  if (intervalField) intervalField.hidden = mode === "daily";
  if (dailyField) dailyField.hidden = mode !== "daily";
}

function syncTaskUi() {
  const scheduled = !!$("#crawlScheduled")?.checked;
  const opts = $("#taskScheduleOpts");
  if (opts) opts.hidden = !scheduled;
  syncScheduleModeUi();
  loadTasks();
}

function publishPlatformEnabled(meta) {
  if (!meta) return true;
  const v = meta.enabled;
  if (v === false || v === 0 || v === "false" || v === "0") return false;
  return true;
}

async function loadPublishPlatforms(selectedIds) {
  const box = $("#publishPlatformChecks");
  if (!box) return;
  let apiPlatforms = [];
  try {
    const data = await api("/api/platforms/publish");
    if (data && data.success !== false) {
      apiPlatforms = Array.isArray(data.platforms) ? data.platforms : [];
    }
  } catch (_) {
    /* 离线时用预设列表 */
  }
  const byId = new Map();
  apiPlatforms.forEach((p) => {
    if (p?.id) byId.set(String(p.id), p);
  });
  PUBLISH_PLATFORM_ORDER.forEach((preset) => {
    const cur = byId.get(preset.id);
    if (!cur) {
      byId.set(preset.id, { id: preset.id, name: preset.name, enabled: true });
    } else if (!cur.name) {
      cur.name = preset.name;
    }
  });
  const ordered = [];
  const seen = new Set();
  PUBLISH_PLATFORM_ORDER.forEach((preset) => {
    const meta = byId.get(preset.id) || preset;
    ordered.push({
      id: preset.id,
      name: meta.name || preset.name,
      enabled: publishPlatformEnabled(meta),
    });
    seen.add(preset.id);
  });
  apiPlatforms.forEach((p) => {
    const id = String(p?.id || "");
    if (!id || seen.has(id)) return;
    seen.add(id);
    ordered.push({
      id,
      name: p.name || id,
      enabled: publishPlatformEnabled(p),
    });
  });
  if (!ordered.length) {
    PUBLISH_PLATFORM_ORDER.forEach((preset) => {
      ordered.push({ id: preset.id, name: preset.name, enabled: true });
    });
  }
  const selected = new Set(
    selectedIds?.length ? selectedIds : PUBLISH_PLATFORM_DEFAULT_IDS
  );
  box.innerHTML = ordered
    .map((p) => {
      const disabled = p.enabled ? "" : " disabled";
      const checked = p.enabled && selected.has(p.id) ? " checked" : "";
      return `<label class="publish-plat-check corpus-check${p.enabled ? "" : " is-disabled"}">
      <input type="checkbox" data-platform value="${escapeHtml(p.id)}"${checked}${disabled} />
      <span>${escapeHtml(p.name)}</span>
    </label>`;
    })
    .join("");
}

function selectedPublishPlatforms() {
  const box = $("#publishPlatformChecks");
  if (!box) return [];
  return [...box.querySelectorAll('input[type="checkbox"][data-platform]:checked')]
    .map((el) => el.value)
    .filter(Boolean);
}

function parseMediaPaths(raw) {
  return String(raw || "")
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function toDatetimeLocalValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return String(iso).slice(0, 16);
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function defaultScheduleLocal(minutesAhead = 30) {
  const d = new Date(Date.now() + minutesAhead * 60 * 1000);
  return toDatetimeLocalValue(d.toISOString());
}

const PUBLISH_PREFS_KEY = "pai_publish_prefs";
const PUBLISH_MEDIA_CACHE_MAX_BYTES = 4 * 1024 * 1024;
/** @type {{name:string,type:string,data_b64:string}[]} */
let publishMediaItems = [];
/** 从草稿/队列载入的服务器本地媒体绝对路径（发布时直接复用） */
let publishServerMediaPaths = [];
/** 对应 preview 用的 cache rel */
let publishServerMediaRels = [];

function publishMediaCacheBytes(items = publishMediaItems) {
  return (items || []).reduce(
    (n, it) => n + Math.ceil(((it.data_b64 || "").length * 3) / 4),
    0,
  );
}

function normalizePublishMediaItem(row) {
  if (!row || typeof row !== "object") return null;
  const data_b64 = String(row.data_b64 || row.content_base64 || row.data || "").trim();
  if (!data_b64) return null;
  return {
    name: String(row.name || row.filename || "image.jpg"),
    type: String(row.type || row.mime || "image/jpeg"),
    data_b64,
  };
}

function restorePublishMediaItems(raw) {
  if (!Array.isArray(raw)) {
    publishMediaItems = [];
    return;
  }
  publishMediaItems = raw.map(normalizePublishMediaItem).filter(Boolean);
}

function persistPublishMediaItems() {
  try {
    savePublishPrefs({ mediaFiles: publishMediaItems });
  } catch (_) {
    toast("图片缓存写入失败（可能超出浏览器容量）", "error");
  }
}

function loadPublishPrefs() {
  try {
    const raw = localStorage.getItem(PUBLISH_PREFS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function savePublishPrefs(patch) {
  try {
    const cur = loadPublishPrefs();
    localStorage.setItem(
      PUBLISH_PREFS_KEY,
      JSON.stringify({ ...cur, ...patch, saved_at: Date.now() }),
    );
  } catch (_) {}
}

function snapshotPublishPrefs() {
  savePublishPrefs({
    debuggerUrl: $("#debuggerUrl")?.value.trim() || "127.0.0.1:9222",
    useCdp: !!$("#useCdp")?.checked,
    publishDryRun: !!$("#publishDryRun")?.checked,
    content: $("#publishContent")?.value || "",
    scheduleAt: $("#publishScheduleAt")?.value || "",
    scheduleBaseline: $("#publishScheduleAt")?.dataset.default || "",
    platforms: selectedPublishPlatforms(),
    mediaFiles: publishMediaItems,
  });
}

function restorePublishPrefsFields() {
  const p = loadPublishPrefs();
  if (p.debuggerUrl != null && $("#debuggerUrl")) $("#debuggerUrl").value = p.debuggerUrl;
  if ($("#useCdp")) $("#useCdp").checked = p.useCdp !== false;
  if ($("#publishDryRun")) $("#publishDryRun").checked = !!p.publishDryRun;
  if (p.content != null && $("#publishContent")) $("#publishContent").value = p.content;
  restorePublishMediaItems(p.mediaFiles);
  renderMediaPreview();
  return Array.isArray(p.platforms) ? p.platforms : null;
}

function bindPublishPrefsAutosave() {
  if (document.body.dataset.publishPrefsBound) return;
  document.body.dataset.publishPrefsBound = "1";
  let timer = null;
  const queue = () => {
    clearTimeout(timer);
    timer = setTimeout(snapshotPublishPrefs, 280);
  };
  $("#debuggerUrl")?.addEventListener("input", queue);
  $("#publishContent")?.addEventListener("input", queue);
  $("#publishScheduleAt")?.addEventListener("change", queue);
  $("#useCdp")?.addEventListener("change", queue);
  $("#publishDryRun")?.addEventListener("change", queue);
  $("#publishPlatformChecks")?.addEventListener("change", queue);
}

function initPublishScheduleDefault() {
  const el = $("#publishScheduleAt");
  if (!el) return;
  const p = loadPublishPrefs();
  const def = defaultScheduleLocal(30);
  el.dataset.default = p.scheduleBaseline || def;
  el.value = p.scheduleAt || def;
}

function isPublishScheduleDefault() {
  const el = $("#publishScheduleAt");
  if (!el) return true;
  const baseline = el.dataset.default || "";
  return el.value === baseline;
}

function resetPublishScheduleDefault() {
  initPublishScheduleDefault();
}

function fileToBase64Payload(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      const data_b64 = comma >= 0 ? result.slice(comma + 1) : result;
      resolve({
        name: file.name,
        type: file.type || "",
        data_b64,
      });
    };
    reader.onerror = () => reject(reader.error || new Error("读取文件失败"));
    reader.readAsDataURL(file);
  });
}

async function collectUploadMediaFiles() {
  return publishMediaItems.map(({ name, type, data_b64 }) => ({
    name,
    type,
    data_b64,
  }));
}

function normalizePastedMediaFile(file, index = 0) {
  if (!file) return null;
  const type = file.type || "";
  if (!type.startsWith("image/") && !type.startsWith("video/")) return null;
  if (file.name) return file;
  const ext = (type.split("/")[1] || "png").replace("jpeg", "jpg");
  const name = `paste-${Date.now()}${index ? `-${index}` : ""}.${ext}`;
  return new File([file], name, { type });
}

async function appendPublishMediaFiles(newFiles) {
  if (!newFiles?.length) return 0;
  const next = [...publishMediaItems];
  let added = 0;
  for (let i = 0; i < newFiles.length; i++) {
    const f = normalizePastedMediaFile(newFiles[i], i + 1);
    if (!f) continue;
    if (f.size > 12 * 1024 * 1024) {
      toast(`文件过大（>12MB）: ${f.name}`, "error");
      continue;
    }
    const payload = await fileToBase64Payload(f);
    const trial = [...next, payload];
    if (publishMediaCacheBytes(trial) > PUBLISH_MEDIA_CACHE_MAX_BYTES) {
      toast("图片缓存已满（约 4MB），请删除部分后再添加", "error");
      break;
    }
    next.push(payload);
    added += 1;
  }
  if (!added) return 0;
  publishMediaItems = next;
  persistPublishMediaItems();
  renderMediaPreview();
  snapshotPublishPrefs();
  return added;
}

function handlePublishMediaPaste(e) {
  const panel = $("#panel-publish");
  if (!panel || panel.hidden) return;
  const items = e.clipboardData?.items;
  if (!items?.length) return;
  const files = [];
  for (const item of items) {
    if (item.kind !== "file") continue;
    const f = item.getAsFile();
    if (f && (f.type.startsWith("image/") || f.type.startsWith("video/"))) {
      files.push(f);
    }
  }
  if (!files.length) return;
  e.preventDefault();
  e.stopPropagation();
  appendPublishMediaFiles(files).then((n) => {
    if (n) toast(`已粘贴 ${n} 个媒体文件`, "ok");
  });
}

function bindPublishMediaPaste() {
  const panel = $("#panel-publish");
  if (!panel || panel.dataset.pasteBound) return;
  panel.dataset.pasteBound = "1";
  panel.addEventListener("paste", handlePublishMediaPaste);
}

function removePublishMediaFile(index) {
  if (index < 0 || index >= publishMediaItems.length) return;
  publishMediaItems = publishMediaItems.filter((_, i) => i !== index);
  persistPublishMediaItems();
  renderMediaPreview();
  snapshotPublishPrefs();
}

function renderMediaPreview() {
  const box = $("#publishMediaPreview");
  if (!box) return;
  box.innerHTML = "";
  publishMediaItems.forEach((item, index) => {
    const wrap = document.createElement("div");
    wrap.className = "media-thumb";
    const mime = item.type || "image/jpeg";
    if (mime.startsWith("image/")) {
      const img = document.createElement("img");
      img.className = "thumb";
      img.alt = item.name;
      img.src = `data:${mime};base64,${item.data_b64}`;
      wrap.appendChild(img);
    } else {
      const ph = document.createElement("div");
      ph.className = "thumb thumb-video";
      ph.textContent = "视频";
      wrap.appendChild(ph);
    }
    const del = document.createElement("button");
    del.type = "button";
    del.className = "media-thumb-del";
    del.setAttribute("data-media-del", String(index));
    del.setAttribute("aria-label", "删除");
    del.textContent = "×";
    wrap.appendChild(del);
    const name = document.createElement("div");
    name.className = "thumb-name";
    name.textContent = item.name;
    wrap.appendChild(name);
    box.appendChild(wrap);
  });
  (publishServerMediaPaths || []).forEach((path, index) => {
    const wrap = document.createElement("div");
    wrap.className = "media-thumb";
    const base = String(path).split(/[/\\]/).pop() || `media-${index + 1}`;
    const rel = (publishServerMediaRels || [])[index] || "";
    const isImg = /\.(png|jpe?g|gif|webp|bmp)$/i.test(base);
    if (isImg && rel) {
      const img = document.createElement("img");
      img.className = "thumb";
      img.alt = base;
      img.src = `/api/publish/cache/file?rel=${encodeURIComponent(rel)}`;
      wrap.appendChild(img);
    } else {
      const ph = document.createElement("div");
      ph.className = "thumb thumb-video";
      ph.textContent = isImg ? "图" : "媒体";
      wrap.appendChild(ph);
    }
    const del = document.createElement("button");
    del.type = "button";
    del.className = "media-thumb-del";
    del.setAttribute("data-server-media-del", String(index));
    del.setAttribute("aria-label", "删除");
    del.textContent = "×";
    wrap.appendChild(del);
    const name = document.createElement("div");
    name.className = "thumb-name";
    name.textContent = base;
    wrap.appendChild(name);
    box.appendChild(wrap);
  });
}

async function onPublishMediaFilesChange() {
  const input = $("#publishMediaFiles");
  const files = input?.files ? [...input.files] : [];
  if (files.length) {
    await appendPublishMediaFiles(files);
  }
  if (input) input.value = "";
}

function publishPlatformLabel(platformId) {
  const id = String(platformId || "");
  const box = $("#publishPlatformChecks");
  const input = box?.querySelector(`input[data-platform][value="${CSS.escape(id)}"]`);
  const span = input?.closest("label")?.querySelector("span");
  if (span?.textContent) return span.textContent.trim();
  return PUBLISH_PLATFORM_ORDER.find((p) => p.id === id)?.name || id;
}

function formatPublishStepSummary(results) {
  return (results || [])
    .map((r) => {
      const name = r.name || publishPlatformLabel(r.platform);
      if (r.success) return `${name} ✓`;
      const err = r.error ? ` (${String(r.error).slice(0, 24)})` : "";
      return `${name} ✗${err}`;
    })
    .join(" · ");
}

function renderPublishProgress({ phase, index, total, name, results }) {
  const box = $("#publishProgress");
  if (!box) return;
  box.hidden = false;
  const done = (results || []).length;
  const pct = total ? Math.round((Math.max(0, index - (phase === "running" ? 1 : 0)) / total) * 100) : 0;
  const barPct = phase === "running" ? Math.round(((index - 1) / total) * 100 + 50 / total) : 100;
  const rows = (results || [])
    .map((r) => {
      const label = r.name || publishPlatformLabel(r.platform);
      const cls = r.success ? "done" : "failed";
      const mark = r.success ? "✓" : "✗";
      return `<li class="publish-step ${cls}"><span>${escapeHtml(label)}</span><em>${mark}</em></li>`;
    })
    .join("");
  const current =
    phase === "running" && name
      ? `<li class="publish-step running"><span>${escapeHtml(name)}</span><em>…</em></li>`
      : "";
  box.innerHTML = `
    <div class="publish-progress-head">
      <span>${phase === "running" ? `正在发布 ${index}/${total}` : `已完成 ${done}/${total}`}</span>
      <span class="muted">${pct}%</span>
    </div>
    <div class="publish-progress-bar"><i style="width:${Math.min(100, barPct)}%"></i></div>
    <ul class="publish-progress-steps">${rows}${current}</ul>`;
}

function clearPublishProgress() {
  const box = $("#publishProgress");
  if (!box) return;
  box.hidden = true;
  box.innerHTML = "";
}

async function publishNowViaCdp(onProgress) {
  const platforms = selectedPublishPlatforms();
  if (!platforms.length) {
    throw new Error("请至少选择一个平台");
  }
  const content = $("#publishContent")?.value.trim() || "";
  const media_files = await collectUploadMediaFiles();
  const initialPaths = [...(publishServerMediaPaths || [])];
  if (!content && !media_files.length && !initialPaths.length) {
    throw new Error("请填写正文或上传图片");
  }
  const dry = !!$("#publishDryRun")?.checked;
  const base = {
    title: "",
    content,
    tags: "",
    media_paths: initialPaths,
    use_cdp: true,
    debugger_url: $("#debuggerUrl")?.value.trim() || "127.0.0.1:9222",
    submit: !dry,
  };
  const stepResults = [];
  let stagedMediaPaths = [...initialPaths];
  for (let i = 0; i < platforms.length; i++) {
    const pid = platforms[i];
    const name = publishPlatformLabel(pid);
    onProgress?.({
      phase: "running",
      index: i + 1,
      total: platforms.length,
      platform: pid,
      name,
      results: stepResults,
    });
    setStatus($("#publishStatus"), `正在发布 (${i + 1}/${platforms.length}) ${name}…`);
    const data = await api("/api/publish", {
      method: "POST",
      body: JSON.stringify({
        ...base,
        platforms: [pid],
        media_paths: stagedMediaPaths,
        media_files: stagedMediaPaths.length ? [] : media_files,
      }),
    });
    if (data.media_paths?.length) {
      stagedMediaPaths = data.media_paths;
    }
    const row = data.results?.[0] || {
      platform: pid,
      platform_name: name,
      success: !!data.success,
      error: data.error,
    };
    stepResults.push({
      platform: pid,
      name: row.platform_name || name,
      success: !!row.success,
      error: row.error || (row.success ? "" : data.error),
    });
    onProgress?.({
      phase: row.success ? "done" : "fail",
      index: i + 1,
      total: platforms.length,
      platform: pid,
      name,
      results: stepResults,
    });
  }
  const success_count = stepResults.filter((r) => r.success).length;
  return {
    success: success_count > 0,
    total: platforms.length,
    success_count,
    results: stepResults,
  };
}

async function submitPublish() {
  if (isPublishScheduleDefault()) {
    return {
      mode: "now",
      data: await publishNowViaCdp((p) => renderPublishProgress(p)),
    };
  }
  const platforms = selectedPublishPlatforms();
  const names = platforms.map(publishPlatformLabel).join("、");
  setStatus($("#publishStatus"), `正在加入定时队列 · ${names || "—"}…`);
  const draft = await collectPublishDraft({ requireSchedule: true });
  draft.scheduled_at = $("#publishScheduleAt")?.value || "";
  const data = await api("/api/publish/queue", {
    method: "POST",
    body: JSON.stringify(draft),
  });
  if (!data.success) {
    throw new Error(data.error || "加入定时队列失败");
  }
  return { mode: "schedule", data };
}

async function collectPublishDraft({ requireSchedule = false, allowNoPlatform = false } = {}) {
  const media_files = await collectUploadMediaFiles();
  const platforms = selectedPublishPlatforms();
  const media_paths = [...(publishServerMediaPaths || [])];
  const draft = {
    title: "",
    content: $("#publishContent")?.value.trim() || "",
    tags: "",
    series_note: $("#publishSeriesNote")?.value.trim() || "",
    platforms,
    media_paths,
    media_files,
    use_cdp: true,
    debugger_url: $("#debuggerUrl")?.value.trim() || "127.0.0.1:9222",
    scheduled_at: $("#publishScheduleAt")?.value || "",
  };
  if (!allowNoPlatform && !draft.platforms.length) {
    throw new Error("请至少选择一个平台");
  }
  if (!draft.content && !draft.media_paths.length && !draft.media_files.length) {
    throw new Error("请填写正文或上传图片");
  }
  if (requireSchedule && !draft.scheduled_at) {
    throw new Error("请设置预约发布时间");
  }
  return draft;
}

function clearPublishEditorKeepMeta() {
  if ($("#publishContent")) $("#publishContent").value = "";
  if ($("#publishSeriesNote")) {
    /* 系列备注保留，方便连续录入同一系列 */
  }
  publishMediaItems = [];
  publishServerMediaPaths = [];
  publishServerMediaRels = [];
  if ($("#publishMedia")) $("#publishMedia").value = "";
  persistPublishMediaItems();
  const input = $("#publishMediaFiles");
  if (input) input.value = "";
  renderMediaPreview();
  resetPublishScheduleDefault();
  snapshotPublishPrefs();
}

const PUBLISH_MODE_LS = "publishWorkbenchMode";
let publishWorkbenchMode = "publish";

function applyPublishWorkbenchMode(mode) {
  const m = mode === "cache" ? "cache" : "publish";
  publishWorkbenchMode = m;
  document.querySelectorAll(".publish-mode-tab").forEach((btn) => {
    const on = btn.getAttribute("data-publish-mode") === m;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".publish-only-field, .publish-only-toolbar, .publish-only-section").forEach((el) => {
    el.hidden = m === "cache";
  });
  document.querySelectorAll(".cache-only-field, .cache-only-toolbar, .cache-only-section").forEach((el) => {
    el.hidden = m !== "cache";
  });
  const platHint = $("#publishCachePlatHint");
  if (platHint) platHint.hidden = m !== "cache";
  const hint = $("#publishModeHint");
  if (hint) {
    hint.innerHTML =
      m === "cache"
        ? "仅缓存模式：粘贴图文加入系列卡片，攒够后再<strong>勾选批量发布</strong>。不会自动发到平台。"
        : "正文 + 图片发布到所选平台。预约时间<strong>默认不修改则立即发布</strong>；也可切到「仅缓存」攒一批再手动批量发。";
  }
  const platLabel = $("#publishPlatformLabel");
  if (platLabel) platLabel.textContent = m === "cache" ? "批量发布时使用的平台" : "发布平台";
  try {
    localStorage.setItem(PUBLISH_MODE_LS, m);
  } catch (_) {}
  if (m === "cache") loadPublishSeriesCards();
  else {
    loadPublishQueue();
    loadPublishCache();
  }
}

function restorePublishWorkbenchMode() {
  try {
    const saved = localStorage.getItem(PUBLISH_MODE_LS);
    if (saved === "cache" || saved === "publish") {
      applyPublishWorkbenchMode(saved);
      return;
    }
  } catch (_) {}
  applyPublishWorkbenchMode("publish");
}

async function saveSeriesCacheItem() {
  setStatus($("#publishStatus"), "正在加入系列缓存…");
  try {
    const draft = await collectPublishDraft({ allowNoPlatform: true });
    const data = await api("/api/publish/cache/save", {
      method: "POST",
      body: JSON.stringify(draft),
    });
    if (!data.success) {
      setStatus($("#publishStatus"), data.error || "保存失败", "error");
      return;
    }
    const it = data.item || {};
    setStatus($("#publishStatus"), `已加入系列 #${it.id} · ${it.storage_rel || ""}`, "ok");
    clearPublishEditorKeepMeta();
    await loadPublishSeriesCards();
    await loadPublishQueue();
  } catch (e) {
    setStatus($("#publishStatus"), String(e), "error");
  }
}

async function loadPublishSeriesCards() {
  const box = $("#publishSeriesList");
  const statsEl = $("#seriesStats");
  if (!box) return;
  try {
    const data = await api("/api/publish/queue");
    const items = (data.items || []).filter((it) =>
      ["draft", "failed", "cancelled"].includes(it.status)
    );
    const draftN = (data.items || []).filter((it) => it.status === "draft").length;
    if (statsEl) {
      statsEl.textContent = `待发缓存 ${draftN} · 可操作 ${items.length}`;
    }
    if (!items.length) {
      box.innerHTML = `<div class="item muted">暂无系列卡片。粘贴图文后点「加入系列缓存」。</div>`;
      return;
    }
    box.innerHTML = items
      .map((it) => {
        const thumbs = (it.media_rels || [])
          .slice(0, 4)
          .map(
            (rel) =>
              `<img src="/api/publish/cache/file?rel=${encodeURIComponent(rel)}" alt="" loading="lazy" />`
          )
          .join("");
        const cover = (it.media_rels || [])[0]
          ? `<div class="series-cover"><img src="/api/publish/cache/file?rel=${encodeURIComponent(it.media_rels[0])}" alt="" /></div>`
          : `<div class="series-cover series-cover-empty">纯文本</div>`;
        const note = it.series_note || it.tags || "";
        const canBatch = it.status === "draft" || it.status === "failed" || it.status === "cancelled";
        return `<article class="series-card" data-qid="${escapeAttr(it.id)}">
          <label class="series-check">
            <input type="checkbox" data-series-check ${canBatch ? "" : "disabled"} ${it.status === "draft" ? "checked" : ""} />
            <span class="status-pill ${escapeAttr(it.status)}">${escapeHtml(statusLabel(it.status))}</span>
          </label>
          ${cover}
          <div class="series-body">
            ${note ? `<p class="series-note">${escapeHtml(note)}</p>` : ""}
            <p class="series-snippet">${escapeHtml(it.snippet || it.content || "")}</p>
            ${thumbs && (it.media_rels || []).length > 1 ? `<div class="cache-thumbs">${thumbs}</div>` : ""}
            <p class="path-mono">${escapeHtml(it.id)} · ${escapeHtml(it.created_at || "").slice(0, 16)}</p>
          </div>
          <div class="series-actions">
            <button type="button" class="btn ghost btn-sm" data-series-act="run">去发布</button>
            <button type="button" class="btn ghost btn-sm" data-series-act="load">载入</button>
            <button type="button" class="btn ghost btn-sm" data-series-act="copy">复制</button>
            <button type="button" class="btn ghost btn-sm" data-series-act="del">删除</button>
          </div>
        </article>`;
      })
      .join("");
  } catch (e) {
    box.innerHTML = `<div class="item" style="color:#8c2828">${escapeHtml(String(e))}</div>`;
  }
}

function selectedSeriesIds() {
  return [...document.querySelectorAll("#publishSeriesList [data-series-check]:checked")]
    .map((el) => el.closest("[data-qid]")?.getAttribute("data-qid"))
    .filter(Boolean);
}

async function batchPublishSeriesSelected() {
  const ids = selectedSeriesIds();
  if (!ids.length) {
    setStatus($("#publishStatus"), "请先勾选要发布的卡片", "error");
    return;
  }
  const platforms = selectedPublishPlatforms();
  if (!platforms.length) {
    setStatus($("#publishStatus"), "请勾选批量发布的目标平台", "error");
    return;
  }
  if (!confirm(`将按顺序发布 ${ids.length} 条到：${platforms.map(publishPlatformLabel).join("、")}？`)) {
    return;
  }
  setStatus($("#publishStatus"), `批量发布中 0/${ids.length}…`);
  try {
    const data = await api("/api/publish/queue/batch-run", {
      method: "POST",
      body: JSON.stringify({
        ids,
        platforms,
        debugger_url: $("#debuggerUrl")?.value.trim() || "127.0.0.1:9222",
      }),
    });
    if (!data.success) {
      setStatus($("#publishStatus"), data.error || "批量发布失败", "error");
      return;
    }
    setStatus(
      $("#publishStatus"),
      `批量完成：成功 ${data.ok || 0}/${data.total || ids.length}`,
      data.ok === data.total ? "ok" : "error"
    );
    await loadPublishSeriesCards();
    await loadPublishQueue();
  } catch (e) {
    setStatus($("#publishStatus"), String(e), "error");
  }
}

async function loadQueueItemIntoPublishEditor(it, { switchMode = true } = {}) {
  if (!it) throw new Error("条目为空");
  if (switchMode) applyPublishWorkbenchMode("publish");
  if ($("#publishTitle")) $("#publishTitle").value = it.title || "";
  if ($("#publishContent")) $("#publishContent").value = it.content || "";
  if ($("#publishTags")) $("#publishTags").value = it.tags || "";
  if ($("#publishSeriesNote") && it.series_note) {
    $("#publishSeriesNote").value = it.series_note;
  }
  if ($("#publishScheduleAt")) {
    const when = toDatetimeLocalValue(it.scheduled_at);
    $("#publishScheduleAt").value = when || ($("#publishScheduleAt").dataset.default || "");
  }
  applyPublishPlatformHint(it.platforms || []);
  publishMediaItems = [];
  publishServerMediaPaths = Array.isArray(it.media_paths) ? [...it.media_paths] : [];
  publishServerMediaRels = Array.isArray(it.media_rels) ? [...it.media_rels] : [];
  if ($("#publishMedia")) {
    $("#publishMedia").value = publishServerMediaPaths.join("\n");
  }
  persistPublishMediaItems();
  renderMediaPreview();
  snapshotPublishPrefs();
  setStatus(
    $("#publishStatus"),
    `已载入草稿 #${it.id || ""} 到「发布/定时」，请确认平台与时间后点「发布」`,
    "ok"
  );
}

function statusLabel(st) {
  const map = {
    pending: "待发布",
    running: "发布中",
    done: "已完成",
    failed: "失败",
    cancelled: "已取消",
    draft: "仅缓存",
  };
  return map[st] || st || "?";
}

function mirrorQueueLocal(items) {
  try {
    localStorage.setItem(
      "pai_publish_queue_cache",
      JSON.stringify({ saved_at: Date.now(), items: items || [] })
    );
  } catch (_) {}
}

async function loadPublishQueue() {
  const box = $("#publishQueueList");
  if (!box) return;
  try {
    const data = await api("/api/publish/queue");
    const items = data.items || [];
    const stats = data.stats || {};
    mirrorQueueLocal(items);
    const statsEl = $("#queueStats");
    if (statsEl) {
      statsEl.textContent = `共 ${stats.all || 0} · 待发 ${stats.pending || 0} · 缓存 ${stats.draft || 0} · 完成 ${stats.done || 0} · 失败 ${stats.failed || 0}`;
    }
    if (data.cache_root && $("#cacheRootLabel")) {
      $("#cacheRootLabel").textContent = data.cache_root;
    }
    if (!items.length) {
      box.innerHTML = `<div class="item muted">队列为空。上传图文后可「存草稿」或「保存并加入定时队列」。</div>`;
      return;
    }
    box.innerHTML = items
      .map((it) => {
        const mediaN = it.media_count || (it.media_paths || []).length;
        const plats = (it.platforms || []).join(", ");
        const err = it.last_error
          ? `<p class="snippet" style="color:#8c2828">${escapeHtml(it.last_error)}</p>`
          : "";
        const canEdit = ["pending", "failed", "cancelled", "draft"].includes(it.status);
        const thumbs = (it.media_rels || [])
          .slice(0, 4)
          .map(
            (rel) =>
              `<img src="/api/publish/cache/file?rel=${encodeURIComponent(rel)}" alt="" loading="lazy" />`
          )
          .join("");
        return `<article class="item" data-qid="${escapeAttr(it.id)}" data-rel="${escapeAttr(it.storage_rel || "")}">
          <div class="queue-row">
            <div class="meta">
              <span class="status-pill ${escapeAttr(it.status)}">${escapeHtml(statusLabel(it.status))}</span>
              <span>${escapeHtml(it.month || "")}</span>
              <span>${escapeHtml(it.id)}</span>
              <span>${escapeHtml(plats || "-")}</span>
              <span>${mediaN ? `图 ${mediaN}` : "纯文本"}</span>
            </div>
            <div class="queue-actions">
              ${
                canEdit
                  ? `<button type="button" class="btn ghost btn-sm" data-q-act="run">去发布</button>
                     <button type="button" class="btn ghost btn-sm" data-q-act="save-time">保存时间</button>
                     <button type="button" class="btn ghost btn-sm" data-q-act="cancel">${it.status === "cancelled" ? "恢复" : "取消"}</button>`
                  : ""
              }
              <button type="button" class="btn ghost btn-sm" data-q-act="copy">复制文案</button>
              <button type="button" class="btn ghost btn-sm" data-q-act="open">打开目录</button>
              <button type="button" class="btn ghost btn-sm" data-q-act="load">载入编辑</button>
              <button type="button" class="btn ghost btn-sm" data-q-act="del">删除</button>
            </div>
          </div>
          <p class="snippet">${escapeHtml(it.snippet || it.content || it.title || "")}</p>
          ${thumbs ? `<div class="cache-thumbs">${thumbs}</div>` : ""}
          <p class="path-mono">${escapeHtml(it.storage_dir || it.storage_rel || "")}</p>
          <label class="field">
            <span>预约时间</span>
            <input type="datetime-local" data-q-time value="${escapeAttr(toDatetimeLocalValue(it.scheduled_at))}" ${canEdit ? "" : "disabled"} />
          </label>
          ${err}
        </article>`;
      })
      .join("");
  } catch (e) {
    box.innerHTML = `<div class="item" style="color:#8c2828">${escapeHtml(String(e))}</div>`;
  }
}

async function savePublishBundle({ enqueue }) {
  setStatus($("#publishStatus"), enqueue ? "正在保存并加入队列…" : "正在存草稿…");
  try {
    const draft = await collectPublishDraft({
      requireSchedule: enqueue,
      allowNoPlatform: !enqueue,
    });
    const data = await api(enqueue ? "/api/publish/queue" : "/api/publish/cache/save", {
      method: "POST",
      body: JSON.stringify(draft),
    });
    if (!data.success) {
      setStatus($("#publishStatus"), data.error || "保存失败", "error");
      return;
    }
    const it = data.item || {};
    setStatus(
      $("#publishStatus"),
      enqueue
        ? `已入队 ${it.id} · ${it.scheduled_at || ""} · ${it.storage_rel || ""}`
        : `已存草稿 ${it.id} · ${it.storage_rel || ""}`,
      "ok"
    );
    $("#publishResult").textContent = JSON.stringify(it, null, 2);
    clearPublishEditorKeepMeta();
    await loadPublishQueue();
    await loadPublishCache();
  } catch (e) {
    setStatus($("#publishStatus"), String(e), "error");
  }
}

async function loadPublishCacheMonths() {
  const sel = $("#cacheMonthSelect");
  if (!sel) return;
  const data = await api("/api/publish/cache/months");
  const months = data.months || [];
  if (data.cache_root && $("#cacheRootLabel")) {
    $("#cacheRootLabel").textContent = data.cache_root;
  }
  const current = sel.value;
  sel.innerHTML = "";
  if (!months.length) {
    const now = new Date();
    const m = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = `${m} (0)`;
    sel.appendChild(opt);
    return;
  }
  months.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.month;
    opt.textContent = `${m.month} (${m.count})`;
    sel.appendChild(opt);
  });
  if (current && [...sel.options].some((o) => o.value === current)) {
    sel.value = current;
  }
}

async function loadPublishCache() {
  const box = $("#publishCacheList");
  if (!box) return;
  try {
    await loadPublishCacheMonths();
    const month = $("#cacheMonthSelect")?.value || "";
    const data = await api(`/api/publish/cache?month=${encodeURIComponent(month)}`);
    const items = data.items || [];
    if (!items.length) {
      box.innerHTML = `<div class="item muted">本月暂无缓存。上传图文后点「存草稿」。</div>`;
      return;
    }
    box.innerHTML = items
      .map((it) => {
        const thumbs = (it.media_files || [])
          .slice(0, 6)
          .map((name) => {
            const rel = `${it.storage_rel}/media/${name}`;
            return `<img src="/api/publish/cache/file?rel=${encodeURIComponent(rel)}" alt="${escapeAttr(name)}" loading="lazy" />`;
          })
          .join("");
        return `<article class="item" data-crel="${escapeAttr(it.storage_rel)}">
          <div class="queue-row">
            <div class="meta">
              <span>${escapeHtml(it.folder || "")}</span>
              <span>${(it.media_count || 0) ? `图 ${it.media_count}` : "纯文本"}</span>
              <span>${escapeHtml(it.status || "")}</span>
            </div>
            <div class="queue-actions">
              <button type="button" class="btn ghost btn-sm" data-c-act="copy">复制文案</button>
              <button type="button" class="btn ghost btn-sm" data-c-act="open">打开目录</button>
              <button type="button" class="btn ghost btn-sm" data-c-act="load">载入编辑</button>
            </div>
          </div>
          <p class="snippet">${escapeHtml(it.snippet || it.title || "")}</p>
          ${thumbs ? `<div class="cache-thumbs">${thumbs}</div>` : ""}
          <p class="path-mono">${escapeHtml(it.storage_dir || "")}</p>
        </article>`;
      })
      .join("");
  } catch (e) {
    box.innerHTML = `<div class="item" style="color:#8c2828">${escapeHtml(String(e))}</div>`;
  }
}

async function copyCacheContent(rel) {
  const data = await api(`/api/publish/cache/content?rel=${encodeURIComponent(rel)}`);
  if (!data.success) throw new Error(data.error || "读取失败");
  const text = data.content_md || "";
  await navigator.clipboard.writeText(text);
  return text;
}

async function openCacheDir(rel) {
  const data = await api("/api/publish/cache/reveal", {
    method: "POST",
    body: JSON.stringify({ rel }),
  });
  if (!data.success) throw new Error(data.error || "打开失败");
  return data.path;
}

async function loadArticles() {
  const data = await api("/api/articles");
  const sel = $("#articleSelect");
  const current = sel.value;
  sel.innerHTML = `<option value="">选择本地文章…</option>`;
  (data.items || []).forEach((it) => {
    const opt = document.createElement("option");
    opt.value = it.path;
    opt.textContent = `${it.title} · ${it.mtime}`;
    sel.appendChild(opt);
  });
  if (current) sel.value = current;
}

function bind() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  $("#btnFilterNews")?.addEventListener("click", () => {
    loadPosts(
      $("#newsKeyword").value.trim(),
      state.newsPlatform || "",
      "news",
      $("#newsView")?.value || "active",
      ""
    );
  });

  $("#newsView")?.addEventListener("change", () => {
    loadPosts(
      $("#newsKeyword").value.trim(),
      state.newsPlatform || "",
      "news",
      $("#newsView")?.value || "active",
      ""
    );
  });

  $("#btnLoadLater")?.addEventListener("click", () => loadLibrary("later"));
  $("#laterKeyword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadLibrary("later");
  });
  $("#btnLoadArchived")?.addEventListener("click", () => loadLibrary("archived"));
  $("#archivedKeyword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadLibrary("archived");
  });
  $("#btnLoadTags")?.addEventListener("click", () => loadLibrary("tags"));
  $("#btnClearTagFilter")?.addEventListener("click", () => {
    if ($("#tagsFilter")) $("#tagsFilter").value = "";
    loadLibrary("tags");
  });
  $("#tagsFilter")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadLibrary("tags");
  });

  $("#btnLoadCorpus")?.addEventListener("click", () => loadCorpus());
  $("#btnXgrowthRun")?.addEventListener("click", () => runXgrowthViral());
  $("#btnSynthRandom")?.addEventListener("click", () => runCorpusSynthesizeRandom());
  $("#btnSynthPicked")?.addEventListener("click", () => runCorpusSynthesizePicked());
  $("#btnCorpusManual")?.addEventListener("click", () => createManualCorpus());
  $("#btnCorpusSelectAll")?.addEventListener("click", () => {
    state.corpusSelected = new Set((state.corpusItems || []).slice(0, 3).map((x) => Number(x.id)));
    renderCorpusItems(state.corpusItems || []);
  });
  $("#btnCorpusClearSel")?.addEventListener("click", () => {
    state.corpusSelected = new Set();
    renderCorpusItems(state.corpusItems || []);
  });
  $("#btnLoadGenerations")?.addEventListener("click", () => loadGenerations());
  $("#btnLoadFeatured")?.addEventListener("click", () => loadGenerations());
  $("#labCaptureForm")?.addEventListener("submit", runLabCapture);
  $("#btnLabCopyMd")?.addEventListener("click", () => labCopyMarkdown());
  $("#btnLabRegen")?.addEventListener("click", () => runCorpusRegen({ explicit: true }));
  $("#btnLabSaveFeatured")?.addEventListener("click", () => labSaveFeatured());
  $("#btnLabGenImages")?.addEventListener("click", () => runLabBatchImages());
  $("#labImagePickAll")?.addEventListener("change", (e) => {
    const variants = state.labVariants || [];
    if (e.target.checked) state.labImagePick = new Set(variants.map((_, i) => i));
    else state.labImagePick = new Set();
    renderLabVariants(variants, (state.labVariants || []).indexOf(state.labActiveVariant));
  });
  document.querySelectorAll(".lab-mode-tab[data-lab-mode]").forEach((btn) => {
    btn.addEventListener("click", () => switchLabMode(btn.getAttribute("data-lab-mode")));
  });
  $("#btnMemosSaveConfig")?.addEventListener("click", () => saveMemosConfig());
  $("#btnMemosFetch")?.addEventListener("click", () => fetchMemosList());
  $("#btnMemosGenImages")?.addEventListener("click", () => runMemosBatchImages());
  $("#btnMemosSync")?.addEventListener("click", () => syncMemosImagesBack());
  $("#btnMemosRefreshTags")?.addEventListener("click", () => loadMemosTags());
  $("#memosRange")?.addEventListener("change", () => {
    syncMemosCustomRangeVis();
    if (($("#memosRange")?.value || "") !== "custom") fetchMemosList();
  });
  $("#memosSince")?.addEventListener("change", () => fetchMemosList());
  $("#memosUntil")?.addEventListener("change", () => fetchMemosList());
  $("#memosTag")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      fetchMemosList();
    }
  });
  $("#memosPickAll")?.addEventListener("change", (e) => {
    const items = state.memosItems || [];
    if (e.target.checked) state.memosPick = new Set(items.map((_, i) => i));
    else state.memosPick = new Set();
    renderMemosList(items);
  });
  $("#memosKeyword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      fetchMemosList();
    }
  });
  document.querySelectorAll("[data-memos-view]").forEach((btn) => {
    btn.addEventListener("click", () => setMemosEditView(btn.getAttribute("data-memos-view")));
  });
  $("#memosEditSource")?.addEventListener("input", () => {
    if (($("#memosEditPanes")?.getAttribute("data-view") || "") !== "edit") {
      refreshMemosEditPreview();
    }
  });
  $("#memosEditForm")?.addEventListener("submit", (e) => {
    if (e.submitter?.value === "save") saveMemosEditor(e);
  });
  syncMemosCustomRangeVis();
  applyLabMode(state.labMode || "lab");
  document.querySelectorAll("#labTweaks [data-tweak]").forEach((btn) => {
    btn.addEventListener("click", () => runLabTweak(btn.getAttribute("data-tweak")));
  });
  $("#btnLabPublishPreview")?.addEventListener("click", () => labPublishViaCdp());
  $("#btnLabProfileConfig")?.addEventListener("click", () => openLabProfileConfig());
  $("#labProfileConfigForm")?.addEventListener("submit", (e) => {
    if (e.submitter?.value === "save") saveLabProfileConfig(e);
  });
  $("#btnLabConfigReset")?.addEventListener("click", () => resetLabProfileConfig());
  bindLabConfigTabs();
  $("#labPublishPreviewForm")?.addEventListener("submit", (e) => {
    if (e.submitter?.value !== "confirm") return;
    e.preventDefault();
    $("#labPublishPreviewDialog")?.close();
    labSendToPublish();
  });
  $("#corpusEditForm")?.addEventListener("submit", (e) => {
    const submitter = e.submitter;
    if (submitter && submitter.value === "cancel") return;
    if (submitter && submitter.value === "save") {
      e.preventDefault();
      saveCorpusEdit(e);
    }
  });
  $("#corpusKeyword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadCorpus();
  });
  $("#corpusKeyword")?.addEventListener("change", () => scheduleLabSessionSave());
  $("#corpusQuality")?.addEventListener("change", () => loadCorpus());
  $("#corpusStatus")?.addEventListener("change", () => {
    scheduleLabSessionSave();
    loadCorpus();
  });
  $("#btnCorpusRegen")?.addEventListener("click", () => runCorpusRegen({ explicit: true }));
  $("#regenTopic")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      setStatus($("#corpusRegenStatus"), "请点击「生成 3 个变体」按钮", "error");
    }
  });
  $("#regenTopic")?.addEventListener("input", () => {
    updateLabSteps();
    scheduleLabSessionSave();
  });
  $("#regenPrompt")?.addEventListener("input", () => scheduleLabSessionSave());
  $("#labCaptureInput")?.addEventListener("input", () => scheduleLabSessionSave());
  ["xgrowthLimit", "xgrowthMinVel", "xgrowthPotential", "xgrowthOpenTweet"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", () => scheduleLabSessionSave());
  });

  $("#btnExpand")?.addEventListener("click", async () => {
    const keyword = $("#newsKeyword").value.trim();
    if (!keyword) {
      setStatus($("#crawlStatus"), "请先填写主题关键词", "error");
      return;
    }
    if ($("#crawlExpand")) $("#crawlExpand").checked = true;
    setStatus($("#crawlStatus"), "正在用本地 AI 衍生搜索词…");
    try {
      const data = await api("/api/keywords/expand", {
        method: "POST",
        body: JSON.stringify({ keyword }),
      });
      const box = $("#expandPreview");
      const body = $("#expandPreviewBody");
      box.hidden = false;
      body.textContent = JSON.stringify(data, null, 2);
      setStatus(
        $("#crawlStatus"),
        data.success ? `衍生完成（${data.provider || "ai"}），可点「开始抓取」` : data.error || "衍生失败",
        data.success ? "ok" : "error"
      );
    } catch (e) {
      setStatus($("#crawlStatus"), String(e), "error");
    }
  });

  $("#crawlScheduled")?.addEventListener("change", syncTaskUi);
  $("#crawlScheduleMode")?.addEventListener("change", syncScheduleModeUi);
  $("#btnRefreshTasks")?.addEventListener("click", loadTasks);
  document.querySelectorAll("#taskStatusBar [data-task-status]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.taskStatus = btn.getAttribute("data-task-status") || "all";
      loadTasks();
    });
  });
  document.querySelectorAll("#schedulePresets [data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = btn.getAttribute("data-preset") || "";
      if (preset === "daily") {
        if ($("#crawlScheduleMode")) $("#crawlScheduleMode").value = "daily";
        if ($("#crawlDailyHour")) $("#crawlDailyHour").value = "9";
        if ($("#crawlJitter")) $("#crawlJitter").value = "15";
      } else {
        if ($("#crawlScheduleMode")) $("#crawlScheduleMode").value = "interval";
        if ($("#crawlInterval")) $("#crawlInterval").value = preset;
        if ($("#crawlJitter")) $("#crawlJitter").value = preset === "30" ? "10" : "20";
      }
      if ($("#crawlScheduled")) $("#crawlScheduled").checked = true;
      syncTaskUi();
    });
  });

  $("#btnCrawl")?.addEventListener("click", async () => {
    const keyword = $("#newsKeyword").value.trim();
    const scheduled = !!$("#crawlScheduled")?.checked;
    const expand = !!$("#crawlExpand")?.checked;
    const platforms = selectedPlatforms();
    $("#btnCrawl").disabled = true;
    setStatus($("#crawlStatus"), scheduled ? "已创建周期任务…" : "已提交抓取任务…");
    try {
      const payload = {
        keyword,
        expand,
        platforms,
        scheduled,
        schedule_mode: $("#crawlScheduleMode")?.value || "interval",
        interval_min: Number($("#crawlInterval")?.value || 30),
        jitter_min: Number($("#crawlJitter")?.value || 10),
        daily_hour: Number($("#crawlDailyHour")?.value ?? 9),
        run_now: true,
      };
      const data = await api("/api/crawl", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!data.success) {
        setStatus($("#crawlStatus"), data.error || "启动失败", "error");
        return;
      }
      await loadTasks();
      if (data.job_id) {
        await pollJob(data.job_id);
      } else if (data.task?.last_job_id) {
        await pollJob(data.task.last_job_id);
      } else {
        setStatus($("#crawlStatus"), "周期任务已启动", "ok");
      }
    } catch (e) {
      setStatus($("#crawlStatus"), String(e), "error");
    } finally {
      $("#btnCrawl").disabled = false;
    }
  });

  $("#btnLoadHistory")?.addEventListener("click", () => {
    const pid = state.historyPlatform || $("#historyPlatform").value.trim();
    state.historyPlatform = pid;
    loadPosts(
      $("#historyKeyword").value.trim(),
      pid,
      "history",
      $("#historyView")?.value || "all",
      $("#historyTag")?.value.trim() || ""
    );
  });

  $("#historyView")?.addEventListener("change", () => {
    loadPosts(
      $("#historyKeyword").value.trim(),
      state.historyPlatform || $("#historyPlatform").value.trim(),
      "history",
      $("#historyView")?.value || "all",
      $("#historyTag")?.value.trim() || ""
    );
  });

  $("#btnCreate").addEventListener("click", async () => {
    const topic = $("#createTopic").value.trim();
    if (!topic) {
      setStatus($("#createStatus"), "请填写主题", "error");
      return;
    }
    $("#btnCreate").disabled = true;
    setStatus($("#createStatus"), "正在生成，可能需要数十秒…");
    try {
      const data = await api("/api/create", {
        method: "POST",
        body: JSON.stringify({
          topic,
          prompt: $("#createPrompt").value.trim(),
          style: $("#createStyle").value.trim() || "专业",
          words: Number($("#createWords").value || 2000),
        }),
      });
      if (!data.success) {
        setStatus($("#createStatus"), data.error || "生成失败", "error");
        return;
      }
      state.lastCreate = {
        title: topic,
        content: data.content || "",
        path: data.saved_path || "",
      };
      $("#createTitlePreview").textContent = topic;
      $("#createContentPreview").textContent = data.content || "";
      setStatus(
        $("#createStatus"),
        data.saved_path ? `已保存：${data.saved_path}` : "生成成功",
        "ok"
      );
      await loadArticles();
    } catch (e) {
      setStatus($("#createStatus"), String(e), "error");
    } finally {
      $("#btnCreate").disabled = false;
    }
  });

  $("#btnUseForPublish").addEventListener("click", () => {
    if (!state.lastCreate.content) {
      setStatus($("#createStatus"), "请先生成文章", "error");
      return;
    }
    $("#publishContent").value = state.lastCreate.content;
    switchTab("publish");
  });

  $("#btnLoadArticles")?.addEventListener("click", loadArticles);

  $("#articleSelect")?.addEventListener("change", async () => {
    const path = $("#articleSelect").value;
    if (!path) return;
    const data = await api(`/api/article?path=${encodeURIComponent(path)}`);
    if (!data.success) {
      setStatus($("#publishStatus"), data.error || "读取失败", "error");
      return;
    }
    $("#publishTitle").value = data.title || "";
    $("#publishContent").value = data.content || "";
    setStatus($("#publishStatus"), `已载入 ${path}`, "ok");
  });

  $("#btnPublish").addEventListener("click", async () => {
    $("#btnPublish").disabled = true;
    clearPublishProgress();
    const platformNames = selectedPublishPlatforms().map(publishPlatformLabel).join("、");
    setStatus(
      $("#publishStatus"),
      isPublishScheduleDefault()
        ? platformNames
          ? `正在发布 · ${platformNames}`
          : "正在发布…"
        : platformNames
          ? `正在加入定时队列 · ${platformNames}`
          : "正在加入定时队列…"
    );
    try {
      const result = await submitPublish();
      if (result.mode === "now") {
        const data = result.data;
        const okN = data.success_count || 0;
        const total = data.total || 0;
        const detail = formatPublishStepSummary(data.results);
        renderPublishProgress({
          phase: "done",
          index: total,
          total,
          results: data.results,
        });
        setStatus(
          $("#publishStatus"),
          data.success
            ? `发布完成 ${okN}/${total}${detail ? ` · ${detail}` : ""}`
            : detail || data.error || "发布失败",
          data.success ? "ok" : "error"
        );
        if (data.success) clearPublishEditorKeepMeta();
      } else {
        const it = result.data.item || {};
        const when = it.scheduled_at || $("#publishScheduleAt")?.value || "";
        setStatus(
          $("#publishStatus"),
          `已加入定时队列 ${it.id || ""} · ${when}`,
          "ok"
        );
        clearPublishEditorKeepMeta();
        await loadPublishQueue();
        await loadPublishCache();
      }
    } catch (e) {
      setStatus($("#publishStatus"), String(e), "error");
    } finally {
      $("#btnPublish").disabled = false;
    }
  });

  $("#btnQueueAdd")?.addEventListener("click", () => savePublishBundle({ enqueue: true }));
  $("#btnCacheSave")?.addEventListener("click", () => savePublishBundle({ enqueue: false }));
  $("#btnSeriesCacheAdd")?.addEventListener("click", () => saveSeriesCacheItem());
  $("#btnSeriesRefresh")?.addEventListener("click", () => loadPublishSeriesCards());
  $("#btnSeriesSelectAll")?.addEventListener("click", () => {
    document.querySelectorAll("#publishSeriesList [data-series-check]:not(:disabled)").forEach((el) => {
      el.checked = true;
    });
  });
  $("#btnSeriesBatchPublish")?.addEventListener("click", () => batchPublishSeriesSelected());
  $("#btnSeriesClearDrafts")?.addEventListener("click", async () => {
    try {
      const data = await api("/api/publish/queue/clear-done", {
        method: "POST",
        body: "{}",
      });
      setStatus($("#publishStatus"), `已清理 ${data.cleared || 0} 条`, "ok");
      await loadPublishSeriesCards();
      await loadPublishQueue();
    } catch (e) {
      setStatus($("#publishStatus"), String(e), "error");
    }
  });
  document.querySelectorAll(".publish-mode-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      applyPublishWorkbenchMode(btn.getAttribute("data-publish-mode") || "publish");
    });
  });
  $("#publishSeriesList")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-series-act]");
    if (!btn) return;
    const card = btn.closest("[data-qid]");
    if (!card) return;
    const id = card.getAttribute("data-qid") || "";
    const act = btn.getAttribute("data-series-act");
    try {
      if (act === "run" || act === "load") {
        const data = await api(`/api/publish/queue/${encodeURIComponent(id)}`);
        let it = data.item;
        if (!it) {
          const q = await api("/api/publish/queue");
          it = (q.items || []).find((x) => String(x.id) === String(id));
        }
        if (!it) throw new Error("条目不存在");
        await loadQueueItemIntoPublishEditor(it);
        return;
      }
      if (act === "del") {
        if (!confirm(`删除缓存 ${id}？`)) return;
        await api(`/api/publish/queue/${encodeURIComponent(id)}?remove_files=1`, {
          method: "DELETE",
        });
        await loadPublishSeriesCards();
        return;
      }
      if (act === "copy") {
        const q = await api("/api/publish/queue");
        const it = (q.items || []).find((x) => String(x.id) === String(id));
        if (!it) throw new Error("条目不存在");
        await navigator.clipboard.writeText(it.content || it.snippet || "");
        setStatus($("#publishStatus"), "文案已复制", "ok");
      }
    } catch (e) {
      setStatus($("#publishStatus"), String(e), "error");
    }
  });
  $("#btnQueueRefresh")?.addEventListener("click", () => {
    loadPublishQueue();
    loadPublishCache();
    if (publishWorkbenchMode === "cache") loadPublishSeriesCards();
  });
  $("#btnQueueClearDone")?.addEventListener("click", async () => {
    try {
      const data = await api("/api/publish/queue/clear-done", {
        method: "POST",
        body: "{}",
      });
      setStatus($("#publishStatus"), `已清理 ${data.cleared || 0} 条`, "ok");
      await loadPublishQueue();
    } catch (e) {
      setStatus($("#publishStatus"), String(e), "error");
    }
  });
  $("#publishMediaFiles")?.addEventListener("change", onPublishMediaFilesChange);
  $("#publishMediaPreview")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-media-del]");
    const sbtn = e.target.closest("[data-server-media-del]");
    if (btn) {
      removePublishMediaFile(Number(btn.getAttribute("data-media-del")));
      return;
    }
    if (sbtn) {
      const idx = Number(sbtn.getAttribute("data-server-media-del"));
      if (Number.isFinite(idx) && idx >= 0) {
        publishServerMediaPaths = publishServerMediaPaths.filter((_, i) => i !== idx);
        publishServerMediaRels = publishServerMediaRels.filter((_, i) => i !== idx);
        if ($("#publishMedia")) $("#publishMedia").value = publishServerMediaPaths.join("\n");
        renderMediaPreview();
        snapshotPublishPrefs();
      }
    }
  });
  bindPublishMediaPaste();
  bindPublishPrefsAutosave();
  $("#btnCacheRefresh")?.addEventListener("click", () => loadPublishCache());
  $("#cacheMonthSelect")?.addEventListener("change", () => loadPublishCache());
  $("#btnCacheOpenRoot")?.addEventListener("click", async () => {
    try {
      const months = await api("/api/publish/cache/months");
      const root = months.cache_root || "";
      if (!root) {
        setStatus($("#publishStatus"), "缓存目录尚未初始化", "error");
        return;
      }
      await openCacheDir(root);
      setStatus($("#publishStatus"), `已打开 ${root}`, "ok");
    } catch (e) {
      setStatus($("#publishStatus"), String(e), "error");
    }
  });

  $("#publishCacheList")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-c-act]");
    if (!btn) return;
    const card = btn.closest("[data-crel]");
    if (!card) return;
    const rel = card.getAttribute("data-crel") || "";
    const act = btn.getAttribute("data-c-act");
    try {
      if (act === "copy") {
        await copyCacheContent(rel);
        setStatus($("#publishStatus"), "文案已复制到剪贴板", "ok");
        return;
      }
      if (act === "open") {
        const path = await openCacheDir(rel);
        setStatus($("#publishStatus"), `已打开 ${path}`, "ok");
        return;
      }
      if (act === "load") {
        const data = await api(`/api/publish/cache/content?rel=${encodeURIComponent(rel)}`);
        const md = data.content_md || "";
        const lines = md.split("\n");
        let title = "";
        let bodyStart = 0;
        if (lines[0]?.startsWith("# ")) {
          title = lines[0].slice(2).trim();
          bodyStart = 1;
          while (lines[bodyStart] === "") bodyStart += 1;
        }
        const sep = lines.findIndex((l) => l.trim() === "---");
        const body = lines
          .slice(bodyStart, sep >= 0 ? sep : undefined)
          .join("\n")
          .trim();
        $("#publishTitle").value = title;
        $("#publishContent").value = body;
        setStatus($("#publishStatus"), `已载入 ${rel}`, "ok");
      }
    } catch (e) {
      setStatus($("#publishStatus"), String(e), "error");
    }
  });

  $("#publishQueueList")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-q-act]");
    if (!btn) return;
    const card = btn.closest("[data-qid]");
    if (!card) return;
    const id = card.getAttribute("data-qid");
    const rel = card.getAttribute("data-rel") || "";
    const act = btn.getAttribute("data-q-act");
    try {
      if (act === "del") {
        await api(`/api/publish/queue/${encodeURIComponent(id)}`, { method: "DELETE" });
        setStatus($("#publishStatus"), `已删除队列项 ${id}（磁盘文件保留）`, "ok");
        await loadPublishQueue();
        await loadPublishCache();
        return;
      }
      if (act === "copy") {
        if (!rel) throw new Error("无存储路径");
        await copyCacheContent(rel);
        setStatus($("#publishStatus"), "文案已复制到剪贴板", "ok");
        return;
      }
      if (act === "open") {
        if (!rel) throw new Error("无存储路径");
        const path = await openCacheDir(rel);
        setStatus($("#publishStatus"), `已打开 ${path}`, "ok");
        return;
      }
      if (act === "load" || act === "run") {
        const data = await api(`/api/publish/queue/${encodeURIComponent(id)}`);
        const it = data.item || {};
        await loadQueueItemIntoPublishEditor(it);
        return;
      }
      if (act === "save-time") {
        const input = card.querySelector("[data-q-time]");
        const when = input?.value || "";
        if (!when) {
          setStatus($("#publishStatus"), "请填写预约时间", "error");
          return;
        }
        const data = await api(`/api/publish/queue/${encodeURIComponent(id)}/update`, {
          method: "POST",
          body: JSON.stringify({ scheduled_at: when, status: "pending", requeue: true, enabled: true }),
        });
        if (!data.success) {
          setStatus($("#publishStatus"), data.error || "保存失败", "error");
          return;
        }
        setStatus($("#publishStatus"), `已更新时间 ${when}`, "ok");
        await loadPublishQueue();
        return;
      }
      if (act === "cancel") {
        const pill = card.querySelector(".status-pill");
        const cur = pill?.classList.contains("cancelled");
        const data = await api(`/api/publish/queue/${encodeURIComponent(id)}/update`, {
          method: "POST",
          body: JSON.stringify(
            cur
              ? { status: "pending", requeue: true, enabled: true }
              : { status: "cancelled", enabled: false }
          ),
        });
        if (!data.success) {
          setStatus($("#publishStatus"), data.error || "操作失败", "error");
          return;
        }
        await loadPublishQueue();
        return;
      }
    } catch (e) {
      setStatus($("#publishStatus"), String(e), "error");
    }
  });

  $("#btnSigSaveCfg")?.addEventListener("click", () => saveSignalsConfig());
  $("#btnSigRun")?.addEventListener("click", () => runSignalsCrawl());
  $("#btnSigPause")?.addEventListener("click", () => signalsControl("pause"));
  $("#btnSigResume")?.addEventListener("click", () => signalsControl("resume"));
  $("#btnSigStop")?.addEventListener("click", () => signalsControl("stop"));
  setSigControlButtons({ running: false, paused: false });
  $("#btnSigRefresh")?.addEventListener("click", () => loadSignalCards());
  $("#sigCardsPager")?.addEventListener("click", (e) => {
    const prev = e.target.closest("#btnSigCardsPrev");
    const next = e.target.closest("#btnSigCardsNext");
    if (prev && !prev.disabled) {
      goSigCardsPage(_sigCardsPage - 1);
    } else if (next && !next.disabled) {
      goSigCardsPage(_sigCardsPage + 1);
    }
  });
  $("#sigCardsPager")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const input = e.target.closest("#sigCardsPageInput");
    if (!input) return;
    e.preventDefault();
    goSigCardsPage(input.value);
  });
  $("#btnSigBacktest")?.addEventListener("click", () => startSigCardsBacktest());
  $("#btnSigBacktestResult")?.addEventListener("click", () => openSigBacktestResultDialog());
  loadSigBacktestLast();
  $("#sigFilterTrade")?.addEventListener("change", () => loadSignalCards());
  $("#sigFilterName")?.addEventListener("change", () => {
    persistSigCardsFilter();
    loadSignalCards();
  });
  $("#sigFilterRange")?.addEventListener("change", () => {
    syncSigFilterCustomVisibility();
    persistSigCardsFilter();
    if ($("#sigFilterRange")?.value !== "custom") loadSignalCards();
  });
  $("#sigFilterFrom")?.addEventListener("change", () => {
    persistSigCardsFilter();
    loadSignalCards();
  });
  $("#sigFilterTo")?.addEventListener("change", () => {
    persistSigCardsFilter();
    loadSignalCards();
  });
  $("#btnSigFilterApply")?.addEventListener("click", () => {
    persistSigCardsFilter();
    loadSignalCards();
  });
  $("#btnSigFilterReset")?.addEventListener("click", () => resetSigCardsFilter());
  $("#sigShowAllWindows")?.addEventListener("change", () => renderSigWindows(_sigWindowsCache));
  const sigHideKol = $("#sigHideKol");
  if (sigHideKol) {
    sigHideKol.checked = localStorage.getItem("sigHideKol") === "1";
    applySigKolVisibility();
    sigHideKol.addEventListener("change", () => {
      localStorage.setItem("sigHideKol", sigHideKol.checked ? "1" : "0");
      applySigKolVisibility();
    });
  }
  $("#btnSigTestPreview")?.addEventListener("click", () => sendSignalsTest({ dryRun: true }));
  $("#btnSigTestSend")?.addEventListener("click", () => sendSignalsTest({ dryRun: false }));
  $("#sigTestHandle")?.addEventListener("change", () => fillSigTestDefaultsFromHandle());
  $("#sigTestBody")?.addEventListener("input", () => {
    if ($("#sigTestBody")) $("#sigTestBody").dataset.touched = "1";
  });
  const sigHideTest = $("#sigHideTest");
  if (sigHideTest) {
    sigHideTest.checked = localStorage.getItem("sigHideTest") === "1";
    applySigTestVisibility();
    sigHideTest.addEventListener("change", () => applySigTestVisibility(true));
  }
  $("#btnSigHideTest")?.addEventListener("click", () => {
    const cb = $("#sigHideTest");
    if (!cb) return;
    cb.checked = true;
    applySigTestVisibility(true);
  });
  $("#btnSigCycle")?.addEventListener("click", () => toggleSigCycle());
  document.querySelectorAll(".sig-mode-tab[data-sig-mode]").forEach((btn) => {
    btn.addEventListener("click", () => switchSigMode(btn.getAttribute("data-sig-mode")));
  });
  restoreSigModeFromStorage();
  restoreSigCardsFilter();
  $("#btnSigUserRun")?.addEventListener("click", () => runUserSignalsCrawl());
  bindSigUserFormPersistence();
  $("#btnSigUserClearCache")?.addEventListener("click", () => clearSigUserCache());
  $("#btnSigUserPause")?.addEventListener("click", () => signalsControl("pause"));
  $("#btnSigUserResume")?.addEventListener("click", () => signalsControl("resume"));
  $("#btnSigUserStop")?.addEventListener("click", () => signalsControl("stop"));
  $("#btnSigUserSelectAll")?.addEventListener("click", () => setSigUserBloggerSelection(true));
  $("#btnSigUserSelectNone")?.addEventListener("click", () => setSigUserBloggerSelection(false));
  $("#sigUserBloggerList")?.addEventListener("change", () => persistSigUserForm());
  $("#btnSigValueRun")?.addEventListener("click", () => runValueReturnCrawl());
  $("#btnSigValuePause")?.addEventListener("click", () => signalsControl("pause"));
  $("#btnSigValueResume")?.addEventListener("click", () => signalsControl("resume"));
  $("#btnSigValueStop")?.addEventListener("click", () => signalsControl("stop"));
  $("#sigValueRecommendedOnly")?.addEventListener("change", () => loadSignalCards());
  $("#btnSigCdpConfig")?.addEventListener("click", () => openSigCdpDialog());
  $("#btnRtRefresh")?.addEventListener("click", () => loadRealtimePanel());
  $("#rtStatus")?.addEventListener("change", () => loadRealtimePanel());
  $("#rtModule")?.addEventListener("change", () => loadRealtimePanel());
  $("#btnRtRunOi")?.addEventListener("click", () => runRealtimeModule("oi_funding"));
  $("#btnRtRunOnchain")?.addEventListener("click", () => runRealtimeModule("onchain"));
  $("#btnRtDemoTv")?.addEventListener("click", () => ingestRealtimeTvDemo());
  $("#rtEventList")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-rt-action]");
    if (!btn) return;
    const id = Number(btn.getAttribute("data-rt-id") || 0);
    const action = btn.getAttribute("data-rt-action") || "";
    if (!id || !action) return;
    setRealtimeStatus(id, action);
  });
  $("#sigCdpConfigForm")?.addEventListener("submit", (e) => {
    if (e.submitter?.value === "save") saveSigCdpConfig(e);
  });
  $("#sigCardEditForm")?.addEventListener("submit", (e) => {
    if (e.submitter?.value === "save") saveSigCardEdit(e);
  });
  $("#sigCards")?.addEventListener("click", (e) => {
    const arch = e.target.closest("[data-sig-value-archive]");
    if (arch) {
      e.preventDefault();
      archiveSigValueCard(arch.getAttribute("data-sig-value-archive") || "");
      return;
    }
    const btn = e.target.closest("[data-sig-edit]");
    if (!btn) return;
    e.preventDefault();
    openSigCardEdit(btn.getAttribute("data-sig-edit") || "");
  });

  $("#btnTcIngest")?.addEventListener("click", () => runTweetCardIngest());
  $("#btnTcRefresh")?.addEventListener("click", () => loadTweetCards());
  const tcPrivacy = $("#tcHideSensitive");
  if (tcPrivacy) {
    tcPrivacy.checked = localStorage.getItem("tcHideSensitive") === "1";
    tcPrivacy.addEventListener("change", () => {
      localStorage.setItem("tcHideSensitive", tcPrivacy.checked ? "1" : "0");
      loadTweetCards();
    });
  }
  $("#tcKeyword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadTweetCards();
  });
}

const SIG_USER_LS = "sigUserFormPrefs";
let _sigUserSaveTimer = null;

const SIG_BACKFILL_RANGES = {
  last_7d: "近7天",
  last_14d: "近14天",
  last_2w: "两周内",
  last_30d: "近30天",
  last_90d: "近90天",
  this_week: "本周",
  this_month: "本月",
  this_quarter: "本季度",
};

function normalizeSigBackfillRange(raw, fallback = "last_7d") {
  const key = String(raw || "").trim().toLowerCase();
  if (SIG_BACKFILL_RANGES[key]) return key;
  const w = Number(raw);
  if (Number.isFinite(w) && w > 0) {
    if (w <= 1) return "last_7d";
    if (w <= 2) return "last_14d";
    if (w <= 4) return "last_30d";
    return "last_90d";
  }
  return SIG_BACKFILL_RANGES[fallback] ? fallback : "last_7d";
}

function resolveSigUserBackfillRange(local, cfg) {
  const has = (v) => v !== undefined && v !== null && v !== "";
  if (has(local?.user_backfill_range)) return normalizeSigBackfillRange(local.user_backfill_range);
  if (has(cfg?.user_backfill_range)) return normalizeSigBackfillRange(cfg.user_backfill_range);
  if (has(local?.user_weeks)) return normalizeSigBackfillRange(local.user_weeks);
  if (has(cfg?.user_weeks)) return normalizeSigBackfillRange(cfg.user_weeks);
  return "last_7d";
}

function getSigUserBackfillRange(cfg) {
  const dom = $("#sigUserBackfillRange")?.value;
  if (dom && SIG_BACKFILL_RANGES[normalizeSigBackfillRange(dom)]) {
    return normalizeSigBackfillRange(dom);
  }
  return resolveSigUserBackfillRange(readSigUserFormLocal(), cfg || {});
}

function readSigUserFormLocal() {
  try {
    const raw = localStorage.getItem(SIG_USER_LS);
    return raw ? JSON.parse(raw) : {};
  } catch (_) {
    return {};
  }
}

function writeSigUserFormLocal(patch) {
  const prev = readSigUserFormLocal();
  localStorage.setItem(
    SIG_USER_LS,
    JSON.stringify({ ...prev, ...patch, savedAt: Date.now() })
  );
}

function collectSigUserForm() {
  const profile = $("#sigUserProfileUrl")?.value.trim() || "";
  const handle = parseSigUserHandle(profile);
  return {
    user_profile_url: profile,
    user_handle: handle,
    user_blogger_ids: getSelectedSigUserBloggerIds(),
    user_backfill_range: normalizeSigBackfillRange($("#sigUserBackfillRange")?.value || "this_month"),
    user_max_tweets: Math.max(10, Math.min(300, Number($("#sigUserMaxTweets")?.value || 50) || 50)),
  };
}

function getSelectedSigUserBloggerIds() {
  return [...document.querySelectorAll("#sigUserBloggerList input[data-blogger-id]:checked")]
    .map((el) => String(el.getAttribute("data-blogger-id") || "").toLowerCase())
    .filter(Boolean);
}

function setSigUserBloggerSelection(on) {
  document.querySelectorAll("#sigUserBloggerList input[data-blogger-id]").forEach((el) => {
    el.checked = !!on;
  });
  persistSigUserForm();
}

function renderSigUserBloggerList(items, selectedIds) {
  const box = $("#sigUserBloggerList");
  if (!box) return;
  const selected = new Set(
    (Array.isArray(selectedIds) ? selectedIds : [])
      .map((x) => String(x || "").toLowerCase())
      .filter(Boolean)
  );
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) {
    box.innerHTML = "";
    return;
  }
  // 首次无缓存时默认全选，方便批量本月回溯
  const localIds = readSigUserFormLocal().user_blogger_ids;
  const useDefaultAll = selected.size === 0 && !Array.isArray(localIds);
  box.innerHTML = rows
    .map((b) => {
      const id = String(b.id || b.handle || "").toLowerCase();
      const name = String(b.name || id);
      const checked = useDefaultAll || selected.has(id) ? " checked" : "";
      const aliases = (b.aliases || []).length
        ? ` · ${(b.aliases || []).slice(0, 2).join("/")}`
        : "";
      return `<label class="sig-blogger-item" title="${escapeAttr(b.profile_url || `https://x.com/${id}`)}">
        <input type="checkbox" data-blogger-id="${escapeAttr(id)}"${checked} />
        <span>${escapeHtml(name)}</span>
        <span class="sig-blogger-id">@${escapeHtml(id)}${escapeHtml(aliases)}</span>
      </label>`;
    })
    .join("");
}

function applySigUserForm(cfg, bloggers) {
  const local = readSigUserFormLocal();
  const hasLocal = (key) =>
    Object.prototype.hasOwnProperty.call(local, key) && local[key] !== undefined && local[key] !== null;
  const pick = (key, fallback) => {
    if (hasLocal(key) && local[key] !== "") return local[key];
    // 允许本地显式存空字符串（如额外博主已清空）
    if (hasLocal(key) && local[key] === "" && key === "user_profile_url") return "";
    const cv = cfg?.[key];
    if (cv !== undefined && cv !== null && cv !== "") return cv;
    return fallback;
  };
  const bloggerItems = Array.isArray(bloggers)
    ? bloggers
    : Array.isArray(bloggers?.items)
      ? bloggers.items
      : _sigBloggersCache;
  _sigBloggersCache = bloggerItems || [];
  const selected = Array.isArray(local.user_blogger_ids)
    ? local.user_blogger_ids
    : Array.isArray(cfg?.user_blogger_ids)
      ? cfg.user_blogger_ids
      : [];
  renderSigUserBloggerList(_sigBloggersCache, selected);
  if ($("#sigUserProfileUrl")) {
    // 额外博主：本地有记录（含空）一律以本地为准，不再用服务端旧值盖回去
    if (hasLocal("user_profile_url")) {
      $("#sigUserProfileUrl").value = String(local.user_profile_url || "");
    } else {
      $("#sigUserProfileUrl").value = "";
    }
  }
  if ($("#sigUserBackfillRange")) {
    $("#sigUserBackfillRange").value = resolveSigUserBackfillRange(local, cfg);
  }
  if ($("#sigUserMaxTweets")) {
    $("#sigUserMaxTweets").value = String(pick("user_max_tweets", 50));
  }
  writeSigUserFormLocal(collectSigUserForm());
}

let _sigBloggersCache = [];

async function persistSigUserForm({ immediate = false } = {}) {
  const body = collectSigUserForm();
  writeSigUserFormLocal(body);
  if (_sigUserSaveTimer) {
    clearTimeout(_sigUserSaveTimer);
    _sigUserSaveTimer = null;
  }
  const save = async () => {
    try {
      const data = await api("/api/signals/config", {
        method: "POST",
        body: JSON.stringify({
          user_profile_url: body.user_profile_url,
          user_backfill_range: body.user_backfill_range,
          user_max_tweets: body.user_max_tweets,
        }),
      });
      if (data?.config) writeSigUserFormLocal({ ...body, ...data.config });
    } catch (_) {
      /* localStorage 已缓存，下次加载仍可用 */
    }
  };
  if (immediate) await save();
  else _sigUserSaveTimer = setTimeout(save, 350);
}

function bindSigUserFormPersistence() {
  const fields = [
    "#sigUserProfileUrl",
    "#sigUserBackfillRange",
    "#sigUserMaxTweets",
  ];
  for (const sel of fields) {
    const el = $(sel);
    if (!el) continue;
    const evt =
      el.type === "checkbox" || el.type === "number" || el.tagName === "SELECT"
        ? "change"
        : "input";
    el.addEventListener(evt, () => persistSigUserForm());
    if (el.type === "number" || (el.tagName === "INPUT" && el.type !== "checkbox")) {
      el.addEventListener("blur", () => persistSigUserForm({ immediate: true }));
    }
  }
}

async function loadSignalsPanel() {
  try {
    const data = await api("/api/signals/config");
    const cfg = data.config || {};
    state.sigConfig = cfg;
    if ($("#sigListUrl")) {
      $("#sigListUrl").value = cfg.list_url || `https://x.com/i/lists/${cfg.list_id || ""}`;
    }
    if ($("#sigCutoffHours") && cfg.cutoff_hours != null) {
      $("#sigCutoffHours").value = cfg.cutoff_hours;
    }
    if ($("#sigMaxTweets") && cfg.max_tweets != null) {
      $("#sigMaxTweets").value = cfg.max_tweets;
    }
    if ($("#sigWatchEnabled")) $("#sigWatchEnabled").checked = !!cfg.watch_enabled;
    if ($("#sigCycleEnabled")) $("#sigCycleEnabled").checked = !!cfg.cycle_enabled;
    if ($("#sigDeepMode") && cfg.deep_sleep_mode) {
      $("#sigDeepMode").value = cfg.deep_sleep_mode === "patrol" ? "patrol" : "sleep";
    }
    if ($("#sigUserProfileUrl") || $("#sigUserBackfillRange") || $("#sigUserBloggerList")) {
      applySigUserForm(cfg, data.bloggers);
    }
    fillSigFilterNameOptions(
      Array.isArray(data.bloggers?.items)
        ? data.bloggers.items
        : Array.isArray(data.channels?.mappings)
          ? data.channels.mappings.map((m) => ({
              id: m.handle,
              name: m.channelName || m.handle,
            }))
          : _sigBloggersCache
    );
    restoreSigCardsFilter();
    syncSigCdpBadge(data.debugger_url_effective || cfg.debugger_url || "127.0.0.1:9223");
    if ($("#sigDebuggerUrl")) {
      $("#sigDebuggerUrl").value = cfg.debugger_url || data.debugger_url_effective || "127.0.0.1:9223";
    }
    renderSigWindows(data.windows || []);
    renderSigSchedule(data.schedule || [], data.watch || {}, data.daily_estimate || {});
    renderSigCycle(data.cycle || {}, cfg);
    updateSigCycleButton(data.cycle || {}, cfg);
    const ch = data.channels || {};
    const hint = $("#sigChannelsHint");
    if (hint) {
      const mapped = ch.mapped_count || 0;
      const en = ch.enabled === false ? "关闭" : "开启";
      const maps = (ch.mappings || [])
        .slice(0, 8)
        .map((m) => `${m.handle || ""}→${m.channelName || "?"}(${m.channelId || "?"})`)
        .join(" · ");
      hint.textContent =
        `Cards API ${en} · 已映射 ${mapped} 个用户 · 已推送 ${data.pushed_count || 0} · ${ch.path || "config/signals_channels.yaml"}` +
        (maps ? ` · ${maps}` : "");
    }
    fillSigTestHandleSelect(ch.mappings || []);
    const n = data.card_count || 0;
    const badge = $("#countSignals");
    if (badge) badge.textContent = String(n);
  } catch (e) {
    /* ignore */
  }
  await loadSignalCards();
  loadSigBacktestLast();
}

function syncSigCdpBadge(url) {
  const el = $("#sigCdpBadge");
  const btn = $("#btnSigCdpConfig");
  const v = String(url || "127.0.0.1:9223").trim();
  if (el) {
    el.textContent = `CDP ${v}`;
    el.title = `Chrome CDP：${v}`;
  }
  if (btn) btn.title = `CDP 调试地址：${v}`;
}

function openSigCdpDialog() {
  const dlg = $("#sigCdpConfigDialog");
  if (!dlg) return;
  setStatus($("#sigCdpConfigStatus"), "");
  if (typeof dlg.showModal === "function") dlg.showModal();
}

async function saveSigCdpConfig(e) {
  e.preventDefault();
  const raw = $("#sigDebuggerUrl")?.value.trim() || "";
  if (!raw) {
    setStatus($("#sigCdpConfigStatus"), "请填写 host:port", "error");
    return;
  }
  setStatus($("#sigCdpConfigStatus"), "保存中…");
  try {
    const data = await api("/api/signals/config", {
      method: "POST",
      body: JSON.stringify({ debugger_url: raw }),
    });
    if (!data.success) {
      setStatus($("#sigCdpConfigStatus"), data.error || "保存失败", "error");
      return;
    }
    const eff = data.config?.debugger_url || data.debugger_url_effective || raw;
    syncSigCdpBadge(eff);
    if ($("#sigDebuggerUrl")) $("#sigDebuggerUrl").value = eff;
    toast(`CDP 已设为 ${eff}`, "ok");
    $("#sigCdpConfigDialog")?.close();
  } catch (err) {
    setStatus($("#sigCdpConfigStatus"), String(err), "error");
  }
}

async function loadRealtimePanel() {
  const box = $("#rtEventList");
  const meta = $("#rtMeta");
  const status = ($("#rtStatus")?.value ?? "pending").trim();
  const module = ($("#rtModule")?.value ?? "").trim();
  const qs = new URLSearchParams({ limit: "50" });
  if (status) qs.set("status", status);
  if (module) qs.set("module", module);
  try {
    const data = await api(`/api/realtime/events?${qs.toString()}`);
    const pending = data.stats?.pending ?? data.total ?? 0;
    const badge = $("#countRealtime");
    if (badge) badge.textContent = String(data.stats?.pending ?? 0);
    if (meta) {
      const by = data.stats?.by_module || {};
      const parts = Object.entries(by).map(([k, v]) => `${k}:${v}`);
      meta.textContent = `共 ${data.total ?? 0} 条 · pending ${data.stats?.pending ?? 0}` +
        (parts.length ? ` · ${parts.join(" · ")}` : "");
    }
    const items = data.items || [];
    if (!box) return;
    if (!items.length) {
      box.innerHTML = `<div class="lab-empty">暂无事件。可点「注入 TV 样例」或启动 webhook / 轮询。</div>`;
      return;
    }
    box.innerHTML = items
      .map((it) => {
        const raw = escapeHtml(JSON.stringify(it.raw || {}, null, 2).slice(0, 1200));
        return `<article class="rt-card" data-rt-id="${escapeAttr(String(it.id))}">
          <header class="rt-card-head">
            <span class="rt-mod">${escapeHtml(it.module || "")}</span>
            <span class="rt-sev">${escapeHtml(it.severity || "")}</span>
            <span class="rt-st">${escapeHtml(it.status || "")}</span>
            <time class="muted">${escapeHtml(String(it.created_at || "").slice(0, 19))}</time>
          </header>
          <h3 class="rt-title">${escapeHtml(it.title || `#${it.id}`)}</h3>
          <pre class="rt-draft">${escapeHtml(it.draft_text || "")}</pre>
          <details class="rt-raw"><summary>raw / extracted</summary>
            <pre>${raw}</pre>
            <pre>${escapeHtml(JSON.stringify(it.extracted || {}, null, 2).slice(0, 800))}</pre>
          </details>
          <div class="rt-actions">
            <button type="button" class="btn primary btn-sm" data-rt-action="approved" data-rt-id="${escapeAttr(String(it.id))}">通过</button>
            <button type="button" class="btn ghost btn-sm" data-rt-action="rejected" data-rt-id="${escapeAttr(String(it.id))}">丢弃</button>
            <button type="button" class="btn ghost btn-sm" data-rt-action="snoozed" data-rt-id="${escapeAttr(String(it.id))}">稍后再看</button>
            <button type="button" class="btn ghost btn-sm" data-rt-action="pending" data-rt-id="${escapeAttr(String(it.id))}">回待审</button>
          </div>
        </article>`;
      })
      .join("");
  } catch (e) {
    if (meta) meta.textContent = String(e);
    if (box) box.innerHTML = `<div class="lab-empty">加载失败</div>`;
  }
}

async function setRealtimeStatus(id, status) {
  setStatus($("#rtStatusMsg"), "更新中…");
  try {
    const data = await api("/api/realtime/events", {
      method: "POST",
      body: JSON.stringify({ id, status }),
    });
    if (!data.success) {
      setStatus($("#rtStatusMsg"), data.error || "失败", "error");
      return;
    }
    setStatus($("#rtStatusMsg"), `已标记 ${status}`, "ok");
    await loadRealtimePanel();
  } catch (e) {
    setStatus($("#rtStatusMsg"), String(e), "error");
  }
}

async function runRealtimeModule(module) {
  setStatus($("#rtStatusMsg"), `运行 ${module}…`);
  try {
    const data = await api("/api/realtime/run", {
      method: "POST",
      body: JSON.stringify({ module, skip_llm: true }),
    });
    if (!data.success) {
      setStatus($("#rtStatusMsg"), data.error || "失败", "error");
      return;
    }
    const n = (data.results || []).filter((r) => r.ok).length;
    setStatus($("#rtStatusMsg"), `${module} 完成 · 入库约 ${n} 条`, "ok");
    await loadRealtimePanel();
  } catch (e) {
    setStatus($("#rtStatusMsg"), String(e), "error");
  }
}

async function ingestRealtimeTvDemo() {
  const stamp = Date.now();
  setStatus($("#rtStatusMsg"), "注入 TV 样例…");
  try {
    const data = await api("/api/realtime/ingest/tv", {
      method: "POST",
      body: JSON.stringify({
        skip_llm: true,
        symbol: "BTCUSDT",
        timeframe: "4H",
        side: "long",
        structure: `spring_demo_${stamp}`,
        message: "区间假跌破放量收回（本地样例）",
      }),
    });
    if (!data.ok) {
      setStatus($("#rtStatusMsg"), data.error || "注入失败", "error");
      return;
    }
    setStatus($("#rtStatusMsg"), `已入库 #${data.event_id}`, "ok");
    await loadRealtimePanel();
  } catch (e) {
    setStatus($("#rtStatusMsg"), String(e), "error");
  }
}

function restoreMainTabFromStorage() {
  try {
    const saved = localStorage.getItem(APP_MAIN_TAB_LS);
    const legacy = new Set(["news", "later", "archived", "tags", "history"]);
    const target = saved && APP_MAIN_TABS.includes(saved)
      ? saved
      : (legacy.has(saved) ? "signals" : null);
    if (target) {
      switchTab(target);
      return target;
    }
  } catch (_) {
    /* ignore corrupt cache */
  }
  switchTab("signals");
  return "signals";
}

function applySigModeUi(mode) {
  const m = mode === "user" ? "user" : mode === "value" ? "value" : "list";
  state.sigMode = m;
  document.querySelectorAll(".sig-mode-tab[data-sig-mode]").forEach((btn) => {
    const on = btn.getAttribute("data-sig-mode") === m;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  const listBox = $("#sigModeList");
  const userBox = $("#sigModeUser");
  const valueBox = $("#sigModeValue");
  if (listBox) listBox.hidden = m !== "list";
  if (userBox) userBox.hidden = m !== "user";
  if (valueBox) valueBox.hidden = m !== "value";
  const tradeFilter = $("#sigFilterTrade")?.closest("label");
  if (tradeFilter) tradeFilter.hidden = m === "value";
  const recOnly = $("#sigValueRecommendedOnly")?.closest("label");
  // already in value panel
  void recOnly;
}

function restoreSigModeFromStorage() {
  try {
    const saved = localStorage.getItem(APP_SIG_MODE_LS);
    if (saved === "user" || saved === "list" || saved === "value") {
      applySigModeUi(saved);
    }
  } catch (_) {
    /* ignore corrupt cache */
  }
}

function switchSigMode(mode) {
  applySigModeUi(mode);
  try {
    localStorage.setItem(APP_SIG_MODE_LS, state.sigMode);
  } catch (_) {
    /* ignore quota */
  }
  loadSignalCards();
}

function sigCardDedupKey(c) {
  const h = String(c.user_handle || parseSigUserHandle(c.author || "")).toLowerCase();
  const ts = Math.floor(sigCardTimeMs(c) / 1000);
  if (h && ts > 0) return `${h}:${ts}`;
  return String(c.tweet_id || c.id || "");
}

function dedupSigCards(items) {
  const map = new Map();
  for (const c of items || []) {
    const key = sigCardDedupKey(c) || `_${map.size}`;
    const prev = map.get(key);
    if (!prev) {
      map.set(key, c);
      continue;
    }
    const prevTrade = isSigTradeSignal(prev.signal || {});
    const curTrade = isSigTradeSignal(c.signal || {});
    map.set(key, curTrade && !prevTrade ? c : prevTrade && !curTrade ? prev : c);
  }
  return [...map.values()].sort((a, b) => sigCardTimeMs(b) - sigCardTimeMs(a));
}

function sigSourceLabel(c) {
  const modes = Array.isArray(c.source_modes)
    ? c.source_modes
    : c.source_mode
      ? [c.source_mode]
      : [];
  const labels = [];
  if (modes.includes("list_realtime")) labels.push("列表");
  if (modes.includes("user_backfill")) labels.push("博主");
  if (modes.includes("value_return")) labels.push("价值");
  if (!labels.length && c.list_id && String(c.list_id).startsWith("user:")) labels.push("博主");
  if (!labels.length && c.source_mode === "value_return") labels.push("价值");
  if (!labels.length && c.list_id) labels.push("列表");
  return labels.length ? labels.join("+") : "";
}

function parseSigUserHandle(raw) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const m = text.match(/(?:x\.com|twitter\.com)\/([^/?#]+)/i);
  if (m) {
    const h = m[1];
    if (["i", "home", "search", "explore"].includes(h.toLowerCase())) return "";
    return h.replace(/^@/, "");
  }
  if (text.startsWith("@")) return text.slice(1).split("/")[0];
  if (/^[A-Za-z0-9_]{1,15}$/.test(text)) return text;
  return "";
}

function setSigUserControlButtons({ running = false, paused = false } = {}) {
  const pause = $("#btnSigUserPause");
  const resume = $("#btnSigUserResume");
  const stop = $("#btnSigUserStop");
  const run = $("#btnSigUserRun");
  if (run) run.disabled = running;
  if (pause) {
    pause.disabled = !running || paused;
    pause.hidden = paused;
  }
  if (resume) {
    resume.disabled = !running || !paused;
    resume.hidden = !paused;
  }
  if (stop) stop.disabled = !running;
}

function renderSigUserRunLog(lines, itemLogs, batchResult) {
  const pre = $("#sigUserRunLog");
  if (!pre) return;
  const arr = Array.isArray(lines) ? lines : [];
  let logs = arr.length ? arr.join("\n") : "";
  const summaryMark = "======== 逐条摘要（验证用） ========";
  const cut = logs.indexOf(`\n${summaryMark}`);
  if (cut >= 0) logs = logs.slice(0, cut);
  const items = Array.isArray(itemLogs) ? itemLogs : [];
  let summaries = "";
  if (items.length) {
    const block = items
      .map((it, i) => {
        if (it && it.summary_line) return String(it.summary_line);
        return formatSigItemSummaryLine(it, i + 1, items.length);
      })
      .filter(Boolean)
      .join("\n");
    if (block) {
      summaries = `\n\n${summaryMark}\n${block}`;
    }
  }
  let batchTail = "";
  const batchItems = Array.isArray(batchResult?.items) ? batchResult.items : [];
  const failures = Array.isArray(batchResult?.failures)
    ? batchResult.failures
    : batchItems.filter((r) => r && !r.success && !r.aborted);
  if (batchItems.length > 1 || failures.length) {
    const linesOut = batchItems.map((r) => {
      const id = r.id || "?";
      const name = r.name || id;
      if (r.aborted) return `○ @${id}（${name}）：已终止`;
      if (r.success) {
        return `✓ @${id}（${name}）：抓取 ${r.fetched ?? "-"} · 解析 ${r.parsed ?? "-"} · 交易 ${r.trade_count ?? "-"}`;
      }
      return `✗ @${id}（${name}）：${r.message || r.error || "未知错误"}`;
    });
    if (failures.length && !logs.includes("批量失败明细")) {
      linesOut.push("", "======== 批量失败明细 ========");
      for (const f of failures) {
        linesOut.push(`✗ @${f.id || "?"}：${f.error || f.message || "未知错误"}`);
      }
    }
    batchTail = `\n\n======== 批量结果 ========\n${linesOut.join("\n")}`;
  }
  const text = logs + summaries + batchTail;
  if (!text.trim()) {
    pre.hidden = true;
    pre.textContent = "";
    return;
  }
  pre.hidden = false;
  pre.textContent = text;
  pre.scrollTop = pre.scrollHeight;
}

function formatSigItemSummaryLine(log, index, total) {
  if (!log || typeof log !== "object") return "";
  if (log.summary_line) return String(log.summary_line);
  const idx =
    index && total ? `[${index}/${total}] ` : index ? `[${index}] ` : "";
  const author = log.author || "(未知)";
  const timeS = log.display_time || log.time_label || String(log.created_at || "").slice(0, 19) || "未知";
  const preview = String(log.preview || "（空）").slice(0, 80);
  let flag = "非交易";
  let coins = "-";
  let dir = "-";
  if (log.skipped) {
    flag = "跳过";
  } else if (log.has_trade_signal) {
    flag = "交易";
    coins = (log.coins || []).slice(0, 6).join(",") || "-";
    dir = sigDirectionLabel(log.direction || "");
  }
  const result = log.result ? ` → ${log.result}${log.from_cache ? " · 缓存" : ""}` : "";
  return `${idx}${timeS} | ${author} | ${flag} | 币种=${coins} | 方向=${dir} | ${preview}${result}`;
}

function appendSigBacktestLog(line) {
  const pre = $("#sigBacktestLog");
  if (!pre) return;
  pre.hidden = false;
  pre.textContent = (pre.textContent ? `${pre.textContent}\n` : "") + line;
  pre.scrollTop = pre.scrollHeight;
}

function _validateCtxFromOpts(opts = {}) {
  const logSel = opts.logSel || "#sigBacktestLog";
  const progressSel = opts.progressSel || "#sigBacktestProgress";
  return {
    _backtestOnly: !!opts.backtestOnly,
    appendLog(line) {
      const pre = $(logSel);
      if (!pre) return;
      pre.hidden = false;
      pre.textContent = (pre.textContent ? `${pre.textContent}\n` : "") + line;
      pre.scrollTop = pre.scrollHeight;
    },
    setProgress(text) {
      const el = $(progressSel);
      if (el) el.textContent = text;
    },
    onDone(data) {
      if (typeof opts.onDone === "function") opts.onDone(data);
    },
  };
}

let _sigValidateCtx = null;
let _sigBacktestLast = null;
let _sigBacktestPending = null;
const SIG_BACKTEST_LS = "sigBacktestLastResult";

function persistSigBacktestLast() {
  const r = _sigBacktestLast;
  if (!r || !(r.items || []).length) return;
  try {
    localStorage.setItem(
      SIG_BACKTEST_LS,
      JSON.stringify({
        start: r.start,
        jobId: r.jobId,
        mock: r.mock,
        window_days: r.window_days,
        signal_count: r.signal_count,
        note: r.note,
        mode: r.mode,
        signals: r.signals,
        items: r.items,
        errors: r.errors || [],
        finished: true,
        savedAt: r.savedAt || Date.now(),
      })
    );
  } catch (_) {
    /* ignore quota */
  }
}

function loadSigBacktestLast() {
  if (_sigBacktestLast?.items?.length) {
    updateSigBacktestResultButton();
    return;
  }
  try {
    const raw = localStorage.getItem(SIG_BACKTEST_LS);
    if (!raw) return;
    const data = JSON.parse(raw);
    if (!data || !(data.items || []).length) return;
    _sigBacktestLast = data;
  } catch (_) {
    /* ignore corrupt cache */
  }
  updateSigBacktestResultButton();
}

function updateSigBacktestResultButton() {
  const btn = $("#btnSigBacktestResult");
  if (btn) btn.disabled = !(_sigBacktestLast?.items || []).length;
}

function setSigBacktestLast(partial) {
  if (!partial || !(partial.items || []).length) return;
  _sigBacktestLast = {
    ...(_sigBacktestLast || {}),
    ...partial,
    finished: true,
    savedAt: Date.now(),
  };
  persistSigBacktestLast();
  updateSigBacktestResultButton();
}

function toUtcIso(raw) {
  if (!raw) return new Date().toISOString();
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return new Date().toISOString();
  return d.toISOString();
}

function normalizeBacktestSymbol(coin) {
  return String(coin || "")
    .trim()
    .toUpperCase()
    .replace(/USDT$|USDC$|BUSD$/, "");
}

function cardToBacktestSignals(card) {
  const sig = card?.signal || {};
  if (!isSigTradeSignal(sig)) return [];
  const dir = normalizeSigDirectionKey(sig.direction);
  const coins = (sig.coins || [])
    .map(normalizeBacktestSymbol)
    .filter(Boolean);
  if (!coins.length) return [];
  const signalAt = toUtcIso(card.created_at || card.parsed_at || card.display_time);
  const entryRaw = (sig.entries || [])[0];
  const entry = entryRaw != null && String(entryRaw).trim() ? String(entryRaw).trim() : "";
  const baseId = String(card.tweet_id || card.id || "");
  return coins.map((symbol) => {
    const row = {
      id: baseId ? `${baseId}-${symbol}` : symbol,
      symbol,
      direction: dir,
      signalAt,
    };
    if (entry) {
      row.entry = entry;
      row.entryMode = "limit";
    } else {
      row.entryMode = "market";
    }
    return row;
  });
}

function collectBacktestSignalsFromCards(cards) {
  const arr = Array.isArray(cards) ? cards : [];
  const onlyTrade = !!$("#sigFilterTrade")?.checked;
  const out = [];
  const seen = new Set();
  for (const card of arr) {
    if (onlyTrade && !isSigTradeSignal(card?.signal)) continue;
    for (const sig of cardToBacktestSignals(card)) {
      const key = `${sig.id}|${sig.symbol}|${sig.signalAt}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(sig);
    }
  }
  return out.slice(0, 500);
}

function formatBacktestTime(raw) {
  if (!raw) return "-";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return String(raw).slice(0, 19);
  return formatDateFullCST(d).replace(/ \+08:00$/, "").slice(0, 19);
}

function formatBacktestResultItem(it) {
  if (!it || typeof it !== "object") return "";
  const symbol = String(it.symbol || "?");
  if (it.error) {
    return `<article class="sig-card is-noise sig-backtest-card">
      <div class="sig-card-top">
        <span class="sig-coin">${escapeHtml(symbol)}</span>
        <span class="muted">回测失败</span>
      </div>
      <p class="sig-summary">${escapeHtml(String(it.error))}</p>
    </article>`;
  }
  const dirKey = String(it.direction || "unknown").toLowerCase();
  const dir = sigDirectionLabel(it.direction);
  const timeLabel = formatBacktestTime(it.signalAt);
  const entryRaw = it.entry;
  const hasEntry = entryRaw != null && entryRaw !== "";
  const entry = hasEntry ? String(entryRaw) : "市价";
  const entryMode = it.entryMode === "limit" || (hasEntry && it.entryMode !== "market") ? "限价" : "市价";
  const windowDays = it.windowDays ?? 3;
  const threshold = it.profitThresholdPct != null ? `${it.profitThresholdPct}%` : "-";
  const maxP = it.maxProfitPct != null ? `${it.maxProfitPct}%` : "-";
  const minP = it.minProfitPct != null ? `${it.minProfitPct}%` : "-";
  const hitMax =
    it.hitProfitThresholdBeforeMax == null ? "-" : it.hitProfitThresholdBeforeMax ? "是" : "否";
  const hitMin =
    it.hitProfitThresholdBeforeMin == null ? "-" : it.hitProfitThresholdBeforeMin ? "是" : "否";
  const pnl = it.currentPnlPct != null ? `${it.currentPnlPct}%` : "-";
  const mockBadge = it.mock ? `<span class="sig-backtest-mock">Mock</span>` : "";

  const signalId = String(it.signalId || it.id || "");
  const tweetId = signalId.split("-")[0];
  const srcCard = _sigCardsCache.find((c) => String(c.tweet_id || "") === tweetId);
  const summaryRaw = srcCard
    ? stripSigTimePrefix(srcCard.signal?.summary || srcCard.text || "")
    : "";
  const summary = summaryRaw.trim();

  const levels = [
    `<div><b>入场</b>${escapeHtml(entry)} · ${escapeHtml(entryMode)}</div>`,
    `<div><b>窗口</b>${windowDays} 天 · 阈值 ${escapeHtml(threshold)}</div>`,
    `<div><b>最高盈利</b>${escapeHtml(maxP)}${
      it.maxProfitAt ? ` · ${escapeHtml(formatBacktestTime(it.maxProfitAt))}` : ""
    }</div>`,
    `<div><b>最低盈利</b>${escapeHtml(minP)}${
      it.minProfitAt ? ` · ${escapeHtml(formatBacktestTime(it.minProfitAt))}` : ""
    }</div>`,
    `<div><b>触顶前达阈值</b>${escapeHtml(hitMax)} · <b>触底前达阈值</b>${escapeHtml(hitMin)}</div>`,
  ];

  return `<article class="sig-card is-trade sig-backtest-card">
    <div class="sig-card-top">
      ${mockBadge}
      <span class="sig-dir ${escapeAttr(dirKey)}">${escapeHtml(dir)}</span>
      <span class="sig-coin">${escapeHtml(symbol)}</span>
      <span class="sig-time" title="帖子时间">${escapeHtml(timeLabel)}</span>
    </div>
    ${summary ? `<p class="sig-summary" title="${escapeAttr(summary)}">${escapeHtml(summary)}</p>` : ""}
    <div class="sig-levels">${levels.join("")}</div>
    <div class="sig-card-foot">
      <span class="sig-conf">当前盈亏 ${escapeHtml(pnl)}</span>
    </div>
  </article>`;
}

function renderSigBacktestResultDialog() {
  const meta = $("#sigBacktestResultMeta");
  const body = $("#sigBacktestResultBody");
  if (!meta || !body) return;
  const r = _sigBacktestLast;
  if (!r || !(r.items || []).length) {
    meta.innerHTML = "";
    body.innerHTML = `<p class="sig-backtest-empty">请先点击「发送回测」并等待任务完成。</p>`;
    return;
  }
  const start = r.start || {};
  const count = (r.items || []).length;
  const isMock = !!(start.mock ?? r.mock);
  const windowDays = start.windowDays ?? r.window_days ?? 3;
  const note = start.note || r.note || "";
  const jobShort = r.jobId ? `${String(r.jobId).slice(0, 8)}…` : "";
  meta.innerHTML = [
    `<span class="sig-backtest-meta-chip">${count} 条</span>`,
    `<span class="sig-backtest-meta-chip">${windowDays} 天窗口</span>`,
    isMock ? `<span class="sig-backtest-meta-chip is-mock">Mock</span>` : "",
    jobShort ? `<span class="sig-backtest-meta-chip" title="${escapeAttr(String(r.jobId))}">${escapeHtml(jobShort)}</span>` : "",
    note ? `<span class="sig-backtest-meta-chip is-note" title="${escapeAttr(note)}">${escapeHtml(note)}</span>` : "",
  ]
    .filter(Boolean)
    .join("");
  body.innerHTML = (r.items || []).map((it) => formatBacktestResultItem(it)).join("");
}

function openSigBacktestResultDialog() {
  renderSigBacktestResultDialog();
  $("#sigBacktestResultDialog")?.showModal();
}

function handleValidateWsMessage(msg) {
  const c = _sigValidateCtx || _validateCtxFromOpts({});
  const kind = msg.kind || msg.type || "";
  const data = msg.data || msg.payload || msg;
  if (kind === "card_validate_started") {
    c.appendLog(`开始验证 · 共 ${data.total || "?"} 张`);
    c.setProgress(`0 / ${data.total || "?"}`);
  } else if (kind === "card_validate_progress") {
    c.setProgress(`${data.index || 0} / ${data.total || "?"}`);
  } else if (kind === "card_validate_item") {
    const item = data.item || data;
    c.appendLog(formatValidateItem(item));
  } else if (kind === "card_validate_done") {
    const items = data.items || [];
    c.appendLog(`验证完成 · ${items.length} 条结果`);
    c.setProgress("完成");
    closeSigValidateWs();
    c.onDone(data);
  } else if (kind === "card_validate_error") {
    c.appendLog(`验证失败：${data.error || "未知错误"}`);
    c.setProgress("失败");
    closeSigValidateWs();
  }
}

function formatValidateItem(it) {
  if (!it || typeof it !== "object") return "";
  if (it.error) {
    return `[错误] ${it.symbol || "?"} · ${it.error}`;
  }
  const parts = [
    it.mock ? "[Mock]" : "",
    it.signalId ? `id=${it.signalId}` : it.cardId ? `#${it.cardId}` : "",
    it.symbol ? `币种=${it.symbol}` : "",
    it.direction ? sigDirectionLabel(it.direction) : "",
  ].filter(Boolean);
  if (it.entry != null) parts.push(`入场=${it.entry}`);
  if (it.entryMode) parts.push(`方式=${it.entryMode}`);
  if (it.windowDays != null) parts.push(`${it.windowDays}天窗口`);
  if (it.maxProfitPct != null) parts.push(`最高盈利 ${it.maxProfitPct}%`);
  if (it.minProfitPct != null) parts.push(`最低盈利 ${it.minProfitPct}%`);
  if (it.maxDrawdownPct != null) parts.push(`最大回撤 ${it.maxDrawdownPct}%`);
  if (it.currentPnlPct != null) parts.push(`当前盈亏 ${it.currentPnlPct}%`);
  if (it.profitThresholdPct != null) parts.push(`阈值 ${it.profitThresholdPct}%`);
  if (it.hitProfitThresholdBeforeMax != null) {
    parts.push(`触顶前达阈值=${it.hitProfitThresholdBeforeMax ? "是" : "否"}`);
  }
  if (it.hitProfitThresholdBeforeMin != null) {
    parts.push(`触底前达阈值=${it.hitProfitThresholdBeforeMin ? "是" : "否"}`);
  }
  if (it.maxProfitAt) parts.push(`峰值@${String(it.maxProfitAt).slice(0, 19)}`);
  if (it.minProfitAt) parts.push(`谷底@${String(it.minProfitAt).slice(0, 19)}`);
  return parts.join(" · ");
}

let _sigValidateWs = null;
let _sigValidatePollTimer = null;

function closeSigValidateWs() {
  if (_sigValidateWs) {
    try {
      _sigValidateWs.close();
    } catch (_) {
      /* ignore */
    }
    _sigValidateWs = null;
  }
  if (_sigValidatePollTimer) {
    clearInterval(_sigValidatePollTimer);
    _sigValidatePollTimer = null;
  }
  _sigValidateCtx = null;
}

async function connectValidateJobWs(jobId, ctx, { mock = false } = {}) {
  _sigValidateCtx = ctx;
  try {
    const wsCfg = await api("/api/signals/cards/ws-config");
    const wsUrl = wsCfg.ws_url || "ws://127.0.0.1:3851/ws";
    _sigValidateWs = new WebSocket(wsUrl);
    _sigValidateWs.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.channel && msg.channel !== "meta") return;
        handleValidateWsMessage(msg);
      } catch (_) {
        /* ignore malformed */
      }
    };
    _sigValidateWs.onerror = () => ctx.appendLog("WebSocket 连接异常，将使用轮询");
  } catch (_) {
    ctx.appendLog("WebSocket 不可用，使用轮询");
  }

  _sigValidatePollTimer = setInterval(async () => {
    try {
      const st = await api(`/api/signals/cards/validate/${encodeURIComponent(jobId)}`);
      if (st.status === "done") {
        const items = st.items || [];
        items.forEach((it) => ctx.appendLog(formatValidateItem(it)));
        ctx.appendLog(`${mock ? "[Mock] " : ""}轮询：验证完成`);
        ctx.setProgress("完成");
        closeSigValidateWs();
        ctx.onDone({ items, errors: st.errors || [], mock, jobId });
      } else if (st.status === "error") {
        ctx.appendLog(`轮询：${st.error || "验证失败"}`);
        closeSigValidateWs();
      } else {
        ctx.setProgress(st.status || "running");
      }
    } catch (_) {
      /* ignore poll errors */
    }
  }, 2500);
}

async function startSigCardsBacktest() {
  const btn = $("#btnSigBacktest");
  if (btn) btn.disabled = true;
  closeSigValidateWs();
  const log = $("#sigBacktestLog");
  if (log) {
    log.hidden = false;
    log.textContent = "";
  }
  if ($("#sigBacktestProgress")) $("#sigBacktestProgress").textContent = "";
  const signals = collectBacktestSignalsFromCards(_sigCardsCache);
  if (!signals.length) {
    toast("无有效交易信号可回测（需币种 + 做多/做空 + 时间）", "error");
    if (btn) btn.disabled = false;
    return;
  }
  const body = { signals };
  toast(`启动 Cards 回测（${signals.length} 条信号）…`, "info");
  _sigBacktestPending = { signals };
  try {
    const data = await api("/api/signals/cards/validate", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const ctx = _validateCtxFromOpts({
      logSel: "#sigBacktestLog",
      progressSel: "#sigBacktestProgress",
      backtestOnly: true,
      onDone(doneData) {
        const items = doneData.items || [];
        if (items.length) {
          setSigBacktestLast({
            ...(_sigBacktestPending || {}),
            items,
            errors: doneData.errors || [],
            jobId: doneData.jobId || _sigBacktestPending?.jobId,
          });
        }
        _sigBacktestPending = null;
        toast("回测验证完成", "ok");
      },
    });
    if (!data.success || !data.job_id) {
      const msg = data.error || data.hint || "回测启动失败";
      ctx.appendLog(msg);
      if (data.hint && data.error && !String(data.error).includes(data.hint)) {
        ctx.appendLog(data.hint);
      }
      if (data.note) ctx.appendLog(data.note);
      toast(msg.split(" · ")[0].slice(0, 120), "error");
      return;
    }
    _sigBacktestPending = {
      signals,
      start: data.raw || {},
      jobId: data.job_id,
      mock: data.mock,
      window_days: data.window_days,
      signal_count: data.signal_count,
      note: data.note,
      mode: data.mode,
    };
    ctx.appendLog(
      `POST /api/v1/cards/validate · signals=${signals.length} · windowDays=${data.window_days ?? 3}${
        data.mock ? " · mock" : ""
      }`
    );
    if (data.note) ctx.appendLog(data.note);
    ctx.appendLog(`jobId=${data.job_id} · ws://127.0.0.1:3851/ws`);
    await connectValidateJobWs(data.job_id, ctx, { mock: !!data.mock });
  } catch (e) {
    appendSigBacktestLog(String(e));
    toast(String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function clearSigUserCache() {
  const form = collectSigUserForm();
  const handles = [...(form.user_blogger_ids || [])];
  if (form.user_handle) handles.push(form.user_handle);
  const uniq = [...new Set(handles.map((h) => String(h || "").toLowerCase()).filter(Boolean))];
  if (!uniq.length) {
    toast("请勾选博主或填写额外链接", "error");
    return;
  }
  const label = uniq.map((h) => `@${h}`).join("、");
  if (!confirm(`清除 ${label} 的解析缓存？\n将删除本地已解析卡片与已见记录，下次会重新 AI 解析。`)) {
    return;
  }
  const btn = $("#btnSigUserClearCache");
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/signals/user/clear-cache", {
      method: "POST",
      body: JSON.stringify({
        handles: uniq,
        profile_url: form.user_profile_url,
        user_handle: form.user_handle,
      }),
    });
    if (!data.success) {
      toast(data.error || "清除失败", "error");
      setStatus($("#sigUserStatus"), data.error || "清除失败", "error");
      return;
    }
    toast(data.message || "缓存已清除", "ok");
    setStatus($("#sigUserStatus"), data.message || "缓存已清除", "ok");
    await loadSignalsPanel();
  } catch (e) {
    toast(String(e), "error");
    setStatus($("#sigUserStatus"), String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runUserSignalsCrawl() {
  const btn = $("#btnSigUserRun");
  const form = collectSigUserForm();
  const handles = [...(form.user_blogger_ids || [])];
  if (form.user_handle) handles.push(form.user_handle);
  const uniq = [...new Set(handles.map((h) => String(h || "").toLowerCase()).filter(Boolean))];
  if (!uniq.length) {
    toast("请勾选博主或填写额外链接/@handle", "error");
    return;
  }
  if (btn) btn.disabled = true;
  await persistSigUserForm({ immediate: true });
  const label = uniq.map((h) => `@${h}`).join("、");
  setStatus($("#sigUserStatus"), `提交批量回溯（${uniq.length}）：${label}…`);
  renderSigUserRunLog([]);
  setSigUserControlButtons({ running: false, paused: false });
  try {
    const start = await api("/api/signals/user/run", {
      method: "POST",
      body: JSON.stringify({
        handles: uniq,
        profile_url: form.user_profile_url,
        backfill_range: form.user_backfill_range,
        max_tweets: form.user_max_tweets,
      }),
    });
    if (!start.success || !start.job_id) {
      setStatus($("#sigUserStatus"), start.error || "启动失败", "error");
      return;
    }
    const jobId = start.job_id;
    _sigActiveJobId = jobId;
    setSigUserControlButtons({ running: true, paused: false });
    for (;;) {
      await new Promise((r) => setTimeout(r, 1200));
      const data = await api(`/api/jobs/${jobId}`);
      const job = data.job || {};
      renderSigUserRunLog(job.logs || [], job.result?.item_logs, job.result);
      const paused = job.status === "paused" || job.control_status === "paused";
      setSigUserControlButtons({
        running: !["done", "error", "cancelled"].includes(job.status),
        paused,
      });
      setStatus(
        $("#sigUserStatus"),
        paused ? `已暂停 · ${job.message || ""}` : job.message || job.status || "运行中…"
      );
      if (["done", "error", "cancelled"].includes(job.status)) {
        const result = job.result || {};
        const ok = job.status === "done" || job.status === "cancelled";
        const hasFail = Number(result.failed || 0) > 0 || (result.failures || []).length > 0;
        setStatus(
          $("#sigUserStatus"),
          result.message || job.message || (job.status === "cancelled" ? "已终止" : "完成"),
          ok && !hasFail ? "ok" : "error"
        );
        renderSigUserRunLog(job.logs || [], result.item_logs, result);
        if (ok) {
          toast(result.message || "博主回溯完成", hasFail ? "error" : "ok");
          const savedRange = form.user_backfill_range;
          const savedIds = form.user_blogger_ids;
          await loadSignalsPanel();
          if ($("#sigUserBackfillRange") && savedRange) {
            $("#sigUserBackfillRange").value = normalizeSigBackfillRange(savedRange);
          }
          if (savedIds?.length) {
            renderSigUserBloggerList(_sigBloggersCache, savedIds);
            writeSigUserFormLocal({ user_blogger_ids: savedIds });
          }
          await loadSignalCards();
        }
        break;
      }
    }
  } catch (e) {
    setStatus($("#sigUserStatus"), String(e), "error");
  } finally {
    _sigActiveJobId = "";
    setSigUserControlButtons({ running: false, paused: false });
    if (btn) btn.disabled = false;
  }
}

function applySigTestVisibility(fromUser) {
  const cb = $("#sigHideTest");
  const box = $("#sigTestBox");
  const btn = $("#btnSigHideTest");
  if (!box) return;
  const hide = fromUser && cb ? !!cb.checked : localStorage.getItem("sigHideTest") === "1";
  if (cb) cb.checked = hide;
  localStorage.setItem("sigHideTest", hide ? "1" : "0");
  box.classList.toggle("is-hidden", hide);
  box.style.display = hide ? "none" : "";
  if (btn) btn.textContent = hide ? "显示" : "隐藏";
}

function updateSigCycleButton(cycle, cfg) {
  const btn = $("#btnSigCycle");
  const cb = $("#sigCycleEnabled");
  const on = !!(cycle?.cycle_enabled ?? cfg?.cycle_enabled);
  if (cb) cb.checked = on;
  if (!btn) return;
  btn.textContent = on ? "关闭周期抓取" : "开启周期抓取";
  btn.classList.toggle("primary", !on);
  btn.classList.toggle("ghost", on);
}

async function toggleSigCycle() {
  const btn = $("#btnSigCycle");
  if (btn) btn.disabled = true;
  try {
    let on = !!$("#sigCycleEnabled")?.checked;
    try {
      const cur = await api("/api/signals/config");
      on = !!(cur.config?.cycle_enabled);
    } catch (_) {
      /* use checkbox */
    }
    const data = await api("/api/signals/cycle", {
      method: "POST",
      body: JSON.stringify({ enabled: !on }),
    });
    if (!data.success) {
      toast(data.error || "操作失败", "error");
      return;
    }
    const cycle = data.cycle || {};
    updateSigCycleButton(cycle, { cycle_enabled: cycle.cycle_enabled });
    renderSigCycle(cycle, { cycle_enabled: cycle.cycle_enabled, last_crawl_at: cycle.last_crawl_at });
    toast(cycle.cycle_enabled ? "周期抓取已开启（5–15 分钟）" : "周期抓取已关闭", "ok");
  } catch (e) {
    toast(String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderSigCycle(cycle, cfg) {
  const hint = $("#sigCycleHint");
  if (!hint) return;
  const on = !!(cycle.cycle_enabled ?? cfg.cycle_enabled);
  const last = String(cycle.last_crawl_at || cfg.last_crawl_at || "").slice(0, 19);
  if (!on) {
    hint.textContent = last
      ? `周期抓取未开启 · 上次爬取 ${last}`
      : "周期抓取未开启 · 勾选后保存即按 5–15 分钟随机间隔增量抓取（首次最多 8h）";
    hint.className = "status";
    return;
  }
  const wait = cycle.next_wait_seconds;
  const next = String(cycle.next_run_at || "").slice(0, 19);
  const running = cycle.running ? " · 抓取中" : "";
  const lastRun = cycle.last_run_at ? ` · 上轮 ${String(cycle.last_run_at).slice(0, 19)}` : "";
  const waitTxt =
    wait != null ? ` · 约 ${Math.round(wait / 60)} 分后触发` : "";
  hint.textContent = `周期抓取中${running}${waitTxt} · 下次 ${next || "—"}${lastRun}${
    last ? ` · 上次完成 ${last}` : ""
  }`;
  hint.className = "status ok";
}

function renderSigSchedule(schedule, watch, estimate) {
  const box = $("#sigScheduleTable");
  const hint = $("#sigWatchHint");
  const next = watch.next || {};
  const on = !!watch.watch_enabled;
  if (hint) {
    if (!on) {
      hint.textContent = "分时监听未开启 · 勾选后保存即可按北京时间自动扫列表";
      hint.className = "status";
    } else if (next.sleeping) {
      hint.textContent = `监听中 · 当前休眠 · ${next.reason || ""} · 下次 ${String(next.next_run_at || "").slice(0, 19)}`;
      hint.className = "status";
    } else {
      const est = estimate.approx_runs != null ? ` · 估全天 ~${estimate.approx_runs} 次` : "";
      hint.textContent = `监听中 · ${next.slot_label || next.slot_id || ""} · 约 ${next.wait_minutes || "?"} 分后触发 · 下次 ${String(next.next_run_at || "").slice(0, 19)}${est}`;
      hint.className = "status ok";
    }
  }
  if (!box) return;
  const cur = watch.slot_id || next.slot_id || "";
  box.innerHTML = (schedule || [])
    .map((r) => {
      const onRow = r.id === cur ? " · ← 当前" : "";
      return `<div>${escapeHtml(r.range)} · ${escapeHtml(r.label)} · ${escapeHtml(r.interval)} ${escapeHtml(r.weight || "")}${onRow}</div>`;
    })
    .join("");
}

let _sigWindowsCache = [];

function formatSigWindowExecTime(raw) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const d = new Date(text);
  if (Number.isNaN(d.getTime())) return text.slice(0, 19);
  return formatDateFullCST(d).replace(/ \+08:00$/, "").slice(0, 19);
}

function formatSigWindowLine(w) {
  const rangeLabel = SIG_BACKFILL_RANGES[w.backfill_range] || w.range_label || "";
  const since = String(w.since || "").slice(0, 19);
  const from = String(w.from || "").slice(0, 19);
  const to = String(w.to || "").slice(0, 19);
  const execAt = formatSigWindowExecTime(w.fetched_at || w.executed_at || w.run_at || "");
  const rangePart = rangeLabel
    ? ` · ${escapeHtml(rangeLabel)}${since ? `（自 ${escapeHtml(since)}）` : ""}`
    : "";
  const execPart = execAt ? ` · 执行 ${escapeHtml(execAt)}` : "";
  const spanPart = from && to ? ` · 帖文 ${escapeHtml(from)} → ${escapeHtml(to)}` : "";
  return `#${escapeHtml(String(w.list_id || ""))}${rangePart}${execPart}${spanPart} · 解析 ${w.parsed || 0}/${w.fetched || 0}`;
}

function applySigKolVisibility() {
  const box = $("#sigCards");
  const hide = localStorage.getItem("sigHideKol") === "1";
  const cb = $("#sigHideKol");
  if (cb) cb.checked = hide;
  if (box) box.classList.toggle("sig-hide-kol", hide);
}

function renderSigWindows(windows) {
  const box = $("#sigWindows");
  if (!box) return;
  _sigWindowsCache = Array.isArray(windows) ? windows.slice() : [];
  if (!_sigWindowsCache.length) {
    box.textContent = "暂无记录（跑完一轮后会写入，下次默认只拉新区间）";
    return;
  }
  const showAll = !!$("#sigShowAllWindows")?.checked;
  const rows = showAll ? _sigWindowsCache : _sigWindowsCache.slice(0, 1);
  box.innerHTML = rows.map((w) => `<div>${formatSigWindowLine(w)}</div>`).join("");
  if (!showAll && _sigWindowsCache.length > 1) {
    box.insertAdjacentHTML(
      "beforeend",
      `<div class="muted" style="margin-top:4px">另有 ${_sigWindowsCache.length - 1} 条历史记录 · 勾选「查看全部」展开</div>`
    );
  }
}

async function saveSignalsConfig() {
  try {
    const data = await api("/api/signals/config", {
      method: "POST",
      body: JSON.stringify({
        list_url: $("#sigListUrl")?.value.trim() || "",
        cutoff_hours: Number($("#sigCutoffHours")?.value || 24),
        max_tweets: Number($("#sigMaxTweets")?.value || 40),
        watch_enabled: !!$("#sigWatchEnabled")?.checked,
        cycle_enabled: !!$("#sigCycleEnabled")?.checked,
        deep_sleep_mode: $("#sigDeepMode")?.value || "sleep",
      }),
    });
    if (data.success) {
      const cfg = data.config || {};
      let msg = "配置已保存";
      if (cfg.watch_enabled) msg += " · 分时监听已开";
      if (cfg.cycle_enabled) msg += " · 周期抓取已开";
      toast(msg, "ok");
      if (data.config?.list_url && $("#sigListUrl")) {
        $("#sigListUrl").value = data.config.list_url;
      }
      await loadSignalsPanel();
    } else toast(data.error || "保存失败", "error");
  } catch (e) {
    toast(String(e), "error");
  }
}

let _sigTestMappings = [];

function fillSigTestHandleSelect(mappings) {
  const sel = $("#sigTestHandle");
  if (!sel) return;
  const prev = sel.value;
  _sigTestMappings = Array.isArray(mappings) ? mappings : [];
  const opts = [
    `<option value="">（手动 / 默认频道）</option>`,
    ..._sigTestMappings.map((m) => {
      const h = String(m.handle || "");
      const label = `${m.channelName || "?"} · @${h} · ${m.channelId || "?"}`;
      return `<option value="${escapeAttr(h)}">${escapeHtml(label)}</option>`;
    }),
  ];
  sel.innerHTML = opts.join("");
  if (prev && [...sel.options].some((o) => o.value === prev)) {
    sel.value = prev;
  } else if (_sigTestMappings.length) {
    sel.value = String(_sigTestMappings[0].handle || "");
  }
  fillSigTestDefaultsFromHandle();
}

function fillSigTestDefaultsFromHandle() {
  const handle = $("#sigTestHandle")?.value || "";
  const m = _sigTestMappings.find((x) => String(x.handle) === handle);
  const body = $("#sigTestBody");
  if (!body || body.dataset.touched === "1") return;
  if (m) {
    body.placeholder = `[测试] ${m.channelName || handle} · BTC 做多，关注支撑`;
  }
}

function collectSigTestPayload(extra = {}) {
  const handle = $("#sigTestHandle")?.value.trim() || "";
  return {
    handle,
    body: $("#sigTestBody")?.value.trim() || "",
    all_mapped: !!$("#sigTestAllMapped")?.checked,
    ...extra,
  };
}

function sigDirectionLabel(dir) {
  const key = normalizeSigDirectionKey(dir) || String(dir || "unknown").toLowerCase();
  const map = {
    long: "做多",
    short: "做空",
    flat: "中性",
    watch: "观望",
    unknown: "未知",
  };
  return map[key] || "未知";
}

function normalizeSigDirectionKey(dir) {
  const raw = String(dir || "").trim();
  const key = raw.toLowerCase();
  const map = {
    long: "long",
    short: "short",
    做多: "long",
    做空: "short",
    看多: "long",
    看空: "short",
    买入: "long",
    卖出: "short",
  };
  return map[raw] || map[key] || "";
}

function isSigTradeSignal(sig) {
  if (!sig || typeof sig !== "object") return false;
  const coins = (sig.coins || []).map((c) => String(c).trim()).filter(Boolean);
  const dir = normalizeSigDirectionKey(sig.direction);
  return coins.length > 0 && (dir === "long" || dir === "short");
}

function formatSigTestSignal(sig) {
  if (!sig || typeof sig !== "object") return "";
  const coins = (sig.coins || []).join(",") || "-";
  const dir = sigDirectionLabel(sig.direction);
  const flag = sig.has_trade_signal ? "有交易信号" : "无交易信号";
  const parts = [`AI解析: ${flag}`, `币种=${coins}`, `方向=${dir}`];
  if ((sig.entries || []).length) parts.push(`入场=${(sig.entries || []).join("/")}`);
  if ((sig.take_profits || []).length) parts.push(`止盈=${(sig.take_profits || []).join("/")}`);
  if (sig.stop_loss) parts.push(`止损=${sig.stop_loss}`);
  if (sig.leverage) parts.push(`杠杆=${sig.leverage}`);
  if (sig.summary) parts.push(`摘要=${sig.summary}`);
  if (sig.provider) parts.push(`解析=${sig.provider === "heuristic" ? "规则解析" : "AI 解析"}`);
  return parts.join(" · ");
}

function formatSigTestItemLog(it) {
  const head = `${it.success ? "OK" : "FAIL"} · ${it.channelName || "?"} (${it.channelId || "?"}) · @${it.handle || "-"}`;
  const sigLine = formatSigTestSignal(it.signal);
  if (it.dry_run) {
    return `${head}\n${sigLine}\n${JSON.stringify(it.payload || {}, null, 2)}`;
  }
  const lines = [head];
  if (sigLine) lines.push(sigLine);
  if (!it.success) {
    lines.push(`原因: ${it.error_detail || it.error || "未知错误"} (status=${it.status ?? "?"})`);
    const req = it.request || {};
    lines.push(`请求 URL: ${req.url || it.url || "?"}`);
    lines.push(`请求 Headers: ${JSON.stringify(req.headers || {}, null, 2)}`);
    lines.push(`请求 Body:\n${JSON.stringify(it.payload || req.body || {}, null, 2)}`);
    if (it.response) {
      lines.push(`响应:\n${JSON.stringify(it.response, null, 2)}`);
    }
    return lines.join("\n");
  }
  lines.push(`status=${it.status || 200}`);
  if (it.response) {
    lines.push(JSON.stringify(it.response, null, 2));
  }
  return lines.join("\n");
}

async function sendSignalsTest({ dryRun = false } = {}) {
  const previewBtn = $("#btnSigTestPreview");
  const sendBtn = $("#btnSigTestSend");
  if (previewBtn) previewBtn.disabled = true;
  if (sendBtn) sendBtn.disabled = true;
  const forceDry = dryRun || !!$("#sigTestDryRun")?.checked;
  const bodyText = $("#sigTestBody")?.value.trim() || "";
  if (!bodyText) {
    toast("请填写推文正文", "error");
    if (previewBtn) previewBtn.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
    return;
  }
  setStatus($("#sigTestStatus"), forceDry ? "AI 解析并生成预览…" : "AI 解析并发送…");
  const log = $("#sigTestLog");
  try {
    const data = await api("/api/signals/push-test", {
      method: "POST",
      body: JSON.stringify(
        collectSigTestPayload({
          dry_run: forceDry,
        })
      ),
    });
    const lines = (data.items || []).map((it) => formatSigTestItemLog(it));
    if (log) {
      log.hidden = false;
      log.textContent = lines.join("\n\n") || JSON.stringify(data, null, 2);
    }
    const ok = !!data.success;
    const firstFail = (data.items || []).find((it) => !it.success);
    setStatus(
      $("#sigTestStatus"),
      forceDry
        ? `预览 ${data.previewed || (data.items || []).length} 条`
        : ok
          ? `发送完成：成功 ${data.sent || 0} · 失败 ${data.failed || 0}`
          : `发送失败：${firstFail?.error_detail || firstFail?.error || "见下方日志"}`,
      ok ? "ok" : "error"
    );
    toast(
      forceDry ? "已生成测试 payload" : ok ? `测试推送成功 ${data.sent || 0}` : "测试推送失败，见日志",
      ok ? "ok" : "error"
    );
  } catch (e) {
    setStatus($("#sigTestStatus"), String(e), "error");
    if (log) {
      log.hidden = false;
      log.textContent = String(e);
    }
  } finally {
    if (previewBtn) previewBtn.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
  }
}

let _sigActiveJobId = "";

function setSigControlButtons({ running = false, paused = false } = {}) {
  const pause = $("#btnSigPause");
  const resume = $("#btnSigResume");
  const stop = $("#btnSigStop");
  const run = $("#btnSigRun");
  if (run) run.disabled = running;
  if (pause) {
    pause.disabled = !running || paused;
    pause.hidden = paused;
  }
  if (resume) {
    resume.disabled = !running || !paused;
    resume.hidden = !paused;
  }
  if (stop) stop.disabled = !running;
}

function renderSigRunLog(lines) {
  const pre = $("#sigRunLog");
  if (!pre) return;
  const arr = Array.isArray(lines) ? lines : [];
  if (!arr.length) {
    pre.hidden = true;
    pre.textContent = "";
    return;
  }
  pre.hidden = false;
  pre.textContent = arr.join("\n");
  pre.scrollTop = pre.scrollHeight;
}

async function signalsControl(action) {
  if (!_sigActiveJobId) {
    toast("没有进行中的任务", "error");
    return;
  }
  try {
    const data = await api("/api/signals/control", {
      method: "POST",
      body: JSON.stringify({ job_id: _sigActiveJobId, action }),
    });
    if (!data.success) {
      toast(data.error || "操作失败", "error");
      return;
    }
    if (action === "pause") {
      setSigControlButtons({ running: true, paused: true });
      setStatus($("#sigStatus"), "已暂停");
    } else if (action === "resume") {
      setSigControlButtons({ running: true, paused: false });
      setStatus($("#sigStatus"), "已继续");
    } else if (action === "stop") {
      setStatus($("#sigStatus"), "正在终止…");
    }
  } catch (e) {
    toast(String(e), "error");
  }
}

async function runSignalsCrawl() {
  const btn = $("#btnSigRun");
  if (btn) btn.disabled = true;
  setStatus($("#sigStatus"), "提交任务…");
  renderSigRunLog([]);
  setSigControlButtons({ running: false, paused: false });
  try {
    await saveSignalsConfig();
    const start = await api("/api/signals/run", {
      method: "POST",
      body: JSON.stringify({
        list_url: $("#sigListUrl")?.value.trim() || "",
        cutoff_hours: Number($("#sigCutoffHours")?.value || 24),
        max_tweets: Number($("#sigMaxTweets")?.value || 40),
        ignore_windows: !!$("#sigIgnoreWindows")?.checked,
      }),
    });
    if (!start.success || !start.job_id) {
      setStatus($("#sigStatus"), start.error || "启动失败", "error");
      return;
    }
    const jobId = start.job_id;
    _sigActiveJobId = jobId;
    setSigControlButtons({ running: true, paused: false });
    for (;;) {
      await new Promise((r) => setTimeout(r, 1200));
      const data = await api(`/api/jobs/${jobId}`);
      const job = data.job || {};
      renderSigRunLog(job.logs || []);
      const paused = job.status === "paused" || job.control_status === "paused";
      setSigControlButtons({
        running: !["done", "error", "cancelled"].includes(job.status),
        paused,
      });
      setStatus(
        $("#sigStatus"),
        paused ? `已暂停 · ${job.message || ""}` : job.message || job.status || "运行中…"
      );
      if (["done", "error", "cancelled"].includes(job.status)) {
        const result = job.result || {};
        const ok = job.status === "done" || job.status === "cancelled";
        setStatus(
          $("#sigStatus"),
          result.message || job.message || (job.status === "cancelled" ? "已终止" : "完成"),
          ok ? "ok" : "error"
        );
        if (ok) {
          toast(
            job.status === "cancelled"
              ? result.message || "已终止"
              : result.message || "列表信号已更新",
            "ok"
          );
          await loadSignalsPanel();
        }
        break;
      }
    }
  } catch (e) {
    setStatus($("#sigStatus"), String(e), "error");
  } finally {
    _sigActiveJobId = "";
    setSigControlButtons({ running: false, paused: false });
    if (btn) btn.disabled = false;
  }
}

function formatDateFullCST(d) {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(d);
  const g = (type) => parts.find((p) => p.type === type)?.value || "00";
  return `${g("year")}-${g("month")}-${g("day")} ${g("hour")}:${g("minute")}:${g("second")} +08:00`;
}

function sigCardTimeMs(c) {
  const raw = c.created_at || c.parsed_at || c.display_time || c.time_label || "";
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? 0 : d.getTime();
}

function stripSigTimePrefix(text) {
  return String(text || "").replace(/^\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*/, "").trim();
}

function formatSigCardTime(c) {
  const disp = String(c.display_time || "").trim();
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(disp)) {
    return disp.replace(/ \+\d{4}$/, "").slice(0, 19);
  }
  const raw = c.created_at || c.parsed_at || c.time_label || "";
  if (raw && raw !== "未知") {
    const d = new Date(raw);
    if (!Number.isNaN(d.getTime())) {
      return formatDateFullCST(d).replace(/ \+08:00$/, "");
    }
    return String(raw);
  }
  return formatDateFullCST(new Date()).replace(/ \+08:00$/, "");
}

let _sigCardsCache = [];
const SIG_CARDS_PAGE_SIZE = 20;
let _sigCardsPage = 1;

function renderSigCardItem(c) {
  const isValue = state.sigMode === "value" || c.source_mode === "value_return";
  const sig = c.signal || {};
  const trade = isSigTradeSignal(sig);
  const dirKey = normalizeSigDirectionKey(sig.direction) || "unknown";
  const dir = sigDirectionLabel(sig.direction);
  const coins = (sig.coins || [])
    .map((x) => `<span class="sig-coin">${escapeHtml(String(x))}</span>`)
    .join("");
  const levels = [];
  if ((sig.entries || []).length) {
    levels.push(`<div><b>入场</b>${escapeHtml((sig.entries || []).join(" / "))}</div>`);
  }
  if ((sig.take_profits || []).length) {
    levels.push(`<div><b>止盈</b>${escapeHtml((sig.take_profits || []).join(" / "))}</div>`);
  }
  if (sig.stop_loss) {
    levels.push(`<div><b>止损</b>${escapeHtml(String(sig.stop_loss))}</div>`);
  }
  if (sig.leverage) {
    levels.push(`<div><b>杠杆</b>${escapeHtml(String(sig.leverage))}</div>`);
  }
  if (sig.timeframe) {
    levels.push(`<div><b>周期</b>${escapeHtml(String(sig.timeframe))}</div>`);
  }
  const imgs = (c.images || [])
    .map((im) => {
      const src = sigImgSrc(im);
      if (!src) return "";
      const href = normalizeSigImgUrl(im.url || "") || src;
      return `<a href="${escapeAttr(href)}" target="_blank" rel="noopener"><img src="${escapeAttr(src)}" alt="${escapeAttr(im.alt || "")}" loading="lazy" referrerpolicy="no-referrer" /></a>`;
    })
    .join("");
  const chMap = c.channel || {};
  const authorHandle = String(c.author || "").replace(/^@/, "");
  const authorLabel = chMap.channelName
    ? `${chMap.channelName} <span class="sig-handle">@${escapeHtml(authorHandle)}</span>`
    : escapeHtml(c.author || "");
  const channelMeta = chMap.channelId
    ? `<span class="sig-channel-id" title="Cards channelId">#${escapeHtml(String(chMap.channelId))}</span>`
    : "";
  const timeLabel = formatSigCardTime(c);
  const summaryText = stripSigTimePrefix(sig.summary || c.text || "");
  const sourceTag = sigSourceLabel(c);
  const tid = escapeAttr(String(c.tweet_id || ""));
  const ev = c.value_eval && typeof c.value_eval === "object" ? c.value_eval : {};
  const score =
    c.value_score != null ? Number(c.value_score) : ev.score != null ? Number(ev.score) : null;
  const rec = !!(c.value_recommended || ev.is_recommended);
  const takeaways = Array.isArray(c.key_takeaways)
    ? c.key_takeaways
    : Array.isArray(ev.key_takeaways)
      ? ev.key_takeaways
      : [];
  const scoreBadge =
    score != null && !Number.isNaN(score)
      ? `<span class="sig-value-score${rec ? " is-rec" : ""}">${score.toFixed(1)}${rec ? " 荐" : ""}</span>`
      : "";
  const valueMeta = isValue
    ? `<div class="sig-value-meta">
        ${ev.category ? `<span>${escapeHtml(String(ev.category))}</span>` : ""}
        ${ev.format ? `<span>${escapeHtml(String(ev.format))}</span>` : ""}
        ${ev.threshold != null ? `<span>门槛 ${escapeHtml(String(ev.threshold))}</span>` : ""}
        ${c.archived ? `<span>已归档</span>` : ""}
        ${c.expires_at && !c.archived ? `<span>过期 ${escapeHtml(String(c.expires_at).slice(0, 16))}</span>` : ""}
      </div>
      ${
        takeaways.length
          ? `<ul class="sig-value-takeaways">${takeaways
              .slice(0, 4)
              .map((t) => `<li>${escapeHtml(String(t))}</li>`)
              .join("")}</ul>`
          : ""
      }`
    : "";
  const topBadge = isValue
    ? scoreBadge
    : `<span class="sig-dir ${escapeAttr(dirKey)}">${escapeHtml(dir)}</span>${coins}`;
  const footConf = isValue
    ? `${rec ? "推荐" : "未达门槛"} · 得分 ${score != null ? score.toFixed(2) : "-"}${
        ev.provider ? ` · ${escapeHtml(String(ev.provider))}` : ""
      }${sourceTag ? ` · ${escapeHtml(sourceTag)}` : ""}${c.archived ? " · 归档" : ""}`
    : `${trade ? "信号" : "非交易"} · 置信度 ${escapeHtml(String(sig.confidence ?? ""))} · ${escapeHtml(
        sig.provider === "heuristic" ? "规则解析" : "AI 解析"
      )}${sourceTag ? ` · ${escapeHtml(sourceTag)}` : ""}${c.cache_only ? " · 缓存" : ""}`;

  return `<article class="sig-card${isValue ? (rec ? " is-value-rec" : " is-value") : trade ? " is-trade" : " is-noise"}" data-tweet-id="${tid}" data-dedup-key="${escapeAttr(sigCardDedupKey(c))}">
    <div class="sig-card-top">
      ${topBadge}
      <span class="sig-author">${authorLabel}</span>
      ${channelMeta}
      <span class="sig-time" title="发帖时间">${escapeHtml(timeLabel)}</span>
    </div>
    <p class="sig-summary">${escapeHtml(summaryText).slice(0, 240)}</p>
    ${valueMeta}
    ${!isValue && levels.length ? `<div class="sig-levels">${levels.join("")}</div>` : ""}
    ${!isValue && sig.image_notes ? `<p class="muted" style="margin:0;font-size:.74rem">图注：${escapeHtml(String(sig.image_notes).slice(0, 160))}</p>` : ""}
    ${imgs ? `<div class="sig-imgs">${imgs}</div>` : ""}
    <pre class="sig-text">${escapeHtml(stripSigTimePrefix(c.text || ""))}</pre>
    <div class="sig-card-foot">
      <a href="${escapeAttr(c.url || "#")}" target="_blank" rel="noopener">原帖</a>
      ${tid && !isValue ? `<button type="button" class="btn-link" data-sig-edit="${tid}">编辑</button>` : ""}
      ${tid && isValue && !c.archived ? `<button type="button" class="btn-link" data-sig-value-archive="${tid}">归档</button>` : ""}
      <span class="sig-conf">${footConf}</span>
    </div>
  </article>`;
}

function sigCardsTotalPages(total = _sigCardsCache.length) {
  return Math.max(1, Math.ceil(total / SIG_CARDS_PAGE_SIZE));
}

function goSigCardsPage(page) {
  const pages = sigCardsTotalPages();
  const p = Math.max(1, Math.min(pages, parseInt(String(page), 10) || 1));
  if (p === _sigCardsPage) return;
  _sigCardsPage = p;
  renderSigCardsView();
}

function renderSigCardsPager(total, page) {
  const pager = $("#sigCardsPager");
  if (!pager) return;
  const pages = sigCardsTotalPages(total);
  if (total <= SIG_CARDS_PAGE_SIZE) {
    pager.hidden = true;
    pager.innerHTML = "";
    return;
  }
  pager.hidden = false;
  pager.innerHTML = `
    <button type="button" class="btn ghost" id="btnSigCardsPrev"${page <= 1 ? " disabled" : ""}>上一页</button>
    <label class="sig-cards-pager-jump">
      第
      <input type="number" id="sigCardsPageInput" class="sig-cards-pager-input" min="1" max="${pages}" value="${page}" aria-label="页码">
      / ${pages} 页
    </label>
    <span class="sig-cards-pager-meta">共 ${total} 条 · 每页 ${SIG_CARDS_PAGE_SIZE} 条</span>
    <button type="button" class="btn ghost" id="btnSigCardsNext"${page >= pages ? " disabled" : ""}>下一页</button>
  `;
}

function renderSigCardsView() {
  const box = $("#sigCards");
  if (!box) return;
  const items = _sigCardsCache;
  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / SIG_CARDS_PAGE_SIZE));
  if (_sigCardsPage > pages) _sigCardsPage = pages;
  if (_sigCardsPage < 1) _sigCardsPage = 1;
  const badge = $("#countSignals");
  if (badge) badge.textContent = String(total);
  if (!total) {
    box.innerHTML = `<p class="muted">暂无卡片。确认 Chrome 已开调试口并登录 X 后，点「开始抓取解析」。</p>`;
    renderSigCardsPager(0, 1);
    return;
  }
  const start = (_sigCardsPage - 1) * SIG_CARDS_PAGE_SIZE;
  const slice = items.slice(start, start + SIG_CARDS_PAGE_SIZE);
  box.innerHTML = slice.map((c) => renderSigCardItem(c)).join("");
  renderSigCardsPager(total, _sigCardsPage);
  applySigKolVisibility();
}

function openSigCardEdit(tweetId) {
  const tid = String(tweetId || "").trim();
  const card = _sigCardsCache.find((c) => String(c.tweet_id || "") === tid);
  if (!card) {
    toast("未找到卡片", "error");
    return;
  }
  const dlg = $("#sigCardEditDialog");
  if (!dlg) return;
  $("#sigEditTweetId").value = tid;
  $("#sigEditText").value = stripSigTimePrefix(card.text || "");
  $("#sigEditSupplement").value = "";
  setStatus($("#sigEditStatus"), "");
  dlg.showModal();
}

async function saveSigCardEdit(e) {
  e.preventDefault();
  const tid = $("#sigEditTweetId")?.value.trim() || "";
  const text = $("#sigEditText")?.value ?? "";
  const supplement = $("#sigEditSupplement")?.value ?? "";
  if (!tid) return;
  const btn = $("#btnSigEditSave");
  if (btn) btn.disabled = true;
  setStatus($("#sigEditStatus"), "重新 AI 解析中…");
  try {
    const data = await api("/api/signals/cards/reparse", {
      method: "POST",
      body: JSON.stringify({ tweet_id: tid, text, supplement }),
    });
    if (!data.success) {
      setStatus($("#sigEditStatus"), data.error || "解析失败", "error");
      return;
    }
    const sig = data.signal || {};
    const trade = isSigTradeSignal(sig);
    const msg = trade
      ? `已更新为交易信号 · ${(sig.coins || []).join("/") || "?"} · ${sigDirectionLabel(sig.direction)}`
      : "已更新（当前判定为非交易信号）";
    setStatus($("#sigEditStatus"), msg, trade ? "ok" : "");
    toast(msg, trade ? "ok" : "info");
    $("#sigCardEditDialog")?.close();
    await loadSignalCards();
  } catch (err) {
    setStatus($("#sigEditStatus"), String(err), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadSignalCards() {
  const box = $("#sigCards");
  if (!box) return;
  const onlyTrade = !!$("#sigFilterTrade")?.checked;
  const filter = collectSigCardsFilter();
  const valueMode = state.sigMode === "value";
  let url = `/api/signals/cards?limit=500&merge=${valueMode ? "0" : "1"}`;
  if (valueMode) {
    url += "&source=value_return";
    if ($("#sigValueRecommendedOnly")?.checked) url += "&recommended=1";
  } else if (onlyTrade) {
    url += "&trade=1";
  }
  if (filter.handle) {
    url += `&handle=${encodeURIComponent(filter.handle)}`;
  }
  if (filter.range === "custom") {
    if (filter.from) url += `&from=${encodeURIComponent(filter.from)}`;
    if (filter.to) url += `&to=${encodeURIComponent(filter.to)}`;
  } else if (filter.range) {
    url += `&range=${encodeURIComponent(filter.range)}`;
  }
  try {
    const data = await api(url);
    renderSigWindows(data.windows || []);
    if ((data.channels?.mappings || []).length) {
      const curOpts = $("#sigFilterName")?.options?.length || 0;
      if (curOpts <= 1) {
        fillSigFilterNameOptions(
          (data.channels.mappings || []).map((m) => ({
            id: m.handle,
            name: m.channelName || m.handle,
          }))
        );
      }
    }
    const cfg = data.config || {};
    if ($("#sigValueListUrl")) {
      $("#sigValueListUrl").value = cfg.list_url || (cfg.list_id ? `https://x.com/i/lists/${cfg.list_id}` : $("#sigListUrl")?.value || "");
    }
    if (cfg.value_cutoff_hours && $("#sigValueCutoffHours")) {
      $("#sigValueCutoffHours").value = cfg.value_cutoff_hours;
    }
    if (cfg.value_max_tweets && $("#sigValueMaxTweets")) {
      $("#sigValueMaxTweets").value = cfg.value_max_tweets;
    }
    _sigCardsCache = dedupSigCards(data.items || []);
    _sigCardsPage = 1;
    renderSigCardsView();
  } catch (e) {
    box.innerHTML = `<p class="muted">加载失败：${escapeHtml(String(e))}</p>`;
    renderSigCardsPager(0, 1);
  }
}

async function runValueReturnCrawl() {
  const btn = $("#btnSigValueRun");
  const logEl = $("#sigValueRunLog");
  if (btn) btn.disabled = true;
  setStatus($("#sigValueStatus"), "提交价值评估…");
  if (logEl) {
    logEl.hidden = false;
    logEl.textContent = "";
  }
  setSigValueControlButtons({ running: false, paused: false });
  try {
    const listUrl = $("#sigListUrl")?.value.trim() || $("#sigValueListUrl")?.value.trim() || "";
    const start = await api("/api/signals/value/run", {
      method: "POST",
      body: JSON.stringify({
        list_url: listUrl,
        cutoff_hours: Number($("#sigValueCutoffHours")?.value || 24),
        max_tweets: Number($("#sigValueMaxTweets")?.value || 40),
        reparse: !!$("#sigValueReparse")?.checked,
      }),
    });
    if (!start.success || !start.job_id) {
      setStatus($("#sigValueStatus"), start.error || "启动失败", "error");
      return;
    }
    const jobId = start.job_id;
    _sigActiveJobId = jobId;
    setSigValueControlButtons({ running: true, paused: false });
    for (;;) {
      await new Promise((r) => setTimeout(r, 1200));
      const data = await api(`/api/jobs/${jobId}`);
      const job = data.job || {};
      if (logEl) {
        logEl.hidden = false;
        logEl.textContent = (job.logs || []).slice(-80).join("\n");
        logEl.scrollTop = logEl.scrollHeight;
      }
      const paused = job.status === "paused" || job.control_status === "paused";
      setSigValueControlButtons({
        running: !["done", "error", "cancelled"].includes(job.status),
        paused,
      });
      setStatus(
        $("#sigValueStatus"),
        paused ? `已暂停 · ${job.message || ""}` : job.message || job.status || "运行中…"
      );
      if (["done", "error", "cancelled"].includes(job.status)) {
        const result = job.result || {};
        const ok = job.status === "done" || job.status === "cancelled";
        const msg =
          result.message ||
          job.message ||
          (job.status === "cancelled" ? "已终止" : "完成");
        setStatus($("#sigValueStatus"), msg, ok ? "ok" : "error");
        if (ok) {
          toast(msg, "ok");
          await loadSignalCards();
        }
        break;
      }
    }
  } catch (e) {
    setStatus($("#sigValueStatus"), String(e), "error");
  } finally {
    _sigActiveJobId = "";
    setSigValueControlButtons({ running: false, paused: false });
    if (btn) btn.disabled = false;
  }
}

function setSigValueControlButtons({ running = false, paused = false } = {}) {
  const pause = $("#btnSigValuePause");
  const resume = $("#btnSigValueResume");
  const stop = $("#btnSigValueStop");
  const run = $("#btnSigValueRun");
  if (run) run.disabled = running;
  if (pause) {
    pause.disabled = !running || paused;
    pause.hidden = paused;
  }
  if (resume) {
    resume.disabled = !running || !paused;
    resume.hidden = !paused;
  }
  if (stop) stop.disabled = !running;
}

async function archiveSigValueCard(tweetId) {
  const tid = String(tweetId || "").trim();
  if (!tid) return;
  const data = await api("/api/signals/value/archive", {
    method: "POST",
    body: JSON.stringify({ tweet_id: tid }),
  });
  if (!data.success) {
    toast(data.error || "归档失败", "error");
    return;
  }
  toast("已归档", "ok");
  await loadSignalCards();
}

const SIG_CARDS_FILTER_LS = "sigCardsFilterPrefs";

function readSigCardsFilterLocal() {
  try {
    const raw = localStorage.getItem(SIG_CARDS_FILTER_LS);
    return raw ? JSON.parse(raw) : {};
  } catch (_) {
    return {};
  }
}

function persistSigCardsFilter() {
  try {
    localStorage.setItem(SIG_CARDS_FILTER_LS, JSON.stringify(collectSigCardsFilter()));
  } catch (_) {
    /* ignore */
  }
}

function collectSigCardsFilter() {
  const range = String($("#sigFilterRange")?.value || "").trim();
  let from = String($("#sigFilterFrom")?.value || "").trim();
  let to = String($("#sigFilterTo")?.value || "").trim();
  // datetime-local → 按北京时间交给后端
  if (from && !from.includes("T")) from = from.replace(" ", "T");
  if (to && !to.includes("T")) to = to.replace(" ", "T");
  if (from && from.length === 16) from = `${from}:00`;
  if (to && to.length === 16) to = `${to}:00`;
  if (from && !/[zZ]|[+-]\d{2}:\d{2}$/.test(from)) from = `${from}+08:00`;
  if (to && !/[zZ]|[+-]\d{2}:\d{2}$/.test(to)) to = `${to}+08:00`;
  return {
    handle: String($("#sigFilterName")?.value || "").trim().toLowerCase(),
    range,
    from: range === "custom" ? from : "",
    to: range === "custom" ? to : "",
  };
}

function syncSigFilterCustomVisibility() {
  const custom = $("#sigFilterRange")?.value === "custom";
  const fromWrap = $("#sigFilterFromWrap");
  const toWrap = $("#sigFilterToWrap");
  if (fromWrap) fromWrap.hidden = !custom;
  if (toWrap) toWrap.hidden = !custom;
}

function fillSigFilterNameOptions(items) {
  const sel = $("#sigFilterName");
  if (!sel) return;
  const prev = sel.value;
  const local = readSigCardsFilterLocal();
  const preferred = prev || local.handle || "";
  const rows = Array.isArray(items) ? items : [];
  const seen = new Set();
  const opts = [`<option value="">全部</option>`];
  for (const b of rows) {
    const id = String(b.id || b.handle || "").toLowerCase();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const name = String(b.name || b.channelName || id);
    opts.push(
      `<option value="${escapeAttr(id)}">${escapeHtml(name)} (@${escapeHtml(id)})</option>`
    );
  }
  sel.innerHTML = opts.join("");
  if (preferred && [...sel.options].some((o) => o.value === preferred)) {
    sel.value = preferred;
  }
}

function restoreSigCardsFilter() {
  const local = readSigCardsFilterLocal();
  if ($("#sigFilterRange") && local.range != null) {
    $("#sigFilterRange").value = String(local.range || "");
  }
  if ($("#sigFilterFrom") && local.from) {
    $("#sigFilterFrom").value = String(local.from).slice(0, 16);
  }
  if ($("#sigFilterTo") && local.to) {
    $("#sigFilterTo").value = String(local.to).slice(0, 16);
  }
  syncSigFilterCustomVisibility();
}

function resetSigCardsFilter() {
  if ($("#sigFilterName")) $("#sigFilterName").value = "";
  if ($("#sigFilterRange")) $("#sigFilterRange").value = "";
  if ($("#sigFilterFrom")) $("#sigFilterFrom").value = "";
  if ($("#sigFilterTo")) $("#sigFilterTo").value = "";
  syncSigFilterCustomVisibility();
  persistSigCardsFilter();
  loadSignalCards();
}

function fmtCount(n) {
  const v = Number(n || 0);
  if (!Number.isFinite(v) || v <= 0) return "0";
  if (v >= 1e6) return (v / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  return String(Math.round(v));
}

function isTcPrivacyOn() {
  return !!$("#tcHideSensitive")?.checked || localStorage.getItem("tcHideSensitive") === "1";
}

function tcAuthorView(c) {
  if (!isTcPrivacyOn()) {
    return {
      name: c.author_name || c.author_handle || "未知",
      handle: c.author_handle ? `@${c.author_handle}` : "",
      avatar: c.author_avatar || "",
    };
  }
  return {
    name: "已隐藏用户",
    handle: "@••••••",
    avatar: "",
  };
}

async function loadTweetCards() {
  const box = $("#tcCards");
  if (!box) return;
  const privacy = isTcPrivacyOn();
  box.classList.toggle("tc-privacy-on", privacy);
  const kw = $("#tcKeyword")?.value.trim() || "";
  try {
    const data = await api(
      `/api/tweet-cards?limit=60${kw ? `&keyword=${encodeURIComponent(kw)}` : ""}`
    );
    const items = data.items || [];
    const badge = $("#countTweetCards");
    if (badge) badge.textContent = String((data.stats && data.stats.total) || items.length);
    if (!items.length) {
      box.innerHTML = `<p class="muted">暂无卡片。粘贴推特链接后点「解析入库」。</p>`;
      return;
    }
    box.innerHTML = items
      .map((c) => {
        const author = tcAuthorView(c);
        const avatar = author.avatar
          ? `<img class="tc-avatar" src="${escapeAttr(author.avatar)}" alt="" loading="lazy" />`
          : `<div class="tc-avatar" aria-hidden="true"></div>`;
        const tags = [
          c.emotion ? `<span class="tc-tag emo">${escapeHtml(c.emotion)}</span>` : "",
          c.category ? `<span class="tc-tag cat">${escapeHtml(c.category)}</span>` : "",
          ...(c.tags || []).map((t) => `<span class="tc-tag">#${escapeHtml(String(t))}</span>`),
        ].join("");
        const points = (c.core_points || [])
          .map((p) => `<li>${escapeHtml(String(p))}</li>`)
          .join("");
        const imgs = (c.images || [])
          .map(
            (u) =>
              `<a href="${escapeAttr(u)}" target="_blank" rel="noopener"><img src="${escapeAttr(u)}" alt="" loading="lazy" /></a>`
          )
          .join("");
        const tid = String(c.tweet_id || "");
        return `<article class="tc-card"${privacy ? "" : ` data-tid="${escapeAttr(tid)}"`}>
          <div class="tc-head">
            ${avatar}
            <div class="tc-author">
              <strong>${escapeHtml(author.name)}</strong>
              <span>${escapeHtml(author.handle)}</span>
            </div>
          </div>
          <p class="tc-summary">${escapeHtml(c.summary || (c.text || "").slice(0, 60))}</p>
          ${points ? `<ul class="tc-points">${points}</ul>` : ""}
          <div class="tc-tags">${tags}</div>
          <div class="tc-metrics">
            <span>赞 <b>${fmtCount(c.likes)}</b></span>
            <span>评 <b>${fmtCount(c.replies)}</b></span>
            <span>转 <b>${fmtCount(c.retweets)}</b></span>
            <span>藏 <b>${fmtCount(c.bookmarks)}</b></span>
            <span>浏 <b>${fmtCount(c.views)}</b></span>
          </div>
          ${imgs ? `<div class="tc-imgs">${imgs}</div>` : ""}
          <pre class="tc-body">${escapeHtml(c.text || "")}</pre>
          <div class="tc-foot">
            ${privacy ? `<span class="muted">原帖链接已隐藏</span>` : `<a href="${escapeAttr(c.url || "#")}" target="_blank" rel="noopener">打开原帖</a>`}
            <button type="button" class="btn ghost xs" data-tc-del="${escapeAttr(tid)}">删除</button>
            <span class="muted">${escapeHtml(String(c.source || ""))} · ${escapeHtml(String(c.updated_at || "").slice(0, 16))}</span>
          </div>
        </article>`;
      })
      .join("");
    box.querySelectorAll("[data-tc-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const tid = btn.getAttribute("data-tc-del");
        if (!tid || !confirm(privacy ? "删除这条卡片？" : `删除卡片 ${tid}？`)) return;
        try {
          await api(`/api/tweet-cards/${encodeURIComponent(tid)}`, { method: "DELETE" });
          toast("已删除", "ok");
          await loadTweetCards();
        } catch (e) {
          toast(String(e), "error");
        }
      });
    });
  } catch (e) {
    box.innerHTML = `<p class="muted">加载失败：${escapeHtml(String(e))}</p>`;
  }
}

async function runTweetCardIngest() {
  const raw = $("#tcInput")?.value.trim() || "";
  if (!raw) {
    toast("请先粘贴推特链接", "error");
    return;
  }
  const btn = $("#btnTcIngest");
  if (btn) btn.disabled = true;
  setStatus($("#tcStatus"), "提交解析…");
  try {
    const start = await api("/api/tweet-cards/ingest", {
      method: "POST",
      body: JSON.stringify({ text: raw }),
    });
    if (!start.success || !start.job_id) {
      setStatus($("#tcStatus"), start.error || "启动失败", "error");
      return;
    }
    const jobId = start.job_id;
    for (;;) {
      await new Promise((r) => setTimeout(r, 1200));
      const data = await api(`/api/jobs/${jobId}`);
      const job = data.job || {};
      setStatus($("#tcStatus"), job.message || job.status || "运行中…");
      if (job.status === "done" || job.status === "error") {
        const result = job.result || {};
        setStatus(
          $("#tcStatus"),
          job.status === "done"
            ? result.message || job.message || "完成"
            : job.message || "失败",
          job.status === "done" ? "ok" : "error"
        );
        if (job.status === "done") {
          toast(result.message || "已入库", "ok");
          if ($("#tcInput")) $("#tcInput").value = "";
          await loadTweetCards();
        }
        break;
      }
    }
  } catch (e) {
    setStatus($("#tcStatus"), String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function boot() {
  bind();
  restoreMainTabFromStorage();
  initPublishScheduleDefault();
  restorePublishPrefsFields();
  await refreshHealth();
  const savedPlatforms = loadPublishPrefs().platforms;
  await loadPublishPlatforms(savedPlatforms?.length ? savedPlatforms : undefined);
  await loadPublishQueue();
  await loadPublishCache();
  await refreshCorpusStats();
  // 默认进入列表信号（若 localStorage 无有效 tab）
  if (!$(".tab.active")) switchTab("signals");
  else if ($("#panel-signals")?.classList.contains("active")) loadSignalsPanel();
  setInterval(refreshHealth, 15000);
  setInterval(loadPublishQueue, 20000);
  setInterval(refreshCorpusStats, 45000);
  setInterval(() => {
    const panel = $("#panel-signals");
    if (panel && !panel.hidden) loadSignalsPanel();
  }, 30000);
  setInterval(() => {
    const panel = $("#panel-realtime");
    if (panel && !panel.hidden) loadRealtimePanel();
  }, 45000);
}

boot();
