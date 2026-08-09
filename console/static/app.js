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
};

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
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
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
  if (name === "corpus") loadCorpus();
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

function renderPathView(pathObj) {
  const el = $("#corpusPathView");
  if (!el) return;
  const steps = Array.isArray(pathObj?.steps) ? pathObj.steps : [];
  if (!steps.length) {
    el.className = "path-view muted";
    el.textContent = "暂无取材路径";
    return;
  }
  el.className = "path-view";
  const nodes = steps
    .map((s, i) => {
      const layer = LAYER_LABEL[s.layer] || s.layer || `步骤${i + 1}`;
      const detail = [
        s.via || s.provider || s.store || "",
        s.title ? String(s.title).slice(0, 40) : "",
        s.topic ? `话题:${s.topic}` : "",
        s.template_id != null ? `#${s.template_id}` : "",
        s.at || "",
      ]
        .filter(Boolean)
        .join(" · ");
      return `<li class="path-step" data-layer="${escapeAttr(s.layer || "")}">
        <span class="path-layer">${escapeHtml(layer)}</span>
        <span class="path-detail">${escapeHtml(detail)}</span>
      </li>`;
    })
    .join("");
  el.innerHTML = `<ol class="path-flow">${nodes}</ol>`;
}

function renderCorpusItems(items) {
  const box = $("#corpusList");
  if (!box) return;
  if (!items || !items.length) {
    box.innerHTML = `<div class="item"><h3>暂无模板</h3><p class="snippet muted">可先跑「xgrowth 爆款热榜拆解」，或在资讯列表点「拆解入库」。</p></div>`;
    return;
  }
  box.innerHTML = items
    .map((it) => {
      const factors = it.factors || {};
      const tagObj = factors.tags || {};
      const elements = factors.elements || {};
      const metrics = factors.metrics || {};
      const kws = (it.keywords || []).map((k) => `<span class="chip">${escapeHtml(k)}</span>`).join("");
      const tags = (it.tags || []).map((t) => `<span class="chip tag">${escapeHtml(t)}</span>`).join("");
      const q = it.quality || "unrated";
      const domainLine = [
        factors.domain || tagObj.primary
          ? `${factors.domain || ""} · ${tagObj.primary || ""} / ${tagObj.secondary || ""}`
          : "",
        metrics.velocity_per_hour ? `${metrics.velocity_per_hour}/h` : "",
        elements.hook_type || "",
      ]
        .filter(Boolean)
        .join(" · ");
      const reason = factors.viral_reason
        ? `<p class="snippet">爆款原因：${escapeHtml(String(factors.viral_reason).slice(0, 180))}</p>`
        : "";
      return `
        <article class="item corpus-item" data-id="${escapeAttr(String(it.id))}">
          <div class="item-head">
            <span class="source-badge">#${escapeHtml(String(it.id))} · ${escapeHtml(it.source_platform || "?")}</span>
            <h3>${escapeHtml(it.pattern || it.source_title || "(无模板)")}</h3>
          </div>
          <div class="meta">
            <span>情绪 ${escapeHtml(it.emotion || "-")}</span>
            <span>冲突 ${escapeHtml(it.tension || "-")}</span>
            <span>权重 ${escapeHtml(String(it.weight ?? 1))}</span>
            <span class="badge q-${escapeAttr(q)}">${escapeHtml(q)}</span>
            ${it.source_url ? `<a href="${escapeAttr(it.source_url)}" target="_blank" rel="noreferrer">原文</a>` : ""}
          </div>
          ${domainLine ? `<p class="snippet muted">${escapeHtml(domainLine)}</p>` : ""}
          ${it.hooks ? `<p class="snippet">钩子：${escapeHtml(it.hooks)}</p>` : ""}
          ${reason}
          <div class="chip-row">${kws}${tags}</div>
          <div class="item-actions">
            <button class="btn ghost btn-sm" type="button" data-corpus="use">选用生成</button>
            <button class="btn ghost btn-sm" type="button" data-corpus="path">取材路径</button>
            <button class="btn ghost btn-sm" type="button" data-corpus="good">标优质</button>
            <button class="btn ghost btn-sm" type="button" data-corpus="bad">标淘汰</button>
            <button class="btn ghost btn-sm" type="button" data-corpus="archive">归档</button>
            <button class="btn ghost btn-sm" type="button" data-corpus="tag">加标签</button>
          </div>
        </article>`;
    })
    .join("");

  box.querySelectorAll("[data-corpus]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const root = btn.closest(".corpus-item");
      const id = Number(root?.getAttribute("data-id") || 0);
      const action = btn.getAttribute("data-corpus");
      if (!id || !action) return;
      const item = (state.corpusItems || []).find((x) => Number(x.id) === id);
      if (action === "use") {
        if ($("#regenTemplateId")) $("#regenTemplateId").value = String(id);
        if (item) renderPathView(item.provenance || {});
        $("#corpusRegenBox")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        toast(`已选用模板 #${id}`, "ok");
        return;
      }
      if (action === "path") {
        renderPathView(item?.provenance || {});
        toast("已显示取材路径", "ok");
        return;
      }
      btn.disabled = true;
      try {
        if (action === "tag") {
          const raw = window.prompt("输入标签（逗号分隔）", "");
          if (!raw) return;
          const tags = raw
            .split(/[,，]/)
            .map((s) => s.trim())
            .filter(Boolean);
          const data = await api(`/api/corpus/templates/${id}`, {
            method: "POST",
            body: JSON.stringify({ action: "add_tags", tags }),
          });
          if (!data.success) toast(data.error || "失败", "error");
          else {
            toast("已加标签", "ok");
            await loadCorpus();
          }
          return;
        }
        const map = { good: "rate_good", bad: "rate_bad", archive: "archive" };
        const data = await api(`/api/corpus/templates/${id}`, {
          method: "POST",
          body: JSON.stringify({ action: map[action] }),
        });
        if (!data.success) toast(data.error || "失败", "error");
        else {
          toast("已更新", "ok");
          await loadCorpus();
        }
      } catch (e) {
        toast(String(e), "error");
      } finally {
        btn.disabled = false;
      }
    });
  });
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
  const kw = $("#corpusKeyword")?.value.trim() || "";
  const emotion = $("#corpusEmotion")?.value.trim() || "";
  const quality = $("#corpusQuality")?.value || "";
  const status = $("#corpusStatus")?.value ?? "active";
  if (kw) qs.set("keyword", kw);
  if (emotion) qs.set("emotion", emotion);
  if (quality) qs.set("quality", quality);
  if (status) qs.set("status", status);
  qs.set("limit", "80");
  setStatus($("#corpusMeta"), "加载中…");
  try {
    const data = await api(`/api/corpus/templates?${qs.toString()}`);
    if (!data.success) {
      setStatus($("#corpusMeta"), data.error || "加载失败", "error");
      return;
    }
    state.corpusItems = data.items || [];
    setStatus($("#corpusMeta"), `共 ${data.total} 条模板`, "ok");
    renderCorpusItems(state.corpusItems);
    await refreshCorpusStats();
  } catch (e) {
    setStatus($("#corpusMeta"), String(e), "error");
  }
}

