/**
 * 任务系统 — 流程：开周排期 / 每日执行 / 随时捕捉 / 周五收周
 */
(function (global) {
  "use strict";

  const LS_STORE = "tr_tasks_store_v2";
  const LS_MODE = "tr_tasks_mode_v1";
  const LS_BOARD = "tr_tasks_board_v4";
  const LS_TPL_CFG = "tr_tasks_tpl_cfg";
  const LS_TPL_CUSTOM = "tr_tasks_tpl_custom_v1";
  const LS_NOTES = "tr_tasks_week_notes";
  const LS_MONTHS = "tr_tasks_month_plans_v1";

  const $ = (sel) => document.querySelector(sel);
  const TD = () => global.TasksData;

  const state = {
    mode: "home",
    boardView: "schedule",
    boardFlow: "exec",
    columnOrder: "asc",
    categoryId: "",
    subcategoryId: "",
    catFilter: "all",
    subSearch: "",
    boardWeek: "",
    statsPeriod: "month",
    statsAnchor: "",
    monthsYear: 0,
    monthsKey: "",
    monthsPane: "plan",
    editingId: null,
    editingMonthItemId: null,
    dragTaskId: null,
  };

  function uid() {
    return `task_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
  }

  function weekKey(d = new Date()) {
    const dt = new Date(d);
    dt.setHours(12, 0, 0, 0);
    const day = dt.getDay() || 7;
    dt.setDate(dt.getDate() + 4 - day);
    const year = dt.getFullYear();
    const jan1 = new Date(year, 0, 1);
    const week = Math.ceil(((dt - jan1) / 86400000 + jan1.getDay() + 1) / 7);
    return `${year}-W${String(week).padStart(2, "0")}`;
  }

  function monthKey(d = new Date()) {
    const dt = new Date(d);
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`;
  }

  function activeWeekKey() {
    return state.boardWeek || weekKey();
  }

  function monthItemUid() {
    return `mi_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
  }

  function parseMonthKey(mk) {
    const m = /^(\d{4})-(\d{2})$/.exec(mk || "");
    return m ? { year: Number(m[1]), month: Number(m[2]) } : null;
  }

  function monthKeyAdd(mk, delta) {
    const p = parseMonthKey(mk);
    if (!p) return monthKey();
    const d = new Date(p.year, p.month - 1 + delta, 1, 12);
    return monthKey(d);
  }

  function monthPhase(mk) {
    const cur = monthKey();
    if (mk < cur) return "past";
    if (mk > cur) return "future";
    return "current";
  }

  function monthKeyForWeek(wk) {
    return monthKey(weekDateRange(wk).start);
  }

  function monthLabel(mk) {
    const p = parseMonthKey(mk);
    return p ? `${p.year} 年 ${p.month} 月` : mk;
  }

  function weeksInMonth(mk) {
    const p = parseMonthKey(mk);
    if (!p) return [];
    const last = new Date(p.year, p.month, 0).getDate();
    const weeks = [];
    const seen = new Set();
    for (let day = 1; day <= last; day += 1) {
      const d = new Date(p.year, p.month - 1, day, 12);
      if ((d.getDay() || 7) === 1) {
        const wk = weekKey(d);
        if (!seen.has(wk)) {
          seen.add(wk);
          weeks.push(wk);
        }
      }
    }
    return weeks;
  }

  function loadAllMonthPlans() {
    try {
      return JSON.parse(localStorage.getItem(LS_MONTHS) || "{}") || {};
    } catch (_) {
      return {};
    }
  }

  function saveAllMonthPlans(all) {
    localStorage.setItem(LS_MONTHS, JSON.stringify(all));
  }

  function ensureMonthPlan(mk) {
    const all = loadAllMonthPlans();
    if (!all[mk]) {
      const phase = monthPhase(mk);
      all[mk] = {
        monthKey: mk,
        title: "",
        goals: [],
        items: [],
        status: phase === "past" ? "archived" : phase === "current" ? "active" : "planned",
      };
      saveAllMonthPlans(all);
    }
    return all[mk];
  }

  function getMonthPlan(mk) {
    return loadAllMonthPlans()[mk] || null;
  }

  function saveMonthPlan(plan) {
    const all = loadAllMonthPlans();
    all[plan.monthKey] = plan;
    saveAllMonthPlans(all);
  }

  function monthHasContent(plan) {
    if (!plan) return false;
    return (plan.goals || []).some((g) => String(g).trim()) || (plan.items || []).length > 0;
  }

  function priFromMonth(p) {
    if (p === "P0" || p === "must") return "must";
    if (p === "P2" || p === "inspiration") return "inspiration";
    return "defer";
  }

  function priToMonth(p) {
    if (p === "must") return "P0";
    if (p === "inspiration") return "P2";
    return "P1";
  }

  function addMonthGoal(mk, text) {
    const t = String(text || "").trim();
    if (!t) return;
    const plan = ensureMonthPlan(mk);
    plan.goals = [...(plan.goals || []), t];
    saveMonthPlan(plan);
  }

  function updateMonthGoals(mk, goals) {
    const plan = ensureMonthPlan(mk);
    plan.goals = goals.map((g) => String(g).trim()).filter(Boolean);
    saveMonthPlan(plan);
  }

  function addMonthItem(mk, partial) {
    const plan = ensureMonthPlan(mk);
    const item = {
      id: monthItemUid(),
      title: String(partial.title || "").trim(),
      categoryId: partial.categoryId || "misc",
      subcategoryId: partial.subcategoryId || "misc.adhoc",
      priority: partial.priority || "P1",
      targetWeekId: partial.targetWeekId || "",
      status: "planned",
      rolledFromMonthKey: partial.rolledFromMonthKey || "",
    };
    if (!item.title) return null;
    plan.items = [...(plan.items || []), item];
    saveMonthPlan(plan);
    return item;
  }

  function updateMonthItem(mk, itemId, patch) {
    const plan = ensureMonthPlan(mk);
    const i = (plan.items || []).findIndex((x) => x.id === itemId);
    if (i < 0) return null;
    plan.items[i] = { ...plan.items[i], ...patch };
    saveMonthPlan(plan);
    return plan.items[i];
  }

  function splitMonthItemToWeek(mk, itemId, wk) {
    const plan = ensureMonthPlan(mk);
    const item = (plan.items || []).find((x) => x.id === itemId);
    if (!item || item.status !== "planned") return false;
    if (allTasks().some((t) => t.weekKey === wk && t.monthItemId === item.id)) return false;
    const task = makeTask({
      title: item.title,
      categoryId: item.categoryId,
      subcategoryId: item.subcategoryId || "misc.adhoc",
      priority: priFromMonth(item.priority),
      kind: "month",
      monthItemId: item.id,
      daySlot: 0,
      weekKey: wk,
      monthKey: mk,
    });
    upsertTask(task);
    item.status = "split";
    item.targetWeekId = wk;
    saveMonthPlan(plan);
    return true;
  }

  function returnTaskToMonthPool(task) {
    if (!task) return;
    const mk = task.monthKey || monthKeyForWeek(task.weekKey);
    const plan = ensureMonthPlan(mk);
    if (task.monthItemId) {
      updateMonthItem(mk, task.monthItemId, { status: "planned", targetWeekId: "" });
    } else {
      addMonthItem(mk, {
        title: task.title,
        categoryId: task.categoryId,
        subcategoryId: task.subcategoryId,
        priority: priToMonth(task.priority),
      });
    }
    deleteTask(task.id);
  }

  function rolloverTaskToNextMonth(task) {
    if (!task) return;
    const mk = task.monthKey || monthKeyForWeek(task.weekKey);
    const nextMk = monthKeyAdd(mk, 1);
    ensureMonthPlan(nextMk);
    addMonthItem(nextMk, {
      title: task.title,
      categoryId: task.categoryId,
      subcategoryId: task.subcategoryId,
      priority: priToMonth(task.priority),
      rolledFromMonthKey: mk,
    });
    if (task.monthItemId) {
      updateMonthItem(mk, task.monthItemId, { status: "dropped" });
    }
    deleteTask(task.id);
  }

  function applyMonthItemsToWeek(wk) {
    const mk = monthKeyForWeek(wk);
    const plan = getMonthPlan(mk);
    if (!plan) return 0;
    let added = 0;
    (plan.items || [])
      .filter((i) => i.status === "planned" && i.targetWeekId === wk)
      .forEach((item) => {
        if (splitMonthItemToWeek(mk, item.id, wk)) added += 1;
      });
    return added;
  }

  function todayDaySlot() {
    const d = new Date().getDay();
    if (d >= 1 && d <= 5) return d;
    return TD().WEEKEND_SLOT || 6;
  }

  function isWeekendSlot(slot) {
    return Number(slot) === (TD().WEEKEND_SLOT || 6);
  }

  function tomorrowDaySlot() {
    const t = todayDaySlot();
    if (t >= 1 && t <= 4) return t + 1;
    if (t === 5) return TD().WEEKEND_SLOT || 6;
    if (isWeekendSlot(t)) return 1;
    return 0;
  }

  function daySlotLabel(slot, { role } = {}) {
    const s = Number(slot);
    if (!s) return "待排期";
    const name = TD().DAY_NAME[s] || "";
    if (role === "today") {
      if (isWeekendSlot(s)) return "周末";
      return "今天";
    }
    if (role === "tomorrow") {
      if (s === 1 && isWeekendSlot(todayDaySlot())) return "周一";
      if (isWeekendSlot(s)) return "周末";
      return "明天";
    }
    return name;
  }

  function weekNumber(wk) {
    const m = /^(\d{4})-W(\d{2})$/.exec(wk || "");
    return m ? Number(m[2]) : 0;
  }

  function weekDateRange(wk) {
    const m = /^(\d{4})-W(\d{2})$/.exec(wk || "");
    if (!m) return { start: new Date(), end: new Date() };
    const year = Number(m[1]);
    const week = Number(m[2]);
    const jan4 = new Date(year, 0, 4, 12, 0, 0, 0);
    const day = jan4.getDay() || 7;
    const mon = new Date(jan4);
    mon.setDate(jan4.getDate() - day + 1 + (week - 1) * 7);
    const sun = new Date(mon);
    sun.setDate(mon.getDate() + 6);
    const fmt = (d) => `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { start: mon, end: sun, label: `${fmt(mon)} ~ ${fmt(sun)}` };
  }

  function weekRangeLabel(wk) {
    const n = weekNumber(wk);
    const r = weekDateRange(wk);
    return `第 ${n} 周 · ${r.start.getFullYear()}-${r.label}`;
  }

  function priLabel(p) {
    if (p === "must") return "P0";
    if (p === "defer") return "P1";
    if (p === "inspiration") return "P2";
    return p || "P1";
  }

  function priBarColor(p) {
    if (p === "must") return "#C45C26";
    if (p === "defer") return "#3F6B58";
    return "#8A8175";
  }

  const TASK_STATUS = [
    { key: "todo", label: "未开始" },
    { key: "doing", label: "进行中" },
    { key: "done", label: "已完成" },
    { key: "deferred", label: "延期" },
  ];

  function taskStatusLabel(status) {
    return TASK_STATUS.find((s) => s.key === status)?.label || "未开始";
  }

  function normalizeTaskStatus(status) {
    if (status === "done") return "done";
    if (status === "doing") return "doing";
    if (status === "deferred") return "deferred";
    return "todo";
  }

  function renderTaskStatusBadge(t) {
    const st = normalizeTaskStatus(t.status);
    const ai = t.aiGenerated
      ? `<span class="tsk-status-badge is-ai">AI生成</span>`
      : "";
    return `${ai}<span class="tsk-status-badge is-${st}">${escapeHtml(taskStatusLabel(st))}</span>`;
  }

  function taskSourceLine(t) {
    const src = t.kind === "template" ? "模板" : t.kind === "month" ? "月任务" : "自定义";
    return `来源：${src} · ${priLabel(t.priority)}`;
  }

  function truncateCardSummary(text, maxLen = 18) {
    const s = String(text || "")
      .trim()
      .replace(/\s+/g, " ");
    if (!s) return "";
    if (s.length <= maxLen) return s;
    return `${s.slice(0, maxLen - 1)}…`;
  }

  function execResultSummary(t) {
    return truncateCardSummary(t.execResult);
  }

  function textToBulletLines(text, maxLines = 4) {
    const lines = String(text || "")
      .split(/\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    const show = lines.slice(0, maxLines);
    const more = lines.length > maxLines;
    return { show, more };
  }

  function renderPopoverBullets(text, maxLines = 4) {
    const { show, more } = textToBulletLines(text, maxLines);
    if (!show.length) return "";
    return (
      show.map((l) => `<div class="tsk-pop-li">· ${escapeHtml(l)}</div>`).join("") +
      (more ? `<div class="tsk-pop-li is-more">…</div>` : "")
    );
  }

  function buildTaskPopoverHtml(t) {
    const st = taskStatusLabel(normalizeTaskStatus(t.status));
    const notesHtml = renderPopoverBullets(t.notes, 4);
    const resultRaw = String(t.execResult || "").trim();
    const resultLines = renderPopoverBullets(resultRaw, 4);
    const resultHtml = resultLines || `<div class="tsk-pop-li is-empty">尚未填写执行结果</div>`;
    return `<div class="tsk-pop-head">
        <strong class="tsk-pop-title">${escapeHtml(t.title)}</strong>
        <span class="tsk-pop-meta">${escapeHtml(priLabel(t.priority))} · ${escapeHtml(st)}</span>
      </div>
      <div class="tsk-pop-divider"></div>
      <div class="tsk-pop-section">
        <div class="tsk-pop-label">要点</div>
        ${notesHtml || `<div class="tsk-pop-li is-empty">暂无要点</div>`}
      </div>
      <div class="tsk-pop-section">
        <div class="tsk-pop-label">执行结果</div>
        ${resultHtml}
      </div>
      <div class="tsk-pop-divider"></div>
      <div class="tsk-pop-foot">左键打开编辑 · 右键改状态</div>`;
  }

  let popoverShowTimer = null;
  let popoverHideTimer = null;
  let popoverAnchor = null;

  function ensureTaskPopover() {
    let el = document.getElementById("tskCardPopover");
    if (!el) {
      el = document.createElement("div");
      el.id = "tskCardPopover";
      el.className = "tsk-card-popover";
      el.hidden = true;
      el.addEventListener("mouseenter", () => {
        clearTimeout(popoverHideTimer);
      });
      el.addEventListener("mouseleave", () => {
        scheduleHideTaskPopover();
      });
      document.body.appendChild(el);
    }
    return el;
  }

  function positionTaskPopover(pop, anchor) {
    const rect = anchor.getBoundingClientRect();
    const pw = 340;
    const gap = 8;
    let left = rect.right + gap;
    let top = rect.top;
    if (left + pw > window.innerWidth - 12) {
      left = Math.max(12, rect.left);
      top = rect.bottom + gap;
    }
    const maxTop = window.innerHeight - pop.offsetHeight - 12;
    if (top > maxTop) top = Math.max(12, maxTop);
    pop.style.width = `${pw}px`;
    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
  }

  function hideTaskPopover() {
    clearTimeout(popoverShowTimer);
    clearTimeout(popoverHideTimer);
    popoverAnchor = null;
    const el = document.getElementById("tskCardPopover");
    if (el) el.hidden = true;
  }

  function scheduleHideTaskPopover() {
    clearTimeout(popoverHideTimer);
    popoverHideTimer = setTimeout(hideTaskPopover, 150);
  }

  function showTaskPopoverForCard(card) {
    const id = card.getAttribute("data-task-id");
    const t = taskById(id);
    if (!t) return;
    const pop = ensureTaskPopover();
    pop.innerHTML = buildTaskPopoverHtml(t);
    pop.hidden = false;
    popoverAnchor = card;
    positionTaskPopover(pop, card);
  }

  function bindTaskCardPopover(root) {
    root?.querySelectorAll(".tsk-task-card").forEach((card) => {
      card.addEventListener("mouseenter", () => {
        clearTimeout(popoverHideTimer);
        clearTimeout(popoverShowTimer);
        popoverShowTimer = setTimeout(() => showTaskPopoverForCard(card), 200);
      });
      card.addEventListener("mouseleave", () => {
        clearTimeout(popoverShowTimer);
        scheduleHideTaskPopover();
      });
    });
  }

  let statusMenuEl = null;

  function closeStatusMenu() {
    statusMenuEl?.remove();
    statusMenuEl = null;
    document.removeEventListener("click", closeStatusMenu, true);
    document.removeEventListener("contextmenu", closeStatusMenu, true);
  }

  function setTaskStatus(id, status) {
    const t = taskById(id);
    if (!t) return;
    const prev = t.status;
    t.status = status;
    t.updatedAt = new Date().toISOString();
    if (status === "done") {
      t.completedAt = new Date().toISOString();
      upsertTask(t);
      if (prev !== "done" && t.repeatable) respawnRepeatable(t);
      if (t.monthItemId && t.monthKey) {
        updateMonthItem(t.monthKey, t.monthItemId, { status: "done" });
      }
    } else {
      t.completedAt = null;
      upsertTask(t);
    }
    renderAll();
  }

  function openTaskStatusMenu(x, y, taskId) {
    closeStatusMenu();
    const t = taskById(taskId);
    if (!t) return;
    const cur = normalizeTaskStatus(t.status);
    const menu = document.createElement("div");
    menu.className = "tsk-status-menu";
    menu.innerHTML = TASK_STATUS.map(
      (s) =>
        `<button type="button" class="tsk-status-menu-item${cur === s.key ? " on" : ""}" data-set-status="${escapeAttr(s.key)}">${escapeHtml(s.label)}</button>`
    ).join("");
    document.body.appendChild(menu);
    statusMenuEl = menu;
    const mw = menu.offsetWidth;
    const mh = menu.offsetHeight;
    let left = x;
    let top = y;
    if (left + mw > window.innerWidth - 8) left = window.innerWidth - mw - 8;
    if (top + mh > window.innerHeight - 8) top = window.innerHeight - mh - 8;
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.querySelectorAll("[data-set-status]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        setTaskStatus(taskId, btn.getAttribute("data-set-status"));
        closeStatusMenu();
      });
    });
    setTimeout(() => {
      document.addEventListener("click", closeStatusMenu, true);
      document.addEventListener("contextmenu", closeStatusMenu, true);
    }, 0);
  }

  function bindTaskCardContextMenu(root) {
    root?.querySelectorAll(".tsk-task-card").forEach((card) => {
      card.addEventListener("contextmenu", (e) => {
        if (e.target.closest(".tsk-card-menu")) return;
        e.preventDefault();
        hideTaskPopover();
        openTaskStatusMenu(e.clientX, e.clientY, card.getAttribute("data-task-id"));
      });
    });
  }

  function bindTaskCardInteractions(root) {
    bindTaskCardPopover(root);
    bindTaskCardContextMenu(root);
  }

  function renderKanbanTaskCard(t, opts = {}) {
    const {
      draggable = false,
      catalog = false,
      compact = false,
      done: forceDone,
      extraClass = "",
      actionsHtml = "",
    } = opts;
    const isCatalog = catalog || isTemplateCatalog(t);
    const done = forceDone ?? t.status === "done";
    const summary = execResultSummary(t);
    const priColor = priBarColor(t.priority);
    const dragAttr = draggable ? ' draggable="true"' : "";
    const planCls = draggable ? " tsk-plan-card" : "";
    const catCls = isCatalog ? " tsk-catalog-card" : "";
    const typeCls = opts.exec ? " tsk-exec-card" : opts.backlog ? " tsk-backlog-card" : "";
    const showCatBadge = opts.backlog || opts.plan;
    const catBadge = showCatBadge ? renderCardCatBadge(t) : "";
    return `<article class="tsk-card tsk-task-card tsk-hover-card${typeCls}${planCls}${catCls}${done ? " is-done" : ""}${compact ? " is-compact" : ""}${extraClass || ""}"
      ${dragAttr} data-task-id="${escapeAttr(t.id)}"${isCatalog ? ' data-template-catalog="1"' : ""}>
      <div class="tsk-card-pri-bar" style="background:${priColor}"></div>
      <div class="tsk-card-inner">
        <div class="tsk-card-body is-openable" data-task-open="${escapeAttr(t.id)}" role="button" tabindex="0">
          ${catBadge}
          <span class="tsk-card-title">${escapeHtml(t.title)}</span>
          <span class="meta tsk-card-source">${escapeHtml(taskSourceLine(t))}</span>
          <div class="tsk-card-footline">
            ${renderTaskStatusBadge(t)}${summary ? `<span class="tsk-card-summary">${escapeHtml(summary)}</span>` : ""}
          </div>
        </div>
        ${actionsHtml ? `<div class="tsk-card-actions">${actionsHtml}</div>` : ""}
      </div>
    </article>`;
  }

  function catTagClass(categoryId) {
    return TD().CAT_COLORS?.[categoryId] || "misc";
  }

  function renderCardCatBadge(t) {
    const name = TD().catLabel(t.categoryId);
    const cls = catTagClass(t.categoryId);
    return `<span class="tsk-card-cat tsk-tag cat-${escapeAttr(cls)}">${escapeHtml(name)}</span>`;
  }

  function loadWeekNote(wk) {
    try {
      const all = JSON.parse(localStorage.getItem(LS_NOTES) || "{}") || {};
      return (
        all[wk] || {
          highlights: [
            { text: "先做工作台，再做统计", tone: "must" },
            { text: "模板不要超过 8 条", tone: "must" },
            { text: "操盘观察可降为自定义", tone: "defer" },
          ],
          monthGoals: [],
        }
      );
    } catch (_) {
      return { highlights: [], monthGoals: [] };
    }
  }

  function saveWeekNote(wk, note) {
    try {
      const all = JSON.parse(localStorage.getItem(LS_NOTES) || "{}") || {};
      all[wk] = note;
      localStorage.setItem(LS_NOTES, JSON.stringify(all));
    } catch (_) {
      /* ignore */
    }
  }

  function weekProgressDetail(wk) {
    const items = scheduledTasks(tasksForWeek(wk));
    const tpl = items.filter((t) => t.kind === "template");
    const custom = items.filter((t) => t.kind !== "template");
    const tplDone = tpl.filter((t) => t.status === "done").length;
    const customDone = custom.filter((t) => t.status === "done").length;
    const done = tplDone + customDone;
    const total = items.length;
    return {
      done,
      total,
      rate: total ? Math.round((done / total) * 100) : 0,
      tplDone,
      tplTotal: tpl.length,
      customDone,
      customTotal: custom.length,
    };
  }

  function renderTaskRow(t, { showDay, fullTitle } = {}) {
    const cat = TD().catLabel(t.categoryId);
    const day = showDay && isScheduled(t) ? TD().DAY_NAME[t.daySlot] : "";
    return `<div class="tsk-task-row">
      <label class="tsk-task-row-main${fullTitle ? " is-full" : ""}">
        <input type="checkbox" data-task-done="${escapeAttr(t.id)}" ${t.status === "done" ? "checked" : ""} />
        <span>${escapeHtml(t.title)}</span>
      </label>
      <span class="tsk-tag cat-${escapeAttr(catTagClass(t.categoryId))}">${escapeHtml(cat)}${day ? ` · ${escapeHtml(day)}` : ""}</span>
    </div>`;
  }

  function renderHighlightRow(item, idx) {
    const tone = item.tone === "defer" ? "dim" : "ok";
    return `<div class="tsk-task-row tsk-highlight-row">
      <input type="text" class="tsk-highlight-input" data-hl-idx="${idx}" value="${escapeAttr(item.text || "")}" />
      <span class="tsk-tag ${tone}">${item.tone === "defer" ? "可延后" : "必须"}</span>
    </div>`;
  }

  function updateWeekChip() {
    const el = $("#tasksWeekChip");
    if (!el) return;
    if (state.mode === "months" && state.monthsKey) {
      el.textContent = monthLabel(state.monthsKey);
    } else {
      el.textContent = weekRangeLabel(activeWeekKey());
    }
  }

  function monthGoalsCount(plan) {
    return (plan?.goals || []).filter((g) => String(g).trim()).length;
  }

  function weekShortRange(wk) {
    const r = weekDateRange(wk);
    const f = (d) => `${d.getMonth() + 1}/${d.getDate()}`;
    return `${f(r.start)}–${f(r.end)}`;
  }

  function monthSummaryStats(mk, plan) {
    const goals = monthGoalsCount(plan);
    const pool = (plan.items || []).filter((i) => i.status === "planned" && !i.targetWeekId).length;
    const weekCount = weeksInMonth(mk).length;
    const completed = scheduledTasks(tasksForMonth(mk)).filter((t) => t.status === "done").length;
    return { goals, pool, weekCount, completed };
  }

  function monthIsFullyEmpty(mk, plan) {
    if (monthHasContent(plan)) return false;
    return !weeksInMonth(mk).some((wk) => weekProgress(wk).total > 0);
  }

  function monthNavDot(mk) {
    const phase = monthPhase(mk);
    const hasContent = monthHasContent(getMonthPlan(mk));
    if (phase === "past") return "—";
    if (phase === "current") return "●";
    if (hasContent) return "○";
    return "·";
  }

  function monthNavHint(mk) {
    const phase = monthPhase(mk);
    const plan = getMonthPlan(mk);
    const goalsN = monthGoalsCount(plan);
    const hasContent = monthHasContent(plan);
    if (phase === "past") return "历史";
    if (phase === "current") return goalsN ? `本月 · ${goalsN} 条主线` : "本月";
    if (hasContent) return "已规划";
    return "";
  }

  function renderMonthNavItem(mk, selMk) {
    const p = parseMonthKey(mk);
    const phase = monthPhase(mk);
    const hint = monthNavHint(mk);
    const dot = monthNavDot(mk);
    return `<button type="button" class="tsk-month-nav-item${mk === selMk ? " on" : ""} is-${phase}" data-pick-month="${escapeAttr(mk)}">
      <span class="tsk-month-nav-dot is-${phase}${dot === "●" ? " filled" : ""}${dot === "○" ? " ring" : ""}">${dot}</span>
      <span class="tsk-month-nav-label">${p?.month || ""} 月</span>
      ${hint ? `<span class="tsk-month-nav-hint muted">${escapeHtml(hint)}</span>` : ""}
    </button>`;
  }

  function buildMonthNavHtml(year, selMk) {
    const upcoming = [];
    const past = [];
    for (let m = 1; m <= 12; m += 1) {
      const mk = `${year}-${String(m).padStart(2, "0")}`;
      if (monthPhase(mk) === "past") past.push(mk);
      else upcoming.push(mk);
    }
    past.reverse();
    const parts = upcoming.map((mk) => renderMonthNavItem(mk, selMk));
    if (upcoming.length && past.length) {
      parts.push('<div class="tsk-month-nav-sep" aria-hidden="true"></div>');
    }
    past.forEach((mk) => parts.push(renderMonthNavItem(mk, selMk)));
    return parts.join("");
  }

  function renderMonthSummaryBar(stats) {
    return `<div class="tsk-month-summary">主线 ${stats.goals} · 月池 ${stats.pool} · ${stats.weekCount} 周 · 完成 ${stats.completed}</div>`;
  }

  function renderWeekRows(weeks, { readOnly } = {}) {
    if (!weeks.length) return "";
    return weeks
      .map((wk) => {
        const p = weekProgress(wk);
        const range = weekShortRange(wk);
        const n = weekNumber(wk);
        const p0 = tasksForWeek(wk).filter(
          (t) => t.priority === "must" && t.status !== "done" && t.status !== "cancelled" && isScheduled(t)
        ).length;
        const prog = `${p.done}/${p.total}${p0 ? ` · P0 ${p0}` : ""}`;
        if (readOnly) {
          return `<div class="tsk-week-row is-readonly">
            <span class="tsk-week-row-w">W${n}</span>
            <span class="tsk-week-row-range">${range}</span>
            <span class="tsk-week-row-prog muted">${prog}</span>
          </div>`;
        }
        return `<button type="button" class="tsk-week-row" data-open-week="${escapeAttr(wk)}">
          <span class="tsk-week-row-w">W${n}</span>
          <span class="tsk-week-row-range">${range}</span>
          <span class="tsk-week-row-prog">${prog}</span>
          <span class="tsk-week-row-go">进入这周 →</span>
        </button>`;
      })
      .join("");
  }

  function shiftActiveWeek(delta) {
    const r = weekDateRange(activeWeekKey());
    const d = new Date(r.start);
    d.setDate(d.getDate() + delta * 7);
    state.boardWeek = weekKey(d);
    saveBoardPrefs();
    renderAll();
  }

  function isScheduled(t) {
    const s = Number(t?.daySlot);
    const max = TD().WEEKEND_SLOT || 6;
    return s >= 1 && s <= max;
  }

  function isBacklog(t) {
    return !isScheduled(t);
  }

  function isTemplateCatalog(t) {
    return !!t?.templateCatalog;
  }

  function catalogInstanceKey(wk, templateKey) {
    return `${wk}|catalog|${templateKey}`;
  }

  function migrateTask(t) {
    const x = { ...t };
    if (x.daySlot === undefined || x.daySlot === null) x.daySlot = 0;
    x.daySlot = Number(x.daySlot);
    if (!Number.isFinite(x.daySlot)) x.daySlot = 0;
    x.repeatable = !!x.repeatable;
    x.templateCatalog = !!x.templateCatalog;
    x.notes = String(x.notes || "").trim();
    x.execResult = String(x.execResult || "").trim();
    x.aiGenerated = !!x.aiGenerated;
    if (x.status === "cancelled") {
      /* keep */
    } else if (!["todo", "doing", "done", "deferred"].includes(x.status)) {
      x.status = x.status === "done" ? "done" : "todo";
    }
    const so = Number(x.sortOrder);
    x.sortOrder = Number.isFinite(so) ? so : Date.parse(x.createdAt || "") || Date.now();
    return x;
  }

  function taskSortKey(t) {
    const o = Number(t?.sortOrder);
    return Number.isFinite(o) ? o : Date.parse(t?.createdAt || "") || 0;
  }

  function sortTasksByOrder(tasks) {
    return [...tasks].sort(
      (a, b) => taskSortKey(a) - taskSortKey(b) || String(a.id).localeCompare(String(b.id))
    );
  }

  /** 待排区固定顺序：模板池按模板定义序，自定义待排按创建时间。不可拖拽排序。 */
  function backlogTasks(wk) {
    const catalog = templateCatalogTasks(wk);
    const custom = tasksForWeek(wk)
      .filter((t) => isBacklog(t) && !isTemplateCatalog(t) && t.status !== "cancelled")
      .sort((a, b) => {
        const ca = Date.parse(a.createdAt || "") || 0;
        const cb = Date.parse(b.createdAt || "") || 0;
        return ca - cb || String(a.id).localeCompare(String(b.id));
      });
    return [...catalog, ...custom];
  }

  function columnTasks(wk, daySlot) {
    const day = Number(daySlot);
    if (day === 0) return backlogTasks(wk);
    return sortTasksByOrder(
      tasksForWeek(wk).filter((t) => t.status !== "cancelled" && isScheduled(t) && t.daySlot === day)
    );
  }

  function applyColumnSortOrders(wk, daySlot, orderedIds) {
    const store = loadStore();
    orderedIds.forEach((id, i) => {
      const row = store.tasks.find((t) => t.id === id);
      if (row) {
        row.sortOrder = (i + 1) * 1000;
        row.updatedAt = new Date().toISOString();
      }
    });
    saveStore(store);
  }

  function reorderTaskInColumn(taskId, daySlot, insertBeforeId, wk = activeWeekKey()) {
    const t = taskById(taskId);
    if (!t) return false;
    const day = Number(daySlot);
    if (isTemplateCatalog(t) && day > 0) return spawnFromCatalog(taskId, day);

    // 待排区：顺序固定，仅允许从日程列拖回（不插入指定位置）
    if (day === 0) {
      if (isTemplateCatalog(t) || t.daySlot === 0) return false;
      return moveTaskDay(taskId, 0, { force: true });
    }

    const sameCol = t.weekKey === wk && t.daySlot === day;
    if (!sameCol) {
      if (isTemplateCatalog(t)) return false;
      if (!moveTaskDay(taskId, day, { force: true })) return false;
    }

    const moved = taskById(taskId);
    if (!moved) return false;
    let column = columnTasks(wk, day).filter((x) => x.id !== taskId);
    let idx = insertBeforeId ? column.findIndex((x) => x.id === insertBeforeId) : column.length;
    if (idx < 0) idx = column.length;
    column.splice(idx, 0, moved);
    applyColumnSortOrders(
      wk,
      day,
      column.map((x) => x.id)
    );
    return true;
  }

  function dropInsertBeforeId(body, clientY, dragId) {
    const cards = [...body.querySelectorAll(".tsk-plan-card, .tsk-backlog-card")].filter(
      (c) => !c.classList.contains("is-dragging") && c.getAttribute("data-task-id") !== dragId
    );
    for (const card of cards) {
      const rect = card.getBoundingClientRect();
      if (clientY < rect.top + rect.height / 2) return card.getAttribute("data-task-id");
    }
    return null;
  }

  function clearDropIndicators(root) {
    root?.querySelectorAll(".tsk-drop-indicator").forEach((el) => el.remove());
    root?.querySelectorAll(".tsk-kcol-body.is-drag-over").forEach((el) => el.classList.remove("is-drag-over"));
  }

  function showDropIndicator(body, beforeId) {
    const root = body.closest(".tsk-kanban") || body;
    clearDropIndicators(root);
    body.classList.add("is-drag-over");
    const line = document.createElement("div");
    line.className = "tsk-drop-indicator";
    if (beforeId) {
      const target = [...body.querySelectorAll("[data-task-id]")].find(
        (el) => el.getAttribute("data-task-id") === beforeId
      );
      if (target) body.insertBefore(line, target);
      else body.appendChild(line);
    } else {
      body.appendChild(line);
    }
  }

  function emptyStore() {
    return { tasks: [], templateApplied: {}, catalogDismissed: {}, instanceDismissed: {} };
  }

  function ensureDismissed(store) {
    if (!store.catalogDismissed) store.catalogDismissed = {};
    if (!store.instanceDismissed) store.instanceDismissed = {};
    return store;
  }

  function dismissedCatalogKeys(store, wk) {
    ensureDismissed(store);
    return new Set(store.catalogDismissed[wk] || []);
  }

  function dismissCatalog(store, wk, templateKey) {
    if (!templateKey) return;
    ensureDismissed(store);
    const set = new Set(store.catalogDismissed[wk] || []);
    set.add(templateKey);
    store.catalogDismissed[wk] = [...set];
  }

  function dismissInstance(store, wk, instanceKey) {
    if (!instanceKey) return;
    ensureDismissed(store);
    const set = new Set(store.instanceDismissed[wk] || []);
    set.add(instanceKey);
    store.instanceDismissed[wk] = [...set];
  }

  function clearInstanceDismissed(store, wk, instanceKey) {
    if (!instanceKey) return;
    ensureDismissed(store);
    const list = store.instanceDismissed[wk];
    if (!list?.length) return;
    store.instanceDismissed[wk] = list.filter((k) => k !== instanceKey);
  }

  function loadStore() {
    try {
      const raw = localStorage.getItem(LS_STORE);
      if (!raw) return emptyStore();
      const data = JSON.parse(raw);
      if (!data?.tasks) return emptyStore();
      data.tasks = data.tasks.map(migrateTask);
      if (!data.templateApplied) data.templateApplied = {};
      ensureDismissed(data);
      return data;
    } catch (_) {
      return emptyStore();
    }
  }

  function saveStore(data) {
    localStorage.setItem(LS_STORE, JSON.stringify(data));
    refreshTabCount();
  }

  function allTasks() {
    return loadStore().tasks;
  }

  function taskById(id) {
    return allTasks().find((t) => t.id === id) || null;
  }

  function upsertTask(task) {
    const store = loadStore();
    const i = store.tasks.findIndex((t) => t.id === task.id);
    if (i >= 0) store.tasks[i] = task;
    else store.tasks.unshift(task);
    saveStore(store);
    return task;
  }

  function deleteTask(id) {
    const store = loadStore();
    const task = store.tasks.find((t) => t.id === id);
    if (task) {
      const wk = task.weekKey;
      if (isTemplateCatalog(task) && task.templateKey) {
        dismissCatalog(store, wk, task.templateKey);
      } else if (task.instanceKey) {
        dismissInstance(store, wk, task.instanceKey);
      }
    }
    store.tasks = store.tasks.filter((t) => t.id !== id);
    saveStore(store);
  }

  function tasksForWeek(wk) {
    return allTasks().filter((t) => t.weekKey === wk);
  }

  function tasksForMonth(mk) {
    return allTasks().filter((t) => t.monthKey === mk);
  }

  function scheduledTasks(tasks) {
    return tasks.filter((t) => isScheduled(t) && t.status !== "cancelled");
  }

  function refreshTabCount() {
    const today = todayDaySlot();
    const wk = weekKey();
    let n = 0;
    if (today) {
      n = tasksForWeek(wk).filter(
        (t) => t.daySlot === today && t.status !== "done" && t.status !== "cancelled"
      ).length;
    }
    const el = $("#countTasks");
    if (el) el.textContent = String(n);
  }

  function loadTemplateOverrides() {
    try {
      return JSON.parse(localStorage.getItem(LS_TPL_CFG) || "{}") || {};
    } catch (_) {
      return {};
    }
  }

  function saveTemplateOverride(key, patch) {
    const cfg = loadTemplateOverrides();
    cfg[key] = { ...(cfg[key] || {}), ...patch };
    localStorage.setItem(LS_TPL_CFG, JSON.stringify(cfg));
  }

  function loadCustomTemplates() {
    try {
      const raw = JSON.parse(localStorage.getItem(LS_TPL_CUSTOM) || "[]");
      return Array.isArray(raw) ? raw : [];
    } catch (_) {
      return [];
    }
  }

  function saveCustomTemplates(list) {
    localStorage.setItem(LS_TPL_CUSTOM, JSON.stringify(list));
  }

  function isBuiltinTemplateKey(key) {
    return TD().WEEKLY_TEMPLATES.some((t) => t.key === key);
  }

  function isCustomTemplateKey(key) {
    return loadCustomTemplates().some((t) => t.key === key);
  }

  function mergeTemplateOverride(tpl, ov) {
    const o = ov[tpl.key];
    if (!o) return { ...tpl };
    return {
      ...tpl,
      title: o.title !== undefined ? o.title : tpl.title,
      notes: o.notes !== undefined ? o.notes : tpl.notes || "",
      priority: o.priority || tpl.priority,
      slot: o.slot !== undefined ? o.slot : tpl.slot || "",
      scheduleKind: o.scheduleKind || tpl.scheduleKind,
      weekdays: Array.isArray(o.weekdays) ? o.weekdays : tpl.weekdays,
    };
  }

  function getEffectiveTemplates() {
    const ov = loadTemplateOverrides();
    const seen = new Set();
    const merged = [];
    [...TD().WEEKLY_TEMPLATES, ...loadCustomTemplates()].forEach((tpl) => {
      if (seen.has(tpl.key) || ov[tpl.key]?.hidden) return;
      seen.add(tpl.key);
      merged.push(mergeTemplateOverride(tpl, ov));
    });
    return merged;
  }

  function activeTemplateKeys() {
    return new Set(getEffectiveTemplates().map((t) => t.key));
  }

  function addTemplateFromSubcategory(subcategoryId) {
    const key = TD().templateKeyForSub(subcategoryId);
    if (activeTemplateKeys().has(key)) {
      if (typeof toast === "function") toast("该小类已在模板池中", "error");
      return false;
    }
    const tpl = TD().makeWeeklyTemplateBySubId(subcategoryId);
    if (!tpl) {
      if (typeof toast === "function") toast("小类不存在", "error");
      return false;
    }
    if (!isBuiltinTemplateKey(key)) {
      const list = loadCustomTemplates();
      if (!list.some((t) => t.key === key)) {
        list.push(tpl);
        saveCustomTemplates(list);
      }
    }
    saveTemplateOverride(key, { hidden: false });
    if (typeof toast === "function") toast(`已加入模板：${tpl.title}`, "ok");
    return true;
  }

  function removeTemplateFromPool(key) {
    if (isCustomTemplateKey(key)) {
      saveCustomTemplates(loadCustomTemplates().filter((t) => t.key !== key));
    } else if (isBuiltinTemplateKey(key)) {
      saveTemplateOverride(key, { hidden: true });
    }
  }

  function renderTemplateRow(tpl) {
    const days = TD().formatTemplateDays(tpl);
    const kind = TD().SCHEDULE_KIND_LABEL[tpl.scheduleKind] || tpl.scheduleKind;
    const custom = isCustomTemplateKey(tpl.key);
    return `<div class="tsk-tpl-row" data-tpl-key="${escapeAttr(tpl.key)}">
      <div>
        <strong>${escapeHtml(tpl.title)}</strong>
        <span class="muted">${escapeHtml(TD().subLabel(tpl.subcategoryId))} · ${escapeHtml(kind)} · ${escapeHtml(days)}${custom ? " · 自定义" : ""}</span>
      </div>
      <label class="field" style="margin:0;min-width:160px"><span>默认周几（1-6 逗号，6=周末）</span>
        <input type="text" class="tsk-tpl-days" value="${escapeAttr((tpl.weekdays || []).join(","))}" />
      </label>
      <div class="tsk-tpl-row-actions">
        <select class="tsk-tpl-kind">
          <option value="once"${tpl.scheduleKind === "once" ? " selected" : ""}>只做一次</option>
          <option value="weekdays"${tpl.scheduleKind === "weekdays" ? " selected" : ""}>工作日</option>
          <option value="days"${tpl.scheduleKind === "days" ? " selected" : ""}>指定几天</option>
        </select>
        <button type="button" class="btn-link xs" data-tpl-remove="${escapeAttr(tpl.key)}">移除</button>
      </div>
    </div>`;
  }

  function refreshTplSubOptions() {
    const catSel = $("#tplAddCategory");
    const subSel = $("#tplAddSub");
    if (!catSel || !subSel) return;
    const cat = TD().getCategory(catSel.value);
    const inPool = activeTemplateKeys();
    subSel.innerHTML = (cat?.subs || [])
      .map((s) => {
        const key = TD().templateKeyForSub(s.id);
        const has = inPool.has(key);
        return `<option value="${escapeAttr(s.id)}"${has ? " disabled" : ""}>${escapeHtml(s.name)}${has ? " · 已有" : ""}</option>`;
      })
      .join("");
  }

  function syncTaskToTemplate(task) {
    if (!task?.templateKey) return false;
    saveTemplateOverride(task.templateKey, {
      title: task.title,
      notes: task.notes || "",
      priority: task.priority,
      slot: task.slot || "",
    });
    if (typeof toast === "function") toast("已同步到模板 · 之后新生成的周会沿用", "ok");
    return true;
  }

  function slotToDate(wk, daySlot) {
    const slot = Number(daySlot);
    if (!slot || slot < 1) return "";
    const r = weekDateRange(wk);
    const d = new Date(r.start);
    d.setDate(d.getDate() + (slot === 6 ? 5 : slot - 1));
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function taskDrawerHeading(t) {
    if (isTemplateCatalog(t)) return `待排 · ${t.title || "任务"} · 模板池`;
    const day = isScheduled(t) ? TD().DAY_NAME[t.daySlot] || "" : "待排";
    const date = isScheduled(t) ? slotToDate(t.weekKey, t.daySlot) : "";
    return `${day} · ${t.title || "任务"}${date ? ` · ${date}` : ""}`;
  }

  function refreshTaskInstanceKey(task) {
    if (task.kind === "template" && task.templateKey && isScheduled(task)) {
      task.instanceKey = TD().instanceDedupKey(task.weekKey, task.templateKey, task.daySlot);
    }
  }

  function copyTaskToDay(id, daySlot) {
    const t = taskById(id);
    if (!t) return;
    const slot = Number(daySlot);
    if (isTemplateCatalog(t) && slot) {
      spawnFromCatalog(id, slot);
      return;
    }
    upsertTask(
      makeTask({
        title: t.title,
        notes: t.notes,
        categoryId: t.categoryId,
        subcategoryId: t.subcategoryId,
        priority: t.priority,
        slot: t.slot,
        kind: "custom",
        daySlot: Number.isFinite(slot) ? slot : 0,
        weekKey: t.weekKey,
      })
    );
    if (typeof toast === "function") toast("已复制", "ok");
  }

  function weekIsGenerated(wk) {
    return !!loadStore().templateApplied[wk];
  }

  function makeTask(partial) {
    const now = new Date().toISOString();
    const d = partial.createdAt ? new Date(partial.createdAt) : new Date();
    let daySlot = 0;
    if (partial.daySlot !== undefined && partial.daySlot !== null && partial.daySlot !== "") {
      daySlot = Number(partial.daySlot);
    } else if (partial.priority === "inspiration") {
      daySlot = 0;
    }
    if (!Number.isFinite(daySlot)) daySlot = 0;

    return migrateTask({
      id: partial.id || uid(),
      title: String(partial.title || "").trim(),
      notes: String(partial.notes || "").trim(),
      execResult: String(partial.execResult || "").trim(),
      categoryId: partial.categoryId || "misc",
      subcategoryId: partial.subcategoryId || "misc.adhoc",
      priority: partial.priority || "defer",
      kind: partial.kind || "custom",
      templateKey: partial.templateKey || "",
      instanceKey: partial.instanceKey || "",
      monthItemId: partial.monthItemId || "",
      status: partial.status || "todo",
      weekKey: partial.weekKey || weekKey(d),
      monthKey: partial.monthKey || monthKey(d),
      daySlot,
      weeklyMain: !!partial.weeklyMain,
      monthlyMainline: !!partial.monthlyMainline,
      slot: partial.slot || "",
      repeatable: !!partial.repeatable,
      templateCatalog: !!partial.templateCatalog,
      aiGenerated: !!partial.aiGenerated,
      sortOrder: partial.sortOrder ?? Date.now(),
      createdAt: partial.createdAt || now,
      updatedAt: now,
      completedAt: partial.completedAt || null,
    });
  }

  function ensureTemplateCatalog(wk) {
    const store = loadStore();
    const existingKeys = new Set(
      store.tasks.filter((t) => t.weekKey === wk && t.instanceKey).map((t) => t.instanceKey)
    );
    const dismissed = dismissedCatalogKeys(store, wk);
    let added = 0;
    getEffectiveTemplates().forEach((tpl) => {
      if (dismissed.has(tpl.key)) return;
      const ckey = catalogInstanceKey(wk, tpl.key);
      if (existingKeys.has(ckey)) return;
      store.tasks.unshift(
        makeTask({
          title: tpl.title,
          notes: tpl.notes || "",
          categoryId: tpl.categoryId,
          subcategoryId: tpl.subcategoryId,
          priority: tpl.priority,
          kind: "template",
          templateKey: tpl.key,
          instanceKey: ckey,
          templateCatalog: true,
          daySlot: 0,
          slot: tpl.slot || "",
          weekKey: wk,
        })
      );
      existingKeys.add(ckey);
      added += 1;
    });
    if (added) saveStore(store);
    return added;
  }

  function templateCatalogTasks(wk) {
    const order = new Map(getEffectiveTemplates().map((t, i) => [t.key, i]));
    return tasksForWeek(wk)
      .filter((t) => isTemplateCatalog(t) && t.status !== "cancelled" && order.has(t.templateKey))
      .sort((a, b) => (order.get(a.templateKey) ?? 99) - (order.get(b.templateKey) ?? 99));
  }

  function pruneOrphanCatalog(wk) {
    const valid = new Set(getEffectiveTemplates().map((t) => t.key));
    const store = loadStore();
    const next = store.tasks.filter(
      (t) => !(t.weekKey === wk && isTemplateCatalog(t) && t.templateKey && !valid.has(t.templateKey))
    );
    if (next.length !== store.tasks.length) {
      store.tasks = next;
      saveStore(store);
    }
  }

  function spawnFromCatalog(catalogId, daySlot) {
    const cat = taskById(catalogId);
    const slot = Number(daySlot);
    if (!cat?.templateCatalog || !cat.templateKey || !slot) return false;
    const wk = cat.weekKey;
    const ikey = TD().instanceDedupKey(wk, cat.templateKey, slot);
    const exists = allTasks().some((t) => t.weekKey === wk && t.instanceKey === ikey && t.status !== "cancelled");
    if (exists) {
      if (typeof toast === "function") toast("该日已有这条模板任务", "error");
      return false;
    }
    const tpl = getEffectiveTemplates().find((x) => x.key === cat.templateKey);
    const store = loadStore();
    clearInstanceDismissed(store, wk, ikey);
    saveStore(store);
    upsertTask(
      makeTask({
        title: cat.title || tpl?.title || "",
        notes: cat.notes || tpl?.notes || "",
        categoryId: cat.categoryId || tpl?.categoryId,
        subcategoryId: cat.subcategoryId || tpl?.subcategoryId,
        priority: cat.priority || tpl?.priority,
        kind: "template",
        templateKey: cat.templateKey,
        instanceKey: ikey,
        daySlot: slot,
        slot: cat.slot || tpl?.slot || "",
        weekKey: wk,
        templateCatalog: false,
      })
    );
    if (typeof toast === "function") toast(`已排入${TD().DAY_NAME[slot] || ""}`, "ok");
    return true;
  }

  function applyWeeklyTemplate(opts = {}) {
    const refill = !!opts.refill;
    const wk = opts.weekKey || activeWeekKey();
    const store = loadStore();
    const already = !!store.templateApplied[wk];
    if (!refill && already) {
      if (typeof toast === "function") toast("这一周已生成 · 空位请用「填格」", "error");
      return 0;
    }
    const existingKeys = new Set(
      store.tasks.filter((t) => t.weekKey === wk && t.instanceKey).map((t) => t.instanceKey)
    );
    const instanceDismissed = new Set(store.instanceDismissed[wk] || []);
    let added = 0;
    getEffectiveTemplates().forEach((tpl) => {
      TD().expandTemplateSlots(tpl).forEach((slot) => {
        if (!slot.daySlot) return;
        const ikey = TD().instanceDedupKey(wk, tpl.key, slot.daySlot);
        if (existingKeys.has(ikey)) return;
        if (instanceDismissed.has(ikey)) return;
        const task = makeTask({
          title: tpl.title,
          notes: tpl.notes || "",
          categoryId: tpl.categoryId,
          subcategoryId: tpl.subcategoryId,
          priority: tpl.priority,
          kind: "template",
          templateKey: tpl.key,
          instanceKey: ikey,
          daySlot: slot.daySlot,
          slot: tpl.slot || "",
          weekKey: wk,
        });
        store.tasks.unshift(task);
        existingKeys.add(ikey);
        added += 1;
      });
    });
    if (!refill) {
      const monthAdded = applyMonthItemsToWeek(wk);
      added += monthAdded;
    }
    if (!already) store.templateApplied[wk] = new Date().toISOString();
    saveStore(store);
    ensureTemplateCatalog(wk);
    const backlog = store.tasks.filter(
      (t) => t.weekKey === wk && isBacklog(t) && !isTemplateCatalog(t) && t.status !== "cancelled"
    ).length;
    if (typeof toast === "function") {
      const msg = refill
        ? added
          ? `填格 +${added} 条`
          : "没有空位可填"
        : added
          ? `已生成 ${added} 条 · 待排 ${backlog}`
          : "模板实例已齐";
      toast(msg, added || refill ? "ok" : "error");
      if (!refill && backlog > 3) toast("待排期 >3：请打开「模板」改默认星期", "error");
    }
    return added;
  }

  function quickCapture(title, notes) {
    const t = String(title || "").trim();
    if (!t) return;
    upsertTask(
      makeTask({
        title: t,
        notes: String(notes || "").trim(),
        priority: "inspiration",
        daySlot: 0,
        kind: "custom",
        categoryId: "misc",
        subcategoryId: "misc.adhoc",
        repeatable: false,
      })
    );
    if (typeof toast === "function") toast("已加入待排期", "ok");
  }

  function cloneBacklogTask(source, patch = {}) {
    return makeTask({
      title: source.title,
      notes: source.notes,
      categoryId: source.categoryId,
      subcategoryId: source.subcategoryId,
      priority: source.priority,
      kind: "custom",
      daySlot: 0,
      weekKey: activeWeekKey(),
      repeatable: !!source.repeatable,
      ...patch,
    });
  }

  function duplicateBacklogTask(id) {
    const t = taskById(id);
    if (!t) return;
    upsertTask(cloneBacklogTask(t));
    if (typeof toast === "function") toast("已复制到待排期", "ok");
  }

  function respawnRepeatable(task) {
    if (!task?.repeatable) return;
    upsertTask(
      cloneBacklogTask(task, {
        status: "todo",
        daySlot: 0,
        completedAt: null,
      })
    );
  }

  function toggleDone(task) {
    const done = task.status === "done";
    task.status = done ? "todo" : "done";
    task.completedAt = done ? null : new Date().toISOString();
    task.updatedAt = new Date().toISOString();
    upsertTask(task);
    if (!done && task.repeatable) respawnRepeatable(task);
    if (!done && task.monthItemId && task.monthKey) {
      updateMonthItem(task.monthKey, task.monthItemId, { status: "done" });
    }
  }

  function weekProgress(wk) {
    const d = weekProgressDetail(wk);
    return { done: d.done, total: d.total, rate: d.rate };
  }

  function dayLoad(wk, daySlot, excludeId) {
    const items = tasksForWeek(wk).filter(
      (t) => t.daySlot === daySlot && t.status !== "cancelled" && t.status !== "done" && t.id !== excludeId
    );
    return { total: items.length, p0: items.filter((t) => t.priority === "must").length };
  }

  function dayLimitWarning(wk, daySlot, task, excludeId) {
    const max = TD().WEEKEND_SLOT || 6;
    if (!daySlot || daySlot < 1 || daySlot > max) return "";
    const load = dayLoad(wk, daySlot, excludeId);
    const lim = TD().DAY_LIMITS;
    const isP0 = task?.priority === "must";
    if (load.total >= lim.total) return `该日已有 ${load.total} 条（建议 ≤${lim.total}）`;
    if (isP0 && load.p0 >= lim.p0) return `该日 P0 已有 ${load.p0} 条`;
    if (isP0 && load.p0 + 1 > lim.p0) return `移入后 P0 将超限`;
    if (load.total + 1 > lim.total) return `移入后总数将超限`;
    return "";
  }

  function moveTaskDay(id, daySlot, opts = {}) {
    const t = taskById(id);
    if (!t) return false;
    if (isTemplateCatalog(t)) {
      const slot = Number(daySlot);
      if (slot) return spawnFromCatalog(id, slot);
      return false;
    }
    const slot = Number(daySlot);
    const finalSlot = Number.isFinite(slot) ? slot : 0;
    const warn = dayLimitWarning(t.weekKey, finalSlot, t, t.id);
    if (warn && !opts.force) {
      if (typeof toast === "function") toast(warn, "error");
      return false;
    }
    t.daySlot = finalSlot;
    if (finalSlot === 0 && t.priority === "must") t.priority = "defer";
    t.updatedAt = new Date().toISOString();
    upsertTask(t);
    return true;
  }

  function moveToTomorrow(id) {
    const tm = tomorrowDaySlot();
    if (!tm) {
      moveTaskDay(id, 0, { force: true });
      if (typeof toast === "function") toast("已退回待排期", "ok");
    } else {
      moveTaskDay(id, tm);
      if (typeof toast === "function") {
        toast(isWeekendSlot(tm) ? "已移到周末" : tm === 1 && isWeekendSlot(todayDaySlot()) ? "已移到周一" : "已移到明天", "ok");
      }
    }
  }

  function orderedDaySlots() {
    const weekend = TD().WEEKEND_SLOT || 6;
    const work = (TD().PLAN_SLOTS || TD().WEEKDAY_SLOTS).filter((d) => d !== weekend);
    if (state.columnOrder === "desc") return [...work.reverse(), weekend];
    return [...work, weekend];
  }

  function taskMetaShort(t) {
    return taskSourceLine(t).replace(/^来源：/, "");
  }

  function taskScheduleHint(t) {
    if (!isScheduled(t)) return "未排期";
    return `已在${TD().DAY_NAME[t.daySlot] || ""}`;
  }

  function backlogColTitle() {
    return "待排";
  }

  function slotDateShort(wk, daySlot) {
    const slot = Number(daySlot);
    if (!slot || slot < 1) return "";
    const r = weekDateRange(wk);
    const d = new Date(r.start);
    d.setDate(d.getDate() + (slot === 6 ? 5 : slot - 1));
    return `${d.getMonth() + 1}.${d.getDate()}`;
  }

  function colHead(label, dateShort) {
    const date = dateShort
      ? `<span class="tsk-kcol-date">${escapeHtml(dateShort)}</span>`
      : "";
    return `<header class="tsk-kcol-head"><span class="tsk-kcol-title">${escapeHtml(label)}</span>${date}</header>`;
  }

  function dayColHead(wk, daySlot, { highlightToday } = {}) {
    const dayName = TD().DAY_NAME[daySlot] || "周末";
    const dateStr = slotDateShort(wk, daySlot);
    const text = highlightToday ? `${dayName} ${dateStr} · 今天` : `${dayName} ${dateStr}`;
    return `<header class="tsk-kcol-head day-head${highlightToday ? " is-today-head" : ""}"><span class="tsk-kcol-title">${escapeHtml(text)}</span></header>`;
  }

  function scrollToTodayColumn(root) {
    const col = root?.querySelector(".tsk-kanban-day.is-today");
    if (!col) return;
    requestAnimationFrame(() => {
      col.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    });
  }

  function planColumnSlots() {
    return orderedDaySlots();
  }

  function moveDayOptions() {
    const opts = [{ slot: 0, label: "待排" }];
    planColumnSlots().forEach((d) => opts.push({ slot: d, label: TD().DAY_NAME[d] || "周末" }));
    return opts;
  }

  function renderDeleteBtn(taskId) {
    return `<button type="button" class="btn-link xs tsk-card-del" data-task-del="${escapeAttr(taskId)}">删除</button>`;
  }

  function renderDayMenu(taskId, kind) {
    const attr = kind === "copy" ? "data-copy-day" : "data-move-day";
    const label = kind === "copy" ? "复制到…" : "移到 ▾";
    const items = moveDayOptions()
      .map(
        (o) =>
          `<button type="button" class="tsk-menu-item" ${attr}="${o.slot}" data-task-id="${escapeAttr(taskId)}">${escapeHtml(o.label)}</button>`
      )
      .join("");
    return `<details class="tsk-card-menu">
      <summary class="btn-link xs">${label}</summary>
      <div class="tsk-card-menu-pop">${items}</div>
    </details>`;
  }

  function renderSchedBar(opts = {}) {
    const { applied = false, categoryOnly = false } = opts;
    const wk = activeWeekKey();
    const isCurWeek = wk === weekKey();
    const isWeek = state.boardFlow === "plan";
    const genLabel = isCurWeek ? "生成本周" : "生成这一周";
    const wn = weekNumber(wk);
    const range = weekShortRange(wk);

    const viewChips = `<div class="tsk-board-bar-group tsk-board-bar-view">
      <button type="button" class="tsk-chip${state.boardView === "schedule" ? " on" : ""}" data-board-view="schedule">日程</button>
      <button type="button" class="tsk-chip${state.boardView === "category" ? " on" : ""}" data-board-view="category">分类</button>
    </div>`;

    const weekRangeCls = isCurWeek ? "tsk-bar-week-label week-range is-current-week" : "tsk-bar-week-label week-range";
    const weekNav = `<div class="tsk-board-bar-group tsk-board-bar-week">
      <button type="button" class="btn ghost xs" data-week-shift="-1" title="上一周">〈</button>
      <span class="${weekRangeCls}">第 ${wn} 周 · ${range}</span>
      <button type="button" class="btn ghost xs" data-week-shift="1" title="下一周">〉</button>
      ${!isCurWeek ? `<button type="button" class="tsk-chip tsk-week-goto-current" data-week-goto="current">本周</button>` : ""}
      <button type="button" class="btn-link xs" data-week-jump="1">下周</button>
      <button type="button" class="btn-link xs" id="btnPickWeek">选周</button>
    </div>`;

    const todayScopeBtn = isCurWeek
      ? `<button type="button" class="tsk-chip tsk-chip-scope${!isWeek ? " on is-scope-today" : ""}" data-board-scope="today">今天</button>`
      : `<button type="button" class="tsk-chip tsk-chip-scope tsk-chip-goto-today" data-board-scope="today-home">回到本周今天</button>`;
    const scopeChips =
      categoryOnly || state.boardView !== "schedule"
        ? ""
        : `<div class="tsk-board-bar-group tsk-board-bar-mid">
            ${todayScopeBtn}
            <button type="button" class="tsk-chip tsk-chip-scope${isWeek ? " on is-scope-week" : ""}" data-board-scope="week">整周</button>
            <span class="tsk-bar-sep"></span>
            <button type="button" class="tsk-chip${state.columnOrder === "asc" ? " on" : ""}" data-col-order="asc">一→末</button>
            <button type="button" class="tsk-chip${state.columnOrder === "desc" ? " on" : ""}" data-col-order="desc">末→一</button>
          </div>`;

    const actions =
      categoryOnly || state.boardView !== "schedule"
        ? `<div class="tsk-board-bar-actions"></div>`
        : `<div class="tsk-board-bar-group tsk-board-bar-actions">
            ${!applied ? `<button type="button" class="btn primary btn-sm" id="btnTasksGenPlan">${genLabel}</button>` : ""}
            ${applied ? `<button type="button" class="btn-link" id="btnTasksRefill">填格</button>` : ""}
            <button type="button" class="btn-link" id="btnOpenTemplates">模板</button>
          </div>`;

    return `<div class="tsk-board-bar">${viewChips}${weekNav}${scopeChips || `<div class="tsk-board-bar-mid"></div>`}${actions}</div>`;
  }

  function bindSchedBar(root, { applied } = {}) {
    bindBoardViewChips(root);
    bindBoardToolbar(root);
    bindWeekBarNav(root);
    root?.querySelectorAll('[id="btnOpenTemplates"]').forEach((btn) => {
      btn.addEventListener("click", openTemplateDrawer);
    });
    root?.querySelector("#btnTasksGenPlan")?.addEventListener("click", () => {
      const wk = activeWeekKey();
      applyWeeklyTemplate({ weekKey: wk });
      state.boardFlow = "plan";
      saveBoardPrefs();
      renderAll();
    });
    root?.querySelector("#btnTasksRefill")?.addEventListener("click", () => {
      applyWeeklyTemplate({ refill: true, weekKey: activeWeekKey() });
      renderAll();
    });
  }

  function bindWeekBarNav(root) {
    root?.querySelectorAll("[data-week-shift]").forEach((btn) => {
      if (btn.id === "btnPickWeek") return;
      btn.addEventListener("click", () => shiftActiveWeek(Number(btn.getAttribute("data-week-shift"))));
    });
    root?.querySelector('[data-week-goto="current"]')?.addEventListener("click", () => {
      state.boardWeek = weekKey();
      saveBoardPrefs();
      renderAll();
    });
    root?.querySelector('[data-week-jump="1"]')?.addEventListener("click", () => shiftActiveWeek(1));
    root?.querySelector("#btnPickWeek")?.addEventListener("click", () => {
      let inp = $("#taskWeekPicker");
      if (!inp) {
        inp = document.createElement("input");
        inp.type = "week";
        inp.id = "taskWeekPicker";
        inp.className = "tsk-week-picker-input";
        inp.hidden = true;
        document.body.appendChild(inp);
      }
      inp.value = toWeekInput(activeWeekKey());
      inp.onchange = () => {
        state.boardWeek = fromWeekInput(inp.value);
        saveBoardPrefs();
        renderAll();
      };
      if (typeof inp.showPicker === "function") inp.showPicker();
      else inp.click();
    });
  }

  function renderHome() {
    const box = $("#tasksHome");
    if (!box) return;
    updateWeekChip();
    const wk = activeWeekKey();
    const isCurrentWeek = wk === weekKey();
    const weekTasks = tasksForWeek(wk);
    const prog = weekProgressDetail(wk);
    const today = todayDaySlot();
    const todayWk = weekKey();
    const todayTasks = tasksForWeek(todayWk).filter(
      (t) => today && t.daySlot === today && t.status !== "cancelled" && t.status !== "done"
    );
    const weekP0 = weekTasks.filter(
      (t) => t.priority === "must" && isScheduled(t) && t.status !== "cancelled" && t.status !== "done"
    );
    const curMonth = monthKey();
    const monthPlan = ensureMonthPlan(curMonth);
    const monthGoals = (monthPlan.goals || []).slice(0, 3);
    const note = loadWeekNote(wk);
    const applied = !!loadStore().templateApplied[wk];
    const todayLabel = isWeekendSlot(today) ? "周末" : TD().DAY_NAME[today] || "今天";
    const weekendRest = isWeekendSlot(today) && !todayTasks.length;

    box.innerHTML = `
      <div class="tsk-home-head">
        <h1 class="tsk-page-title">${isCurrentWeek ? "本周工作台" : "周回看"}</h1>
        <div class="tsk-week-nav">
          <button type="button" class="btn ghost xs" data-week-shift="-1" title="上一周">‹</button>
          <span class="tsk-week-nav-label">${escapeHtml(weekRangeLabel(wk))}</span>
          <button type="button" class="btn ghost xs" data-week-shift="1" title="下一周">›</button>
          ${!isCurrentWeek ? `<button type="button" class="btn-link" data-week-reset>回本周</button>` : ""}
        </div>
      </div>
      ${
        weekendRest
          ? `<div class="tsk-today-strip"><span class="muted">周末可休息</span><button type="button" class="btn-link" id="btnHomeGoPlan">排期本周</button></div>`
          : `<div class="tsk-today-strip">
              <span class="tsk-today-label">${escapeHtml(todayLabel)}</span>
              <div class="tsk-today-list">${renderExecCards(todayTasks, { empty: "", compact: true })}</div>
            </div>`
      }
      <div class="tsk-grid-3">
        ${
          weekP0.length
            ? `<div class="tsk-proto-card"><h3>整周 P0</h3>${weekP0.map((t) => renderTaskRow(t, { showDay: true, fullTitle: true })).join("")}</div>`
            : ""
        }
        ${
          monthGoals.length
            ? `<div class="tsk-proto-card"><h3>本月主线 <button type="button" class="btn-link" id="btnEditMonthPlan">编辑</button></h3>
              ${monthGoals.map((g) => `<div class="tsk-goal-line">${escapeHtml(g)}</div>`).join("")}</div>`
            : `<div class="tsk-proto-card"><h3>本月主线 <button type="button" class="btn-link" id="btnEditMonthPlan">去规划</button></h3>
              <p class="muted tsk-kempty-sm">尚未设定 · 可预排下月及更远</p></div>`
        }
        <div class="tsk-proto-card${!weekP0.length ? " tsk-span-2" : ""}">
          <h3>本周要点</h3>
          ${(note.highlights || []).map((item, i) => renderHighlightRow(item, i)).join("")}
        </div>
      </div>
      <div class="tsk-proto-card tsk-progress-card">
        <div class="tsk-progress-head">
          <h3>本周进度 · ${prog.done}/${prog.total}</h3>
          <div class="tsk-home-actions">
            <button type="button" class="btn primary btn-sm" id="btnHomeGoPlan">排期本周</button>
            ${applied ? `<button type="button" class="btn-link" id="btnHomeRefill">填格</button>` : ""}
            <button type="button" class="btn-link" id="btnHomeNewTask">新建</button>
          </div>
        </div>
        <div class="tsk-proto-bar"><i style="width:${prog.rate}%"></i></div>
        <p class="muted tsk-proto-meta">模板 ${prog.tplDone}/${prog.tplTotal} · 自定义 ${prog.customDone}/${prog.customTotal}</p>
        <form class="tsk-capture" id="taskCaptureForm">
          <input id="taskCaptureInput" type="text" placeholder="标题 → 待排期" autocomplete="off" />
          <input id="taskCaptureNotes" type="text" placeholder="细则（可选）" autocomplete="off" />
          <button type="submit" class="btn-link">捕捉</button>
        </form>
      </div>`;

    $("#btnHomeRefill")?.addEventListener("click", () => {
      applyWeeklyTemplate({ refill: true, weekKey: wk });
      renderAll();
    });
    box.querySelectorAll("[data-week-shift]").forEach((btn) => {
      btn.addEventListener("click", () => shiftActiveWeek(Number(btn.getAttribute("data-week-shift"))));
    });
    box.querySelector("[data-week-reset]")?.addEventListener("click", () => {
      state.boardWeek = weekKey();
      saveBoardPrefs();
      renderAll();
    });
    $("#btnEditMonthPlan")?.addEventListener("click", () => {
      state.monthsKey = curMonth;
      state.monthsYear = parseMonthKey(curMonth)?.year || new Date().getFullYear();
      switchMode("months");
    });
    $("#btnHomeGoPlan")?.addEventListener("click", () => {
      switchMode("board");
      state.boardView = "schedule";
      state.boardFlow = "plan";
      saveBoardPrefs();
      renderBoard();
    });
    $("#btnHomeNewTask")?.addEventListener("click", () => {
      switchMode("board");
      state.boardView = "category";
      saveBoardPrefs();
      openTaskDialog(null);
    });
    $("#taskCaptureForm")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const inp = $("#taskCaptureInput");
      const n = $("#taskCaptureNotes");
      quickCapture(inp?.value, n?.value);
      if (inp) inp.value = "";
      if (n) n.value = "";
      renderAll();
    });
    box.querySelectorAll(".tsk-highlight-input").forEach((inp) => {
      inp.addEventListener("change", () => {
        const idx = Number(inp.getAttribute("data-hl-idx"));
        const n = loadWeekNote(wk);
        if (!n.highlights[idx]) return;
        n.highlights[idx].text = inp.value.trim();
        saveWeekNote(wk, n);
      });
    });
    bindExecCardEvents(box);
    box.querySelectorAll("[data-task-done]").forEach((cb) => {
      cb.addEventListener("change", () => {
        const t = taskById(cb.getAttribute("data-task-done"));
        if (t) toggleDone(t);
        renderAll();
      });
    });
  }

  function renderMiniList(items) {
    return items
      .map(
        (t) => `<li><span class="tsk-mini-title">${escapeHtml(t.title)}</span>
          <span class="muted">${isScheduled(t) ? TD().DAY_NAME[t.daySlot] : "待排期"}</span></li>`
      )
      .join("");
  }

  function renderExecCards(items, { empty, compact, board } = {}) {
    if (!items.length) return empty === "" ? "" : `<p class="muted tsk-kempty-sm">${escapeHtml(empty || "暂无")}</p>`;
    return items.map((t) => renderExecCard(t, { compact, board })).join("");
  }

  function renderExecCard(t, { compact, board } = {}) {
    const done = t.status === "done";
    let actions = `<label class="tsk-check-sm"><input type="checkbox" data-task-done="${escapeAttr(t.id)}" ${done ? "checked" : ""} /></label>`;
    if (board && !done) {
      actions += `${renderDayMenu(t.id, "move")}${renderDayMenu(t.id, "copy")}`;
    } else if (!done && !board) {
      actions += `<button type="button" class="btn-link xs" data-task-tmrw="${escapeAttr(t.id)}">明天</button>`;
    }
    return renderKanbanTaskCard(t, { exec: true, compact, actionsHtml: actions });
  }

  function renderBacklogCard(t, { draggable, planCatalog } = {}) {
    const catalog = isTemplateCatalog(t);
    let actions = "";
    if (catalog && planCatalog) {
      actions = `<span class="muted tsk-drag-hint">拖入日程</span>${renderDeleteBtn(t.id)}`;
    } else {
      actions = `${renderDayMenu(t.id, "move")}${renderDayMenu(t.id, "copy")}${renderDeleteBtn(t.id)}`;
    }
    return renderKanbanTaskCard(t, { backlog: true, draggable, catalog, actionsHtml: actions });
  }

  function renderBacklogCards(items, { draggable, planCatalog } = {}) {
    if (!items.length) return "";
    return items.map((t) => renderBacklogCard(t, { draggable, planCatalog })).join("");
  }

  function taskMetaLine(t) {
    const parts = [];
    if (t.kind === "template") parts.push("模板");
    else parts.push("自定义");
    parts.push(priLabel(t.priority));
    if (t.slot && TD().SLOT_LABEL?.[t.slot]) parts.push(TD().SLOT_LABEL[t.slot]);
    return parts.join(" · ");
  }

  function renderPlanCard(t) {
    const actions = `${renderDayMenu(t.id, "move")}${renderDayMenu(t.id, "copy")}${renderDeleteBtn(t.id)}`;
    return renderKanbanTaskCard(t, { draggable: true, plan: true, actionsHtml: actions });
  }

  function renderWeekEmpty(wk) {
    const isCur = wk === weekKey();
    const label = isCur ? "生成本周" : "生成这一周";
    return `<div class="tsk-week-empty">
      <p class="muted">这一周还没生成</p>
      <button type="button" class="btn primary btn-sm" data-gen-week="${escapeAttr(wk)}">${label}</button>
    </div>`;
  }

  function bindScheduleCardEvents(root) {
    root?.querySelectorAll(".tsk-card-menu summary").forEach((el) => {
      el.addEventListener("mousedown", (e) => e.stopPropagation());
      el.addEventListener("click", (e) => e.stopPropagation());
    });
    root?.querySelectorAll("[data-task-open]").forEach((el) => {
      const open = () => openTaskDrawer(el.getAttribute("data-task-open"));
      el.addEventListener("click", (e) => {
        if (e.target.closest(".tsk-card-menu")) return;
        open();
      });
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      });
    });
    root?.querySelectorAll("[data-move-day]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        btn.closest("details")?.removeAttribute("open");
        const id = btn.getAttribute("data-task-id");
        if (moveTaskDay(id, btn.getAttribute("data-move-day"))) renderAll();
      });
    });
    root?.querySelectorAll("[data-copy-day]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        btn.closest("details")?.removeAttribute("open");
        copyTaskToDay(btn.getAttribute("data-task-id"), btn.getAttribute("data-copy-day"));
        renderAll();
      });
    });
    root?.querySelectorAll("[data-task-del]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (confirm("删除这一条？")) {
          deleteTask(btn.getAttribute("data-task-del"));
          renderAll();
        }
      });
    });
    root?.querySelectorAll("[data-gen-week]").forEach((btn) => {
      btn.addEventListener("click", () => {
        applyWeeklyTemplate({ weekKey: btn.getAttribute("data-gen-week") });
        state.boardFlow = "plan";
        saveBoardPrefs();
        renderAll();
      });
    });
    bindTaskCardInteractions(root);
  }

  function renderColEmpty(kind) {
    if (kind === "drop") return `<p class="tsk-kplaceholder">投放</p>`;
    if (kind === "backlog") return `<p class="tsk-kplaceholder">空</p>`;
    return "";
  }

  function renderKanbanCol({ label, dateShort, body, extraClass, dropDay, isToday, daySlot, headHtml }) {
    const drop = dropDay !== undefined ? ` data-drop-day="${dropDay}"` : "";
    const isDayCol = daySlot !== undefined && daySlot > 0;
    const dayCls = isDayCol ? " tsk-kanban-day" : "";
    const todayCls = isToday ? " is-today" : "";
    const head = headHtml || colHead(label, dateShort);
    const slotAttr = isDayCol ? ` data-day-slot="${daySlot}"` : "";
    return `<section class="tsk-kcol${dayCls}${extraClass || ""}${todayCls}"${drop}${slotAttr}>
      ${head}
      <div class="tsk-kcol-body">${body}</div>
    </section>`;
  }

  function bindExecCardEvents(root) {
    root.querySelectorAll("[data-task-done]").forEach((cb) => {
      cb.addEventListener("change", () => {
        const t = taskById(cb.getAttribute("data-task-done"));
        if (t) toggleDone(t);
        renderAll();
      });
    });
    root.querySelectorAll("[data-task-tmrw]").forEach((btn) => {
      btn.addEventListener("click", () => {
        moveToTomorrow(btn.getAttribute("data-task-tmrw"));
        renderAll();
      });
    });
    bindScheduleCardEvents(root);
  }

  function bindBacklogCardEvents(root) {
    bindScheduleCardEvents(root);
  }

  function renderBoard() {
    const main = $("#tasksBoardMain");
    const catView = $("#tasksCategoryView");
    if (!main) return;
    updateWeekChip();

    if (state.boardView === "category") {
      main.hidden = true;
      if (catView) {
        catView.hidden = false;
        renderCategoryView(catView);
      }
      return;
    }

    main.hidden = false;
    if (catView) catView.hidden = true;

    if (state.boardFlow === "close") renderCloseBoard(main);
    else renderWeekScheduleBoard(main);
  }

  function bindBoardViewChips(root) {
    root?.querySelectorAll("[data-board-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.boardView = btn.getAttribute("data-board-view");
        saveBoardPrefs();
        renderBoard();
      });
    });
  }

  function renderWeekScheduleBoard(container) {
    const wk = activeWeekKey();
    const applied = weekIsGenerated(wk);
    const isCurWeek = wk === weekKey();
    const focusToday = state.boardFlow === "exec";
    const flowPlan = state.boardFlow === "plan";

    if (!applied) {
      container.innerHTML = `${renderSchedBar({ applied, flow: flowPlan ? "plan" : "exec" })}${renderWeekEmpty(wk)}`;
      bindSchedBar(container, { applied });
      bindScheduleCardEvents(container);
      return;
    }

    pruneOrphanCatalog(wk);
    ensureTemplateCatalog(wk);
    const backlogAll = backlogTasks(wk);
    const byDay = {};
    planColumnSlots().forEach((d) => {
      byDay[d] = columnTasks(wk, d);
    });
    const curToday = isCurWeek ? todayDaySlot() : 0;
    const weekendSlot = TD().WEEKEND_SLOT || 6;
    const kanbanCls = `tsk-kanban tsk-kanban-week${isCurWeek ? " is-current" : ""}${focusToday ? " is-focus-today" : ""}`;

    const dayCols = planColumnSlots()
      .map((d) => {
        const items = byDay[d] || [];
        const isWeekend = d === weekendSlot;
        const highlightToday = isCurWeek && focusToday && curToday === d;
        return renderKanbanCol({
          daySlot: d,
          headHtml: dayColHead(wk, d, { highlightToday }),
          body: items.map(renderPlanCard).join("") || renderColEmpty("drop"),
          dropDay: d,
          isToday: highlightToday,
          extraClass: isWeekend ? " tsk-kcol-weekend" : "",
        });
      })
      .join("");

    container.innerHTML = `
      ${renderSchedBar({ flow: flowPlan ? "plan" : "exec", applied })}
      <div class="${kanbanCls}">
        ${renderKanbanCol({
          label: backlogColTitle(),
          body: renderBacklogCards(backlogAll, { draggable: true, planCatalog: true }) || renderColEmpty("backlog"),
          extraClass: " tsk-kcol-backlog",
          dropDay: 0,
        })}
        ${dayCols}
      </div>`;

    bindSchedBar(container, { applied });
    bindPlanDrag(container);
    bindScheduleCardEvents(container);
    if (focusToday && isCurWeek && curToday) scrollToTodayColumn(container);
  }

  function bindPlanDrag(root) {
    root.querySelectorAll(".tsk-plan-card, .tsk-backlog-card").forEach((card) => {
      card.addEventListener("dragstart", (e) => {
        state.dragTaskId = card.getAttribute("data-task-id");
        e.dataTransfer?.setData("text/plain", state.dragTaskId);
        if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
        card.classList.add("is-dragging");
      });
      card.addEventListener("dragend", () => {
        card.classList.remove("is-dragging");
        clearDropIndicators(root);
        state.dragTaskId = null;
      });
    });
    root.querySelectorAll(".tsk-kcol[data-drop-day]").forEach((col) => {
      const body = col.querySelector(".tsk-kcol-body");
      if (!body) return;
      const day = Number(col.getAttribute("data-drop-day"));
      const isBacklogCol = day === 0;
      body.addEventListener("dragover", (e) => {
        e.preventDefault();
        const dragId = e.dataTransfer?.getData("text/plain") || state.dragTaskId;
        const dragTask = dragId ? taskById(dragId) : null;
        if (isBacklogCol) {
          if (dragTask && dragTask.daySlot > 0 && !isTemplateCatalog(dragTask)) {
            if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
            body.classList.add("is-drag-over");
          }
          return;
        }
        if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
        const beforeId = dropInsertBeforeId(body, e.clientY, dragId);
        showDropIndicator(body, beforeId);
      });
      body.addEventListener("dragleave", (e) => {
        if (!body.contains(e.relatedTarget)) {
          body.classList.remove("is-drag-over");
          body.querySelectorAll(".tsk-drop-indicator").forEach((el) => el.remove());
        }
      });
      body.addEventListener("drop", (e) => {
        e.preventDefault();
        clearDropIndicators(root);
        const id = e.dataTransfer?.getData("text/plain") || state.dragTaskId;
        if (!id) return;
        const beforeId = isBacklogCol ? null : dropInsertBeforeId(body, e.clientY, id);
        if (reorderTaskInColumn(id, day, beforeId, activeWeekKey())) renderAll();
      });
    });
  }

  function renderCloseBoard(container) {
    const wk = state.boardWeek || weekKey();
    const open = tasksForWeek(wk).filter(
      (t) => t.status !== "done" && t.status !== "cancelled" && isScheduled(t)
    );
    const applied = !!loadStore().templateApplied[wk];
    container.innerHTML = `
      ${renderSchedBar({ flow: "close", applied })}
      <div class="tsk-close-list">
        ${open.length ? open.map((t) => renderCloseRow(t)).join("") : `<p class="muted tsk-kempty-sm">本周已清空</p>`}
      </div>`;
    bindSchedBar(container, { applied });
    container.querySelectorAll("[data-close-act]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-task-id");
        const act = btn.getAttribute("data-close-act");
        const t = taskById(id);
        if (!t) return;
        if (act === "drop") deleteTask(id);
        else if (act === "backlog") moveTaskDay(id, 0, { force: true });
        else if (act === "month") returnTaskToMonthPool(t);
        else if (act === "roll") rolloverTaskToNextMonth(t);
        else if (act === "next") {
          t.weekKey = weekKey(new Date(Date.now() + 7 * 86400000));
          t.status = "todo";
          t.updatedAt = new Date().toISOString();
          upsertTask(t);
        }
        renderAll();
      });
    });
  }

  function renderCloseRow(t) {
    return `<div class="tsk-close-row">
      <span><strong>${escapeHtml(t.title)}</strong> <span class="muted">${escapeHtml(TD().DAY_NAME[t.daySlot] || "")}</span></span>
      <span class="tsk-close-btns">
        <button type="button" class="btn-link xs" data-close-act="drop" data-task-id="${escapeAttr(t.id)}">丢弃</button>
        <button type="button" class="btn-link xs" data-close-act="next" data-task-id="${escapeAttr(t.id)}">推下周</button>
        <button type="button" class="btn-link xs" data-close-act="backlog" data-task-id="${escapeAttr(t.id)}">待排期</button>
        <button type="button" class="btn-link xs" data-close-act="month" data-task-id="${escapeAttr(t.id)}">月池</button>
        <button type="button" class="btn-link xs" data-close-act="roll" data-task-id="${escapeAttr(t.id)}">结转下月</button>
      </span>
    </div>`;
  }

  function renderCategoryView(container) {
    if (!container) return;
    const applied = !!loadStore().templateApplied[state.boardWeek || weekKey()];
    container.innerHTML = `
      ${renderSchedBar({ flow: "exec", applied, categoryOnly: true })}
      <div class="tsk-workbench tsk-workbench-cat">
        <aside class="tsk-col tsk-col-cat" aria-label="大类">
          <h3 class="tsk-col-title">大类</h3>
          <div id="tasksCategories" class="tsk-cat-list"></div>
        </aside>
        <section class="tsk-col tsk-col-sub" aria-label="子类">
          <h3 class="tsk-col-title">子类</h3>
          <input id="tasksSubSearch" class="tsk-sub-search" type="search" placeholder="过滤子类…" value="${escapeAttr(state.subSearch || "")}" />
          <div class="tsk-filter-chips tsk-sub-filters">
            <button type="button" class="tsk-chip${state.catFilter === "all" ? " on" : ""}" data-cat-filter="all">全部</button>
            <button type="button" class="tsk-chip${state.catFilter === "template" ? " on" : ""}" data-cat-filter="template">模板</button>
            <button type="button" class="tsk-chip${state.catFilter === "custom" ? " on" : ""}" data-cat-filter="custom">自定义</button>
            <button type="button" class="tsk-chip${state.catFilter === "open" ? " on" : ""}" data-cat-filter="open">未完成</button>
          </div>
          <div id="tasksSubcategories" class="tsk-sub-list"></div>
        </section>
        <section class="tsk-col tsk-col-cards" aria-label="任务卡">
          <div id="tasksCards" class="tsk-cards-pane"></div>
        </section>
      </div>`;

    bindSchedBar(container, { applied });

    const cats = $("#tasksCategories");
    const subs = $("#tasksSubcategories");
    const cards = $("#tasksCards");
    if (!cats || !subs || !cards) return;
    const wk = state.boardWeek || weekKey();
    const categories = TD().CATEGORIES;
    if (!state.categoryId) state.categoryId = categories[0]?.id || "";
    const cat = TD().getCategory(state.categoryId);
    if (!cat) return;
    if (!state.subcategoryId || !cat.subs.some((s) => s.id === state.subcategoryId)) {
      state.subcategoryId = cat.subs[0]?.id || "";
    }
    const weekTasks = tasksForWeek(wk).filter((t) => t.status !== "cancelled");
    const q = (state.subSearch || "").trim().toLowerCase();

    cats.innerHTML = categories
      .map((c) => {
        const n = weekTasks.filter((t) => t.categoryId === c.id && t.status !== "done").length;
        return `<button type="button" class="tsk-cat-item${c.id === state.categoryId ? " on" : ""}" data-task-cat="${escapeAttr(c.id)}">
          <span>${escapeHtml(c.name)}</span><em>${n}</em>
        </button>`;
      })
      .join("");

    const filteredSubs = cat.subs.filter((s) => !q || s.name.toLowerCase().includes(q));
    subs.innerHTML = filteredSubs
      .map((s) => {
        let list = weekTasks.filter((t) => t.subcategoryId === s.id);
        if (state.catFilter === "template") list = list.filter((t) => t.kind === "template");
        if (state.catFilter === "custom") list = list.filter((t) => t.kind !== "template");
        if (state.catFilter === "open") list = list.filter((t) => t.status !== "done");
        return `<button type="button" class="tsk-sub-item${s.id === state.subcategoryId ? " on" : ""}${list.length === 0 ? " is-zero" : ""}" data-task-sub="${escapeAttr(s.id)}">
          <span>${escapeHtml(s.name)}</span><em>${list.length}</em>
        </button>`;
      })
      .join("");

    let list = weekTasks.filter((t) => t.subcategoryId === state.subcategoryId);
    if (state.catFilter === "template") list = list.filter((t) => t.kind === "template");
    if (state.catFilter === "custom") list = list.filter((t) => t.kind !== "template");
    if (state.catFilter === "open") list = list.filter((t) => t.status !== "done");

    const subName = TD().subLabel(state.subcategoryId);
    cards.innerHTML = `
      <div class="tsk-cards-head">
        <h3>${escapeHtml(subName)}</h3>
        <button type="button" class="btn-link" id="btnTasksNew">新建</button>
      </div>
      <div class="tsk-card-grid">${list.map((t) => renderCategoryCard(t)).join("") || `<p class="muted tsk-kempty-sm">暂无</p>`}</div>`;
    cats.querySelectorAll("[data-task-cat]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.categoryId = btn.getAttribute("data-task-cat");
        state.subcategoryId = TD().getCategory(state.categoryId)?.subs[0]?.id || "";
        saveBoardPrefs();
        renderBoard();
      });
    });
    subs.querySelectorAll("[data-task-sub]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.subcategoryId = btn.getAttribute("data-task-sub");
        saveBoardPrefs();
        renderBoard();
      });
    });
    container.querySelectorAll("[data-cat-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.catFilter = btn.getAttribute("data-cat-filter");
        saveBoardPrefs();
        renderBoard();
      });
    });
    $("#tasksSubSearch")?.addEventListener("input", (e) => {
      state.subSearch = e.target.value;
      saveBoardPrefs();
      renderBoard();
    });
    $("#btnTasksNew")?.addEventListener("click", () => openTaskDialog(null));
    cards.querySelectorAll("[data-task-edit]").forEach((btn) => {
      btn.addEventListener("click", () => openTaskDialog(btn.getAttribute("data-task-edit")));
    });
    cards.querySelectorAll("[data-task-del]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (confirm("删除？")) {
          deleteTask(btn.getAttribute("data-task-del"));
          renderAll();
        }
      });
    });
    bindTaskCardInteractions(cards);
  }

  function renderCategoryCard(t) {
    const summary = execResultSummary(t);
    const priColor = priBarColor(t.priority);
    const done = t.status === "done";
    return `<article class="tsk-card tsk-task-card tsk-hover-card${done ? " is-done" : ""}" data-task-id="${escapeAttr(t.id)}">
      <div class="tsk-card-pri-bar" style="background:${priColor}"></div>
      <div class="tsk-card-inner">
        <div class="tsk-card-body">
          <span class="tsk-card-title">${escapeHtml(t.title)}</span>
          <span class="meta tsk-card-source">${escapeHtml(taskSourceLine(t))}</span>
          <div class="tsk-card-footline">
            ${renderTaskStatusBadge(t)}${summary ? `<span class="tsk-card-summary">${escapeHtml(summary)}</span>` : ""}
          </div>
          <span class="meta tsk-sched-hint">${escapeHtml(taskScheduleHint(t))}</span>
        </div>
        <div class="tsk-card-foot tsk-card-actions">
          <button type="button" class="btn-link xs" data-task-edit="${escapeAttr(t.id)}">编辑</button>
          <button type="button" class="btn-link xs" data-task-del="${escapeAttr(t.id)}">删除</button>
        </div>
      </div>
    </article>`;
  }

  function bindBoardToolbar(root) {
    root?.querySelectorAll("[data-board-scope]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const scope = btn.getAttribute("data-board-scope");
        if (scope === "week") state.boardFlow = "plan";
        else if (scope === "today") state.boardFlow = "exec";
        else if (scope === "today-home") {
          state.boardWeek = weekKey();
          state.boardFlow = "exec";
        }
        state.boardView = "schedule";
        saveBoardPrefs();
        renderBoard();
      });
    });
    root?.querySelectorAll("[data-board-flow]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.boardFlow = btn.getAttribute("data-board-flow");
        state.boardView = "schedule";
        saveBoardPrefs();
        renderBoard();
      });
    });
    root?.querySelectorAll("[data-col-order]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.columnOrder = btn.getAttribute("data-col-order");
        saveBoardPrefs();
        renderBoard();
      });
    });
  }

  function ensureTplCategorySelect() {
    const catSel = $("#tplAddCategory");
    if (!catSel || catSel.options.length) return;
    catSel.innerHTML = TD()
      .CATEGORIES.map((c) => `<option value="${escapeAttr(c.id)}">${escapeHtml(c.name)}</option>`)
      .join("");
  }

  function openTemplateDrawer() {
    const dlg = $("#taskTemplateDialog");
    const box = $("#taskTemplateList");
    if (!dlg || !box) return;
    ensureTplCategorySelect();
    const byCat = new Map();
    getEffectiveTemplates().forEach((tpl) => {
      if (!byCat.has(tpl.categoryId)) byCat.set(tpl.categoryId, []);
      byCat.get(tpl.categoryId).push(tpl);
    });
    box.innerHTML = TD()
      .CATEGORIES.map((cat) => {
        const items = byCat.get(cat.id);
        if (!items?.length) return "";
        return `<section class="tsk-tpl-group">
          <h4 class="tsk-tpl-group-title">${escapeHtml(cat.name)}</h4>
          ${items.map(renderTemplateRow).join("")}
        </section>`;
      })
      .join("");
    refreshTplSubOptions();
    dlg.showModal();
  }

  function saveTemplateDrawer() {
    $("#taskTemplateList")?.querySelectorAll(".tsk-tpl-row").forEach((row) => {
      const key = row.getAttribute("data-tpl-key");
      const daysRaw = row.querySelector(".tsk-tpl-days")?.value || "";
      const weekdays = daysRaw
        .split(/[,，\s]+/)
        .map((x) => Number(x.trim()))
        .filter((n) => n >= 1 && n <= (TD().WEEKEND_SLOT || 6));
      const scheduleKind = row.querySelector(".tsk-tpl-kind")?.value || "once";
      saveTemplateOverride(key, { weekdays, scheduleKind });
    });
    $("#taskTemplateDialog")?.close();
    if (typeof toast === "function") toast("模板默认已保存 · 下次「生成本周」生效", "ok");
  }

  function renderMonthItemRow(item, mk, { readOnly, weeks } = {}) {
    const wkOpts = (weeks || [])
      .map(
        (w) =>
          `<option value="${escapeAttr(w)}"${item.targetWeekId === w ? " selected" : ""}>W${weekNumber(w)}</option>`
      )
      .join("");
    const st =
      item.status === "split"
        ? "已拆进周"
        : item.status === "done"
          ? "已完成"
          : item.status === "dropped"
            ? "已丢弃"
            : "月池";
    if (readOnly) {
      return `<div class="tsk-month-item">
        <span>${escapeHtml(item.title)}</span>
        <span class="muted">${escapeHtml(item.priority)} · ${escapeHtml(st)}${item.targetWeekId ? ` · W${weekNumber(item.targetWeekId)}` : ""}</span>
      </div>`;
    }
    return `<div class="tsk-month-item" data-month-item="${escapeAttr(item.id)}">
      <span class="tsk-month-item-title">${escapeHtml(item.title)}</span>
      <span class="muted">${escapeHtml(item.priority)} · ${escapeHtml(st)}</span>
      <div class="tsk-month-item-actions">
        ${item.status === "planned" ? `<select class="tsk-month-wk" data-set-week="${escapeAttr(item.id)}">
          <option value="">月池</option>${wkOpts}
        </select>` : ""}
        ${item.status === "planned" ? `<button type="button" class="btn-link xs" data-split-week="${escapeAttr(item.id)}">拆进本周</button>` : ""}
        <button type="button" class="btn-link xs" data-del-month-item="${escapeAttr(item.id)}">删</button>
      </div>
    </div>`;
  }

  function renderMonths() {
    const box = $("#tasksMonths");
    if (!box) return;
    updateWeekChip();
    const curMk = monthKey();
    if (!state.monthsKey) state.monthsKey = curMk;
    if (!state.monthsYear) state.monthsYear = parseMonthKey(state.monthsKey)?.year || new Date().getFullYear();
    const selMk = state.monthsKey;
    const phase = monthPhase(selMk);
    const readOnly = phase === "past";
    const plan = ensureMonthPlan(selMk);
    const weeks = weeksInMonth(selMk);
    const stats = monthSummaryStats(selMk, plan);
    const pool = (plan.items || []).filter((i) => i.status === "planned" && !i.targetWeekId);
    const targeted = (plan.items || []).filter((i) => i.status === "planned" && i.targetWeekId);
    const plannedOpen = (plan.items || []).filter((i) => i.status === "planned");
    const doneItems = (plan.items || []).filter((i) => i.status === "split" || i.status === "done" || i.status === "dropped");
    const fullyEmpty = monthIsFullyEmpty(selMk, plan);
    const goalsLines = (plan.goals || []).filter((g) => String(g).trim());
    const weekRows = renderWeekRows(weeks, { readOnly });
    const monthNav = buildMonthNavHtml(state.monthsYear, selMk);

    let mainBody = "";
    if (readOnly && fullyEmpty) {
      mainBody = `
        ${renderMonthSummaryBar(stats)}
        <p class="tsk-month-empty">这个月还没有记录</p>`;
    } else if (readOnly) {
      const goalsBlock = goalsLines.length
        ? goalsLines.map((g) => `<div class="tsk-goal-line">${escapeHtml(g)}</div>`).join("")
        : "";
      const openBlock = plannedOpen.length
        ? plannedOpen.map((i) => renderMonthItemRow(i, selMk, { readOnly: true, weeks })).join("")
        : "";
      const doneBlock = doneItems.length
        ? doneItems.map((i) => renderMonthItemRow(i, selMk, { readOnly: true, weeks })).join("")
        : "";
      mainBody = `
        ${renderMonthSummaryBar(stats)}
        ${goalsBlock ? `<section class="tsk-month-section"><h3 class="tsk-month-section-h">主线</h3><div class="tsk-month-section-b">${goalsBlock}</div></section>` : ""}
        ${openBlock ? `<section class="tsk-month-section"><h3 class="tsk-month-section-h">未完成 · ${plannedOpen.length}</h3><div class="tsk-month-section-b">${openBlock}</div></section>` : ""}
        ${weekRows ? `<section class="tsk-month-section"><h3 class="tsk-month-section-h">各周</h3><div class="tsk-month-section-b tsk-week-rows">${weekRows}</div></section>` : ""}
        ${doneBlock ? `<section class="tsk-month-section"><h3 class="tsk-month-section-h">记录</h3><div class="tsk-month-section-b">${doneBlock}</div></section>` : ""}
        ${
          plannedOpen.length
            ? `<div class="tsk-month-hist-actions"><button type="button" class="btn-link" data-roll-month="${escapeAttr(selMk)}">未完成结转到下月</button></div>`
            : ""
        }`;
    } else {
      mainBody = `
        <section class="tsk-month-section">
          <div class="tsk-month-section-head">
            <h3 class="tsk-month-section-h">主线</h3>
            <button type="button" class="btn primary btn-sm" id="btnMonthSaveGoals">保存</button>
          </div>
          <textarea id="monthGoalsInput" class="tsk-month-goals" rows="3" placeholder="3–7 条主线，一行一条">${escapeHtml((plan.goals || []).join("\n"))}</textarea>
        </section>
        <section class="tsk-month-section">
          <h3 class="tsk-month-section-h">月池 · ${pool.length}</h3>
          <form class="tsk-month-add" id="monthItemForm">
            <input id="monthItemTitle" type="text" placeholder="月任务标题" required />
            <select id="monthItemCat">${TD().CATEGORIES.map((c) => `<option value="${escapeAttr(c.id)}">${escapeHtml(c.name)}</option>`).join("")}</select>
            <select id="monthItemPri"><option value="P0">P0</option><option value="P1" selected>P1</option><option value="P2">P2</option></select>
            <select id="monthItemWeek"><option value="">月池</option>${weeks.map((w) => `<option value="${escapeAttr(w)}">W${weekNumber(w)} ${weekShortRange(w)}</option>`).join("")}</select>
            <button type="submit" class="btn primary btn-sm">添加</button>
          </form>
          <div class="tsk-month-section-b">${pool.map((i) => renderMonthItemRow(i, selMk, { readOnly, weeks })).join("") || `<p class="tsk-month-inline-empty muted">暂无月池任务</p>`}</div>
        </section>
        ${
          targeted.length
            ? `<section class="tsk-month-section"><h3 class="tsk-month-section-h">已指定周 · ${targeted.length}</h3><div class="tsk-month-section-b">${targeted.map((i) => renderMonthItemRow(i, selMk, { readOnly, weeks })).join("")}</div></section>`
            : ""
        }
        ${
          weekRows
            ? `<section class="tsk-month-section"><h3 class="tsk-month-section-h">各周</h3><div class="tsk-month-section-b tsk-week-rows">${weekRows}</div></section>`
            : ""
        }`;
    }

    box.innerHTML = `
      <div class="tsk-months-layout">
        <aside class="tsk-months-nav">
          <div class="tsk-year-nav">
            <button type="button" class="btn ghost xs" data-year-shift="-1">‹</button>
            <span>${state.monthsYear}</span>
            <button type="button" class="btn ghost xs" data-year-shift="1">›</button>
          </div>
          <div class="tsk-month-list">${monthNav || `<p class="muted tsk-kempty-sm">无月份</p>`}</div>
        </aside>
        <main class="tsk-month-main tsk-month-skin-${phase}">
          <h2 class="tsk-month-title">${escapeHtml(monthLabel(selMk))}</h2>
          ${mainBody}
        </main>
      </div>`;

    box.querySelectorAll("[data-year-shift]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.monthsYear += Number(btn.getAttribute("data-year-shift"));
        const m = parseMonthKey(selMk)?.month;
        if (m) {
          const mk = `${state.monthsYear}-${String(m).padStart(2, "0")}`;
          state.monthsKey = mk;
        }
        renderMonths();
      });
    });
    box.querySelectorAll("[data-pick-month]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.monthsKey = btn.getAttribute("data-pick-month");
        state.monthsYear = parseMonthKey(state.monthsKey)?.year || state.monthsYear;
        renderMonths();
      });
    });
    box.querySelectorAll("[data-open-week]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.boardWeek = btn.getAttribute("data-open-week");
        saveBoardPrefs();
        switchMode("board");
        state.boardFlow = "exec";
        renderBoard();
      });
    });
    $("#btnMonthSaveGoals")?.addEventListener("click", () => {
      const raw = $("#monthGoalsInput")?.value || "";
      updateMonthGoals(selMk, raw.split("\n"));
      if (typeof toast === "function") toast("主线已保存", "ok");
      renderAll();
    });
    $("#monthItemForm")?.addEventListener("submit", (e) => {
      e.preventDefault();
      addMonthItem(selMk, {
        title: $("#monthItemTitle")?.value,
        categoryId: $("#monthItemCat")?.value,
        priority: $("#monthItemPri")?.value,
        targetWeekId: $("#monthItemWeek")?.value || "",
      });
      renderMonths();
    });
    box.querySelectorAll("[data-split-week]").forEach((btn) => {
      btn.addEventListener("click", () => {
        splitMonthItemToWeek(selMk, btn.getAttribute("data-split-week"), weekKey());
        if (typeof toast === "function") toast("已拆进本周", "ok");
        renderAll();
      });
    });
    box.querySelectorAll("[data-set-week]").forEach((sel) => {
      sel.addEventListener("change", () => {
        updateMonthItem(selMk, sel.getAttribute("data-set-week"), {
          targetWeekId: sel.value || "",
        });
        renderMonths();
      });
    });
    box.querySelectorAll("[data-del-month-item]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const plan2 = ensureMonthPlan(selMk);
        plan2.items = (plan2.items || []).filter((i) => i.id !== btn.getAttribute("data-del-month-item"));
        saveMonthPlan(plan2);
        renderMonths();
      });
    });
    box.querySelector("[data-roll-month]")?.addEventListener("click", () => {
      const nextMk = monthKeyAdd(selMk, 1);
      ensureMonthPlan(nextMk);
      const p = ensureMonthPlan(selMk);
      (p.items || [])
        .filter((i) => i.status === "planned")
        .forEach((i) => {
          addMonthItem(nextMk, {
            title: i.title,
            categoryId: i.categoryId,
            subcategoryId: i.subcategoryId,
            priority: i.priority,
            rolledFromMonthKey: selMk,
          });
          i.status = "dropped";
        });
      saveMonthPlan(p);
      if (typeof toast === "function") toast("已结转到下月", "ok");
      renderMonths();
    });
  }

  function lastWeekKeys(n) {
    const keys = [];
    const d = new Date();
    for (let i = n - 1; i >= 0; i -= 1) {
      const dt = new Date(d);
      dt.setDate(dt.getDate() - i * 7);
      keys.push(weekKey(dt));
    }
    return keys;
  }

  function statsByCategory(tasks) {
    const map = new Map();
    scheduledTasks(tasks.filter((t) => t.status !== "cancelled")).forEach((t) => {
      const name = TD().catLabel(t.categoryId);
      const row = map.get(name) || { done: 0, total: 0 };
      row.total += 1;
      if (t.status === "done") row.done += 1;
      map.set(name, row);
    });
    return [...map.entries()].sort((a, b) => b[1].total - a[1].total);
  }

  function renderStats() {
    const box = $("#tasksStats");
    if (!box) return;
    updateWeekChip();
    const period = state.statsPeriod || "month";
    const anchor = state.statsAnchor || (period === "week" ? weekKey() : monthKey());
    const tasks = period === "week" ? tasksForWeek(anchor) : tasksForMonth(anchor);
    const scheduled = scheduledTasks(tasks.filter((t) => t.status !== "cancelled"));
    const created = scheduled.length;
    const completed = scheduled.filter((t) => t.status === "done").length;
    const rate = created ? Math.round((completed / created) * 100) : 0;
    const customN = scheduled.filter((t) => t.kind !== "template").length;
    const customPct = created ? Math.round((customN / created) * 100) : 0;
    const trend = lastWeekKeys(8).map((wk) => {
      const p = weekProgress(wk);
      return `W${weekNumber(wk)} ${p.done}/${p.total}`;
    });
    const byCat = statsByCategory(period === "week" ? tasks : tasksForMonth(anchor));
    const isHist = period === "month" && anchor < monthKey();

    box.innerHTML = `
      <h1 class="tsk-page-title">数据统计</h1>
      <div class="tsk-stats-toolbar">
        <div class="tsk-filter-chips">
          <button type="button" class="tsk-chip${period === "week" ? " on" : ""}" data-stats-period="week">按周</button>
          <button type="button" class="tsk-chip${period === "month" ? " on" : ""}" data-stats-period="month">按月</button>
        </div>
        <label class="field" style="margin:0"><span>${period === "week" ? "周次" : "月份"}</span>
          <input id="tasksStatsAnchor" type="${period === "week" ? "week" : "month"}" value="${escapeAttr(period === "week" ? toWeekInput(anchor) : anchor)}" />
        </label>
        <button type="button" class="btn-link" id="btnStatsGoMonths">${isHist ? "月计划详情" : "月度规划"}</button>
      </div>
      <div class="tsk-stats-kpis">
        <article class="tsk-stat-card"><span>${period === "week" ? "本周" : "本月"}创建</span><strong>${created}</strong></article>
        <article class="tsk-stat-card"><span>${period === "week" ? "本周" : "本月"}完成</span><strong>${completed}</strong></article>
        <article class="tsk-stat-card"><span>完成率</span><strong>${rate}%</strong></article>
        <article class="tsk-stat-card"><span>自定义占比</span><strong>${customPct}%</strong></article>
      </div>
      <div class="tsk-grid-2">
        <div class="tsk-proto-card">
          <h3>近 8 周完成趋势</h3>
          <p class="muted tsk-proto-meta">${escapeHtml(trend.join(" · "))}</p>
          <div class="tsk-proto-bar"><i style="width:${rate}%"></i></div>
        </div>
        <div class="tsk-proto-card">
          <h3>按大类</h3>
          ${
            byCat.length
              ? byCat
                  .map(
                    ([name, row]) =>
                      `<div class="tsk-task-row"><span>${escapeHtml(name)}</span><span class="muted">${row.done} / ${row.total}</span></div>`
                  )
                  .join("")
              : `<p class="muted">暂无数据</p>`
          }
        </div>
      </div>
      <p class="muted tsk-stats-tip">待排期不进完成率。每日建议 P0≤2、总数≤5。</p>`;

    box.querySelectorAll("[data-stats-period]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.statsPeriod = btn.getAttribute("data-stats-period");
        state.statsAnchor = state.statsPeriod === "week" ? weekKey() : monthKey();
        renderStats();
      });
    });
    $("#tasksStatsAnchor")?.addEventListener("change", (e) => {
      state.statsAnchor = state.statsPeriod === "week" ? fromWeekInput(e.target.value) : e.target.value;
      renderStats();
    });
    $("#btnStatsGoMonths")?.addEventListener("click", () => {
      state.monthsKey = period === "month" ? anchor : monthKey();
      state.monthsYear = parseMonthKey(state.monthsKey)?.year || new Date().getFullYear();
      switchMode("months");
    });
  }

  function openTaskDrawer(id) {
    const drawer = $("#taskEditDrawer");
    if (!drawer || !id) return;
    const t = taskById(id);
    if (!t) return;
    state.editingId = t.id;
    const titleEl = $("#taskDrawerTitle");
    if (titleEl) titleEl.textContent = taskDrawerHeading(t);
    $("#taskDrawerTitleInput").value = t.title;
    $("#taskDrawerNotes").value = t.notes || "";
    if ($("#taskDrawerExecResult")) $("#taskDrawerExecResult").value = t.execResult || "";
    $("#taskDrawerPriority").value = t.priority || "defer";
    $("#taskDrawerDaySlot").value = String(t.daySlot ?? 0);
    $("#taskDrawerSlot").value = t.slot || "";
    const syncBtn = $("#btnTaskSyncTemplate");
    if (syncBtn) {
      syncBtn.hidden = !(t.kind === "template" && t.templateKey);
    }
    const weekHint = $("#taskDrawerWeekHint");
    if (weekHint) weekHint.textContent = weekRangeLabel(t.weekKey);
    drawer.showModal();
  }

  function closeTaskDrawer() {
    const drawer = $("#taskEditDrawer");
    if (drawer?.open) drawer.close();
    state.editingId = null;
  }

  function saveTaskFromDrawer() {
    const id = state.editingId;
    const base = id ? taskById(id) : null;
    if (!base) return;
    const title = $("#taskDrawerTitleInput")?.value.trim();
    if (!title) {
      if (typeof toast === "function") toast("请填写标题", "error");
      return;
    }
    let daySlot = Number($("#taskDrawerDaySlot")?.value);
    let priority = $("#taskDrawerPriority")?.value || "defer";
    if (isTemplateCatalog(base)) daySlot = 0;
    else if (priority === "inspiration") daySlot = 0;
    if (!Number.isFinite(daySlot)) daySlot = 0;
    const draft = makeTask({
      ...base,
      title,
      notes: $("#taskDrawerNotes")?.value.trim() || "",
      execResult: $("#taskDrawerExecResult")?.value.trim() || "",
      priority,
      daySlot,
      slot: $("#taskDrawerSlot")?.value || "",
      templateCatalog: isTemplateCatalog(base),
    });
    if (!isTemplateCatalog(base)) refreshTaskInstanceKey(draft);
    const warn = daySlot ? dayLimitWarning(draft.weekKey, daySlot, draft, draft.id) : "";
    if (warn) {
      if (typeof toast === "function") toast(warn, "error");
      return;
    }
    upsertTask(draft);
    closeTaskDrawer();
    renderAll();
  }

  function openTaskDialog(id) {
    const dlg = $("#taskEditDialog");
    if (!dlg) return;
    const existing = id ? taskById(id) : null;
    state.editingId = existing?.id || null;
    const t =
      existing ||
      makeTask({
        categoryId: state.categoryId,
        subcategoryId: state.subcategoryId,
        weekKey: activeWeekKey(),
        daySlot: 0,
      });
    $("#taskEditTitle").textContent = existing ? "编辑任务" : "新建任务";
    $("#taskTitle").value = t.title;
    $("#taskNotes").value = t.notes || "";
    $("#taskPriority").value = t.priority || "defer";
    $("#taskDaySlot").value = String(t.daySlot ?? 0);
    if ($("#taskMonthlyMainline")) $("#taskMonthlyMainline").checked = !!t.monthlyMainline;
    if ($("#taskRepeatable")) $("#taskRepeatable").checked = !!t.repeatable;
    fillTaxonomySelects(t.categoryId, t.subcategoryId);
    dlg.showModal();
  }

  function fillTaxonomySelects(catId, subId) {
    const catSel = $("#taskCategory");
    const subSel = $("#taskSubcategory");
    if (!catSel || !subSel) return;
    catSel.innerHTML = TD().CATEGORIES.map((c) => `<option value="${escapeAttr(c.id)}">${escapeHtml(c.name)}</option>`).join("");
    catSel.value = catId || TD().CATEGORIES[0]?.id;
    renderSubSelect(catSel.value, subId);
    catSel.onchange = () => renderSubSelect(catSel.value, "");
  }

  function renderSubSelect(catId, subId) {
    const subSel = $("#taskSubcategory");
    const cat = TD().getCategory(catId);
    if (!subSel || !cat) return;
    subSel.innerHTML = cat.subs.map((s) => `<option value="${escapeAttr(s.id)}">${escapeHtml(s.name)}</option>`).join("");
    subSel.value = subId && cat.subs.some((s) => s.id === subId) ? subId : cat.subs[0]?.id || "";
  }

  function saveTaskFromDialog() {
    const title = $("#taskTitle")?.value.trim();
    if (!title) {
      if (typeof toast === "function") toast("请填写标题", "error");
      return;
    }
    let daySlot = Number($("#taskDaySlot")?.value);
    let priority = $("#taskPriority")?.value || "defer";
    if (priority === "inspiration") daySlot = 0;
    if (!Number.isFinite(daySlot)) daySlot = 0;
    const base = state.editingId ? taskById(state.editingId) : makeTask({});
    const draft = makeTask({
      ...base,
      title,
      notes: $("#taskNotes")?.value.trim() || "",
      categoryId: $("#taskCategory")?.value,
      subcategoryId: $("#taskSubcategory")?.value,
      priority,
      daySlot,
      kind: "custom",
      monthlyMainline: !!$("#taskMonthlyMainline")?.checked,
      repeatable: !!$("#taskRepeatable")?.checked,
      weekKey: base.weekKey || activeWeekKey(),
    });
    refreshTaskInstanceKey(draft);
    const warn = daySlot ? dayLimitWarning(draft.weekKey, daySlot, draft, draft.id) : "";
    if (warn) {
      if (typeof toast === "function") toast(warn, "error");
      return;
    }
    upsertTask(draft);
    $("#taskEditDialog")?.close();
    renderAll();
  }

  function toWeekInput(wk) {
    const m = /^(\d{4})-W(\d{2})$/.exec(wk || "");
    return m ? `${m[1]}-W${m[2]}` : "";
  }

  function fromWeekInput(val) {
    const m = /^(\d{4})-W(\d{2})$/.exec(val || "");
    return m ? `${m[1]}-W${m[2]}` : weekKey();
  }

  function isTasksFocusMode(mode = state.mode) {
    return mode === "board" || mode === "stats";
  }

  function updateTasksFocusUi() {
    const focus = isTasksFocusMode();
    document.body.classList.toggle("tasks-focus", focus);
    const back = $("#btnTasksFocusBack");
    if (back) back.hidden = !focus;
  }

  function clearTasksFocusUi() {
    document.body.classList.remove("tasks-focus");
    const back = $("#btnTasksFocusBack");
    if (back) back.hidden = true;
  }

  function switchMode(mode) {
    state.mode = mode;
    localStorage.setItem(LS_MODE, mode);
    document.querySelectorAll(".tsk-mode-tab").forEach((btn) => {
      const on = btn.dataset.taskMode === mode;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    $("#tasksModeHome").hidden = mode !== "home";
    $("#tasksModeBoard").hidden = mode !== "board";
    $("#tasksModeMonths").hidden = mode !== "months";
    $("#tasksModeStats").hidden = mode !== "stats";
    updateTasksFocusUi();
    renderAll();
  }

  function renderAll() {
    hideTaskPopover();
    closeStatusMenu();
    refreshTabCount();
    updateWeekChip();
    if (state.mode === "home") renderHome();
    if (state.mode === "board") renderBoard();
    if (state.mode === "months") renderMonths();
    if (state.mode === "stats") renderStats();
  }

  function saveBoardPrefs() {
    localStorage.setItem(
      LS_BOARD,
      JSON.stringify({
        categoryId: state.categoryId,
        subcategoryId: state.subcategoryId,
        boardWeek: state.boardWeek,
        boardView: state.boardView,
        boardFlow: state.boardFlow,
        columnOrder: state.columnOrder,
        catFilter: state.catFilter,
        subSearch: state.subSearch,
      })
    );
  }

  function restorePrefs() {
    state.mode = localStorage.getItem(LS_MODE) || "home";
    state.boardView = "schedule";
    state.boardFlow = "exec";
    try {
      const b = JSON.parse(localStorage.getItem(LS_BOARD) || "{}");
      state.categoryId = b.categoryId || TD().CATEGORIES[0]?.id || "";
      state.subcategoryId = b.subcategoryId || "";
      state.boardWeek = b.boardWeek || weekKey();
      state.boardView = b.boardView || (b.boardFlow === "category" ? "category" : "schedule");
      state.boardFlow = b.boardFlow === "category" ? "exec" : b.boardFlow || "exec";
      state.columnOrder = b.columnOrder || "asc";
      state.catFilter = b.catFilter || "all";
      state.subSearch = b.subSearch || "";
    } catch (_) {
      state.boardWeek = weekKey();
    }
    state.statsAnchor = monthKey();
    state.monthsKey = monthKey();
    state.monthsYear = new Date().getFullYear();
  }

  function bind() {
    document.querySelectorAll(".tsk-mode-tab[data-task-mode]").forEach((btn) => {
      btn.addEventListener("click", () => switchMode(btn.dataset.taskMode));
    });
    $("#btnTasksFocusBack")?.addEventListener("click", () => switchMode("home"));
    $("#taskDrawerForm")?.addEventListener("submit", (e) => {
      e.preventDefault();
      saveTaskFromDrawer();
    });
    $("#taskEditDrawer")?.addEventListener("cancel", (e) => {
      e.preventDefault();
      closeTaskDrawer();
    });
    $("#btnTaskDrawerClose")?.addEventListener("click", closeTaskDrawer);
    $("#btnTaskDrawerDelete")?.addEventListener("click", () => {
      if (state.editingId && confirm("删除这一条？")) {
        deleteTask(state.editingId);
        closeTaskDrawer();
        renderAll();
      }
    });
    $("#btnTaskSyncTemplate")?.addEventListener("click", () => {
      const base = state.editingId ? taskById(state.editingId) : null;
      if (!base?.templateKey) return;
      const title = $("#taskDrawerTitleInput")?.value.trim();
      if (!title) {
        if (typeof toast === "function") toast("请填写标题", "error");
        return;
      }
      let daySlot = Number($("#taskDrawerDaySlot")?.value);
      const priority = $("#taskDrawerPriority")?.value || "defer";
      if (priority === "inspiration") daySlot = 0;
      const draft = makeTask({
        ...base,
        title,
        notes: $("#taskDrawerNotes")?.value.trim() || "",
        execResult: $("#taskDrawerExecResult")?.value.trim() || "",
        priority,
        daySlot: Number.isFinite(daySlot) ? daySlot : 0,
        slot: $("#taskDrawerSlot")?.value || "",
      });
      refreshTaskInstanceKey(draft);
      upsertTask(draft);
      syncTaskToTemplate(draft);
      closeTaskDrawer();
      renderAll();
    });
    $("#taskEditForm")?.addEventListener("submit", (e) => {
      e.preventDefault();
      saveTaskFromDialog();
    });
    $("#btnTaskCancel")?.addEventListener("click", () => $("#taskEditDialog")?.close());
    $("#btnTaskDelete")?.addEventListener("click", () => {
      if (state.editingId && confirm("删除？")) {
        deleteTask(state.editingId);
        $("#taskEditDialog")?.close();
        renderAll();
      }
    });
    $("#btnTplSave")?.addEventListener("click", saveTemplateDrawer);
    $("#btnTplClose")?.addEventListener("click", () => $("#taskTemplateDialog")?.close());
    $("#taskTemplateDialog")?.addEventListener("cancel", (e) => {
      e.preventDefault();
      $("#taskTemplateDialog")?.close();
    });
    $("#tplAddCategory")?.addEventListener("change", refreshTplSubOptions);
    $("#btnTplAdd")?.addEventListener("click", () => {
      const subId = $("#tplAddSub")?.value;
      if (!subId) return;
      if (addTemplateFromSubcategory(subId)) openTemplateDrawer();
    });
    $("#taskTemplateList")?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-tpl-remove]");
      if (!btn) return;
      const key = btn.getAttribute("data-tpl-remove");
      if (!key || !confirm("从模板池移除此项？已生成本周的任务需手动删。")) return;
      removeTemplateFromPool(key);
      openTemplateDrawer();
    });
  }

  function init() {
    if (!TD()) return;
    restorePrefs();
    bind();
    switchMode(state.mode);
  }

  function onTabEnter() {
    renderAll();
  }

  global.TasksPage = {
    init,
    onTabEnter,
    clearTasksFocusUi,
    switchMode,
    weekKey,
    monthKey,
    loadStore,
    applyWeeklyTemplate,
    getMonthPlan,
    ensureMonthPlan,
  };
})(typeof window !== "undefined" ? window : globalThis);
