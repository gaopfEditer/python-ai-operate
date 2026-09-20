/**
 * 叙事类目选择器 UI — 只读三栏面板，数据来自 taxonomy.js
 */
(function (global) {
  "use strict";

  const LS_CAT = "taxonomyCategoryId";
  const LS_TOPIC = "taxonomyTopicId";
  const POPOVER_DELAY_MS = 300;
  const POPOVER_MAX_W = 360;

  const STANCE_LABEL = {
    bull: "看涨",
    bear: "看跌",
    neutral: "中性",
    mixed: "混合",
  };

  /** @type {{ categories: import('./taxonomy').Category[], categoryGroups?: object[] }} */
  let data = { categories: [], categoryGroups: [] };
  /** @type {Map<string, object>} */
  let topicById = new Map();
  /** @type {Map<string, object[]>} */
  let topicsByName = new Map();

  const state = {
    categoryId: "",
    topicId: "",
    topicFilter: "",
    topicImportanceFilter: "all",
    templateFilter: "all",
    popoverTimer: null,
    popoverTopicId: "",
  };

  function normalizeImportance(n) {
    const v = Number(n);
    if (!Number.isFinite(v)) return 3;
    return Math.max(1, Math.min(5, Math.round(v)));
  }

  function topicImportance(t) {
    return normalizeImportance(t?.importance);
  }

  function categoryImportance(c) {
    return normalizeImportance(c?.importance);
  }

  function starsBarText(n) {
    const v = normalizeImportance(n);
    return "★".repeat(v) + "☆".repeat(5 - v);
  }

  function compactStarLabel(n) {
    return `★${normalizeImportance(n)}`;
  }

  function renderStarGlyphs(n, { top } = {}) {
    const v = normalizeImportance(n);
    const cls = top && v >= 5 ? "tax-stars is-top" : "tax-stars";
    let html = `<span class="${cls}" aria-hidden="true">`;
    for (let i = 1; i <= 5; i++) {
      html += `<span class="tax-star${i <= v ? " on" : ""}">${i <= v ? "★" : "☆"}</span>`;
    }
    html += "</span>";
    return html;
  }

  function topicImportanceNote(t) {
    if (t?.importanceNote) return t.importanceNote;
    const cat = getCategory(t?.categoryId);
    return cat?.importanceNote || "";
  }

  function impactPopoverSummary(t) {
    if (t?.impactSummary) return t.impactSummary;
    const chain = t?.impactOn || [];
    if (!chain.length) return "";
    const first = chain[0];
    return `${first.target}：${first.mechanism}（${first.lag}）`;
  }

  function bindThemeLinks(root) {
    root?.querySelectorAll("[data-theme-topic]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        selectTopic(btn.getAttribute("data-theme-topic"));
      });
    });
  }

  const SCENARIO_CLASS = { good: "is-good", bad: "is-bad", mixed: "is-mixed" };

  function renderImpactCards(t) {
    const row = $("#taxonomyImpactRow");
    if (!row) return;
    const list = t?.impactOn || [];
    if (!list.length) {
      row.innerHTML = "";
      row.hidden = true;
      return;
    }
    row.hidden = false;
    row.innerHTML = `<h4 class="tax-right-sub">传导</h4>
      <div class="tax-impact-grid">${list
        .map((imp) => {
          const target = resolveThemeTarget(imp.target);
          const targetEl = target
            ? `<button type="button" class="tax-impact-target is-link" data-theme-topic="${escapeHtml(target.id)}">${escapeHtml(imp.target)}</button>`
            : `<span class="tax-impact-target">${escapeHtml(imp.target)}</span>`;
          return `<article class="tax-impact-card">${targetEl}<p class="tax-impact-mechanism">${escapeHtml(imp.mechanism)}</p><span class="tax-impact-lag muted">${escapeHtml(imp.lag)}</span></article>`;
        })
        .join("")}</div>`;
    bindThemeLinks(row);
  }

  function renderScenarioCards(t) {
    const row = $("#taxonomyScenarioRow");
    if (!row) return;
    const list = (t?.scenarios || []).slice(0, 3);
    if (!list.length) {
      row.innerHTML = "";
      row.hidden = true;
      return;
    }
    row.hidden = false;
    row.innerHTML = `<h4 class="tax-right-sub">情景</h4>
      <div class="tax-scenario-grid">${list
        .map((s) => {
          const cls = SCENARIO_CLASS[s.id] || "";
          const stance = s.stance ? STANCE_LABEL[s.stance] || s.stance : "—";
          const coins = (s.coins || []).join(" · ") || "—";
          return `<article class="tax-scenario-card ${cls}">
          <header><h5>${escapeHtml(s.name || s.id)}</h5><span class="tax-scenario-stance">${escapeHtml(stance)}</span></header>
          <p class="tax-scenario-if"><strong>若</strong> ${escapeHtml(s.if)}</p>
          <p class="tax-scenario-then"><strong>则</strong> ${escapeHtml(s.then)}</p>
          <p class="tax-scenario-coins muted">落地 ${escapeHtml(coins)}</p>
          <p class="tax-scenario-template">${escapeHtml(s.template)}</p>
          <p class="tax-scenario-inv muted"><strong>失效</strong> ${escapeHtml(s.invalidation)}</p>
        </article>`;
        })
        .join("")}</div>`;
  }

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getCategories() {
    return data.categories || [];
  }

  function getCategoryGroups() {
    return data.categoryGroups || [];
  }

  function buildGroupedCategories() {
    const byName = new Map(getCategories().map((c) => [c.name, c]));
    const used = new Set();
    const sections = [];
    for (let i = 0; i < getCategoryGroups().length; i++) {
      const group = getCategoryGroups()[i];
      const items = (group.names || [])
        .map((name) => byName.get(name))
        .filter(Boolean);
      items.forEach((c) => used.add(c.id));
      if (!items.length) continue;
      sections.push({ group, categories: items, showDivider: sections.length > 0 });
    }
    const ungrouped = getCategories().filter((c) => !used.has(c.id));
    if (ungrouped.length) {
      sections.push({
        group: { id: "_ungrouped", name: "", hint: "" },
        categories: ungrouped,
        showDivider: sections.length > 0,
      });
    }
    if (!sections.length) {
      sections.push({
        group: { id: "_all", name: "", hint: "" },
        categories: getCategories(),
        showDivider: false,
      });
    }
    return sections;
  }

  function renderCategoryButton(c) {
    const n = (c.topics || []).length;
    const on = c.id === state.categoryId ? " on" : "";
    const imp = categoryImportance(c);
    const note = c.importanceNote ? ` title="${escapeHtml(c.importanceNote)}"` : "";
    return `<button type="button" class="tax-cat-row${on}" data-cat-id="${escapeHtml(c.id)}"${note}>
          <span class="tax-cat-name">${escapeHtml(c.name)}</span>
          <span class="tax-cat-meta">
            <span class="tax-importance-compact">${compactStarLabel(imp)}</span>
            <span class="tax-cat-count">· ${n}</span>
          </span>
        </button>`;
  }

  function getCategory(id) {
    return getCategories().find((c) => c.id === id) || null;
  }

  function getTopic(id) {
    return topicById.get(id) || null;
  }

  function buildIndexes() {
    topicById = new Map();
    topicsByName = new Map();
    for (const cat of getCategories()) {
      for (const t of cat.topics || []) {
        topicById.set(t.id, t);
        const key = String(t.name || "").trim().toLowerCase();
        if (!topicsByName.has(key)) topicsByName.set(key, []);
        topicsByName.get(key).push(t);
        const short = key.split("/")[0].trim();
        if (short && short !== key) {
          if (!topicsByName.has(short)) topicsByName.set(short, []);
          topicsByName.get(short).push(t);
        }
      }
    }
  }

  function resolveThemeTarget(theme) {
    const raw = String(theme || "").trim();
    if (!raw) return null;
    if (topicById.has(raw)) return topicById.get(raw);
    const low = raw.toLowerCase();
    const byName = topicsByName.get(low);
    if (byName?.length === 1) return byName[0];
    if (byName?.length > 1) return byName.find((t) => t.name === raw) || byName[0];
    for (const t of topicById.values()) {
      const name = String(t.name || "");
      if (name === raw || name.includes(raw) || raw.includes(name.split("/")[0].trim())) {
        return t;
      }
    }
    return null;
  }

  function saveSelection() {
    try {
      if (state.categoryId) localStorage.setItem(LS_CAT, state.categoryId);
      if (state.topicId) localStorage.setItem(LS_TOPIC, state.topicId);
    } catch (_) {
      /* quota */
    }
  }

  function restoreSelection() {
    try {
      state.categoryId = localStorage.getItem(LS_CAT) || "";
      state.topicId = localStorage.getItem(LS_TOPIC) || "";
    } catch (_) {
      state.categoryId = "";
      state.topicId = "";
    }
    const cats = getCategories();
    if (!cats.length) return;
    if (!getCategory(state.categoryId)) {
      state.categoryId = cats[0].id;
    }
    const cat = getCategory(state.categoryId);
    const topics = cat?.topics || [];
    if (!getTopic(state.topicId) || getTopic(state.topicId).categoryId !== state.categoryId) {
      state.topicId = topics[0]?.id || "";
    }
  }

  function selectCategory(id) {
    if (!getCategory(id)) return;
    state.categoryId = id;
    state.topicFilter = "";
    const inp = $("#taxonomyTopicSearch");
    if (inp) inp.value = "";
    const cat = getCategory(id);
    const topics = cat?.topics || [];
    if (!topics.find((t) => t.id === state.topicId)) {
      state.topicId = topics[0]?.id || "";
    }
    saveSelection();
    renderAll();
  }

  function selectTopic(id) {
    const t = getTopic(id);
    if (!t) return;
    state.categoryId = t.categoryId;
    state.topicId = id;
    saveSelection();
    hidePopover(true);
    renderCategories();
    renderTopics();
    renderTemplates();
  }

  function renderCategories() {
    const box = $("#taxonomyCategories");
    if (!box) return;
    box.innerHTML = buildGroupedCategories()
      .map(({ group, categories, showDivider }) => {
        const divider = showDivider ? `<div class="tax-cat-group-divider" role="separator"></div>` : "";
        const hint = group.hint ? ` title="${escapeHtml(group.hint)}"` : "";
        const head = group.name
          ? `<div class="tax-cat-group-head"${hint}>${escapeHtml(group.name)}</div>`
          : "";
        const rows = categories.map((c) => renderCategoryButton(c)).join("");
        return `${divider}<section class="tax-cat-group">${head}<div class="tax-cat-group-items">${rows}</div></section>`;
      })
      .join("");
    box.querySelectorAll("[data-cat-id]").forEach((btn) => {
      btn.addEventListener("click", () => selectCategory(btn.getAttribute("data-cat-id")));
    });
  }

  function filteredTopics() {
    const cat = getCategory(state.categoryId);
    if (!cat) return [];
    const q = state.topicFilter.trim().toLowerCase();
    let list = cat.topics || [];
    if (q) list = list.filter((t) => String(t.name || "").toLowerCase().includes(q));
    const f = state.topicImportanceFilter;
    if (f === "4plus") list = list.filter((t) => topicImportance(t) >= 4);
    if (f === "5") list = list.filter((t) => topicImportance(t) >= 5);
    return list;
  }

  function schedulePopover(topicId, anchor) {
    clearPopoverTimer();
    state.popoverTimer = setTimeout(() => showPopover(topicId, anchor), POPOVER_DELAY_MS);
  }

  function clearPopoverTimer() {
    if (state.popoverTimer) {
      clearTimeout(state.popoverTimer);
      state.popoverTimer = null;
    }
  }

  function hidePopover(immediate) {
    clearPopoverTimer();
    const el = $("#taxonomyPopover");
    if (!el) return;
    if (immediate) {
      el.hidden = true;
      el.innerHTML = "";
      state.popoverTopicId = "";
      return;
    }
    el.hidden = true;
  }

  function positionPopover(anchor) {
    const el = $("#taxonomyPopover");
    if (!el || el.hidden || !anchor) return;
    const rect = anchor.getBoundingClientRect();
    const pad = 8;
    let left = rect.right + pad;
    let top = rect.top;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    el.style.maxWidth = POPOVER_MAX_W + "px";
    el.hidden = false;
    const pw = el.offsetWidth;
    const ph = el.offsetHeight;
    if (left + pw > vw - pad) left = Math.max(pad, rect.left - pw - pad);
    if (top + ph > vh - pad) top = Math.max(pad, vh - ph - pad);
    el.style.left = left + "px";
    el.style.top = top + "px";
  }

  function showPopover(topicId, anchor) {
    const t = getTopic(topicId);
    if (!t || !anchor) return;
    state.popoverTopicId = topicId;
    let el = $("#taxonomyPopover");
    if (!el) {
      el = document.createElement("div");
      el.id = "taxonomyPopover";
      el.className = "tax-popover";
      el.setAttribute("role", "tooltip");
      document.body.appendChild(el);
    }
    const themes = (t.relatedThemes || [])
      .map((theme) => {
        const target = resolveThemeTarget(theme);
        if (target) {
          return `<button type="button" class="tax-theme-chip is-link" data-theme-topic="${escapeHtml(target.id)}">${escapeHtml(theme)}</button>`;
        }
        return `<span class="tax-theme-chip">${escapeHtml(theme)}</span>`;
      })
      .join("");
    const imp = topicImportance(t);
    const impNote = topicImportanceNote(t);
    const weightBlock = `<div class="tax-pop-importance">
      <div class="tax-pop-importance-head">
        <span class="tax-pop-importance-label">内容权重</span>
        <span class="tax-stars-text">${starsBarText(imp)}</span>
      </div>
      ${impNote ? `<p class="tax-pop-importance-note">${escapeHtml(impNote)}</p>` : ""}
    </div>`;
    const impactSum = impactPopoverSummary(t);
    const impactBlock = impactSum
      ? `<div class="tax-pop-section"><h4>传导</h4><p>${escapeHtml(impactSum)}</p><p class="tax-pop-hint muted">详情见右栏</p></div>`
      : "";
    el.innerHTML = `
      ${weightBlock}
      <div class="tax-pop-section"><h4>是什么</h4><p>${escapeHtml(t.meaning || "")}</p></div>
      ${impactBlock}
      <div class="tax-pop-section"><h4>关联</h4><div class="tax-theme-row">${themes || "<span class=\"muted\">—</span>"}</div></div>`;
    el.hidden = false;
    bindThemeLinks(el);
    requestAnimationFrame(() => positionPopover(anchor));
  }

  function renderTopics() {
    const box = $("#taxonomyTopics");
    const title = $("#taxonomyMidTitle");
    if (!box) return;
    const cat = getCategory(state.categoryId);
    if (title) title.textContent = cat ? cat.name : "小类";
    const list = filteredTopics();
    if (!list.length) {
      box.innerHTML = `<p class="tax-empty muted">无匹配小类</p>`;
      return;
    }
    if (!list.find((t) => t.id === state.topicId)) {
      state.topicId = list[0].id;
      saveSelection();
    }
    box.innerHTML = list
      .map((t) => {
        const n = (t.templates || []).length;
        const imp = topicImportance(t);
        const on = t.id === state.topicId ? " on" : "";
        const star5 = imp >= 5 ? " is-star5" : "";
        return `<button type="button" class="tax-topic-row${on}${star5}" data-topic-id="${escapeHtml(t.id)}">
          <span class="tax-topic-name">${escapeHtml(t.name)}</span>
          <span class="tax-topic-meta">
            ${renderStarGlyphs(imp, { top: true })}
            <span class="tax-topic-count">${n}</span>
          </span>
        </button>`;
      })
      .join("");
    box.querySelectorAll("[data-topic-id]").forEach((btn) => {
      const id = btn.getAttribute("data-topic-id");
      btn.addEventListener("click", () => selectTopic(id));
      btn.addEventListener("mouseenter", () => schedulePopover(id, btn));
      btn.addEventListener("mouseleave", () => {
        clearPopoverTimer();
        setTimeout(() => {
          const pop = $("#taxonomyPopover");
          if (pop && !pop.matches(":hover")) hidePopover(true);
        }, 120);
      });
    });
  }

  function filterTemplates(templates) {
    const f = state.templateFilter;
    let list = templates || [];
    if (f === "placeholder") return list.filter((t) => t.placeholder);
    if (f === "bull" || f === "bear" || f === "neutral") {
      return list.filter((t) => t.stance === f);
    }
    return list;
  }

  function renderTemplates() {
    const box = $("#taxonomyTemplates");
    const title = $("#taxonomyRightTitle");
    const t = getTopic(state.topicId);
    if (title) title.textContent = t?.name || "模板";
    renderImpactCards(t);
    renderScenarioCards(t);
    if (!box) return;
    if (!t) {
      box.innerHTML = `<p class="tax-empty muted">请选择小类</p>`;
      return;
    }
    const list = filterTemplates(t.templates || []);
    if (!list.length) {
      box.innerHTML = `<div class="tax-empty-state">
        <p>该小类暂无模板</p>
        <p class="muted">后续按主题在 taxonomy.js 中补充</p>
      </div>`;
      return;
    }
    box.innerHTML = list
      .map((tpl) => {
        const badge = tpl.placeholder
          ? `<span class="tax-tpl-badge is-ph">待补充</span>`
          : `<span class="tax-tpl-badge is-ok">已完善</span>`;
        const stance = tpl.stance ? STANCE_LABEL[tpl.stance] || tpl.stance : "—";
        const coins = (tpl.coins || []).join(" · ") || "—";
        const preview = String(tpl.body || "")
          .split("\n")
          .slice(0, 3)
          .join("\n");
        const tags = (tpl.tags || [])
          .map((tag) => `<span class="chip tag">${escapeHtml(tag)}</span>`)
          .join("");
        return `<article class="tax-tpl-card" data-tpl-id="${escapeHtml(tpl.id)}" tabindex="0">
          <header>
            <h4>${escapeHtml(tpl.title || tpl.id)}</h4>
            ${badge}
          </header>
          <div class="tax-tpl-meta"><span>多空 ${escapeHtml(stance)}</span><span>币种 ${escapeHtml(coins)}</span></div>
          <pre class="tax-tpl-preview">${escapeHtml(preview)}</pre>
          <div class="chip-row">${tags}</div>
        </article>`;
      })
      .join("");
    box.querySelectorAll(".tax-tpl-card").forEach((card) => {
      const open = () => {
        const id = card.getAttribute("data-tpl-id");
        const tpl = (t.templates || []).find((x) => x.id === id);
        if (tpl) openTemplateDialog(tpl, t);
      };
      card.addEventListener("click", open);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      });
    });
  }

  function openTemplateDialog(tpl, topic) {
    const dlg = $("#taxonomyTemplateDialog");
    if (!dlg) return;
    const title = $("#taxonomyDialogTitle");
    const meta = $("#taxonomyDialogMeta");
    const body = $("#taxonomyDialogBody");
    if (title) title.textContent = tpl.title || tpl.id;
    if (meta) {
      const stance = tpl.stance ? STANCE_LABEL[tpl.stance] || tpl.stance : "—";
      meta.textContent = `${topic.name} · ${stance} · ${(tpl.coins || []).join(", ") || "—"}`;
    }
    if (body) body.textContent = tpl.body || "";
    if (typeof dlg.showModal === "function") dlg.showModal();
  }

  function renderTemplateFilters() {
    const box = $("#taxonomyTplFilters");
    if (!box) return;
    const opts = [
      { id: "all", label: "全部" },
      { id: "bull", label: "看涨" },
      { id: "bear", label: "看跌" },
      { id: "neutral", label: "中性" },
      { id: "placeholder", label: "仅占位" },
    ];
    box.innerHTML = opts
      .map((o) => {
        const on = state.templateFilter === o.id ? " on" : "";
        return `<button type="button" class="tax-filter-chip${on}" data-tpl-filter="${escapeHtml(o.id)}">${escapeHtml(o.label)}</button>`;
      })
      .join("");
    box.querySelectorAll("[data-tpl-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.templateFilter = btn.getAttribute("data-tpl-filter") || "all";
        renderTemplateFilters();
        renderTemplates();
      });
    });
  }

  function renderImportanceFilters() {
    const box = $("#taxonomyImportanceFilters");
    if (!box) return;
    const opts = [
      { id: "all", label: "全部星级" },
      { id: "4plus", label: "4 星以上" },
      { id: "5", label: "5 星" },
    ];
    box.innerHTML = opts
      .map((o) => {
        const on = state.topicImportanceFilter === o.id ? " on" : "";
        return `<button type="button" class="tax-filter-chip${on}" data-imp-filter="${escapeHtml(o.id)}">${escapeHtml(o.label)}</button>`;
      })
      .join("");
    box.querySelectorAll("[data-imp-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.topicImportanceFilter = btn.getAttribute("data-imp-filter") || "all";
        renderImportanceFilters();
        renderTopics();
        renderTemplates();
      });
    });
  }

  function renderAll() {
    renderCategories();
    renderImportanceFilters();
    renderTopics();
    renderTemplateFilters();
    renderTemplates();
  }

  function bindGlobal() {
    const search = $("#taxonomyTopicSearch");
    search?.addEventListener("input", () => {
      state.topicFilter = search.value || "";
      renderTopics();
      renderTemplates();
    });
    const pop = $("#taxonomyPopover");
    pop?.addEventListener("mouseleave", () => hidePopover(true));
    window.addEventListener(
      "scroll",
      () => {
        if (state.popoverTopicId) hidePopover(true);
      },
      true
    );
    window.addEventListener("resize", () => hidePopover(true));
    $("#taxonomyTemplateDialog")?.addEventListener("click", (e) => {
      if (e.target === e.currentTarget) e.currentTarget.close();
    });
  }

  function init() {
    if (!global.TaxonomyData?.categories?.length) {
      console.warn("[taxonomy] TaxonomyData 未加载");
      return;
    }
    data = global.TaxonomyData;
    buildIndexes();
    restoreSelection();
    bindGlobal();
    renderAll();
  }

  function onTabEnter() {
    if (!topicById.size && global.TaxonomyData?.categories?.length) {
      init();
      return;
    }
    renderAll();
  }

  global.TaxonomyPage = { init, onTabEnter, selectTopic, selectCategory };
})(typeof window !== "undefined" ? window : globalThis);
