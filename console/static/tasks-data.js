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
    flow: "flow",
    dev: "dev",
    work: "work",
    trade: "trade",
    ops: "ops",
    global_ops: "global",
    misc: "misc",
  };

  const CATEGORIES = [{
    id: "flow",
    name: "流控",
    subs: [
      { id: "flow.plan", name: "任务制定" },
      { id: "flow.coord", name: "任务协调" },
      { id: "flow.prio", name: "优先级与取舍" },
      { id: "flow.review", name: "评估复盘" },
      { id: "flow.brain", name: "头脑风暴" },
      { id: "flow.link", name: "灵感串联" },
      { id: "flow.template", name: "周模板 / 日清单" },
      { id: "flow.block", name: "卡点与阻塞" },
    ],
  },
  {
    id: "work",
    name: "工作内容",
    subs: [
      { id: "work.skill.agent", name: "AI Agent / 工作流自动化" },
      { id: "work.skill.scrape", name: "数据采集与监控告警" },
      { id: "work.skill.dash", name: "交易/运营数据看板" },
      { id: "work.skill.ext", name: "浏览器插件与油猴脚本" },
      { id: "work.skill.indiehack", name: "产品 / 小工具之流" },
      { id: "work.skill.template", name: "模板与脚手架" },
      { id: "work.skill.quantui", name: "行情可视化 / 微结构工具" },
      { id: "work.skill.promptops", name: "可复用 Prompt / 技能库" },
      { id: "work.skill.rare", name: "冷门栈（WebGL、音频、本地模型）" },
    ],
  },
  {
    id: "dev",
    name: "软件开发",
    // 接外包、做效率产品、从外网挖需求
    subs: [
      { id: "dev.upwork", name: "Upwork / 海外接单" },
      { id: "dev.demand", name: "外网需求挖掘" },
      { id: "dev.template", name: "网站/SaaS 模板交付" },
      { id: "dev.plugin", name: "效率插件 / 扩展" },
      { id: "dev.internal", name: "自己用的效率工具" },
      { id: "dev.landing", name: "落地页 / 演示站" },
      { id: "dev.maintain", name: "改版、修摊、长期维护" },
      { id: "dev.portfolio", name: "作品集与案例包装" },
      { id: "dev.pricing", name: "报价、范围、合同" },
    ],
  },
  {
    id: "ops",
    name: "web3运营",
    // 广场发优质内容引流，资讯 + K 线技术
    subs: [
      { id: "ops.square", name: "交易所广场分发" },
      { id: "ops.kolcurate", name: "优质 KOL 单拆解转推" },
      { id: "ops.thread", name: "结构向长帖（费率/OI/多空）" },
      { id: "ops.kline", name: "K 线技术解读" },
      { id: "ops.news", name: "币圈资讯快评" },
      { id: "ops.visual", name: "配图 / 情景卡" },
      { id: "ops.engage", name: "评论区互动引流" },
      { id: "ops.calendar", name: "事件日历选题" },
      { id: "ops.repurpose", name: "一稿多发（X/广场/短视频）" },
    ],
  },
  {
    id: "trade",
    name: "web3操盘",
    // 对 KOL/推荐做布局，用技术分析管仓
    subs: [
      { id: "trade.kolplan", name: "KOL/推荐单落地计划" },
      { id: "trade.setup", name: "入场结构（价/OI/费率）" },
      { id: "trade.pos", name: "仓位与杠杆" },
      { id: "trade.invalid", name: "失效条件 / 止损" },
      { id: "trade.watch", name: "盯盘清单" },
      { id: "trade.event", name: "事件驱动单" },
      { id: "trade.arb", name: "价差 / 拥挤反转" },
      { id: "trade.review", name: "复盘（对错在结构还是执行）" },
    ],
  },
  {
    id: "global_ops",
    name: "海外内容",
    // 海外资讯与可变现渠道，尽量产品化/自动化
    subs: [
      { id: "global.source", name: "海外资讯源监控" },
      { id: "global.auto", name: "资讯采集自动化" },
      { id: "global.dist", name: "海外渠道分发（X/Reddit/IH）" },
      { id: "global.product", name: "可售工具 / 信息产品" },
      { id: "global.freelance", name: "海外客户开发" },
      { id: "global.seo", name: "英文关键词 / 趋势验证" },
      { id: "global.pay", name: "收款与上架（模板/插件）" },
      { id: "global.niche", name: "垂直海外场景（Shopify/booking）" },
    ],
  },
  {
    id: "misc",
    name: "其他内容",
    subs: [
      { id: "misc.inspire", name: "灵感收集" },
      { id: "misc.learn", name: "学习笔记" },
      { id: "misc.life", name: "生活事务" },
      { id: "misc.lab", name: "未验证想法" },
      { id: "misc.long", name: "长期项目" },
    ],
  },
  ];

  /** 各大类默认入选模板池的小类（可在「模板」里继续添加同大类其它小类） */
  const DEFAULT_TEMPLATE_SUBIDS = {
    flow: ["flow.plan", "flow.review", "flow.prio"],
    work: ["work.skill.agent", "work.skill.dash", "work.skill.promptops"],
    dev: ["dev.upwork", "dev.demand", "dev.internal"],
    ops: ["ops.square", "ops.thread", "ops.kline"],
    trade: ["trade.kolplan", "trade.setup", "trade.review"],
    global_ops: ["global.source", "global.dist", "global.product"],
    misc: ["misc.inspire", "misc.lab"],
  };

  function templateKeyForSub(subcategoryId) {
    return `wt.${subcategoryId}`;
  }

  function makeWeeklyTemplate(sub, categoryId) {
    return {
      key: templateKeyForSub(sub.id),
      title: sub.name,
      categoryId,
      subcategoryId: sub.id,
      priority: sub.id === "misc.inspire" ? "inspiration" : "defer",
      scheduleKind: "once",
      weekdays: [],
    };
  }

  function makeWeeklyTemplateBySubId(subcategoryId) {
    const sub = subById.get(subcategoryId);
    if (!sub) return null;
    return makeWeeklyTemplate(sub, sub.categoryId);
  }

  /**
   * 内置默认模板池：每大类精选 2–3 个小类，默认待排期（weekdays 空）。
   * 用户可在「模板默认落点」按大类追加小类；自定义项存 localStorage。
   */
  const WEEKLY_TEMPLATES = CATEGORIES.flatMap((cat) =>
    (DEFAULT_TEMPLATE_SUBIDS[cat.id] || [])
      .map((subId) => {
        const sub = cat.subs.find((s) => s.id === subId);
        return sub ? makeWeeklyTemplate(sub, cat.id) : null;
      })
      .filter(Boolean)
  );

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
    DEFAULT_TEMPLATE_SUBIDS,
    WEEKLY_TEMPLATES,
    templateKeyForSub,
    makeWeeklyTemplate,
    makeWeeklyTemplateBySubId,
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
