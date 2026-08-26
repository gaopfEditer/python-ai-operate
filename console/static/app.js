const $ = (sel) => document.querySelector(sel);

const state = {
  lastCreate: { title: "", content: "", path: "" },
  listTarget: "news",
  knownTags: [],
  counts: { all: 0, active: 0, archived: 0, watch_later: 0, tagged: 0 },
  platforms: [],
  newsPlatform: "",
  historyPlatform: "",
  taskStatus: "all",
  corpusSelected: new Set(),
  corpusItems: [],
  labFormula: "contrarian",
  labProfile: localStorage.getItem("labProfile") || "general",
  labMaterialCategory: localStorage.getItem("labMaterialCategory") || "all",
  labMaterialCategories: [],
  labCategoryTemplates: [],
  labTagFilter: "",
  labVariants: [],
  labActiveVariant: null,
  labConfigActiveTab: "general",
  labConfigProfiles: [],
  sigMode: "list",
};

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
  setCount("#countLater", state.counts.watch_later);
  setCount("#countArchived", state.counts.archived);
  setCount("#countTagged", state.counts.tagged);
  if (state.counts.corpus != null) setCount("#countCorpus", state.counts.corpus);
  refreshTagDatalist();
  renderTagCloud();
  renderPlatformBar("#newsPlatformBar", state.platforms, state.newsPlatform, (pid) => {
    state.newsPlatform = pid;
    loadPosts(
      $("#newsKeyword").value.trim(),
      pid,
      "news",
      $("#newsView")?.value || "active",
      ""
    );
  });
  renderPlatformBar("#historyPlatformBar", state.platforms, state.historyPlatform, (pid) => {
    state.historyPlatform = pid;
    if ($("#historyPlatform")) $("#historyPlatform").value = pid;
    loadPosts(
      $("#historyKeyword").value.trim(),
      pid || $("#historyPlatform").value.trim(),
      "history",
      $("#historyView")?.value || "all",
      $("#historyTag")?.value.trim() || ""
    );
  });
}

function refreshTagDatalist() {
  let dl = $("#knownTagsList");
  if (!dl) {
    dl = document.createElement("datalist");
    dl.id = "knownTagsList";
    document.body.appendChild(dl);
  }
  dl.innerHTML = (state.knownTags || [])
    .map((t) => `<option value="${escapeAttr(t.name || t)}"></option>`)
    .join("");
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
  if (["news", "history", "later", "archived", "tags"].includes(name)) {
    state.listTarget = name;
  }
  if (name === "later") loadLibrary("later");
  if (name === "archived") loadLibrary("archived");
  if (name === "tags") loadLibrary("tags");
  if (name === "corpus") {
    loadLabMaterials().then(() => {
      applyLabProfileMaterialFilter({ reload: false });
      renderLabMaterialTabs();
    });
    loadLabFormulas();
    loadCorpus();
    loadGenerations();
  }
  if (name === "signals") { loadSignalsPanel(); }
  if (name === "tweetcards") { loadTweetCards(); }
  if (name === "publish") {
    loadPublishPlatforms(loadPublishPrefs().platforms || undefined);
    restorePublishPrefsFields();
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
  try {
    const data = await api("/api/posts/stats");
    if (data.success) updateCounts(data.counts, data.tags, data.platforms);
  } catch (e) {
    /* ignore */
  }
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
      loadCorpus();
    });
  });
}

function renderPathView(pathObj) {
  const el = $("#corpusPathView");
  if (!el) return;
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
    renderLabMaterialTabs();
  } catch (_) {
    state.labMaterialCategories = [];
    renderLabMaterialTabs();
  }
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
      syncLabProfileHint();
      loadCorpus();
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
      limit: "8",
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
      const hook = it.hooks || it.factors?.hook || it.pattern || it.source_title || "";
      return `<div class="lab-category-template-item"><strong>#${escapeHtml(String(it.id))}</strong> · ${escapeHtml(String(hook).slice(0, 100))}</div>`;
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
  box.innerHTML = `<div class="lab-skel${loading ? " is-loading" : ""}" aria-hidden="true">
    <div class="lab-skel-card"><div class="sk-line w40"></div><div class="sk-line"></div><div class="sk-line"></div><div class="sk-line w70"></div></div>
    <div class="lab-skel-card"><div class="sk-line w40"></div><div class="sk-line"></div><div class="sk-line"></div><div class="sk-line w70"></div></div>
    <div class="lab-skel-card"><div class="sk-line w40"></div><div class="sk-line"></div><div class="sk-line"></div><div class="sk-line w70"></div></div>
  </div>`;
  if ($("#labResultBar")) $("#labResultBar").hidden = true;
  if ($("#labTweaks")) $("#labTweaks").hidden = true;
}

