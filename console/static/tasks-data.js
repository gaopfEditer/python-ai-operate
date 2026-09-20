/**
 * 任务系统 — taxonomy + 按天落周模板（配置层：默认周几）
 *
 * scheduleKind:
 *   once     — 只做一次 → weekdays[0]
 *   weekdays — 每个工作日一条实例
 *   days     — weekdays 里指定的几天各一条
 * 灵感 / 无 weekday → 待排期（daySlot 0）
 */
(function (global) {
  "use strict";

  const WEEKDAY_SLOTS = [1, 2, 3, 4, 5];
  const WEEKEND_SLOT = 6;
  const PLAN_SLOTS = [1, 2, 3, 4, 5, 6];
  const DAY_SHORT = ["", "一", "二", "三", "四", "五", "末"];
  const DAY_NAME = ["", "周一", "周二", "周三", "周四", "周五", "周末"];

  const SCHEDULE_KIND_LABEL = {
    once: "只做一次",
    weekdays: "工作日重复",
    days: "指定几天",
  };

  const PRIORITY_LABEL = {
    must: "P0",
    defer: "可延后",
    inspiration: "灵感",
  };

  const DAY_LIMITS = { p0: 2, total: 5 };

  const SLOT_LABEL = {
    morning: "上午",
    focus: "高能",
    wrap: "收尾",
  };

  const CAT_COLORS = {
    dev: "dev",
    work: "work",
    trade: "trade",
    ops: "ops",
    global_ops: "global",
    misc: "misc",
  };

  const CATEGORIES = [
    {
      id: "dev",
      name: "软件开发",
      subs: [
        { id: "dev.ui", name: "前端 UI/交互" },
        { id: "dev.ds", name: "组件与设计系统" },
        { id: "dev.api", name: "接口联调" },
        { id: "dev.perf", name: "性能与体验" },
        { id: "dev.bug", name: "Bug 修复" },
        { id: "dev.tool", name: "工程化/工具链" },
        { id: "dev.review", name: "代码评审与重构" },
        { id: "dev.release", name: "发版与验收" },
      ],
    },
    {
      id: "work",
      name: "工作内容",
      subs: [
        { id: "work.meet", name: "会议与对齐" },
        { id: "work.doc", name: "文档与方案" },
        { id: "work.track", name: "进度跟进" },
        { id: "work.xteam", name: "跨部门协作" },
        { id: "work.report", name: "周报/复盘" },
        { id: "work.hire", name: "招聘/面试" },
        { id: "work.admin", name: "行政事务" },
      ],
    },
    {
      id: "trade",
      name: "web3操盘",
      subs: [
        { id: "trade.watch", name: "行情观察" },
        { id: "trade.pos", name: "仓位管理" },
        { id: "trade.onchain", name: "链上数据" },
        { id: "trade.risk", name: "风险控制" },
        { id: "trade.review", name: "交易复盘" },
        { id: "trade.macro", name: "宏观/事件驱动" },
        { id: "trade.exp", name: "策略实验" },
      ],
    },
    {
      id: "ops",
      name: "web3运营",
      subs: [
        { id: "ops.content", name: "内容策划" },
        { id: "ops.community", name: "社区运营" },
        { id: "ops.kol", name: "KOL/合作" },
        { id: "ops.event", name: "活动与空投" },
        { id: "ops.dashboard", name: "数据看板" },
        { id: "ops.brand", name: "品牌与叙事" },
        { id: "ops.growth", name: "用户增长" },
      ],
    },
    {
      id: "global_ops",
      name: "海外运营",
      subs: [
        { id: "global.i18n", name: "多语言内容" },
        { id: "global.social", name: "海外社媒" },
        { id: "global.growth", name: "增长实验" },
        { id: "global.l10n", name: "本地化适配" },
        { id: "global.ads", name: "渠道投放" },
        { id: "global.feedback", name: "用户反馈" },
        { id: "global.partner", name: "合作拓展" },
      ],
    },
    {
      id: "misc",
      name: "其他思路",
      subs: [
        { id: "misc.inspire", name: "灵感收集" },
        { id: "misc.learn", name: "学习笔记" },
        { id: "misc.lab", name: "实验想法" },
        { id: "misc.long", name: "长期项目" },
        { id: "misc.adhoc", name: "临时插入" },
      ],
    },
  ];

  /**
   * 验收标准（生成本周后）：
   * 一：会议对齐、前端主块、行情观察
   * 二：内容策划、行情观察
   * 三：前端主块、行情观察
   * 四：海外/社区、行情观察
   * 五：复盘、发版与验收、行情观察
   * 待排期：灵感 ≤1
   */
  const WEEKLY_TEMPLATES = [
    {
      key: "wt.meet",
      title: "会议与对齐",
      categoryId: "work",
      subcategoryId: "work.meet",
      priority: "must",
      scheduleKind: "once",
      weekdays: [1],
      slot: "morning",
    },
    {
      key: "wt.ui",
      title: "前端主块",
      categoryId: "dev",
      subcategoryId: "dev.ui",
      priority: "must",
      scheduleKind: "days",
      weekdays: [1, 3],
      slot: "focus",
    },
    {
      key: "wt.content",
      title: "内容策划",
      categoryId: "ops",
      subcategoryId: "ops.content",
      priority: "must",
      scheduleKind: "once",
      weekdays: [2],
      slot: "focus",
    },
    {
      key: "wt.social",
      title: "海外/社区",
      categoryId: "global_ops",
      subcategoryId: "global.social",
      priority: "defer",
      scheduleKind: "once",
      weekdays: [4],
    },
    {
      key: "wt.review",
      title: "复盘",
      categoryId: "trade",
      subcategoryId: "trade.review",
      priority: "must",
      scheduleKind: "once",
      weekdays: [5],
      slot: "wrap",
    },
    {
      key: "wt.release",
      title: "发版与验收",
      categoryId: "dev",
      subcategoryId: "dev.release",
      priority: "must",
      scheduleKind: "once",
      weekdays: [5],
      slot: "wrap",
    },
    {
      key: "wt.watch",
      title: "行情观察",
      categoryId: "trade",
      subcategoryId: "trade.watch",
      priority: "defer",
      scheduleKind: "weekdays",
      weekdays: [1, 2, 3, 4, 5],
      slot: "morning",
    },
    {
      key: "wt.inspire",
      title: "灵感收集",
      categoryId: "misc",
      subcategoryId: "misc.inspire",
      priority: "inspiration",
      scheduleKind: "once",
      weekdays: [],
    },
  ];

  const catById = new Map(CATEGORIES.map((c) => [c.id, c]));
  const subById = new Map();
  CATEGORIES.forEach((c) => c.subs.forEach((s) => subById.set(s.id, { ...s, categoryId: c.id, categoryName: c.name })));

  function getCategory(id) {
    return catById.get(id) || null;
  }

  function getSubcategory(id) {
    return subById.get(id) || null;
  }

  function subLabel(subcategoryId) {
    return subById.get(subcategoryId)?.name || subcategoryId || "—";
  }

  function catLabel(categoryId) {
    return catById.get(categoryId)?.name || categoryId || "—";
  }

  function normalizeTemplate(tpl) {
    const t = { ...tpl };
    if (!t.scheduleKind) {
      if ((t.weekdays || []).length >= 5) t.scheduleKind = "weekdays";
      else if ((t.weekdays || []).length > 1) t.scheduleKind = "days";
      else t.scheduleKind = "once";
    }
    return t;
  }

  /** 展开为带 daySlot 的实例描述；0 = 待排期 */
  function expandTemplateSlots(tplRaw) {
    const tpl = normalizeTemplate(tplRaw);
    if (tpl.priority === "inspiration") {
      return [{ ...tpl, daySlot: 0 }];
    }
    const wd = Array.isArray(tpl.weekdays) ? tpl.weekdays : [];
    let days = [];
    if (tpl.scheduleKind === "once") {
      days = wd.length ? [Number(wd[0])] : [];
      days = days.filter((d) => d >= 1 && d <= WEEKEND_SLOT);
    } else if (tpl.scheduleKind === "weekdays") {
      days = (wd.length ? wd : WEEKDAY_SLOTS).map(Number).filter((d) => d >= 1 && d <= 5);
    } else if (tpl.scheduleKind === "days") {
      days = wd.map(Number).filter((d) => d >= 1 && d <= WEEKEND_SLOT);
    }
    if (!days.length) return [{ ...tpl, daySlot: 0 }];
    return days.map((daySlot) => ({ ...tpl, daySlot }));
  }

  function instanceDedupKey(weekKey, templateKey, daySlot) {
    return `${weekKey}|${templateKey}|${daySlot}`;
  }

  function formatTemplateDays(tplRaw) {
    const slots = expandTemplateSlots(tplRaw);
    if (slots.length === 1 && slots[0].daySlot === 0) return "待排期";
    return slots
      .map((s) => DAY_NAME[s.daySlot] || "")
      .filter(Boolean)
      .join("、");
  }

  global.TasksData = {
    CATEGORIES,
    WEEKLY_TEMPLATES,
    WEEKDAY_SLOTS,
    WEEKEND_SLOT,
    PLAN_SLOTS,
    DAY_SHORT,
    DAY_NAME,
    DAY_LIMITS,
    SLOT_LABEL,
    CAT_COLORS,
    SCHEDULE_KIND_LABEL,
    PRIORITY_LABEL,
    getCategory,
    getSubcategory,
    subLabel,
    catLabel,
    normalizeTemplate,
    expandTemplateSlots,
    instanceDedupKey,
    formatTemplateDays,
  };
})(typeof window !== "undefined" ? window : globalThis);