async function runCorpusRegen() {
  const tid = Number($("#regenTemplateId")?.value || 0);
  const topic = $("#regenTopic")?.value.trim() || "";
  if (!tid || !topic) {
    setStatus($("#corpusRegenStatus"), "请填写模板 ID 与新话题", "error");
    return;
  }
  $("#btnCorpusRegen").disabled = true;
  setStatus($("#corpusRegenStatus"), "正在再生成…");
  try {
    const data = await api("/api/corpus/generate", {
      method: "POST",
      body: JSON.stringify({
        template_id: tid,
        topic,
        platform_style: $("#regenStyle")?.value.trim() || "X/Twitter",
        prompt: $("#regenPrompt")?.value.trim() || "",
        save_article: true,
      }),
    });
    if (!data.success) {
      setStatus($("#corpusRegenStatus"), data.error || "生成失败", "error");
      return;
    }
    const out = $("#corpusRegenOut");
    if (out) {
      out.classList.remove("muted");
      out.textContent = data.content || "";
    }
    renderPathView(data.path || data.generation?.path || {});
    state.lastCreate = {
      title: topic,
      content: data.content || "",
      path: data.saved_path || "",
    };
    setStatus(
      $("#corpusRegenStatus"),
      data.saved_path ? `生成成功 · 已存 ${data.saved_path}` : "生成成功",
      "ok"
    );
    await loadArticles();
  } catch (e) {
    setStatus($("#corpusRegenStatus"), String(e), "error");
  } finally {
    $("#btnCorpusRegen").disabled = false;
  }
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

async function loadPublishPlatforms() {
  const data = await api("/api/platforms/publish");
  const sel = $("#publishPlatform");
  sel.innerHTML = "";
  const preferred = new Set(["x", "binance_square"]);
  (data.platforms || []).forEach((p) => {
    if (!p.enabled) return;
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.id})`;
    if (preferred.has(p.id) || preferred.has(String(p.type || ""))) {
      opt.selected = true;
    }
    sel.appendChild(opt);
  });
  if (!sel.options.length) {
    ["x", "binance_square"].forEach((id) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      opt.selected = true;
      sel.appendChild(opt);
    });
  }
}

function selectedPublishPlatforms() {
  const sel = $("#publishPlatform");
  if (!sel) return [];
  return [...sel.selectedOptions].map((o) => o.value).filter(Boolean);
}

function parseMediaPaths(raw) {
  return String(raw || "")
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
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
  $("#corpusKeyword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadCorpus();
  });
  $("#corpusEmotion")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadCorpus();
  });
  $("#corpusQuality")?.addEventListener("change", () => loadCorpus());
  $("#corpusStatus")?.addEventListener("change", () => loadCorpus());
  $("#btnCorpusRegen")?.addEventListener("click", () => runCorpusRegen());
  $("#regenTopic")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runCorpusRegen();
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
    $("#publishTitle").value = state.lastCreate.title;
    $("#publishContent").value = state.lastCreate.content;
    switchTab("publish");
  });

  $("#btnLoadArticles").addEventListener("click", loadArticles);

  $("#articleSelect").addEventListener("change", async () => {
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
    setStatus($("#publishStatus"), "正在发布…");
    $("#publishResult").textContent = "";
    try {
      const platforms = selectedPublishPlatforms();
      if (!platforms.length) {
        setStatus($("#publishStatus"), "请至少选择一个平台", "error");
        return;
      }
      const dry = !!$("#publishDryRun")?.checked;
      const data = await api("/api/publish", {
        method: "POST",
        body: JSON.stringify({
          title: $("#publishTitle").value.trim(),
          content: $("#publishContent").value.trim(),
          tags: $("#publishTags").value.trim(),
          platforms,
          media_paths: parseMediaPaths($("#publishMedia")?.value || ""),
          use_cdp: $("#useCdp").checked,
          debugger_url: $("#debuggerUrl").value.trim(),
          submit: !dry,
          file: $("#articleSelect").value || undefined,
        }),
      });
      $("#publishResult").textContent = JSON.stringify(data, null, 2);
      const okN = data.success_count || 0;
      const total = data.total || 0;
      setStatus(
        $("#publishStatus"),
        data.success
          ? `发布完成 ${okN}/${total}`
          : data.error || "发布失败",
        data.success ? "ok" : "error"
      );
    } catch (e) {
      setStatus($("#publishStatus"), String(e), "error");
    } finally {
      $("#btnPublish").disabled = false;
    }
  });
}

async function boot() {
  bind();
  syncTaskUi();
  await refreshHealth();
  await loadPublishPlatforms();
  await loadArticles();
  await refreshStats();
  await refreshCorpusStats();
  await loadPosts("", state.newsPlatform || "", "news", $("#newsView")?.value || "active", "");
  setInterval(refreshHealth, 15000);
  setInterval(loadTasks, 20000);
  setInterval(refreshStats, 30000);
  setInterval(refreshCorpusStats, 45000);
}

boot();