function renderLabVariants(variants, activeIdx) {
  const box = $("#labVariants");
  if (!box) return;
  if (!variants || !variants.length) {
    showLabSkeleton(false);
    return;
  }
  state.labVariants = variants;
  const idx = activeIdx == null ? 0 : activeIdx;
  state.labActiveVariant = variants[idx];
  box.innerHTML = variants
    .map((v, i) => {
      const on = i === idx ? " on" : "";
      const starred = v.featured ? " starred" : "";
      return `<article class="lab-variant${on}${starred}" data-vidx="${i}">
        <header>
          <span class="lab-vid">${escapeHtml(v.id || String.fromCharCode(65 + i))}</span>
          <strong>${escapeHtml(v.label || "变体")}</strong>
          <button type="button" class="lab-vstar" data-feature-idx="${i}" title="精选留存完整正文与要素">★</button>
        </header>
        <p class="lab-vhook">${escapeHtml(v.hook || "")}</p>
        <pre class="lab-vbody">${escapeHtml(v.content || "")}</pre>
      </article>`;
    })
    .join("");
  box.querySelectorAll(".lab-variant").forEach((el) => {
    el.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-feature-idx]")) return;
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
  if ($("#labResultBar")) $("#labResultBar").hidden = false;
  if ($("#labTweaks")) $("#labTweaks").hidden = false;
  const active = state.labActiveVariant;
  const draft = labBuildPublishDraft(active);
  state.lastCreate = {
    title: draft?.title || $("#regenTopic")?.value.trim() || "Post Lab",
    content: draft?.content || active?.content || "",
    path: "",
  };
  const out = $("#corpusRegenOut");
  if (out) out.textContent = active?.content || "";
  if (typeof updateLabSteps === "function") updateLabSteps();
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
    renderLabPromptSnippets(data.prompt_snippets || []);
    renderLabVariants(data.variants || [], 0);
    renderPathView(data.path || {});
    setStatus(
      $("#corpusRegenStatus"),
      `完成 · ${data.provider || "ai"} · ${(data.variants || []).length} 个变体`,
      "ok"
    );
    await loadGenerations();
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
  const topic = $("#regenTopic")?.value.trim() || "Post Lab";
  const label = v.label || v.id || "变体";
  const title = label.includes(topic) ? label : `${topic} · ${label}`;
  const style = $("#regenStyle")?.value.trim() || "X/Twitter";
  const prof =
    LAB_PROFILES_FALLBACK.find((x) => x.id === state.labProfile) || LAB_PROFILES_FALLBACK[0];
  const tags = [topic, prof?.label].filter(Boolean).join(", ");
  return {
    title,
    content: v.content,
    hook: v.hook || "",
    label,
    tags,
    style,
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
        media_paths: [],
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
  await loadPublishPlatforms();
  applyPublishPlatformHint(labPlatformHintFromStyle(d.style));
  switchTab("publish");
  $("#publishContent")?.focus();
  toast("已带入 CDP 发布页", "ok");
  state.labPublishDraft = null;
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
  if (!content && !media_files.length) {
    throw new Error("请填写正文或上传图片");
  }
  const dry = !!$("#publishDryRun")?.checked;
  const base = {
    title: "",
    content,
    tags: "",
    media_paths: [],
    use_cdp: true,
    debugger_url: $("#debuggerUrl")?.value.trim() || "127.0.0.1:9222",
    submit: !dry,
  };
  const stepResults = [];
  let stagedMediaPaths = [];
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

async function collectPublishDraft({ requireSchedule = false } = {}) {
  const media_files = await collectUploadMediaFiles();
  const draft = {
    title: "",
    content: $("#publishContent")?.value.trim() || "",
    tags: "",
    platforms: selectedPublishPlatforms(),
    media_paths: [],
    media_files,
    use_cdp: true,
    debugger_url: $("#debuggerUrl")?.value.trim() || "127.0.0.1:9222",
    scheduled_at: $("#publishScheduleAt")?.value || "",
  };
  if (!draft.platforms.length) {
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
  publishMediaItems = [];
  persistPublishMediaItems();
  const input = $("#publishMediaFiles");
  if (input) input.value = "";
  renderMediaPreview();
  resetPublishScheduleDefault();
  snapshotPublishPrefs();
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
      box.innerHTML = `<div class="item muted">队列为空。上传图文后可「保存到月度缓存」或「保存并加入定时队列」。</div>`;
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
                  ? `<button type="button" class="btn ghost btn-sm" data-q-act="run">立即发</button>
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
  setStatus($("#publishStatus"), enqueue ? "正在保存并加入队列…" : "正在保存到月度缓存…");
  try {
    const draft = await collectPublishDraft({ requireSchedule: enqueue });
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
        : `已缓存 ${it.id} · ${it.storage_rel || ""}`,
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
      box.innerHTML = `<div class="item muted">本月暂无缓存。上传图文后点「保存到月度缓存」。</div>`;
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

  $("#btnFilterNews").addEventListener("click", () => {
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
  $("#corpusQuality")?.addEventListener("change", () => loadCorpus());
  $("#corpusStatus")?.addEventListener("change", () => loadCorpus());
  $("#btnCorpusRegen")?.addEventListener("click", () => runCorpusRegen({ explicit: true }));
  $("#regenTopic")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      setStatus($("#corpusRegenStatus"), "请点击「生成 3 个变体」按钮", "error");
    }
  });
  $("#regenTopic")?.addEventListener("input", () => updateLabSteps());

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

  $("#btnCrawl").addEventListener("click", async () => {
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

  $("#btnLoadHistory").addEventListener("click", () => {
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
  $("#btnQueueRefresh")?.addEventListener("click", () => {
    loadPublishQueue();
    loadPublishCache();
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
    if (!btn) return;
    removePublishMediaFile(Number(btn.getAttribute("data-media-del")));
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
      if (act === "load") {
        const data = await api(`/api/publish/queue/${encodeURIComponent(id)}`);
        const it = data.item || {};
        $("#publishTitle").value = it.title || "";
        $("#publishContent").value = it.content || "";
        $("#publishMedia").value = (it.media_paths || []).join("\n");
        $("#publishTags").value = it.tags || "";
        if ($("#publishScheduleAt")) {
          $("#publishScheduleAt").value = toDatetimeLocalValue(it.scheduled_at);
        }
        applyPublishPlatformHint(it.platforms || []);
        setStatus($("#publishStatus"), `已载入 ${id} 到编辑区`, "ok");
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
      if (act === "run") {
        setStatus($("#publishStatus"), `正在立即发布 ${id}…`);
        const data = await api(`/api/publish/queue/${encodeURIComponent(id)}/run`, {
          method: "POST",
          body: "{}",
        });
        $("#publishResult").textContent = JSON.stringify(data, null, 2);
        setStatus(
          $("#publishStatus"),
          data.success ? `已发布 ${id}` : data.error || "发布失败",
          data.success ? "ok" : "error"
        );
        await loadPublishQueue();
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
  $("#btnSigPushOnly")?.addEventListener("click", () => pushSignalsOnly());
  $("#btnSigRefresh")?.addEventListener("click", () => loadSignalCards());
  $("#btnSigBacktest")?.addEventListener("click", () => startSigCardsBacktest());
  $("#btnSigBacktestResult")?.addEventListener("click", () => openSigBacktestResultDialog());
  loadSigBacktestLast();
  $("#sigFilterTrade")?.addEventListener("change", () => loadSignalCards());
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
  $("#btnSigUserRun")?.addEventListener("click", () => runUserSignalsCrawl());
  bindSigUserFormPersistence();
  $("#btnSigUserClearCache")?.addEventListener("click", () => clearSigUserCache());
  $("#btnSigUserPause")?.addEventListener("click", () => signalsControl("pause"));
  $("#btnSigUserResume")?.addEventListener("click", () => signalsControl("resume"));
  $("#btnSigUserStop")?.addEventListener("click", () => signalsControl("stop"));
  $("#btnSigUserValidate")?.addEventListener("click", () => startCardsValidate());
  $("#btnSigMockSample")?.addEventListener("click", () => loadMockValidateSample());
  $("#btnSigMockValidate")?.addEventListener("click", () => startMockCardsValidate());
  $("#btnSigCdpConfig")?.addEventListener("click", () => openSigCdpDialog());
  $("#sigCdpConfigForm")?.addEventListener("submit", (e) => {
    if (e.submitter?.value === "save") saveSigCdpConfig(e);
  });
  $("#sigCardEditForm")?.addEventListener("submit", (e) => {
    if (e.submitter?.value === "save") saveSigCardEdit(e);
  });
  $("#sigCards")?.addEventListener("click", (e) => {
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
    user_weeks: Math.max(1, Math.min(52, Number($("#sigUserWeeks")?.value || 1) || 1)),
    user_max_tweets: Math.max(10, Math.min(300, Number($("#sigUserMaxTweets")?.value || 50) || 50)),
    user_skip_non_trade: !!$("#sigUserSkipNonTrade")?.checked,
    user_reparse_seen: !!$("#sigUserReparse")?.checked,
    user_push_enabled: !!$("#sigUserPush")?.checked,
    user_force_push: !!$("#sigUserForcePush")?.checked,
  };
}

function applySigUserForm(cfg) {
  const local = readSigUserFormLocal();
  const pick = (key, fallback) => {
    const lv = local[key];
    if (lv !== undefined && lv !== null && lv !== "") return lv;
    const cv = cfg?.[key];
    if (cv !== undefined && cv !== null && cv !== "") return cv;
    return fallback;
  };
  if ($("#sigUserProfileUrl")) {
    $("#sigUserProfileUrl").value =
      pick("user_profile_url", "") || cfg?.user_profile_url || "";
  }
  if ($("#sigUserWeeks")) {
    $("#sigUserWeeks").value = String(pick("user_weeks", 1));
  }
  if ($("#sigUserMaxTweets")) {
    $("#sigUserMaxTweets").value = String(pick("user_max_tweets", 50));
  }
  if ($("#sigUserSkipNonTrade")) {
    const v = pick("user_skip_non_trade", cfg?.user_skip_non_trade ?? cfg?.skip_non_trade ?? true);
    $("#sigUserSkipNonTrade").checked = !!v;
  }
  if ($("#sigUserReparse")) {
    $("#sigUserReparse").checked = !!pick("user_reparse_seen", false);
  }
  if ($("#sigUserPush")) {
    const v = pick("user_push_enabled", cfg?.user_push_enabled ?? cfg?.push_enabled ?? true);
    $("#sigUserPush").checked = !!v;
  }
  if ($("#sigUserForcePush")) {
    $("#sigUserForcePush").checked = !!pick("user_force_push", false);
  }
  writeSigUserFormLocal(collectSigUserForm());
}

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
        body: JSON.stringify(body),
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
    "#sigUserWeeks",
    "#sigUserMaxTweets",
    "#sigUserSkipNonTrade",
    "#sigUserReparse",
    "#sigUserPush",
    "#sigUserForcePush",
  ];
  for (const sel of fields) {
    const el = $(sel);
    if (!el) continue;
    const evt = el.type === "checkbox" || el.type === "number" ? "change" : "input";
    el.addEventListener(evt, () => persistSigUserForm());
    if (el.type === "number" || el.tagName === "INPUT") {
      el.addEventListener("blur", () => persistSigUserForm({ immediate: true }));
    }
  }
}

async function loadSignalsPanel() {
  try {
    const data = await api("/api/signals/config");
    const cfg = data.config || {};
    if ($("#sigListUrl")) {
      $("#sigListUrl").value = cfg.list_url || `https://x.com/i/lists/${cfg.list_id || ""}`;
    }
    if ($("#sigCutoffHours") && cfg.cutoff_hours != null) {
      $("#sigCutoffHours").value = cfg.cutoff_hours;
    }
    if ($("#sigMaxTweets") && cfg.max_tweets != null) {
      $("#sigMaxTweets").value = cfg.max_tweets;
    }
    if ($("#sigSkipNonTrade")) $("#sigSkipNonTrade").checked = !!cfg.skip_non_trade;
    if ($("#sigPushEnabled")) {
      $("#sigPushEnabled").checked = cfg.push_enabled !== false;
    }
    if ($("#sigWatchEnabled")) $("#sigWatchEnabled").checked = !!cfg.watch_enabled;
    if ($("#sigCycleEnabled")) $("#sigCycleEnabled").checked = !!cfg.cycle_enabled;
    if ($("#sigDeepMode") && cfg.deep_sleep_mode) {
      $("#sigDeepMode").value = cfg.deep_sleep_mode === "patrol" ? "patrol" : "sleep";
    }
    if ($("#sigUserProfileUrl") || $("#sigUserWeeks")) {
      applySigUserForm(cfg);
    }
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

function switchSigMode(mode) {
  const m = mode === "user" ? "user" : "list";
  state.sigMode = m;
  document.querySelectorAll(".sig-mode-tab[data-sig-mode]").forEach((btn) => {
    const on = btn.getAttribute("data-sig-mode") === m;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  const listBox = $("#sigModeList");
  const userBox = $("#sigModeUser");
  if (listBox) listBox.hidden = m !== "list";
  if (userBox) userBox.hidden = m !== "user";
  loadSignalCards();
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

function renderSigUserRunLog(lines, itemLogs) {
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
  const text = logs + summaries;
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

function appendSigValidateLog(line) {
  const pre = $("#sigValidateLog");
  if (!pre) return;
  pre.hidden = false;
  pre.textContent = (pre.textContent ? `${pre.textContent}\n` : "") + line;
  pre.scrollTop = pre.scrollHeight;
}

function appendSigBacktestLog(line) {
  const pre = $("#sigBacktestLog");
  if (!pre) return;
  pre.hidden = false;
  pre.textContent = (pre.textContent ? `${pre.textContent}\n` : "") + line;
  pre.scrollTop = pre.scrollHeight;
}

function _validateCtxFromOpts(opts = {}) {
  const logSel = opts.logSel || "#sigValidateLog";
  const progressSel = opts.progressSel || "#sigValidateProgress";
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
  if (!sig.has_trade_signal) return [];
  const dir = String(sig.direction || "").toLowerCase();
  if (dir !== "long" && dir !== "short") return [];
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
    if (onlyTrade && !card?.signal?.has_trade_signal) continue;
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

async function runCardsValidateJob({ mock = false } = {}) {
  const btnReal = $("#btnSigUserValidate");
  const btnMock = $("#btnSigMockValidate");
  if (btnReal) btnReal.disabled = true;
  if (btnMock) btnMock.disabled = true;
  closeSigValidateWs();
  const log = $("#sigValidateLog");
  if (log) {
    log.hidden = false;
    log.textContent = "";
  }
  const handle = parseSigUserHandle($("#sigUserProfileUrl")?.value.trim() || "");
  const weeks = Number($("#sigUserWeeks")?.value || 1);
  const mockCount = Math.max(1, Math.min(20, Number($("#sigMockCount")?.value || 8) || 8));
  setStatus($("#sigUserStatus"), mock ? "启动 Mock 验证任务…" : "启动 Cards 验证…");
  try {
    const body = mock
      ? { mock: true, mockCount }
      : { mockCount };
    const data = await api("/api/signals/cards/validate", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!data.success || !data.job_id) {
      setStatus($("#sigUserStatus"), data.error || "验证启动失败", "error");
      return;
    }
    const jobId = data.job_id;
    const ctx = _validateCtxFromOpts({
      onDone() {},
    });
    ctx.appendLog(`${mock ? "[Mock] " : ""}jobId=${jobId}`);
    if (mock) ctx.appendLog(`mockCount=${mockCount} · 监听 WebSocket / 轮询…`);
    setStatus($("#sigUserStatus"), `${mock ? "Mock " : ""}验证任务 ${jobId} 运行中…`, "ok");
    await connectValidateJobWs(jobId, ctx, { mock });
  } catch (e) {
    setStatus($("#sigUserStatus"), String(e), "error");
  } finally {
    if (btnReal) btnReal.disabled = false;
    if (btnMock) btnMock.disabled = false;
  }
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

async function startCardsValidate() {
  await runCardsValidateJob({ mock: false });
}

async function startMockCardsValidate() {
  await runCardsValidateJob({ mock: true });
}

async function loadMockValidateSample() {
  const btn = $("#btnSigMockSample");
  if (btn) btn.disabled = true;
  closeSigValidateWs();
  const log = $("#sigValidateLog");
  if (log) {
    log.hidden = false;
    log.textContent = "";
  }
  setStatus($("#sigUserStatus"), "拉取 Mock 静态样例…");
  try {
    const data = await api("/api/signals/cards/validate/mock/sample");
    if (!data.success) {
      const msg = data.message || data.error || "Mock 样例不可用";
      setStatus($("#sigUserStatus"), msg, "error");
      appendSigValidateLog(`失败：${msg}`);
      return;
    }
    const items = data.items || [];
    appendSigValidateLog(`[Mock 静态样例] 共 ${items.length} 条（不跑任务，立刻返回）`);
    items.forEach((it) => appendSigValidateLog(formatValidateItem(it)));
    if ($("#sigValidateProgress")) $("#sigValidateProgress").textContent = `样例 ${items.length} 条`;
    setStatus($("#sigUserStatus"), `Mock 静态样例 ${items.length} 条`, "ok");
    toast(`Mock 静态样例 ${items.length} 条`, "ok");
  } catch (e) {
    setStatus($("#sigUserStatus"), String(e), "error");
    appendSigValidateLog(String(e));
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function clearSigUserCache() {
  const profile = $("#sigUserProfileUrl")?.value.trim() || "";
  const handle = parseSigUserHandle(profile);
  if (!handle) {
    toast("请填写有效的博主链接或 @handle", "error");
    return;
  }
  if (!confirm(`清除 @${handle} 的解析缓存？\n将删除本地已解析卡片与已见记录，下次会重新 AI 解析。`)) {
    return;
  }
  const btn = $("#btnSigUserClearCache");
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/signals/user/clear-cache", {
      method: "POST",
      body: JSON.stringify({ profile_url: profile, user_handle: handle }),
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
  const profile = $("#sigUserProfileUrl")?.value.trim() || "";
  if (!parseSigUserHandle(profile)) {
    toast("请填写有效的博主链接或 @handle", "error");
    return;
  }
  if (btn) btn.disabled = true;
  await persistSigUserForm({ immediate: true });
  setStatus($("#sigUserStatus"), "提交博主回溯任务…");
  renderSigUserRunLog([]);
  setSigUserControlButtons({ running: false, paused: false });
  const form = collectSigUserForm();
  try {
    const start = await api("/api/signals/user/run", {
      method: "POST",
      body: JSON.stringify({
        profile_url: form.user_profile_url,
        weeks: form.user_weeks,
        max_tweets: form.user_max_tweets,
        skip_non_trade: form.user_skip_non_trade,
        reparse_seen: form.user_reparse_seen,
        push: form.user_push_enabled,
        force_push: form.user_force_push,
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
      renderSigUserRunLog(job.logs || [], job.result?.item_logs);
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
        setStatus(
          $("#sigUserStatus"),
          result.message || job.message || (job.status === "cancelled" ? "已终止" : "完成"),
          ok ? "ok" : "error"
        );
        if (ok) {
          toast(result.message || "博主回溯完成", "ok");
          await loadSignalsPanel();
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

function formatSigWindowLine(w) {
  const from = String(w.from || "").slice(0, 19);
  const to = String(w.to || "").slice(0, 19);
  return `#${escapeHtml(String(w.list_id || ""))} · ${escapeHtml(from)} → ${escapeHtml(to)} · 解析 ${w.parsed || 0}/${w.fetched || 0}`;
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
        skip_non_trade: !!$("#sigSkipNonTrade")?.checked,
        push_enabled: !!$("#sigPushEnabled")?.checked,
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

async function pushSignalsOnly() {
  const btn = $("#btnSigPushOnly");
  if (btn) btn.disabled = true;
  setStatus($("#sigStatus"), "推送已存卡片…");
  try {
    const data = await api("/api/signals/push", {
      method: "POST",
      body: JSON.stringify({
        force: !!$("#sigForcePush")?.checked,
        only_trade: !!$("#sigFilterTrade")?.checked || !!$("#sigSkipNonTrade")?.checked,
        limit: 80,
      }),
    });
    setStatus(
      $("#sigStatus"),
      `推送完成：成功 ${data.pushed || 0} · 跳过 ${data.skipped || 0} · 失败 ${data.failed || 0}`,
      data.failed ? "error" : "ok"
    );
    toast(`推送 ${data.pushed || 0} 条`, data.failed ? "error" : "ok");
    await loadSignalsPanel();
  } catch (e) {
    setStatus($("#sigStatus"), String(e), "error");
  } finally {
    if (btn) btn.disabled = false;
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
  const key = String(dir || "unknown").toLowerCase();
  const map = {
    long: "做多",
    short: "做空",
    flat: "中性",
    watch: "观望",
    unknown: "未知",
    做多: "做多",
    做空: "做空",
    中性: "中性",
    观望: "观望",
    未知: "未知",
  };
  return map[key] || map.unknown;
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
        skip_non_trade: !!$("#sigSkipNonTrade")?.checked,
        ignore_windows: !!$("#sigIgnoreWindows")?.checked,
        reparse_seen: !!$("#sigReparseSeen")?.checked,
        push: !!$("#sigPushEnabled")?.checked,
        force_push: !!$("#sigForcePush")?.checked,
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
    const trade = !!sig.has_trade_signal;
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
  let url = `/api/signals/cards?limit=80${onlyTrade ? "&trade=1" : ""}`;
  if (state.sigMode === "user") {
    const handle = parseSigUserHandle($("#sigUserProfileUrl")?.value.trim() || "");
    if (handle) url += `&list_id=${encodeURIComponent(`user:${handle.toLowerCase()}`)}`;
  }
  try {
    const data = await api(url);
    renderSigWindows(data.windows || []);
    const items = (data.items || []).slice().sort((a, b) => sigCardTimeMs(b) - sigCardTimeMs(a));
    _sigCardsCache = items;
    const badge = $("#countSignals");
    if (badge) badge.textContent = String(items.length);
    if (!items.length) {
      box.innerHTML = `<p class="muted">暂无卡片。确认 Chrome 已开调试口并登录 X 后，点「开始抓取解析」。</p>`;
      return;
    }
    box.innerHTML = items
      .map((c) => {
        const sig = c.signal || {};
        const trade = !!sig.has_trade_signal;
        const dirKey = String(sig.direction || "unknown").toLowerCase();
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
        const tid = escapeAttr(String(c.tweet_id || ""));
        return `<article class="sig-card${trade ? " is-trade" : " is-noise"}" data-tweet-id="${tid}">
          <div class="sig-card-top">
            <span class="sig-dir ${escapeAttr(dirKey)}">${escapeHtml(dir)}</span>
            ${coins}
            <span class="sig-author">${authorLabel}</span>
            ${channelMeta}
            <span class="sig-time" title="发帖时间">${escapeHtml(timeLabel)}</span>
          </div>
          <p class="sig-summary">${escapeHtml(summaryText).slice(0, 240)}</p>
          ${levels.length ? `<div class="sig-levels">${levels.join("")}</div>` : ""}
          ${sig.image_notes ? `<p class="muted" style="margin:0;font-size:.74rem">图注：${escapeHtml(String(sig.image_notes).slice(0, 160))}</p>` : ""}
          ${imgs ? `<div class="sig-imgs">${imgs}</div>` : ""}
          <pre class="sig-text">${escapeHtml(stripSigTimePrefix(c.text || ""))}</pre>
          <div class="sig-card-foot">
            <a href="${escapeAttr(c.url || "#")}" target="_blank" rel="noopener">原帖</a>
            ${tid ? `<button type="button" class="btn-link" data-sig-edit="${tid}">编辑</button>` : ""}
            <span class="sig-conf">${trade ? "信号" : "非交易"} · 置信度 ${escapeHtml(String(sig.confidence ?? ""))} · ${escapeHtml(sig.provider === "heuristic" ? "规则解析" : "AI 解析")}${c.cache_only ? " · 缓存" : ""}</span>
          </div>
        </article>`;
      })
      .join("");
    applySigKolVisibility();
  } catch (e) {
    box.innerHTML = `<p class="muted">加载失败：${escapeHtml(String(e))}</p>`;
  }
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
  syncTaskUi();
  initPublishScheduleDefault();
  restorePublishPrefsFields();
  await refreshHealth();
  const savedPlatforms = loadPublishPrefs().platforms;
  await loadPublishPlatforms(savedPlatforms?.length ? savedPlatforms : undefined);
  await loadPublishQueue();
  await loadPublishCache();
  await refreshStats();
  await refreshCorpusStats();
  await loadPosts("", state.newsPlatform || "", "news", $("#newsView")?.value || "active", "");
  setInterval(refreshHealth, 15000);
  setInterval(loadTasks, 20000);
  setInterval(loadPublishQueue, 20000);
  setInterval(refreshStats, 30000);
  setInterval(refreshCorpusStats, 45000);
  setInterval(() => {
    const panel = $("#panel-signals");
    if (panel && !panel.hidden) loadSignalsPanel();
  }, 30000);
}

boot();
