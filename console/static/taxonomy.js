/**
 * 叙事类目词典 + 内容模板数据（taxonomy）
 *
 * 内容由用户按主题追加，不要把文案写死在 UI 组件里。
 * 改本文件即可增删大类 / 小类 / 模板，taxonomy-page.js 无需改结构。
 *
 * 类型约定（等价于 taxonomy.ts）：
 *   Stance = "bull" | "bear" | "neutral" | "mixed"
 *   Category: { id, name, desc?, importance: 1|2|3|4|5, importanceNote?, topics[] }
 *   Topic: { ..., importance, importanceNote?, impactSummary?, impactOn[], scenarios[] }
 *   impactOn: { target, mechanism, lag }[] — 传导链（右栏卡片，浮层 1 句摘要）
 *   scenarios: { id: good|bad|mixed, name, if, then, coins[], stance, template, invalidation }[]
 *   templates: { id, topicId, title, body, stance, coins[], category?, tags[], analogy? }
 *   importance 表示「多常被拿来做内容和交易框架」，非投资评级
 *
 * 边界：不要在此生成完整话术库；每小类 1 段含义、约 3 条话术、0～1 条占位模板即可。
 */
(function (global) {
  "use strict";

  /** @param {string} topicId @param {string} title @param {string} body @param {object} [extra] */
  function phTpl(topicId, title, body, extra) {
    return {
      id: topicId + ".tpl1",
      topicId,
      title,
      stance: "neutral",
      coins: ["BTC"],
      tags: ["占位"],
      body,
      placeholder: true,
      ...(extra || {}),
    };
  }

  /** @param {string} topicId @param {string} title @param {string} body @param {object} [extra] id, stance, coins, category, tags[], analogy */
  function tpl(topicId, title, body, extra) {
    const e = extra || {};
    return {
      id: e.id || topicId + ".tpl1",
      topicId,
      title,
      stance: e.stance ?? "mixed",
      coins: e.coins ?? ["BTC"],
      category: e.category ?? "",
      tags: e.tags ?? [],
      analogy: e.analogy ?? "",
      body,
      placeholder: false,
    };
  }

  /** @param {string} target @param {string} mechanism @param {string} lag */
  function impactOn(target, mechanism, lag) {
    return { target, mechanism, lag };
  }

  /** @param {"good"|"bad"|"mixed"} id @param {object} o */
  function scenario(id, o) {
    return { id, ...o };
  }

  /** @param {object} o */
  function topic(o) {
    return {
      templates: [],
      defaultStance: "mixed",
      importance: 3,
      impactOn: [],
      scenarios: [],
      ...o,
    };
  }

  const categories = [
    {
      id: "macro",
      name: "宏观与传统金融",
      desc: "利率、通胀、就业、美元与风险资产联动",
      topics: [
        topic({
          id: "macro.cpi",
          categoryId: "macro",
          name: "CPI / 通胀数据",
          meaning: "消费者物价指数决定市场对「通胀粘性」与降息预期的定价，是短周期 crypto 波动的高频开关。",
          impactSummary:
            "CPI 经 FOMC 路径、DXY/实际利率、ETF 质量与美股四条链影响 BTC，窗口从数据公布到下次议息。",
          relatedThemes: ["macro.fomc", "macro.dxy", "macro.equities", "structure.etf_flow"],
          talkingPoints: [
            "通胀超预期但核心回落，市场会先交易「坏消息是好消息」",
            "同比改善不等于环比安全，别只看 headline",
            "数据公布前波动率抬升，公布后看 ETF 资金流是否验证",
          ],
          defaultCoins: ["BTC", "DXY"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("FOMC", "超预期→加息/延后降息；低于预期相反", "本次数据到下次议息"),
            impactOn("实际利率 / DXY", "通胀粘滞则美元和实际利率易上，压制 BTC；通胀回落则相反", "数据后 24h"),
            impactOn("ETF / 风险偏好", "利空落地后看 ETF 是跟跌还是吸筹，用来判断质量", "数据后 24h"),
            impactOn("美股 → BTC", "先看纳指夜盘，再看 BTC 是否跟上", "即时"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（对风险资产）",
              if: "headline 略热但 core 回落 / 或整体低于预期",
              then: "交易「坏消息是好消息」，降息交易升温",
              coins: ["BTC", "ETH"],
              stance: "bull",
              template:
                "CPI 表面还热，但核心在降温。市场会先交易路径，不交易单次读数。BTC 短线跟风险资产，失效看 DXY 是否同步转弱。",
              invalidation: "core 也超预期，或鲍威尔/Warsh 当晚把数据说成「还不够」",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "headline 和 core 双双超预期，或服务通胀再加速",
              then: "加息路径上修，实际利率上，ETF 易流出",
              coins: ["BTC", "DXY"],
              stance: "bear",
              template:
                "这次不是 headline 噪音，core 一起超预期。定价会从「一次数据」变成「更多次加息」。先看 BTC 能否守住加息前低点，守不住就不要用反弹当新趋势。",
              invalidation: "美股反而大涨且 ETF 净流入",
            }),
            scenario("mixed", {
              name: "分裂读数",
              if: "headline 超预期、core 回落",
              then: "先涨后分化，波动率抬、方向隔夜才清晰",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "通胀超预期但核心回落，短线会有人喊利空利多各打一架。先交易波动，不交易方向。等 FOMC 和 ETF 资金流来确认谁赢。",
              invalidation: "ETF 次日单边流出且 DXY 续强",
            }),
          ],
          templates: [
            phTpl(
              "macro.cpi",
              "CPI 超预期 vs 核心回落",
              "通胀超预期但核心回落，短线多空各打一架。先交易波动，等 FOMC 与 ETF 资金流确认方向。"
            ),
          ],
        }),
        topic({
          id: "macro.pce",
          categoryId: "macro",
          name: "PCE / 美联储偏好通胀",
          meaning: "PCE 是美联储更关注的通胀指标，对路径指引的权重往往高于 CPI。",
          impactSummary: "PCE 直接喂给 FOMC 叙事，经实际利率/DXY 影响 BTC；Fed 看 PCE 多于 CPI。",
          relatedThemes: ["macro.fomc", "macro.cpi", "macro.dxy"],
          talkingPoints: [
            "PCE 粘住则「更高更久」叙事难消",
            "服务通胀是慢变量，别用单月数据赌拐点",
            "与 CPI 背离时，写清「Fed 看哪个」",
          ],
          defaultCoins: ["BTC", "DXY"],
          impactOn: [
            impactOn("FOMC", "PCE 粘滞→更高更久；回落→降息窗口打开", "下次 SEP / 议息"),
            impactOn("实际利率 / DXY", "核心 PCE 顽固则实际利率难下，压制风险资产", "数据后 24h"),
            impactOn("BTC", "PCE 低于预期→降息交易；高于预期→重力向下", "数据后 24h"),
            impactOn("macro.cpi", "CPI 与 PCE 背离时，写清 Fed 更信哪个", "即时"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "核心 PCE 环比回落且同比路径下修",
              then: "降息预期升温，实际利率回落",
              coins: ["BTC", "ETH"],
              stance: "bull",
              template:
                "Fed 看的 PCE 在降温，比 CPI headline 更重要。市场会交易路径而非单次，BTC 跟降息预期走。失效看鲍威尔是否强调「一次数据不够」。",
              invalidation: "服务业分项反弹或 Fed 官员口头纠偏",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "核心 PCE 再加速或同比粘于 3% 上方",
              then: "降息推迟，DXY 与实际利率易上",
              coins: ["BTC", "DXY"],
              stance: "bear",
              template:
                "PCE 粘住，「更高更久」难消。别用 CPI 改善对冲这条链——写稿时写清 Fed 偏好指标。BTC 反弹先看 DXY 是否同步转弱。",
              invalidation: "同时公布的就业大幅走弱",
            }),
            scenario("mixed", {
              name: "分裂读数",
              if: "headline PCE 热、核心分项分化",
              then: "市场先震荡，等服务/住房分项解读",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "PCE 总量与核心分裂，和 CPI 剧本类似但更偏 Fed 口径。先写结构：哪条分项驱动路径，再落到 BTC 多空。",
              invalidation: "发布会当晚 Fed 定调一边倒",
            }),
          ],
        }),
        topic({
          id: "macro.nfp",
          categoryId: "macro",
          name: "非农 / 就业",
          meaning: "劳动力市场强弱影响软着陆 vs 硬着陆叙事，进而牵动 risk-on / risk-off。",
          impactSummary: "非农经 FOMC 降息窗口、实际利率与美股三条链影响 BTC；revision 与 wage 比 headline 重要。",
          relatedThemes: ["macro.fomc", "macro.dxy", "macro.equities"],
          talkingPoints: [
            "非农强 ≠ 立刻利空 BTC，要看收益率曲线怎么动",
            "失业率抬升有时反而交易降息预期",
            "revision 与 wage 分项比 headline 更重要",
          ],
          defaultCoins: ["BTC", "SPX"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("FOMC", "就业过热→降息推迟；走弱→软着陆/降息交易", "数据到下次议息"),
            impactOn("实际利率 / DXY", "强非农→收益率上、美元强；弱非农相反", "数据后 24h"),
            impactOn("美股", "非农 beat 有时利好「软着陆」而非立刻杀估值", "即时"),
            impactOn("BTC", "先看美股与 DXY，再看 BTC 是否跟风险偏好", "即时"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "非农低于预期且 wage 降温 / 失业率温和抬升",
              then: "降息预期升，risk-on",
              coins: ["BTC", "ETH"],
              stance: "bull",
              template:
                "就业在降温但非崩盘，市场会交易「软着陆+降息」。BTC 跟风险偏好，先看纳指夜盘是否同步。失效看 core PCE 是否同时反弹。",
              invalidation: "鲍威尔强调劳动力仍「过强」",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "非农大超预期且 wage 再加速",
              then: "降息路径后移，实际利率上",
              coins: ["BTC", "DXY"],
              stance: "bear",
              template:
                "就业还热，降息别指望太早。BTC 短线易跟 DXY 承压，高 beta 山寨更敏感。写稿点出 wage 分项，别只报 headline。",
              invalidation: "收益率曲线 steepen 且美股大涨",
            }),
            scenario("mixed", {
              name: "分裂读数",
              if: "headline 强但 revision 下修 / 兼职增全职减",
              then: "先震荡，等 Fed 口径",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "非农 headline 和 revision 打架，和 CPI 分裂读数同一套写法：先交易波动，等 FOMC 定调。",
              invalidation: "次日 Fed 讲话单边解读就业",
            }),
          ],
        }),
        topic({
          id: "macro.fomc",
          categoryId: "macro",
          name: "FOMC / 利率决议",
          meaning: "美联储议息、点阵图、声明措辞和发布会，是定价风险资产的主开关。",
          impactSummary:
            "FOMC 定利率路径，经 DXY/实际利率与 ETF 流入影响 BTC 趋势质量；市场交易的是下一次。",
          relatedThemes: ["macro.dxy", "structure.etf_flow", "macro.equities"],
          talkingPoints: [
            "加息落地但点阵图更鹰，利空是路径不是一次操作",
            "市场交易的是下一次，不是这一次",
            "声明偏鹰但风险资产不跌 = 利空定价完毕",
          ],
          defaultCoins: ["BTC", "DXY"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("DXY / 实际利率", "鹰派点阵→美元与实际利率上；鸽派则相反", "发布会后 24h"),
            impactOn("BTC", "降息/软指引→风险偏好；hawkish surprise→先杀流动性", "即时"),
            impactOn("ETF 流入", "议息后 48h 净流入验证方向，流出则反弹质量差", "议息后 48h"),
            impactOn("美股", "声明措辞 vs 利率决定，纳指常先行", "即时"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "暂停/降息且点阵图下修，鲍威尔口风偏鸽",
              then: "降息交易升温，流动性预期改善",
              coins: ["BTC", "ETH"],
              stance: "bull",
              template:
                "Fed 给的路径比决议本身更重要——点阵图下修就是 risk-on。BTC 看 ETF 是否 48h 内净流入验证。失效：DXY 不跌反涨。",
              invalidation: "通胀数据次日反转鸽派叙事",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "加息或维持但点阵图更鹰、措辞强调通胀未控",
              then: "路径上修，实际利率上，ETF 易流出",
              coins: ["BTC", "DXY"],
              stance: "bear",
              template:
                "加息落地不是终点，点阵图更鹰才是利空。定价从「这一次」变成「更多次」。BTC 守不住议息前低点就别当新趋势。",
              invalidation: "风险资产不跌反涨 = 利空出尽",
            }),
            scenario("mixed", {
              name: "分裂读数",
              if: "加息 25bp 但发布会偏软 / 点阵图分歧",
              then: "先波动后分化，看 ETF 与 DXY 谁赢",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "决议和发布会分裂，和 CPI 分裂同一写法：先交易波动。等 ETF 资金流和 DXY 方向确认后再下结论。",
              invalidation: "次日 Fed 官员统一口径纠偏",
            }),
          ],
          templates: [
            phTpl(
              "macro.fomc",
              "加息落地 vs 点阵图",
              "决议本身是一回事，点阵图和鲍威尔措辞定路径。先看 DXY 与 ETF 48h 净流入再写 BTC 方向。"
            ),
          ],
        }),
        topic({
          id: "macro.dxy",
          categoryId: "macro",
          name: "DXY / 实际利率",
          meaning: "美元与实际利率是 BTC 的「重力方向」，流动性收紧时叙事再热也容易被压回。",
          impactSummary: "DXY 与实际利率是 BTC 重力；破关键位后流动性叙事才容易回归。",
          relatedThemes: ["macro.fomc", "macro.cpi", "structure.etf_flow"],
          talkingPoints: [
            "DXY 破关键位，别只写「利空 BTC」要写传导链",
            "实际利率上行时，高 beta 山寨先死",
            "美元与 BTC 同涨 = 特殊情境，要单独解释",
          ],
          defaultCoins: ["BTC", "DXY"],
          impactOn: [
            impactOn("BTC", "DXY 上→BTC 重力下；DXY 破关键位→流动性叙事回归", "即时"),
            impactOn("实际利率", "与实际利率同步，高 beta 山寨更敏感", "即时"),
            impactOn("ETF 流入", "美元强时 ETF 流入易放缓，反弹质量变差", "周内"),
            impactOn("macro.fomc", "DXY 方向常由 FOMC 路径驱动，写传导别孤立看美元", "下次议息"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（DXY 弱）",
              if: "DXY 跌破关键位 / 实际利率回落",
              then: "BTC 重力减轻，ETF 流入易配合",
              coins: ["BTC", "ETH"],
              stance: "bull",
              template:
                "美元和实际利率在转弱，BTC 的「重力」减轻。别只喊多——看 ETF 是否同步净流入验证。失效：美股同步大跌。",
              invalidation: "地缘推升避险买美元",
            }),
            scenario("bad", {
              name: "坏情况（DXY 强）",
              if: "DXY 续强且实际利率创新高",
              then: "流动性收紧，高 beta 先杀",
              coins: ["BTC", "DXY"],
              stance: "bear",
              template:
                "美元还在上、实际利率还在上，叙事再热也容易被压回。BTC 反弹先看 DXY 是否止涨，山寨别抢跑。",
              invalidation: "BTC 与 DXY 同涨（特殊情境需单独解释）",
            }),
            scenario("mixed", {
              name: "分裂读数",
              if: "DXY 强但 BTC 不跟跌 / 或实际利率与美元背离",
              then: "有特殊催化，别用单一指标下结论",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "美元和 BTC 不同步，说明还有别的链在起作用（ETF、地缘、监管）。先写清哪条链主导，再定多空。",
              invalidation: "24h 内 DXY 与 BTC 恢复负相关",
            }),
          ],
        }),
        topic({
          id: "macro.equities",
          categoryId: "macro",
          name: "美股联动",
          meaning: "BTC 与纳指/标普的相关性在机构化后更高，美股夜盘常是 crypto 的先行指标。",
          impactSummary: "纳指/标普夜盘常领先 BTC；ETF 机构化后相关性更高，但 crypto 特有催化可脱钩。",
          relatedThemes: ["structure.etf_flow", "macro.dxy", "macro.cpi"],
          talkingPoints: [
            "美股跌 BTC 不跟，可能是 crypto 特有催化",
            "期货升水/贴水要看 CME 与现货 ETF 是否一致",
            "财报季别硬蹭，写清「相关不等于因果」",
          ],
          defaultCoins: ["BTC", "NDX"],
          impactOn: [
            impactOn("BTC", "纳指夜盘 lead，BTC 常滞后 0–4h 跟进", "即时"),
            impactOn("ETF 流入", "美股 risk-on 时 ETF 流入易配合 BTC", "日内"),
            impactOn("风险偏好", "标普跌→crypto beta 放大；涨→跟涨但常弱于纳指", "即时"),
            impactOn("DXY", "美股强且 DXY 弱 = 最佳组合；股跌美元涨 = 双杀", "即时"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "纳指大涨且 DXY 弱 / 软着陆叙事",
              then: "BTC 跟涨，ETF 流入易验证",
              coins: ["BTC", "ETH"],
              stance: "bull",
              template:
                "美股 risk-on，BTC 机构化后跟纳指更紧。先看 ETF 是否净流入，再写延续性。失效：BTC 4h 仍不跟。",
              invalidation: "CPI/FOMC 次日逆转风险偏好",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "纳指大跌且 VIX 飙升",
              then: "BTC 易跟跌且 beta 更大",
              coins: ["BTC"],
              stance: "bear",
              template:
                "美股在杀估值，BTC 很难独善其身。高 beta 山寨先死。若 BTC 不跟跌，要写清 crypto 特有催化。",
              invalidation: "BTC 脱钩上涨且有独立利好",
            }),
            scenario("mixed", {
              name: "分裂读数",
              if: "美股涨 BTC 不涨 / 或股跌 BTC 横",
              then: "脱钩，查 ETF、监管或链上特有因子",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "股和币不同步，别硬写联动。先找脱钩原因：ETF 流、监管、还是大额链上转移。",
              invalidation: "24h 内恢复同步涨跌",
            }),
          ],
        }),
        topic({
          id: "macro.geo",
          categoryId: "macro",
          name: "地缘 / 避险",
          meaning: "战争、制裁、能源冲击会同时推升避险与通胀预期，BTC 可能「数字黄金」或「风险资产」两种剧本。",
          impactSummary: "地缘首小时看 BTC 跟黄金还是跟股市；能源冲击分「流动性」与「通胀」两条路径。",
          relatedThemes: ["macro.dxy", "macro.cpi", "macro.equities"],
          talkingPoints: [
            "地缘升级首小时看 BTC 跟黄金还是跟股市",
            "制裁链上地址 ≠ 全网避险，别过度 extrapolate",
            "能源冲击下，写清对流动性 vs 通胀的两条路径",
          ],
          defaultCoins: ["BTC", "XAU"],
          defaultStance: "neutral",
          impactOn: [
            impactOn("BTC", "升级首小时：跟黄金=避险；跟股市跌=风险资产", "即时"),
            impactOn("原油 / 通胀", "能源冲击推通胀预期→间接压 FOMC 路径", "周内"),
            impactOn("DXY", "避险常买美元；若美元与黄金同涨需单独解释", "即时"),
            impactOn("美股", "地缘恶化→ risk-off，BTC 常第二阶段反应", "即时"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（避险叙事）",
              if: "升级但 BTC 跟黄金涨、股市跌",
              then: "交易「数字黄金」剧本",
              coins: ["BTC", "XAU"],
              stance: "bull",
              template:
                "地缘升级首小时，BTC 跟黄金而不是跟股市——写避险剧本。别过度 extrapolate 链上制裁。失效：24h 内 BTC 转跟股市跌。",
              invalidation: "美元暴涨压制所有非美资产",
            }),
            scenario("bad", {
              name: "坏情况（risk-off）",
              if: "全面 risk-off：股、债、BTC 同杀",
              then: "流动性收缩，BTC 当风险资产卖",
              coins: ["BTC"],
              stance: "bear",
              template:
                "这次是流动性危机式抛售，BTC 不会 magically 避险。先写 risk-off，再写有没有独立 crypto 催化。",
              invalidation: "BTC 逆势强且 ETF 净流入",
            }),
            scenario("mixed", {
              name: "分裂读数",
              if: "黄金涨 BTC 横 / 或能源涨但股市不跌",
              then: "两条路径打架，等 24h 定主导",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "地缘从不是单剧本。通胀路径和避险路径同时在定价——先写结构，别首小时就定多空。",
              invalidation: "Fed 或财政回应改变叙事",
            }),
          ],
        }),
      ],
    },
    {
      id: "policy",
      name: "监管、政策与司法",
      desc: "立法、执法、审批与合规边界",
      topics: [
        topic({
          id: "policy.sec",
          categoryId: "policy",
          name: "SEC / 执法",
          meaning: "美国 SEC 对代币、交易所、staking 的执法与诉讼，直接影响美国用户可用的产品与叙事空间。",
          relatedThemes: ["ETF", "交易所", "staking", "policy.enforcement"],
          talkingPoints: [
            "起诉 ≠ 立即退市，写清影响路径（流动性/上币/美国 IP）",
            "和解条款里的「是否承认证券属性」才是长期雷",
            "执法密集期，别把所有币都写成同一命运",
          ],
          defaultCoins: ["BTC", "ETH"],
        }),
        topic({
          id: "policy.etf",
          categoryId: "policy",
          name: "ETF 审批 / 政策",
          meaning: "现货 ETF 的批准、延期、修订与新增资产类别，是增量资金与合法化叙事的核心。",
          relatedThemes: ["structure.etf_flow", "BTC", "ETH"],
          talkingPoints: [
            "批准当天往往 sell the news，写清「预期已计价多少」",
            "延期不是否决，别写成末日",
            "新增 alt ETF 先写合规边界再写价格目标",
          ],
          defaultCoins: ["BTC", "ETH"],
        }),
        topic({
          id: "policy.stable",
          categoryId: "policy",
          name: "稳定币法案",
          meaning: "稳定币监管框架决定链上美元轨道的合规形态，影响 DeFi 与支付叙事。",
          relatedThemes: ["metastory.stable_rail", "DeFi", "USDC"],
          talkingPoints: [
            "草案 vs 通过 vs 执行，三阶段别混写",
            "合规稳定币受益 ≠ 所有算法稳定币同涨",
            "写清对 CEX 入金/出金链路的二阶影响",
          ],
          defaultCoins: ["USDC", "BTC"],
        }),
        topic({
          id: "policy.mica",
          categoryId: "policy",
          name: "MiCA / 欧盟框架",
          meaning: "欧盟 MiCA 为交易所与代币发行提供统一规则，影响欧洲运营与全球合规标杆。",
          relatedThemes: ["交易所", "稳定币", "CASPs"],
          talkingPoints: [
            "牌照名单是慢变量，短期看预期长期看落地",
            "欧洲用户迁移会改变 CEX 份额",
            "与 SEC 路径对比，写「双轨合规」",
          ],
          defaultCoins: ["BTC", "ETH"],
        }),
        topic({
          id: "policy.enforcement",
          categoryId: "policy",
          name: "重大执法 / 和解案",
          meaning: "高额罚款、刑事案、和解协议中的业务限制，会重塑品类风险溢价。",
          relatedThemes: ["policy.sec", "交易所", "mixer"],
          talkingPoints: [
            "和解金金额不如「业务是否可持续」重要",
            "同一事件对不同赛道影响不对称",
            "后续 copycat 执法风险要单独点出",
          ],
          defaultStance: "bear",
        }),
        topic({
          id: "policy.cftc",
          categoryId: "policy",
          name: "CFTC / 衍生品监管",
          meaning: "CFTC 对期货、perp 与离岸平台的管辖，影响杠杆产品可用性与 OI 结构。",
          relatedThemes: ["structure.funding", "Perp DEX", "交易所"],
          talkingPoints: [
            "管辖权争议时，写「谁管 spot 谁管 perp」",
            "限制美国 IP 后 OI 迁移到哪条链",
            "政策草案 comment period 是预期博弈窗口",
          ],
          defaultCoins: ["BTC"],
        }),
      ],
    },
    {
      id: "structure",
      name: "市场结构与资金流",
      desc: "费率、OI、ETF、Dominance 与到期",
      topics: [
        topic({
          id: "structure.funding",
          categoryId: "structure",
          name: "资金费 / OI",
          importance: 5,
          meaning:
            "永续资金费看拥挤方向，持仓量 OI 看杠杆堆积。价格、费率、OI 三者一起看，才能判断是趋势加仓还是挤压前夜。",
          impactSummary:
            "费率极端 + OI 高位预示挤压风险；经爆仓、ETF 质量与期权到期周影响 BTC 短线方向。",
          relatedThemes: [
            "ta.liquidation",
            "structure.etf_flow",
            "structure.options",
            "structure.btcd",
            "structure.liquidity",
            "macro.fomc",
          ],
          talkingPoints: [
            "费率极正 + OI 新高，涨的是拥挤，不是趋势",
            "OI 升、价格不升，多半是两边加杠杆，波动率要来",
            "费率翻负但价格不破位，空头在送钱",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("爆仓 / 清算 cascade", "费率极端后，反向一根就容易踩踏", "即时"),
            impactOn("现货 ETF 流入", "费率热、ETF 却流出 = 杠杆牛，质量差", "数据后 24h"),
            impactOn("期权到期 / Max Pain", "高 OI 叠到期周，max pain 更有引力", "到期日"),
            impactOn("BTC", "拥挤方向常是反转方向", "1–8h"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（趋势健康）",
              if: "价格涨、OI 跟涨、费率温和（未到极端分位）",
              then: "真实加仓，回调可低吸",
              coins: ["BTC"],
              stance: "bull",
              template:
                "这波不是纯空头回补。价格和 OI 一起上，费率还没到拥挤区。短线 BTC 偏多，失效看费率冲到近 30 日高位而价格滞涨。",
              invalidation: "费率暴涨或 OI 创高但价格回吐",
            }),
            scenario("bad", {
              name: "坏情况（拥挤待爆）",
              if: "资金费极端正/负 + OI 高位 + 价格停滞",
              then: "反向一次就挤压，先砸费率拥挤的一侧",
              coins: ["BTC"],
              stance: "bear",
              template:
                "费率已经到极端，OI 还在堆。现在交易的是谁先平仓，不是基本面。极正就不要追多，等一次降 OI 的洗盘。",
              invalidation: "ETF 大额流入把拥挤变成趋势",
            }),
            scenario("mixed", {
              name: "分裂/纠结",
              if: "费率与 OI 反向（价涨 OI 降，或价跌 OI 升）",
              then: "一是空头回补，二是有人在对冲，方向要等下一根确认",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "价格和仓位在打架。先写清是降 OI 上涨还是加 OI 下跌，再下多空。今天只交易波动。",
              invalidation: "4 小时内费率和 OI 重新同向",
            }),
          ],
          templates: [
            tpl(
              "structure.funding",
              "极端费率 + OI 堆",
              "极端{品种}费率已经{极正/极负}，OI 还在堆：现在交易的是谁先平仓。",
              {
                id: "crowd_stack",
                category: "极端",
                analogy: "像拔河两边都在加人，比的是谁先松手",
              }
            ),
            tpl(
              "structure.funding",
              "离瀑布差一根针",
              "高费率 + 高 OI + 价格走不动，{品种}离清算瀑布还差一根针。",
              {
                id: "cascade_needle",
                category: "极端",
                analogy: "三根火柴都点了，桶盖还在收窄",
              }
            ),
            tpl(
              "structure.funding",
              "空头费率 vs 现货买",
              "{品种}空头费率打满、现货却在买：逼空和踩踏只隔一根 K。",
              {
                id: "short_funding_spot_bid",
                category: "极端",
                stance: "mixed",
                analogy: "合约在喊空，现货在接货——同一品种两种剧本",
              }
            ),
            tpl(
              "structure.funding",
              "新高但波动收窄",
              "OI 新高、费率新高、波动却在收窄：这是趋势还是炸药包？",
              {
                id: "squeeze_or_trend",
                category: "极端",
                analogy: "盖子越拧越紧，要么闷燃要么爆",
              }
            ),
            tpl(
              "structure.funding",
              "拥挤先洗 OI",
              "{品种}多头拥挤到极值，第一波洗盘通常先打 OI，不是先打叙事。",
              {
                id: "wash_oi_first",
                category: "极端",
                analogy: "先卸杠杆，再谈故事对不对",
              }
            ),
            tpl(
              "structure.funding",
              "Cascade 检查清单",
              "费率极端后反向一根就容易踩踏：列出{品种}的 cascade 检查清单（哪侧 OI、哪档清算、深度在哪）。",
              {
                id: "cascade_checklist",
                category: "极端",
                analogy: "多米诺：第一块倒下去看下一档在哪",
              }
            ),
            tpl(
              "structure.funding",
              "合约溢价抢方向",
              "{品种}合约比现货贵到离谱，杠杆在抢方向而不是在定价。",
              {
                id: "perp_premium",
                category: "极端",
                analogy: "期货像在竞价抢座，现货还没投票",
              }
            ),
            tpl(
              "structure.funding",
              "期权墙叠费率极值",
              "Max Pain / 期权墙叠在费率极值上：{品种}短线更像磁铁，不是趋势。",
              {
                id: "maxpain_magnet",
                category: "极端",
                analogy: "两块磁铁叠一起，价格被吸向墙而不是跑趋势",
              }
            ),
            tpl(
              "structure.funding",
              "价涨 OI 跟、费率温和",
              "常见价涨、OI 跟、费率不烫：{品种}这叫趋势在加仓。",
              {
                id: "trend_add",
                category: "常见",
                stance: "bull",
                analogy: "价和仓同向，燃料还没烧到极端",
              }
            ),
            tpl(
              "structure.funding",
              "价涨 OI 降",
              "价涨 OI 降：{品种}这波是空头平出来的，还是多头在撤？",
              {
                id: "price_up_oi_down",
                category: "常见",
                analogy: "价在涨，账本在减——先问是谁在离场",
              }
            ),
            tpl(
              "structure.funding",
              "费率转正 OI 不跟",
              "费率转正但 OI 没跟上：情绪到了，仓位没有。",
              {
                id: "funding_up_oi_flat",
                category: "常见",
                analogy: "喇叭响了，人还没进场",
              }
            ),
            tpl(
              "structure.funding",
              "横盘换手",
              "横盘 {N} 根，费率在零轴附近晃：{品种}在换手，不是在选边。",
              {
                id: "range_handoff",
                category: "常见",
                analogy: "球场里换队员，比分还没动",
              }
            ),
            tpl(
              "structure.funding",
              "现货买、费率掉",
              "ETF / 现货在买，费率却在掉：现货和合约又打架了。",
              {
                id: "spot_buy_funding_fade",
                category: "常见",
                analogy: "现货柜台在进货，永续柜台在散场",
              }
            ),
            tpl(
              "structure.funding",
              "OI 微增价格横",
              "{品种}OI 微增、价格横着：仓位在搬，方向还没投票。",
              {
                id: "oi_up_price_flat",
                category: "常见",
                analogy: "人在换座，比赛还没开球",
              }
            ),
            tpl(
              "structure.funding",
              "费率回落价格不崩",
              "费率从极端往回走、价格没崩：拥挤在缓解，不是趋势结束。",
              {
                id: "funding_ease_hold",
                category: "常见",
                stance: "bull",
                analogy: "压力表回落，管道还没裂",
              }
            ),
            tpl(
              "structure.funding",
              "结算前后剧本",
              "同一天：资金费结算前缩量、结算后放量——{品种}的常规剧本（写成「通常怎样」，方便以后套数据）。",
              {
                id: "funding_settle_rhythm",
                category: "大概率",
                analogy: "像潮汐：结算前后流动性常换一档",
              }
            ),
            tpl(
              "structure.funding",
              "极端后常见回归",
              "费率极端之后，{24h/8h}内更常见的是回归，而不是继续加速（模板语气，事后用数据填）。",
              {
                id: "extreme_mean_revert",
                category: "大概率",
                analogy: "橡皮筋拉满，继续拉不如先弹回",
              }
            ),
            tpl(
              "structure.funding",
              "高位突破假的多",
              "OI 堆在高位时，{品种}的突破假的往往比真的多。",
              {
                id: "high_oi_fake_break",
                category: "大概率",
                stance: "bear",
                analogy: "人挤在门口，冲出去的多半是误触",
              }
            ),
            tpl(
              "structure.funding",
              "价 OI 齐升未极端",
              "价和 OI 一起创新高、费率还没极端：趋势延续的概率大于反转。",
              {
                id: "trend_continue",
                category: "大概率",
                stance: "bull",
                analogy: "车还在加油，油箱没到红线",
              }
            ),
            tpl(
              "structure.funding",
              "价新高 OI 不新高",
              "价新高、OI 不新高：冲高回落的概率大于趋势第二段。",
              {
                id: "price_high_oi_not",
                category: "大概率",
                stance: "bear",
                analogy: "价创纪录，跟班的人少了——后劲要怀疑",
              }
            ),
            tpl(
              "structure.funding",
              "清算后新区间",
              "清算完一轮之后，费率归零 + OI 下台阶，更像新区间，而不是立刻反转。",
              {
                id: "post_liq_range",
                category: "大概率",
                analogy: "地震后先稳地基，再谈往哪建",
              }
            ),
            tpl(
              "structure.funding",
              "拥挤与波动反向",
              "拥挤方向与短线波动方向相反时，下一根更常打拥挤的反面。",
              {
                id: "crowd_vs_move",
                category: "大概率",
                analogy: "多数人站一边，短针常先扎向人多的一侧",
              }
            ),
            tpl(
              "structure.funding",
              "短看拥挤、日看现货",
              "{1–8h}看拥挤，{日线}看现货：两者同向才谈趋势，单向只谈波动。",
              {
                id: "horizon_split",
                category: "大概率",
                analogy: "显微镜和地图不能混用——先对齐时间尺度",
              }
            ),
            tpl(
              "structure.funding",
              "费率领先节奏",
              "费率领先价格 1 拍是常态；费率领先 3 拍还不兑现，多半是噪声。",
              {
                id: "funding_lead_lag",
                category: "大概率",
                analogy: "预告片比正片快，连放三遍还没上映就是假预告",
              }
            ),
            tpl(
              "structure.funding",
              "逼空结构",
              "空头费率拥挤 + 现货托底：{品种}更像逼空结构，不是慢熊。",
              {
                id: "bull_squeeze",
                category: "看涨",
                stance: "bull",
                analogy: "空在付钱，现货在接——像被往上涨价里挤",
              }
            ),
            tpl(
              "structure.funding",
              "回踩洗多头",
              "回踩时 OI 下降、费率降温：多头在清洗，不是在崩。",
              {
                id: "bull_pullback_wash",
                category: "看涨",
                stance: "bull",
                analogy: "跑步中途喝水，不是退赛",
              }
            ),
            tpl(
              "structure.funding",
              "健康加仓",
              "价和 OI 一起抬、费率温和：{品种}健康加仓，回调更像买点观察。",
              {
                id: "bull_healthy_add",
                category: "看涨",
                stance: "bull",
                analogy: "量价齐升且费不烫，像有序排队上车",
              }
            ),
            tpl(
              "structure.funding",
              "扫完多头费率收窄",
              "清算扫完低位多头，OI 下来、费率从极负收窄：空头优势在减。",
              {
                id: "bull_post_sweep",
                category: "看涨",
                stance: "bull",
                analogy: "扫完一地多单，空军的弹药也在减",
              }
            ),
            tpl(
              "structure.funding",
              "现货领、合约补",
              "现货 / ETF 持续流入，合约费率还没跟上：现货在领，合约会补。",
              {
                id: "bull_spot_leads",
                category: "看涨",
                stance: "bull",
                analogy: "现货先走，永续常晚一步跟上",
              }
            ),
            tpl(
              "structure.funding",
              "更高低点等 OI",
              "{品种}更高低点已经出现，缺的只是 OI 不再创新低。",
              {
                id: "bull_higher_low",
                category: "看涨",
                stance: "bull",
                analogy: "地基抬高了，就等仓位确认不再下沉",
              }
            ),
            tpl(
              "structure.funding",
              "坏情况失效",
              "坏情况的失效条件出现了：费率从极值回落且价格守住拥挤区上沿。",
              {
                id: "bull_bad_invalidate",
                category: "看涨",
                stance: "bull",
                analogy: "拥挤警报解除，价格还站在门槛上——空要小心",
              }
            ),
            tpl(
              "structure.funding",
              "现货更响",
              "空头用费率说话、多头用现货说话——现在现货更响。",
              {
                id: "bull_spot_louder",
                category: "看涨",
                stance: "bull",
                analogy: "两个麦克风，现货那路音量更大",
              }
            ),
            tpl(
              "structure.funding",
              "多头拥挤走平",
              "多头费率拥挤 + 价格走平：{品种}先等一次 OI 洗盘。",
              {
                id: "bear_crowd_flat",
                category: "看跌",
                stance: "bear",
                analogy: "人堆在多头这边，价却不走——先等卸货",
              }
            ),
            tpl(
              "structure.funding",
              "价新高 OI 顶加速",
              "价新高全靠费率堆起来，OI 在顶部加速：更像派发，不是突破。",
              {
                id: "bear_distribution",
                category: "看跌",
                stance: "bear",
                analogy: "价在创新高，仓在顶上加——像边拉边卖",
              }
            ),
            tpl(
              "structure.funding",
              "ETF 流出叠费率极正",
              "ETF 大额流出叠上费率极正：拥挤变成趋势的那一页。",
              {
                id: "bear_etf_out_crowd",
                category: "看跌",
                stance: "bear",
                analogy: "账本在撤，杠杆还在追——质量最差的一页",
              }
            ),
            tpl(
              "structure.funding",
              "涨 OI 不跟、跌 OI 反加",
              "上涨时 OI 不跟、下跌时 OI 反加：{品种}空头在用真仓位投票。",
              {
                id: "bear_oi_vote_down",
                category: "看跌",
                stance: "bear",
                analogy: "涨时没人加仓，跌时仓反而加——票投给了空",
              }
            ),
            tpl(
              "structure.funding",
              "丢拥挤区下沿",
              "拥挤区下沿丢了，费率和 OI 还没降：下跌才刚开始计费。",
              {
                id: "bear_crowd_break",
                category: "看跌",
                stance: "bear",
                analogy: "支撑带破了，杠杆还没卸——后面常更贵",
              }
            ),
            tpl(
              "structure.funding",
              "多头爆发透支",
              "{品种}多头爆发但量能 / 费率已经透支，下一拍更像发还是继续？",
              {
                id: "bear_long_exhaust",
                category: "看跌",
                stance: "bear",
                analogy: "油门踩到底还上坡，接下来要么冲顶要么熄火",
              }
            ),
            tpl(
              "structure.funding",
              "好情况失效",
              "好情况的失效：费率继续新高或 OI 创高但价格回吐。",
              {
                id: "bear_good_invalidate",
                category: "看跌",
                stance: "bear",
                analogy: "健康叙事还在，但仓位和价格开始打架",
              }
            ),
            tpl(
              "structure.funding",
              "合约加多现货减",
              "合约在加多、现货在减持：这不是共识，是分层。",
              {
                id: "bear_perp_spot_split",
                category: "看跌",
                stance: "bear",
                analogy: "永续在赌，现货在跑——别写成一条心",
              }
            ),
          ],
        }),
        topic({
          id: "structure.etf_flow",
          categoryId: "structure",
          name: "现货 ETF 流入",
          importance: 5,
          meaning:
            "美国现货 ETF 净流入是机构真金白银。价格涨而 ETF 流出，是杠杆或海外盘；价格横、ETF 进，是吸筹。",
          impactSummary:
            "ETF 连流入才能把反弹升级成趋势；与资金费、DXY 交叉验证机构是否在买跌。",
          relatedThemes: [
            "structure.funding",
            "macro.dxy",
            "macro.fomc",
            "people.treasury",
            "structure.btcd",
          ],
          talkingPoints: [
            "价格新高要 ETF 确认，否则是空头回补",
            "单日流入不如 5 日净额",
            "IBIT 进、其他出，是搬家不是新需求",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("BTC", "连流入才能把反弹升级成趋势", "1–3 个交易日"),
            impactOn("资金费 / OI", "ETF 进、费率却极正 = 现货和杠杆抢筹", "同步"),
            impactOn("DXY / 实际利率", "宏观利空但 ETF 吸，说明机构在买跌", "数据后 24h"),
            impactOn("ETH ETF", "BTC 进、ETH 出 = 风险偏好只到一层", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "3 日以上净流入，且价格站上关键位",
              then: "机构在认方向，回调优先看成加仓",
              coins: ["BTC", "ETH"],
              stance: "bull",
              template:
                "不是盘面自己弹，是 ETF 在买。连进比单日数字重要。BTC 短线偏多，失效看连续两日转流出。",
              invalidation: "次日转大流出，或 DXY 大涨",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "价格涨、ETF 连续流出",
              then: "反弹质量差，多半是空头回补或衍生品",
              coins: ["BTC"],
              stance: "bear",
              template:
                "币在涨，账本在卖。这是修复不是新趋势。先等流入回头，再谈突破。",
              invalidation: "IBIT 重新单日大额净申购",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "先大流出再小流入，或只 IBIT 进、板块整体仍净出",
              then: "止血不等于新周期",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "流出之后的一天回流，只够说明砸盘结束，不够说明机构回头。看 5 日净额转正再加重仓表述。",
              invalidation: "5 日净额转正且价格不破前低",
            }),
          ],
          templates: [
            tpl(
              "structure.etf_flow",
              "连出但价在新高",
              "极端{品种}ETF {N} 日连出，价格还在新高：这是杠杆在抬，不是机构在买。",
              {
                id: "ext_out_new_high",
                category: "极端",
                stance: "bear",
                analogy: "账本在卖，价还在涨——杠杆在抬轿，不是机构在买",
              }
            ),
            tpl(
              "structure.etf_flow",
              "单日极值先当事件",
              "单日流入/流出打到极值，{品种}先当事件，不升级成趋势。",
              {
                id: "single_day_extreme",
                category: "极端",
                analogy: "单日数字像烟花，亮一下不等于换季节",
              }
            ),
            tpl(
              "structure.etf_flow",
              "IBIT 进其余出",
              "IBIT 在进、其余在出：表面上的「ETF 买入」可能只是内部搬家。",
              {
                id: "ibit_rotation",
                category: "极端",
                analogy: "钱从一个口袋换到另一个口袋，总量没变",
              }
            ),
            tpl(
              "structure.etf_flow",
              "价崩 ETF 大买",
              "{品种}价格崩、ETF 却在大额买：现货在接飞刀，还是在抄结构？",
              {
                id: "crash_etf_buy",
                category: "极端",
                stance: "mixed",
                analogy: "跌刀子下有人在接——先分清是救场还是抄底",
              }
            ),
            tpl(
              "structure.etf_flow",
              "DXY 涨叠 ETF 大出",
              "DXY 大涨叠 ETF 大出：宏观和现货同时抽水，反弹先当反抽。",
              {
                id: "dxy_out_double",
                category: "极端",
                stance: "bear",
                analogy: "美元在吸、ETF 在撤——两头抽水，反弹先减配",
              }
            ),
            tpl(
              "structure.etf_flow",
              "连入后首日翻出",
              "连续大入之后第一天翻出：趋势没死，但「机构只会买」这句先作废。",
              {
                id: "inflow_then_out",
                category: "极端",
                stance: "mixed",
                analogy: "连买几天后第一天卖——故事还在，口号先收一收",
              }
            ),
            tpl(
              "structure.etf_flow",
              "浅流入价横",
              "浅流入、价格横着：{品种}更像在吸，不是要立刻拉。",
              {
                id: "shallow_in_flat",
                category: "常见",
                stance: "bull",
                analogy: "细水长流地接，不是马上要冲",
              }
            ),
            tpl(
              "structure.etf_flow",
              "价涨 ETF 小出",
              "价涨、ETF 小出：涨的是合约和海外盘，现货没确认。",
              {
                id: "price_up_small_out",
                category: "常见",
                stance: "bear",
                analogy: "价在涨，账本在小卖——杠杆或海外在领",
              }
            ),
            tpl(
              "structure.etf_flow",
              "一天进一天出",
              "一天进、一天出：{品种}ETF 还在噪声区间，别写成机构转向。",
              {
                id: "in_out_noise",
                category: "常见",
                analogy: "进出进出像调音量，不是换台",
              }
            ),
            tpl(
              "structure.etf_flow",
              "单基金在进",
              "只有一条基金在进：总量没改，叙事先不要写「华尔街进场」。",
              {
                id: "one_fund_in",
                category: "常见",
                analogy: "一个选手得分，全队总分没变",
              }
            ),
            tpl(
              "structure.etf_flow",
              "流入费率同向",
              "流入和费率同向：现货加杠杆一起堆，短线更拥挤。",
              {
                id: "inflow_funding_same",
                category: "常见",
                stance: "mixed",
                analogy: "现货和合约一起加——人多了，通道更挤",
              }
            ),
            tpl(
              "structure.etf_flow",
              "流入费率在掉",
              "流入在、费率在掉：现货买、合约降杠杆，结构比单边费率好看。",
              {
                id: "inflow_funding_fade",
                category: "常见",
                stance: "bull",
                analogy: "现货在进货，合约在卸货——分层里现货更干净",
              }
            ),
            tpl(
              "structure.etf_flow",
              "流出后首日小回流",
              "流出后的第一天小回流：只够说明抛盘歇了，不够说明趋势回来。",
              {
                id: "out_then_small_in",
                category: "常见",
                stance: "mixed",
                analogy: "雨停不等于天晴——先看 5 日净额",
              }
            ),
            tpl(
              "structure.etf_flow",
              "ETF 与价同步走平",
              "{品种}ETF 与价格同步走平：机构也在等，不是悄悄进场。",
              {
                id: "etf_price_flat",
                category: "常见",
                analogy: "双方都在等信号，不是暗度陈仓",
              }
            ),
            tpl(
              "structure.etf_flow",
              "单日难升级趋势",
              "单日流入很少单独把反弹升级成趋势，通常要看 {3–5} 日净额。",
              {
                id: "single_day_not_trend",
                category: "大概率",
                analogy: "一天的数据像抽样，趋势要看连续样本",
              }
            ),
            tpl(
              "structure.etf_flow",
              "价涨 ETF 连出",
              "价涨而 ETF 连续流出，冲高回落的概率大于趋势第二段。",
              {
                id: "price_up_outflow",
                category: "大概率",
                stance: "bear",
                analogy: "价在创新高，账本在撤退——第二段要怀疑",
              }
            ),
            tpl(
              "structure.etf_flow",
              "横盘连流入",
              "横盘 + 连续流入，往后更像铺垫，而不是当天就要突破。",
              {
                id: "flat_continuous_in",
                category: "大概率",
                stance: "bull",
                analogy: "在铺轨，不是马上要发车",
              }
            ),
            tpl(
              "structure.etf_flow",
              "大出后立刻大入",
              "大出之后立刻大入，更常见的是回补，不是 V 反确认。",
              {
                id: "out_then_big_in",
                category: "大概率",
                stance: "mixed",
                analogy: "大卖后大买，多半是补仓位不是反转证",
              }
            ),
            tpl(
              "structure.etf_flow",
              "DXY 与 ETF 对着干",
              "DXY 与 ETF 对着干时，短线听美元，中线才把流入当票。",
              {
                id: "dxy_etf_fight",
                category: "大概率",
                analogy: "短线美元话筒更大，中线才数 ETF 的票",
              }
            ),
            tpl(
              "structure.etf_flow",
              "5 日净出价不新低",
              "5 日净流出且价格不创新低：下跌在减速，还不等于见底。",
              {
                id: "five_day_out_no_low",
                category: "大概率",
                stance: "mixed",
                analogy: "刹车踩了，还没说掉头",
              }
            ),
            tpl(
              "structure.etf_flow",
              "流入领先节奏",
              "流入领先价格 1 拍常见；领先很久价格不动，多半被杠杆对冲掉了。",
              {
                id: "inflow_lead_lag",
                category: "大概率",
                analogy: "ETF 先走、价不动——可能有人在另一边对冲",
              }
            ),
            tpl(
              "structure.etf_flow",
              "连入价守住才改口",
              "只有「连续流入 + 价格守住」同时成立，才把反弹改口成趋势。",
              {
                id: "inflow_hold_trend",
                category: "大概率",
                stance: "bull",
                analogy: "两票都投完才改口——缺一张仍是反弹",
              }
            ),
            tpl(
              "structure.etf_flow",
              "连入回踩费率温和",
              "{N} 日净流入、回踩不破、费率不烫：{品种}现货在领，回调当观察。",
              {
                id: "bull_continuous_in",
                category: "看涨",
                stance: "bull",
                analogy: "现货连买、杠杆不烫——回调像上车机会",
              }
            ),
            tpl(
              "structure.etf_flow",
              "价未新高 ETF 先连进",
              "价格还没新高，ETF 已经先连续进：更像在铺，不像在追。",
              {
                id: "bull_in_before_high",
                category: "看涨",
                stance: "bull",
                analogy: "机构先铺货，价还没追——像提前布阵",
              }
            ),
            tpl(
              "structure.etf_flow",
              "大出后流出缩",
              "大出之后流出缩、价格不创新低：抛盘在尽，先看止跌不是看空到底。",
              {
                id: "bull_outflow_shrink",
                category: "看涨",
                stance: "bull",
                analogy: "卖压在减、底没破——先谈止跌",
              }
            ),
            tpl(
              "structure.etf_flow",
              "ETF 进 OI 不炸",
              "ETF 进、OI 不炸、结构出更高低点：机构买的是现货，不是拥挤。",
              {
                id: "bull_spot_not_crowd",
                category: "看涨",
                stance: "bull",
                analogy: "现货在买、杠杆没堆——买的是货不是赌",
              }
            ),
            tpl(
              "structure.etf_flow",
              "DXY 弱叠 ETF 回流",
              "DXY 转弱叠上 ETF 回流：宏观松一点，现货又有人接。",
              {
                id: "bull_dxy_weak_in",
                category: "看涨",
                stance: "bull",
                analogy: "美元松手、ETF 接棒——宏观给现货让路",
              }
            ),
            tpl(
              "structure.etf_flow",
              "浅入变连入",
              "浅流入变成连续流入：叙事可以从「吸筹」改成「加仓」。",
              {
                id: "bull_shallow_to_continuous",
                category: "看涨",
                stance: "bull",
                analogy: "从滴水到连下——故事可以从吸改成加",
              }
            ),
            tpl(
              "structure.etf_flow",
              "坏情况失效",
              "坏情况失效：流出日结束后价格守住，次日没有再创新低。",
              {
                id: "bull_bad_invalidate",
                category: "看涨",
                stance: "bull",
                analogy: "卖压日过后价还站住——空要小心",
              }
            ),
            tpl(
              "structure.etf_flow",
              "合约降杠杆 ETF 进",
              "合约在降杠杆，ETF 还在进：分层里现货这一侧更响。",
              {
                id: "bull_perp_out_etf_in",
                category: "看涨",
                stance: "bull",
                analogy: "永续在撤、ETF 在进——听现货那路",
              }
            ),
            tpl(
              "structure.etf_flow",
              "价新高 ETF 连出",
              "价新高、ETF 连出：{品种}这波更像杠杆行情，现货没跟。",
              {
                id: "bear_high_outflow",
                category: "看跌",
                stance: "bear",
                analogy: "价创纪录、账本在卖——杠杆在演，现货缺席",
              }
            ),
            tpl(
              "structure.etf_flow",
              "连入翻出丢平台",
              "连续流入突然翻出，且价格丢掉平台：机构这页翻成减持。",
              {
                id: "bear_in_then_out_platform",
                category: "看跌",
                stance: "bear",
                analogy: "买几天后翻页卖出——平台也丢了",
              }
            ),
            tpl(
              "structure.etf_flow",
              "ETF 出费率极正",
              "ETF 出、费率还极正：现货走、杠杆还在加多——拥挤变趋势的那一拍。",
              {
                id: "bear_out_crowded_long",
                category: "看跌",
                stance: "bear",
                analogy: "现货在撤、合约还在堆多——最差的一拍",
              }
            ),
            tpl(
              "structure.etf_flow",
              "只有回流无连入",
              "只有回流、没有连续净流入：反弹模板，不当反转模板。",
              {
                id: "bear_rebound_not_reversal",
                category: "看跌",
                stance: "bear",
                analogy: "止血不等于反转——别写 V 反",
              }
            ),
            tpl(
              "structure.etf_flow",
              "DXY 强叠 ETF 净出",
              "DXY 转强 + ETF 转为净流出：两头抽，反弹先减配。",
              {
                id: "bear_dxy_strong_out",
                category: "看跌",
                stance: "bear",
                analogy: "美元吸、ETF 撤——反弹先当减配",
              }
            ),
            tpl(
              "structure.etf_flow",
              "IBIT 都在出",
              "IBIT 都在出，不只是小号基金在出：这不是结构内再平衡。",
              {
                id: "bear_ibit_all_out",
                category: "看跌",
                stance: "bear",
                analogy: "龙头也在卖——不是小基金搬家",
              }
            ),
            tpl(
              "structure.etf_flow",
              "好情况失效",
              "好情况失效：流入在、价格却连续回吐平台低点。",
              {
                id: "bear_good_invalidate",
                category: "看跌",
                stance: "bear",
                analogy: "还在买但价在破——好叙事在失效",
              }
            ),
            tpl(
              "structure.etf_flow",
              "小进仍 5 日净出",
              "流出日之后一天小进，总量仍是 5 日净出：还在分发，不是抄底结束。",
              {
                id: "bear_small_in_still_out",
                category: "看跌",
                stance: "bear",
                analogy: "一天小买、五天仍卖——分发还没完",
              }
            ),
          ],
        }),
        topic({
          id: "structure.exchange_flow",
          categoryId: "structure",
          name: "交易所净流入",
          importance: 4,
          meaning:
            "币进交易所常是潜在卖压，出交易所常是冷储存。要扣掉跨所搬砖和做市，看大额净流 + 价格反应。",
          impactSummary:
            "BTC 净进所抬高砸盘概率；与稳定币进所、ETF 流入交叉验证真实买卖意图。",
          relatedThemes: [
            "structure.etf_flow",
            "onchain.whale",
            "onchain.stable_supply",
            "ta.liquidation",
            "structure.liquidity",
          ],
          talkingPoints: [
            "大额进所 + 价格不跌 = 有人接飞刀，或只是搬砖",
            "出所不能自动等于看涨，可能是去链上挖或去质押",
            "稳定币进所和 BTC 进所含义相反",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("现货抛压", "BTC 净进所抬高砸盘概率", "4–24h"),
            impactOn("稳定币", "USDT/USDC 进所偏买盘预备", "同步"),
            impactOn("现货 ETF 流入", "ETF 流入但 CEX 也在进币，要对冲两边", "1 日"),
            impactOn("爆仓 / 清算 cascade", "进所叠加高 OI，下跌更易连锁", "即时"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "BTC 持续净流出，稳定币净流入交易所",
              then: "现货卖压下降、弹药在所内",
              coins: ["BTC"],
              stance: "bull",
              template:
                "币在出所，稳定币在进所。这是更干净的偏多结构。失效看大额 BTC 重新净流入头所。",
              invalidation: "前三大所 BTC 余额 24h 明显回升",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "BTC 大额净流入，稳定币反而流出",
              then: "卖压抬、买盘弹药在撤",
              coins: ["BTC"],
              stance: "bear",
              template:
                "现货在上架，稳定币在离场。别把反弹当趋势。先看有没有大针去扫流动性。",
              invalidation: "流入后价格不跌、ETF 同时大进",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "总余额变，但只发生在单一所，或和跨链桥对冲",
              then: "可能是做市/搬仓，不解释方向",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "先问是不是搬砖。单所脉冲不要写成巨鲸出货。要对总余额和稳定币方向。",
              invalidation: "多所同时同向净流",
            }),
          ],
          templates: [
            tpl(
              "structure.exchange_flow",
              "出所不等于看涨",
              "出所不能自动等于看涨，可能是去质押或搬砖。要对总余额、稳定币方向和价格反应。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "structure.btcd",
          categoryId: "structure",
          name: "BTC.D / 主导率",
          importance: 5,
          meaning:
            "BTC.D 决定钱在比特币还是山寨。涨主导率时不要写山寨季；跌主导率且 BTC 也涨，才是风险扩散。",
          impactSummary:
            "D 升先砸小票、D 降且 BTC 稳才是山寨扩散；ETF 单边进会抬主导率。",
          relatedThemes: [
            "narrative.altseason",
            "structure.etf_flow",
            "structure.funding",
            "narrative.l1",
            "narrative.meme",
          ],
          talkingPoints: [
            "BTC 横、主导率升 = 山寨在流血",
            "主导率降、BTC 也跌 = 一起杀风险，不是山寨季",
            "真山寨季：BTC 稳或新高 + BTC.D 下降 + ETH.D 或板块先动",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("山寨", "D 升先砸小票", "数日"),
            impactOn("ETH", "ETH.D 不跟降，山寨轮动是假的", "同步"),
            impactOn("现货 ETF 流入", "BTC ETF 单边进会抬 D", "1–3 日"),
            impactOn("内容选题", "D 升写 BTC/宏观，D 降写板块", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（山寨扩散）",
              if: "BTC 持稳或创新高，BTC.D 回落，ETH 或主板块先于 meme 启动",
              then: "风险偏好外溢",
              coins: ["ETH", "SOL"],
              stance: "bull",
              template:
                "不是 BTC 弱，是主导率在让位。先看 ETH 和有收入的板块，不要从狗狗开始写山寨季。",
              invalidation: "BTC 破位或 D 重新走强",
            }),
            scenario("bad", {
              name: "坏情况（避险回 BTC）",
              if: "BTC.D 升、山寨全跌，或宏观利空周",
              then: "现金和 BTC 优先，山寨是出货口",
              coins: ["BTC"],
              stance: "bear",
              template:
                "主导率在说话：市场只要 BTC。这种时候写山寨季是逆结构。先等 D 走平。",
              invalidation: "BTC 新高同时 D 连续 3–5 日下降",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "D 降但 BTC 也跌",
              then: "只是一起去杠杆",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "主导率下降不是山寨季节，是总盘子在缩。先看稳定币市值和 ETF，再谈轮动。",
              invalidation: "总市值止跌且 ETH.D 转强",
            }),
          ],
          templates: [
            tpl(
              "structure.btcd",
              "主导率升不是山寨季",
              "BTC 横、主导率升 = 山寨在流血。D 升时不要写山寨季，先写 BTC 和宏观。",
              { stance: "bear", coins: ["BTC"] }
            ),
          ],
        }),
        topic({
          id: "structure.options",
          categoryId: "structure",
          name: "期权到期 / Max Pain",
          importance: 4,
          meaning:
            "大额到期周，现货常被吸向 max pain（期权卖方最舒服的价格）。到期后墙撤掉，趋势才恢复。IV 和 skew 看贵的是保护还是投机。",
          impactSummary:
            "到期日现货向 max pain 震荡；到期后 IV 回落趋势更好做，叠宏观周要分时段。",
          relatedThemes: [
            "structure.funding",
            "structure.etf_flow",
            "calendar.conference",
            "macro.fomc",
            "ta.structure",
          ],
          talkingPoints: [
            "到期日看墙，到期后看方向",
            "max pain 是引力不是预言",
            "put skew 极高 = 有人在买下跌保险，未必立刻跌",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("BTC", "靠近最大 OI 执行价震荡", "到期当日"),
            impactOn("波动率", "到期后 IV 常回落，趋势更好做", "到期后 24–48h"),
            impactOn("资金费 / OI", "到期周费率失真，少用极端费率做主结论", "同步"),
            impactOn("会议周 / 宏观周", "纳指平仓带动 BTC", "当日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（到期后趋势解放）",
              if: "到期后 IV 下降、现货站上最大 call 墙、ETF 仍流入",
              then: "压制解除，可按原趋势做",
              coins: ["BTC"],
              stance: "bull",
              template:
                "墙过了。剩下的是 ETF 和宏观，不是 max pain。突破执行价后，把到期周的震荡当成蓄势。",
              invalidation: "到期后直接跌回墙下且 OI 不降",
            }),
            scenario("bad", {
              name: "坏情况（墙下消耗）",
              if: "价格卡在大额 call/put 之间，资金费和高 OI 同时存在",
              then: "到期前两天少追突破",
              coins: ["BTC"],
              stance: "bear",
              template:
                "这不是变盘，是到期周。先标 max pain 和两侧墙，突破不作数，收盘站稳再认。",
              invalidation: "日线收盘离开墙区且成交量放大",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "max pain 与 ETF/宏观信号相反",
              then: "当天听墙，隔日听宏观",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "到期日和加息日叠在一起时，先承认两种力。日内不赌方向，夜盘看哪边的钱留下。",
              invalidation: "IV 崩塌后价格仍单边走",
            }),
          ],
          templates: [
            tpl(
              "structure.options",
              "到期量占持仓极高",
              "极端{品种}本周到期量占持仓 {x%}，短线先交易墙，不交易叙事。",
              {
                id: "ext_expiry_oi_pct",
                category: "极端",
                analogy: "墙太厚，先数砖块，别先讲故事",
              }
            ),
            tpl(
              "structure.options",
              "痛点偏离过大",
              "Max Pain 和现价偏离过大：要么先被吸过去，要么到期后墙失效、波动补回来。",
              {
                id: "ext_pain_far",
                category: "极端",
                stance: "mixed",
                analogy: "磁铁离太远——要么被吸过去，要么到期后弹回来",
              }
            ),
            tpl(
              "structure.options",
              "持仓一边倒",
              "{品种}看涨/看跌持仓一边倒，到期更像单边清算，不像温和钉死。",
              {
                id: "ext_one_sided",
                category: "极端",
                stance: "mixed",
                analogy: "一边倒的牌局，到期更像清台不是钉牌",
              }
            ),
            tpl(
              "structure.options",
              "墙叠费率 ETF",
              "期权墙、费率极值、ETF 大出叠在同一天：拥挤和墙一起到期。",
              {
                id: "ext_wall_funding_etf",
                category: "极端",
                stance: "bear",
                analogy: "三股力同一天到期——先防挤，再谈墙",
              }
            ),
            tpl(
              "structure.options",
              "到期碰宏观日",
              "周度到期碰上宏观日（CPI / FOMC）：先分清是数据在动，还是墙在吸。",
              {
                id: "ext_expiry_macro",
                category: "极端",
                analogy: "同一天两个话筒——先听数据，墙当过滤器",
              }
            ),
            tpl(
              "structure.options",
              "到期日波动极窄",
              "到期日当天波动收窄到极致：钉牌成功，次日更容易把压缩的波动还出来。",
              {
                id: "ext_pin_success",
                category: "极端",
                stance: "mixed",
                analogy: "弹簧压到最紧——松手后波动常还回来",
              }
            ),
            tpl(
              "structure.options",
              "痛点上方 Call 墙",
              "{品种}最大痛点上方全是 Call 墙：向上假突破的成本比向下扫 Put 更高。",
              {
                id: "ext_call_wall_above",
                category: "极端",
                stance: "bear",
                analogy: "头顶全是卖单墙——往上假突破更贵",
              }
            ),
            tpl(
              "structure.options",
              "临近到期往痛点靠",
              "临近周五 / 月末，{品种}往 Max Pain 靠：这是钉牌，不是趋势转弯。",
              {
                id: "common_drift_to_pain",
                category: "常见",
                analogy: "到期前价格往痛点滑——像被磁铁吸，不是换方向",
              }
            ),
            tpl(
              "structure.options",
              "到期前波动缩小",
              "到期前 24–48h 波动变小、OI 不再加：庄家在对冲，不是没人看。",
              {
                id: "common_pre_expiry_quiet",
                category: "常见",
                analogy: "市场在调仓对冲，不是没人玩",
              }
            ),
            tpl(
              "structure.options",
              "到期后还波动",
              "到期日过了，墙拆掉，波动重新变大：这是常规「到期后还波动」。",
              {
                id: "common_post_expiry_vol",
                category: "常见",
                stance: "mixed",
                analogy: "墙拆了，被压住的波动常还回来",
              }
            ),
            tpl(
              "structure.options",
              "痛点跟着价格挪",
              "Max Pain 每天跟着价格挪：痛点是结果不是锚，别把移动的点当支撑。",
              {
                id: "common_pain_moves",
                category: "常见",
                analogy: "痛点跟着走——是结果不是预言",
              }
            ),
            tpl(
              "structure.options",
              "近月大远月空",
              "只有近月大、远月空：影响的是本周，改不了月线结构。",
              {
                id: "common_near_month_only",
                category: "常见",
                analogy: "本周的墙，改不了月线的图",
              }
            ),
            tpl(
              "structure.options",
              "Put/Call 升价不跌",
              "Put/Call 比升高但价格不跌：对冲盘在买保护，不等于现货要砸。",
              {
                id: "common_pc_ratio_up",
                category: "常见",
                stance: "mixed",
                analogy: "保险买多了，不等于马上出事故",
              }
            ),
            tpl(
              "structure.options",
              "到期日量大价不动",
              "到期当天成交很大、价格走不动：墙内换手，先当区间。",
              {
                id: "common_high_vol_flat",
                category: "常见",
                analogy: "成交热闹、价不走——墙里换手",
              }
            ),
            tpl(
              "structure.options",
              "周度到期量一般",
              "{品种}周度到期量一般，日度 Max Pain 参考价值有限。",
              {
                id: "common_weekly_light",
                category: "常见",
                analogy: "墙不够厚，日度痛点别太当真",
              }
            ),
            tpl(
              "structure.options",
              "周度钉一下",
              "周度到期更常看到「收盘附近钉一下」，月度到期才值得写成事件。",
              {
                id: "likely_weekly_pin",
                category: "大概率",
                analogy: "周度是小钉，月度才是大事件",
              }
            ),
            tpl(
              "structure.options",
              "痛点附近假突破多",
              "现价在 Max Pain 附近震荡，突破假的往往比真的多。",
              {
                id: "likely_fake_break",
                category: "大概率",
                stance: "mixed",
                analogy: "在痛点附近，假突破比真突破常见",
              }
            ),
            tpl(
              "structure.options",
              "上探墙再回来",
              "墙在上方、费率不极端：先上探墙再回来，比直接穿过更常见。",
              {
                id: "likely_probe_wall",
                category: "大概率",
                analogy: "先碰墙再弹回，比一口气穿过去更常见",
              }
            ),
            tpl(
              "structure.options",
              "到期后走被压一侧",
              "到期后 1–2 根，方向常跟到期前被压制的那一侧走。",
              {
                id: "likely_post_expiry_release",
                category: "大概率",
                stance: "mixed",
                analogy: "墙撤了，被压住的那边常先走",
              }
            ),
            tpl(
              "structure.options",
              "痛点连挪三日",
              "Max Pain 与现货连续 3 日同向挪动，才像趋势在改痛点；一天挪不算。",
              {
                id: "likely_pain_trend_3d",
                category: "大概率",
                stance: "bull",
                analogy: "痛点连挪三天才算趋势在改墙",
              }
            ),
            tpl(
              "structure.options",
              "数据日大于到期日",
              "数据日 > 到期日：同一天有非农/CPI，先写宏观，期权只当过滤器。",
              {
                id: "likely_macro_over_expiry",
                category: "大概率",
                analogy: "宏观数据日，期权墙是配角",
              }
            ),
            tpl(
              "structure.options",
              "Call 近 Put 远",
              "Call 墙近、Put 墙远：下跌空间叙事强，但更常见的是先磨墙再选择。",
              {
                id: "likely_call_near_put_far",
                category: "大概率",
                analogy: "头顶墙近、脚下墙远——先磨再选边",
              }
            ),
            tpl(
              "structure.options",
              "清算后新区间",
              "到期清算完、期权 OI 下台阶，现货更像进入新区间，不是立刻反转。",
              {
                id: "likely_post_oi_step",
                category: "大概率",
                analogy: "墙卸完进新区间，不是立刻掉头",
              }
            ),
            tpl(
              "structure.options",
              "Put 墙被扫费率转暖",
              "Put 墙在下方不远被扫过、费率转暖：空头保护失效，更像逼空结构。",
              {
                id: "bull_put_swept",
                category: "看涨",
                stance: "bull",
                analogy: "下方保护被扫、费率回暖——空在退",
              }
            ),
            tpl(
              "structure.options",
              "痛点上移价守住",
              "Max Pain 上移、现货守在痛点之上：墙在跟着多头走，不是在压。",
              {
                id: "bull_pain_up_hold",
                category: "看涨",
                stance: "bull",
                analogy: "墙跟着价上移——多头在抬天花板",
              }
            ),
            tpl(
              "structure.options",
              "Call 未破 OI 降",
              "到期后 Call 没被打穿、OI 下降：多头不用再付昂贵保护，波动可向上释放。",
              {
                id: "bull_call_hold_oi_down",
                category: "看涨",
                stance: "bull",
                analogy: "头顶墙没破、保护卸了——向上波动可释放",
              }
            ),
            tpl(
              "structure.options",
              "Put 作废结构不破",
              "大额 Put 到期作废，现货没破结构低点：空头弹药过期。",
              {
                id: "bull_put_expire",
                category: "看涨",
                stance: "bull",
                analogy: "下方保险过期、底还在——空弹药没了",
              }
            ),
            tpl(
              "structure.options",
              "墙下横 ETF 进",
              "墙在上、现货横在墙下但 ETF 在进：现货在垫，到期后更像上试。",
              {
                id: "bull_etf_under_wall",
                category: "看涨",
                stance: "bull",
                analogy: "现货在墙下接货——到期后更像上试",
              }
            ),
            tpl(
              "structure.options",
              "更高低点等到期过",
              "{品种}更高低点已出，缺的只是本周到期不再把价格钉回去。",
              {
                id: "bull_higher_low_expiry",
                category: "看涨",
                stance: "bull",
                analogy: "地基已抬，就等本周墙不再钉回去",
              }
            ),
            tpl(
              "structure.options",
              "坏情况失效",
              "坏情况失效：痛点上移且收盘站上原 Call 墙。",
              {
                id: "bull_bad_invalidate",
                category: "看涨",
                stance: "bull",
                analogy: "痛点上移且站上旧墙——空要小心",
              }
            ),
            tpl(
              "structure.options",
              "Call 墙在顶费率烫",
              "Call 墙就在头顶、费率已烫：到期更像盖帽，不像突破。",
              {
                id: "bear_call_wall_hot",
                category: "看跌",
                stance: "bear",
                analogy: "头顶墙 + 费率烫——到期像盖帽不是突破",
              }
            ),
            tpl(
              "structure.options",
              "痛点下移价跌破",
              "Max Pain 下移、现货跌破痛点：墙在跟着空头走。",
              {
                id: "bear_pain_down_break",
                category: "看跌",
                stance: "bear",
                analogy: "墙跟着价下移——空头在抬地板往下",
              }
            ),
            tpl(
              "structure.options",
              "Call 作废丢平台",
              "大额 Call 作废 + 现货丢掉平台：多头保护过期，下跌才开始计费。",
              {
                id: "bear_call_expire_platform",
                category: "看跌",
                stance: "bear",
                analogy: "头顶保护过期、平台丢了——跌才开始计费",
              }
            ),
            tpl(
              "structure.options",
              "拉墙外持仓减",
              "到期前硬拉到墙外、持仓却在减：更像诱多，等墙把价格吸回去。",
              {
                id: "bear_fake_break_out",
                category: "看跌",
                stance: "bear",
                analogy: "硬拉出墙、仓在减——像诱多，等吸回",
              }
            ),
            tpl(
              "structure.options",
              "Put/Call 价一起差",
              "Put/Call 比和价格一起变差：对冲盘在加空，不是普通钉牌。",
              {
                id: "bear_pc_price_worse",
                category: "看跌",
                stance: "bear",
                analogy: "保护盘在加空——不是普通到期钉牌",
              }
            ),
            tpl(
              "structure.options",
              "好情况失效",
              "好情况失效：收盘回到 Max Pain 下方，且次日墙没有上移。",
              {
                id: "bear_good_invalidate",
                category: "看跌",
                stance: "bear",
                analogy: "跌回痛点下、墙没上移——好叙事失效",
              }
            ),
            tpl(
              "structure.options",
              "月度到期叠拥挤",
              "{品种}月度到期叠多头拥挤：先打 OI，叙事后说。",
              {
                id: "bear_monthly_crowd",
                category: "看跌",
                stance: "bear",
                analogy: "大到期 + 多头挤——先卸杠杆再讲故事",
              }
            ),
            tpl(
              "structure.options",
              "墙拆后向下补波动",
              "墙拆掉后第一波是向下补波动，而不是接着原趋势。",
              {
                id: "bear_post_wall_down_vol",
                category: "看跌",
                stance: "bear",
                analogy: "墙拆后第一波常向下还波动，不是顺原趋势",
              }
            ),
          ],
        }),
        topic({
          id: "structure.liquidity",
          categoryId: "structure",
          name: "流动性 / 深度",
          importance: 3,
          meaning:
            "盘口深度、价差、冲击成本决定「同样的消息能砸多深」。周末、亚洲盘、极端行情里深度先消失，价格后动。",
          impactSummary:
            "薄流动性 + 高 OI 易一次扫穿；周末深度更差，BTC 深度先恢复、小币更易插针。",
          relatedThemes: [
            "ta.liquidation",
            "structure.exchange_flow",
            "structure.funding",
            "security.withdraw",
            "onchain.stable_supply",
          ],
          talkingPoints: [
            "深度变薄时，新闻的弹性被放大",
            "大针很多是流动性空洞，不是叙事反转",
            "上破但深度不回，假突破概率高",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("爆仓 / 清算 cascade", "薄流动性 + 高 OI = 一次扫穿", "即时"),
            impactOn("周末行情", "深度更差，消息别按工作日幅度写", "周五晚–周日"),
            impactOn("上币/活动", "刷量所深度是假的", "活动期"),
            impactOn("BTC vs 山寨", "BTC 深度先恢复，小币更易插针", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "回踩时买卖两侧深度回补，价差收窄",
              then: "有人在场内做市，支撑更可信",
              coins: ["BTC"],
              stance: "bull",
              template:
                "这一针没有带走深度。回补比 K 线更重要。当成流动性测试，不是趋势结束。",
              invalidation: "每波反弹深度都更薄",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "买盘梯子连续撤、价差拉宽、稳定币溢价/折价同时出现",
              then: "下一则不大的利空也能打出大针",
              coins: ["BTC"],
              stance: "bear",
              template:
                "盘口比新闻先说话。深度没了就不要解释成「健康回踩」。先减高 Beta。",
              invalidation: "1 小时内深度恢复到事件前",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "BTC 深度还在、山寨深度先没",
              then: "这是分层流动性，不是整个市场崩溃",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "钱还在 BTC 的盘口里，小币已经没人报价。写主导率，不要写牛熊切换。",
              invalidation: "BTC 自身深度也明显变薄",
            }),
          ],
          templates: [
            tpl(
              "structure.liquidity",
              "深度掉到近期低位",
              "极端{品种}盘口深度掉到近期低位，一根市价就能走出「趋势」。",
              {
                id: "ext_depth_low",
                category: "极端",
                stance: "mixed",
                analogy: "池子太浅，一块石头就能激起大浪",
              }
            ),
            tpl(
              "structure.liquidity",
              "一档价差拉宽",
              "{品种}买卖一档价差拉宽：现在交易的是冲击成本，不是方向。",
              {
                id: "ext_spread_wide",
                category: "极端",
                analogy: "买卖价差在喊贵——先算滑点，再谈多空",
              }
            ),
            tpl(
              "structure.liquidity",
              "下方空上方在",
              "向下深度空了、向上还在：跌起来像瀑布，涨起来像爬墙。",
              {
                id: "ext_asymmetric_depth",
                category: "极端",
                stance: "bear",
                analogy: "下面没垫、上面有墙——不对称的盘口",
              }
            ),
            tpl(
              "structure.liquidity",
              "清算墙近盘口薄",
              "清算墙近 + 盘口变薄：cascade 的燃料和导火索到齐了。",
              {
                id: "ext_liq_wall_thin",
                category: "极端",
                stance: "bear",
                analogy: "炸药和引线都到位——只差一根针",
              }
            ),
            tpl(
              "structure.liquidity",
              "稳定币深度一起掉",
              "{品种}稳定币余额掉、现货深度一起掉：能接盘的钱也在撤。",
              {
                id: "ext_stable_depth_out",
                category: "极端",
                stance: "bear",
                analogy: "弹药和挂单一起撤——接盘的人在走",
              }
            ),
            tpl(
              "structure.liquidity",
              "周末深度减半",
              "周末 / 假期深度只剩工作日的一半：波动放大先当流动性事件。",
              {
                id: "ext_weekend_thin",
                category: "极端",
                analogy: "周末池子浅——波动先当流动性，不当方向",
              }
            ),
            tpl(
              "structure.liquidity",
              "吃穿一档不回补",
              "{品种}大单把一档吃穿，回补却不回来：这是抽流动性，不是普通成交。",
              {
                id: "ext_eat_no_refill",
                category: "极端",
                stance: "bear",
                analogy: "吃穿一档却不补——有人在抽走流动性",
              }
            ),
            tpl(
              "structure.liquidity",
              "亚盘薄美盘厚",
              "亚盘薄、美盘厚：{品种}同一根突破，时区不同含义不同。",
              {
                id: "common_asia_us_depth",
                category: "常见",
                analogy: "同一根 K，亚盘突破和美盘突破不是一回事",
              }
            ),
            tpl(
              "structure.liquidity",
              "价动大盘口没补",
              "价动很大、盘口没补：先标冲击，不标趋势。",
              {
                id: "common_move_no_refill",
                category: "常见",
                analogy: "价走了、单没补——先标冲击成本",
              }
            ),
            tpl(
              "structure.liquidity",
              "深度回暖价横",
              "深度回暖、价格横着：流动性在修复，方向还没投票。",
              {
                id: "common_depth_recover_flat",
                category: "常见",
                stance: "bull",
                analogy: "池子在补水，球还没滚方向",
              }
            ),
            tpl(
              "structure.liquidity",
              "点差正常十档降",
              "点差正常、但十档总量在降：表面能成交，底下已经变薄。",
              {
                id: "common_spread_ok_depth_down",
                category: "常见",
                stance: "bear",
                analogy: "门面还开着，仓库已经在搬空",
              }
            ),
            tpl(
              "structure.liquidity",
              "与 BTC 一起变薄",
              "{品种}和 BTC 深度一起变薄：是板块风险偏好，不是山寨单独故事。",
              {
                id: "common_btc_alts_thin",
                category: "常见",
                analogy: "大家一起变薄——是板块在退，不是单币",
              }
            ),
            tpl(
              "structure.liquidity",
              "长影成交一般",
              "上影 / 下影很长、成交一般：薄行情扫完就走，不是充分换手。",
              {
                id: "common_long_wick_thin",
                category: "常见",
                analogy: "长影线 + 薄成交——扫完流动性就回",
              }
            ),
            tpl(
              "structure.liquidity",
              "费率不动深度先掉",
              "资金费率不动、深度先掉：杠杆没挤，流动性先走了。",
              {
                id: "common_depth_before_funding",
                category: "常见",
                stance: "bear",
                analogy: "杠杆还在，做市先撤——流动性领先",
              }
            ),
            tpl(
              "structure.liquidity",
              "ETF 进盘口更薄",
              "ETF 有流入、现货盘口却更薄：机构通道在买，公开订单簿没变厚。",
              {
                id: "common_etf_in_book_thin",
                category: "常见",
                analogy: "机构走暗道买，公开盘口没厚——分层成交",
              }
            ),
            tpl(
              "structure.liquidity",
              "薄市假突破多",
              "深度掉下去之后，假突破比真突破更常见。",
              {
                id: "likely_fake_break_thin",
                category: "大概率",
                analogy: "池浅时假突破比真突破常见",
              }
            ),
            tpl(
              "structure.liquidity",
              "修复先于第二段",
              "流动性修复通常先于趋势第二段，先看到点差收回、再谈方向。",
              {
                id: "likely_repair_before_trend",
                category: "大概率",
                stance: "bull",
                analogy: "先修池子，再谈第二浪",
              }
            ),
            tpl(
              "structure.liquidity",
              "薄市长针是扫流",
              "薄市场里放量长针，事后更常被证明是扫流动性，不是起点。",
              {
                id: "likely_wick_sweep",
                category: "大概率",
                analogy: "薄市长针多半是扫单，不是新趋势起点",
              }
            ),
            tpl(
              "structure.liquidity",
              "价深同向变好",
              "深度与价格同向变好（上涨且买盘增厚）延续概率大于「只涨不厚」。",
              {
                id: "likely_price_depth_up",
                category: "大概率",
                stance: "bull",
                analogy: "涨且买盘厚——比只涨不厚更可持续",
              }
            ),
            tpl(
              "structure.liquidity",
              "美盘前变薄",
              "美盘前一小时变薄，开盘后前 30 分钟方向噪声最大。",
              {
                id: "likely_us_open_noise",
                category: "大概率",
                analogy: "开盘前池浅——前半小时噪声最大",
              }
            ),
            tpl(
              "structure.liquidity",
              "稳定币深度双降",
              "稳定币存量降、深度降，反弹更像反抽；两者都回升才像风险偏好回来。",
              {
                id: "likely_stable_depth_pair",
                category: "大概率",
                analogy: "弹药和盘口一起回，才算风险偏好回来",
              }
            ),
            tpl(
              "structure.liquidity",
              "墙近深度在 vs 没了",
              "墙很近但深度还在，更常先磨；墙近且深度没了，更常一穿就滑。",
              {
                id: "likely_wall_depth",
                category: "大概率",
                analogy: "有墙有深度先磨，有墙没深度一穿就滑",
              }
            ),
            tpl(
              "structure.liquidity",
              "短看深度长看结构",
              "{1h}看深度，{日线}看结构：只在薄时谈波动，厚了才谈趋势。",
              {
                id: "likely_horizon_depth",
                category: "大概率",
                analogy: "薄时谈波动，厚了才谈趋势——别混时间尺",
              }
            ),
            tpl(
              "structure.liquidity",
              "砸时买盘增厚",
              "砸下去时买盘增厚、点差没爆：有人在接，不像无人区下跌。",
              {
                id: "bull_bid_thick_on_drop",
                category: "看涨",
                stance: "bull",
                analogy: "跌时买盘厚、价差稳——有人在接",
              }
            ),
            tpl(
              "structure.liquidity",
              "回踩深度回补",
              "回踩缩量、深度回补、费率不烫：流动性在恢复，回调更像观察。",
              {
                id: "bull_pullback_depth_recover",
                category: "看涨",
                stance: "bull",
                analogy: "缩量回踩 + 深度回来——回调像观察点",
              }
            ),
            tpl(
              "structure.liquidity",
              "下方十档更厚",
              "下方十档明显厚于上方：同样的卖压更难打穿。",
              {
                id: "bull_bid_ladder_thick",
                category: "看涨",
                stance: "bull",
                analogy: "下面梯子厚——同样卖压更难穿",
              }
            ),
            tpl(
              "structure.liquidity",
              "扫过深度未再坏",
              "清算扫过、深度没有再坏：恐慌单出完了，薄的那一页翻过去。",
              {
                id: "bull_post_sweep_depth_ok",
                category: "看涨",
                stance: "bull",
                analogy: "扫完深度还在——恐慌单出尽",
              }
            ),
            tpl(
              "structure.liquidity",
              "稳定币买盘增厚",
              "稳定币回升 + 现货买盘增厚：能买的钱和愿意挂单的人都在。",
              {
                id: "bull_stable_bid_up",
                category: "看涨",
                stance: "bull",
                analogy: "弹药和挂单都在增——两侧都更响",
              }
            ),
            tpl(
              "structure.liquidity",
              "更高低点等盘口厚",
              "{品种}更高低点已出，缺的只是盘口不再越涨越薄。",
              {
                id: "bull_higher_low_depth",
                category: "看涨",
                stance: "bull",
                analogy: "底抬了，就等涨时盘口别再变薄",
              }
            ),
            tpl(
              "structure.liquidity",
              "坏情况失效",
              "坏情况失效：点差收回、向下深度补回，价格守住扫穿区。",
              {
                id: "bull_bad_invalidate",
                category: "看涨",
                stance: "bull",
                analogy: "价差收回、深度补回——薄的那页翻过去了",
              }
            ),
            tpl(
              "structure.liquidity",
              "拉升卖盘增厚",
              "拉起来时卖盘增厚、买盘撤单：上涨在消耗仅剩的买盘。",
              {
                id: "bear_ask_up_bid_out",
                category: "看跌",
                stance: "bear",
                analogy: "涨时卖盘加、买盘撤——在消耗最后买盘",
              }
            ),
            tpl(
              "structure.liquidity",
              "价新高深度新低",
              "价新高、深度新低：这是薄行情推升，不是趋势变厚。",
              {
                id: "bear_high_price_thin",
                category: "看跌",
                stance: "bear",
                analogy: "价创新高、池子在变浅——薄推不是厚趋势",
              }
            ),
            tpl(
              "structure.liquidity",
              "下方深度先没",
              "向下深度先消失，费率还在偏多：跌起来没有垫，涨是拥挤。",
              {
                id: "bear_bid_gone_long_crowd",
                category: "看跌",
                stance: "bear",
                analogy: "下面没垫、费率还偏多——跌无缓冲涨是挤",
              }
            ),
            tpl(
              "structure.liquidity",
              "砸穿不回补",
              "大单砸穿后盘口不回补：流动性被抽走，反弹先当测试。",
              {
                id: "bear_break_no_refill",
                category: "看跌",
                stance: "bear",
                analogy: "砸穿却不补单——反弹先当测试",
              }
            ),
            tpl(
              "structure.liquidity",
              "周末薄遇坏消息",
              "周末薄 + 坏消息：缺口和滑点比方向更先出现。",
              {
                id: "bear_weekend_bad_news",
                category: "看跌",
                stance: "bear",
                analogy: "周末池浅遇利空——缺口滑点先到",
              }
            ),
            tpl(
              "structure.liquidity",
              "好情况失效",
              "好情况失效：上涨中买盘变薄、点差拉宽。",
              {
                id: "bear_good_invalidate",
                category: "看跌",
                stance: "bear",
                analogy: "涨时买盘薄、价差宽——好叙事在失效",
              }
            ),
            tpl(
              "structure.liquidity",
              "脱钩向下深度更差",
              "{品种}和 BTC 脱钩向下，自身深度更差：补跌的空间在流动性里。",
              {
                id: "bear_decouple_thin",
                category: "看跌",
                stance: "bear",
                analogy: "脱钩向下且更薄——补跌空间在滑点里",
              }
            ),
            tpl(
              "structure.liquidity",
              "三层买盘一起撤",
              "稳定币降、ETF 出、盘口薄：三层买盘一起撤。",
              {
                id: "bear_triple_bid_out",
                category: "看跌",
                stance: "bear",
                analogy: "稳定币、ETF、盘口三层一起撤——买盘共振空",
              }
            ),
          ],
        }),
      ],
    },
    {
      id: "narrative",
      name: "币种与板块叙事",
      desc: "L1、Meme、RWA、AI 等主题轮动",
      topics: [
        topic({
          id: "narrative.btc_gold",
          categoryId: "narrative",
          name: "BTC 数字黄金",
          importance: 5,
          meaning:
            "把 BTC 当储备资产、抗通胀和美元体系的替代，而不是高 Beta 科技股。内容要能对上黄金、实际利率、ETF，而不是只喊减半。",
          impactSummary:
            "数字黄金看 BTC 跟黄金还是跟纳指；ETF 连流入 + 实际利率回落时叙事才占上风。",
          relatedThemes: [
            "macro.dxy",
            "structure.etf_flow",
            "macro.geo",
            "macro.fomc",
            "people.treasury",
            "structure.btcd",
          ],
          talkingPoints: [
            "跟纳指就不是数字黄金，跟黄金才是",
            "ETF 是新矿工，买盘在华尔街不是推特",
            "加息周能抗住，叙事才成立",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("黄金", "同向则叙事加分，跟纳指则 narrative 打折", "1–3 日"),
            impactOn("DXY / 实际利率", "利率上，黄金和 BTC 都受压", "即时"),
            impactOn("现货 ETF 流入", "机构认的是储备，不是山寨", "交易日"),
            impactOn("BTC.D / 主导率", "数字黄金周通常抬主导率", "数日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "实际利率回落或 ETF 连流入，BTC 与黄金同向",
              then: "储备叙事占上风",
              coins: ["BTC"],
              stance: "bull",
              template:
                "这周 BTC 在跟黄金，不是跟纳指。数字黄金成立时，先写 ETF 和实际利率，不写山寨轮动。",
              invalidation: "BTC 与 SOX/纳指相关性重新升到极高，黄金不跟",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "加息/美元强，BTC 跌得比黄金深",
              then: "市场仍把它当风险资产",
              coins: ["BTC"],
              stance: "bear",
              template:
                "避险的时候它没稳住。先承认这是流动性资产，不是黄金。等抗跌再捡这条叙事。",
              invalidation: "同日黄金跌、BTC 横或涨",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "ETF 进但价格跟纳指波动",
              then: "机构和短线交易员不在一个剧本里",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "账本在买储备，盘面在交易科技股。两种人各写各的。结论等谁留下。",
              invalidation: "连续 5 日与黄金同向且 ETF 净流入",
            }),
          ],
          templates: [
            tpl(
              "narrative.btc_gold",
              "先对黄金，再对纳指",
              "跟纳指就不是数字黄金，跟黄金才是。先写 ETF 和实际利率，再写减半口号。",
              { stance: "mixed", coins: ["BTC"] }
            ),
          ],
        }),
        topic({
          id: "narrative.l1",
          categoryId: "narrative",
          name: "L1 / 公链竞争",
          importance: 4,
          meaning:
            "ETH、SOL、BNB、新 L1（SUI、APT、MONAD 等）抢执行层：费用、吞吐、开发者、稳定币结算、应用收入。不要写成「谁是以太杀手」。",
          impactSummary:
            "份额看稳定币结算和日费用，不看 TPS；主网上线是叙事高峰，解锁日是卖压高峰。",
          relatedThemes: [
            "narrative.stablechain",
            "narrative.perp_dex",
            "fundamental.tvl",
            "fundamental.unlock",
            "narrative.ai",
          ],
          talkingPoints: [
            "看费用和留存，不看 TPS 海报",
            "新链主网上线是叙事高峰，不是基本面高峰",
            "稳定币和交易盘在哪，链就在哪",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("TVL / 协议收入", "perp/DEX/稳定币结算决定估值", "数周"),
            impactOn("解锁 / Cliff", "高 FDV 新 L1 上线即卖压", "解锁日"),
            impactOn("ETH", "活动迁走会压费用叙事", "中期"),
            impactOn("山寨季 vs 比特币季", "L1 轮动往往先于 meme", "数日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "日费用、活跃地址、稳定币供应同步升，且无大额解锁",
              then: "份额在涨，不是纯炒作",
              coins: ["ETH", "SOL"],
              stance: "bull",
              template:
                "别比 TPS。看稳定币和手续费有没有留下。留下了才能写份额，没留下只是主网庆典。",
              invalidation: "费用一周内腰斩或大解锁临近",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "主网/空投后用量塌，或高 FDV 低收入",
              then: "叙事结束、PMF 未到",
              coins: ["SOL"],
              stance: "bear",
              template:
                "上线不是基本面。交易量和积分一起消失时，不要用生态路线图挡卖压。",
              invalidation: "空投后 30 日留存仍高、费用稳定",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "用量很好但币价弱，或币强数据平",
              then: "一个是基本面，一个是筹码",
              coins: ["ETH"],
              stance: "mixed",
              template:
                "链热币冷，或币热链冷。先写数据再写价格，别合成一句「生态爆发」。",
              invalidation: "两者重新同向 2 周",
            }),
          ],
          templates: [
            tpl(
              "narrative.l1",
              "份额看费用，不看 TPS",
              "稳定币和交易盘在哪，链就在哪。主网庆典不等于基本面。",
              { stance: "mixed", coins: ["ETH", "SOL"] }
            ),
          ],
        }),
        topic({
          id: "narrative.stablechain",
          categoryId: "narrative",
          name: "稳定币公链",
          importance: 5,
          meaning:
            "USDC/USDT 当 gas、机构验证者、支付和 FX 结算层（Arc、Tempo 等）。标的往往是发行商、平台币和结算类应用，不是乱发的链代币。",
          impactSummary:
            "美元即 gas 是轨道争夺；主网周假代币最多，机构链与散户票常脱节。",
          relatedThemes: [
            "narrative.rwa",
            "policy.stable",
            "narrative.perp_dex",
            "metastory.stable_rail",
            "narrative.l1",
          ],
          talkingPoints: [
            "美元即 gas，是轨道不是山寨 L1",
            "代币铸了不等于空投",
            "验证者名单比浏览器 TPS 重要",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("USDC 份额", "发行商链利好本家稳定币", "中期"),
            impactOn("L1 / 公链竞争", "结算或被分走一层", "中期"),
            impactOn("Perp DEX", "应用迁到美元链", "上线后 1–4 周"),
            impactOn("假代币", "主网周骗局最多", "即时"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "主网真上线、机构验证者就位、应用有真实结算",
              then: "写轨道和份额，不写土狗",
              coins: ["USDC"],
              stance: "bull",
              template:
                "这是结算层争夺。看谁用 USDC 付 gas、谁在验证节点上。别把未流通的链代币写成刚兑空投。",
              invalidation: "无真实交易对、只有积分和发射盘",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "只有测试网热度或假 ARC 满天飞",
              then: "叙事被骗局污染",
              coins: ["USDC"],
              stance: "bear",
              template:
                "主网是真的，代币上市不是。任何查空投的链接先当钓鱼。",
              invalidation: "官方明确 TGE 规则与分配",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "机构链在长、散户无币可炒",
              then: "内容和盘面会脱节",
              coins: ["USDC"],
              stance: "mixed",
              template:
                "机构在上链，盘面在找票。两件事不要写成同一个涨。",
              invalidation: "官方开通可交易网络代币并有解锁表",
            }),
          ],
          templates: [
            tpl(
              "narrative.stablechain",
              "轨道已上线，代币还没发",
              "美元即 gas 是轨道不是山寨 L1。主网周先写验证者和结算，不写查空投链接。",
              { stance: "mixed", coins: ["USDC"] }
            ),
          ],
        }),
        topic({
          id: "narrative.rwa",
          categoryId: "narrative",
          name: "RWA / 上链国债",
          importance: 4,
          meaning:
            "国债、信贷、代币化美股、基金份额上链。催化常来自监管豁免、发行规模、赎回是否顺畅，而不是 TVL 海报。",
          impactSummary:
            "RWA 先看能不能赎回和持牌托管；监管开门与债券价格可以同向不同步。",
          relatedThemes: [
            "policy.sec",
            "narrative.stablechain",
            "macro.dxy",
            "policy.stable",
            "narrative.perp_dex",
          ],
          talkingPoints: [
            "有赎回和持牌托管才叫 RWA",
            "收益率来自国债，不来自积分",
            "代币化股票豁免 ≠ 全国零售开盘",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("DXY / 实际利率", "降息预期抬国债代币需求，也压「高收益替代」叙事", "宏观周"),
            impactOn("SEC / 执法", "豁免利好持牌结算和 perp 美股", "政策日"),
            impactOn("稳定币法案", "申赎用 USDC，利好美元轨道", "同步"),
            impactOn("RWA 分叉", "无牌照的先被监管叙事砸", "执法日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "规模增长 + 可赎回 + 出现新的合规定价通道（如豁免）",
              then: "板块有基本面，不只是叙事",
              coins: ["BTC"],
              stance: "bull",
              template:
                "看能不能兑回美元，不看包装了多少国债。通道一开，写持牌龙头，不写三流分叉。",
              invalidation: "赎回卡顿或规模连续下降",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "监管口头利空，或产品无法赎回、收益来自补贴",
              then: "RWA 折价成「链上理财」",
              coins: ["BTC"],
              stance: "bear",
              template:
                "国债上链不是许可证。兑不出、牌照没有，就按高风险理财写，不要按黑石写。",
              invalidation: "一线机构产品规模创新高且赎回正常",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "政策利好但利率大升",
              then: "叙事多、债券价格空",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "监管开门和债券跌可以同时发生。RWA 代币不一定跟国债反着涨。",
              invalidation: "规模与二级价格同步走强",
            }),
          ],
          templates: [
            tpl(
              "narrative.rwa",
              "先问能不能赎回",
              "有赎回和持牌托管才叫 RWA。收益率来自国债，不来自积分。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "narrative.perp_dex",
          categoryId: "narrative",
          name: "Perp DEX",
          importance: 5,
          meaning:
            "链上永续：手续费、资金费、OI、积分/代币。2026 的交易基础设施叙事，常比通用 L1 更贴近「链上纳指/外汇/商品」。",
          impactSummary:
            "Perp DEX 份额看 OI 和真实收入，不看积分日交易量；TGE 前后是抛压测试。",
          relatedThemes: [
            "structure.funding",
            "narrative.stablechain",
            "narrative.rwa",
            "exchange.airdrop",
            "exchange.fee",
          ],
          talkingPoints: [
            "看真实 OI 和费率，不看积分日交易量",
            "发币后才是压力测试",
            "上新资产（外汇、美股、商品）比再开一条链重要",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("平台币", "份额和回购/手续费分成", "持续"),
            impactOn("空投季", "未发币所吃农民，发币所吃抛压", "TGE 前后"),
            impactOn("稳定币公链", "清算和保证金迁到美元链", "主网周"),
            impactOn("费率 / VIP", "CEX 费率活动和合约上币是对手盘", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "OI 与收入升、积分占比下降、新品种有真实持仓",
              then: "份额在涨",
              coins: ["BTC"],
              stance: "bull",
              template:
                "这不是刷量周。OI 留下了，新品种有人对赌。平台币跟份额，不跟积分。",
              invalidation: "日交易量腰斩或资金费长期极端",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "积分农场占量、TGE 临近或刚结束、规则后置",
              then: "代币是出货口",
              coins: ["BTC"],
              stance: "bear",
              template:
                "量是积分养的。发币日把农民变成卖方。没有收入就不要写下一个 Hyperliquid。",
              invalidation: "TGE 后 30 日 OI 仍在、收入不塌",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "产品强、代币弱（或相反）",
              then: "交易所有 PMF，币没有",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "交易所能用，不等于代币能囤。把产品叙事和币价拆开。",
              invalidation: "回购/分成真正落到币上",
            }),
          ],
          templates: [
            tpl(
              "narrative.perp_dex",
              "OI 留下才算份额",
              "看真实 OI 和费率，不看积分日交易量。发币后才是压力测试。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "narrative.ai",
          categoryId: "narrative",
          name: "AI x Crypto",
          importance: 3,
          meaning:
            "算力、推理、agent 支付、数据市场。2026 容易跟纳指 AI 股联动，也容易变成换皮 meme。",
          impactSummary:
            "链上 AI 先看账单谁付；NVDA/SOX 是贝塔来源，没有推理订单就是主题帖。",
          relatedThemes: [
            "macro.equities",
            "infra.hashrate",
            "narrative.stablechain",
            "narrative.l1",
            "narrative.meme",
          ],
          talkingPoints: [
            "有推理订单或 GPU 结算才叫 AI，有个机器人聊天室不叫",
            "AI 股大跌时这一板块先撤",
            "Agent 要会付稳定币，不是只会发推",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("美股联动", "科技股风向标", "当日"),
            impactOn("算力 / 矿工", "DePIN 算力项目同涨同跌", "数日"),
            impactOn("Meme / 文化币", "叙事热时发射台过热", "数日"),
            impactOn("稳定币公链", "agent 结算是稳定币的远期需求", "中期"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "有真实用量（推理、租算力、agent 付费）且 AI 股不崩",
              then: "板块可交易",
              coins: ["BTC"],
              stance: "bull",
              template:
                "先问账单谁付。有稳定币流水再写 AI，没有就当主题帖。",
              invalidation: "用量周环比腰斩或纳指 AI 大跌",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "只有模型包装 + 代币发射",
              then: "按 meme 定价",
              coins: ["BTC"],
              stance: "bear",
              template:
                "AI 是皮，meme 是骨。科技股一抖，这一筐先跌。",
              invalidation: "连续披露可稽核收入",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "美股 AI 强、链上 AI 币弱（或相反）",
              then: "贝塔来源不同",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "纳指的 AI 和链上的 AI 不是同一个指数。别用 NVDA 给土狗估值。",
              invalidation: "两者相关性重新稳定",
            }),
          ],
          templates: [
            tpl(
              "narrative.ai",
              "先看账单，再看模型",
              "有推理订单或 GPU 结算才叫 AI。Agent 要会付稳定币，不是只会发推。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "narrative.meme",
          categoryId: "narrative",
          name: "Meme / 文化币",
          importance: 3,
          meaning:
            "注意力、模因、发射台、名人/政治梗。定价是流量和流动性，不是白皮书。必须标明这是高周转垃圾时间。",
          impactSummary:
            "Meme 是流量定价、BTC.D 是风控；主导率升时不要做多狗。",
          relatedThemes: [
            "structure.btcd",
            "exchange.airdrop",
            "people.kol",
            "structure.liquidity",
            "narrative.altseason",
          ],
          talkingPoints: [
            "主导率上升时不要做多狗",
            "发射台日增发速度 > 接盘速度就是顶",
            "文化能解释开盘，不能解释第二天",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("BTC.D / 主导率", "D 升先杀 meme", "1–3 日"),
            impactOn("活动 / 空投", "新币供给本身是卖压", "当日"),
            impactOn("上市 / 下架", "政治梗更脆", "突发"),
            impactOn("流动性 / 深度", "链上拥堵说明过热", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "BTC 稳、D 降、有文化事件、深度还在",
              then: "可做短线注意力",
              coins: ["BTC"],
              stance: "bull",
              template:
                "这是流量交易。仓位按小时计，主题按当天计。D 一抬头就离场。",
              invalidation: "BTC.D 转强或头池深度蒸发",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "宏观利空周或主导率升",
              then: "meme 是出货口",
              coins: ["BTC"],
              stance: "bear",
              template:
                "山寨季口号救不了狗。先看主导率，再看 K 线。",
              invalidation: "BTC 新高 + D 连续下降",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "单条梗爆、板块指数不涨",
              then: "是个孤品，不是季节",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "一个梗的热度不是板块轮动。别把单票写成 meme 季。",
              invalidation: "同类发射连续 3 日放量且不秒死",
            }),
          ],
          templates: [
            tpl(
              "narrative.meme",
              "流量定价，主导率风控",
              "Meme 是流量生意不是基本面。主导率升时不要做多狗，仓位按小时计。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "narrative.privacy",
          categoryId: "narrative",
          name: "隐私 / 审查抗性",
          importance: 4,
          meaning:
            "隐私支付、混币定性、下架、机构「合规隐私」、ZEC 等。催化经常是制裁、名人/机构持仓、交易所政策，不是技术升级本身。",
          impactSummary:
            "隐私币先看能否交易和下架政策；+20% 是情绪，不是采用曲线。",
          relatedThemes: [
            "policy.enforcement",
            "exchange.listing",
            "structure.etf_flow",
            "policy.sec",
            "infra.censorship",
          ],
          talkingPoints: [
            "进不了 ETF 的东西，在机构流出时可能被拿来交易",
            "下架是流动性事件，先于意识形态",
            "一天 +20% 是情绪，不是采用",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("重大执法 / 和解案", "短线刺激隐私需求", "突发"),
            impactOn("上市 / 下架", "下架直接抽流动性", "公告日"),
            impactOn("BTC 数字黄金", "隐私是补充叙事不是替代", "中期"),
            impactOn("审查 / MEV", "机构更吃「可审计隐私」", "政策周"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "有机构背书或明确需求冲击，且尚未失流动性",
              then: "短线可交易",
              coins: ["ZEC", "BTC"],
              stance: "bull",
              template:
                "钱在找 ETF 买不到的东西。写头部流动性，不写无法出入金的分叉。",
              invalidation: "交易所宣布审查或大额解锁砸盘",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "集体下架、银行通道关、深度没了",
              then: "有叙事无市场",
              coins: ["BTC"],
              stance: "bear",
              template:
                "隐私需求在，订单簿不在。没有盘口就不要给目标价。",
              invalidation: "头部所恢复交易对",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "价格暴涨但链上真实转账没升",
              then: "纯筹码",
              coins: ["ZEC"],
              stance: "mixed",
              template:
                "这是持仓新闻，不是采用曲线。仓位按事件衰减。",
              invalidation: "转账数和地址同步上台阶",
            }),
          ],
          templates: [
            tpl(
              "narrative.privacy",
              "先看能否交易，再看意识形态",
              "下架是流动性事件，先于意识形态。写头部流动性，不写无法出入金的分叉。",
              { stance: "mixed", coins: ["ZEC"] }
            ),
          ],
        }),
        topic({
          id: "narrative.altseason",
          categoryId: "narrative",
          name: "山寨季 vs 比特币季",
          importance: 5,
          meaning:
            "总开关：钱在 BTC 还是 Others。判定要用 BTC.D + BTC 价格 + 稳定币市值，不要用时间表。",
          impactSummary:
            "三条件确认山寨季：BTC 不崩、D 降、ETH/板块先于 meme；一起跌只是风险季。",
          relatedThemes: [
            "structure.btcd",
            "structure.etf_flow",
            "structure.funding",
            "narrative.l1",
            "narrative.meme",
          ],
          talkingPoints: [
            "比特币季：D 升或 BTC 独涨",
            "山寨季：BTC 不破、D 降、ETH 或板块先动",
            "一起跌只是风险季，两边都不是",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("内容选题", "季节决定你写宏观还是写板块", "即时"),
            impactOn("仓位", "季节错了，方向对也亏", "数日"),
            impactOn("现货 ETF 流入", "BTC 单边流入强化比特币季", "交易日"),
            impactOn("Meme / 文化币", "山寨季才有系统性流量", "数日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（确认山寨季）",
              if: "BTC 持稳/新高 + BTC.D 降 + ETH.D 或主流板块先于 meme",
              then: "外溢开始",
              coins: ["ETH", "SOL"],
              stance: "bull",
              template:
                "三个条件齐了再喊山寨季：BTC 不崩、主导率让位、不是只有狗在涨。",
              invalidation: "D 止跌回升或 BTC 破关键位",
            }),
            scenario("bad", {
              name: "坏情况（比特币季/避险）",
              if: "D 升、ETF 只进 BTC、宏观紧",
              then: "山寨是出货盘",
              coins: ["BTC"],
              stance: "bear",
              template:
                "季节还在比特币。把山寨反弹当减仓，不当轮动起点。",
              invalidation: "上述三条件出现",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "D 降但总市值也降",
              then: "去杠杆，不是轮动",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "饼变小的时候，主导率下降没有奖金。先等稳定币市值和 ETF 止血。",
              invalidation: "总市值止跌且 ETH 转强",
            }),
          ],
          templates: [
            tpl(
              "narrative.altseason",
              "三条件确认季节",
              "山寨季：BTC 不破、D 降、ETH 或板块先动。一起跌只是风险季，两边都不是。",
              { stance: "mixed", coins: ["BTC", "ETH"] }
            ),
          ],
        }),
      ],
    },
    {
      id: "fundamental",
      name: "项目与代币基本面",
      desc: "解锁、回购、收入与估值",
      topics: [
        topic({
          id: "fundamental.unlock",
          categoryId: "fundamental",
          name: "解锁 / Cliff",
          meaning: "大额代币解锁与 cliff 到期，带来潜在卖压与预期博弈。",
          relatedThemes: ["calendar.unlock", "FDV"],
          talkingPoints: [
            "解锁比例 < 流通占比才有意义",
            "团队/VC 解锁看链上是否已移动",
            "「解锁利空出尽」要有前置跌幅证据",
          ],
          defaultStance: "bear",
        }),
        topic({
          id: "fundamental.buyback",
          categoryId: "fundamental",
          name: "回购 / 销毁",
          meaning: "协议收入用于回购或销毁，影响 float 与长期 holder 叙事。",
          relatedThemes: ["fundamental.tvl", "fee"],
          talkingPoints: [
            "回购资金来源要可持续",
            "销毁 vs 国库回购对 float 影响不同",
            "announcement vs 链上执行要核对",
          ],
          defaultStance: "bull",
        }),
        topic({
          id: "fundamental.tvl",
          categoryId: "fundamental",
          name: "TVL / 协议收入",
          meaning: "锁仓量与真实 fee 收入衡量协议基本面，需剔除激励与 double count。",
          relatedThemes: ["narrative.l1", "narrative.rwa"],
          talkingPoints: [
            "激励驱动的 TVL 退潮速度",
            "收入 / FDV 估值框架",
            "跨链 double count 陷阱",
          ],
          defaultCoins: ["ETH"],
        }),
        topic({
          id: "fundamental.fdv",
          categoryId: "fundamental",
          name: "FDV vs 流通市值",
          meaning: "全稀释估值与流通市值的剪刀差，决定「便宜」是否只是 illusion。",
          relatedThemes: ["fundamental.unlock", "narrative.l1"],
          talkingPoints: [
            "低 MC 高 FDV = 未来卖压期权",
            "对比同类项目要用同一 unlock 曲线",
            "别用 FDV 单独论证低估",
          ],
          defaultStance: "neutral",
        }),
        topic({
          id: "fundamental.tokenomics",
          categoryId: "fundamental",
          name: "代币模型变更",
          meaning: "通胀率、staking 奖励、fee switch 等经济模型调整。",
          relatedThemes: ["infra.staking", "治理"],
          talkingPoints: [
            "模型变更 = 重新定价，不是小更新",
            "写清受益方（holder / LP / 团队）",
            "过渡期的套利与抛压",
          ],
          defaultStance: "mixed",
        }),
      ],
    },
    {
      id: "ta",
      name: "技术分析与微观结构",
      desc: "结构、费率极端、爆仓与关键位",
      topics: [
        topic({
          id: "ta.structure",
          categoryId: "ta",
          name: "关键结构 / 趋势",
          importance: 4,
          meaning:
            "高低点、突破回踩、BOS/CHoCH、趋势是否还在。先定结构，再套指标。结构反了，RSI 金叉也不写多。",
          impactSummary:
            "结构定方向定义；日线与 4 小时打架时分周期写，BTC 结构没修好不写山寨趋势。",
          relatedThemes: [
            "ta.sr",
            "ta.volume",
            "structure.funding",
            "structure.etf_flow",
            "macro.fomc",
          ],
          talkingPoints: [
            "先问现在是涨势回踩还是跌势反弹",
            "突破要回踩确认，光刺穿不算",
            "日线和 4 小时打架时，内容跟大周期，交易跟小周期并写明",
            "图形：头肩、三角、楔形、旗形在这里读，不单拆小类",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("支撑 / 阻力", "结构决定哪根线还有效", "即时"),
            impactOn("资金费 / OI", "顺势加仓费率温和才健康", "同步"),
            impactOn("现货 ETF 流入", "结构多 + ETF 进，质量升一档", "1–2 日"),
            impactOn("山寨季 vs 比特币季", "BTC 结构没修好，不写山寨趋势", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "高点上移、回踩不破前低、放量突破后收回踩稳",
              then: "趋势仍在",
              coins: ["BTC"],
              stance: "bull",
              template:
                "结构还在，把回调当回踩。不要把一根长上影写成见顶。失效看日线收在前低下方。",
              invalidation: "收盘破前低且无法收回",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "低点下移、反弹不过前高、假突破后加速",
              then: "跌势未完",
              coins: ["BTC"],
              stance: "bear",
              template:
                "这是跌势里的反弹，不是新趋势。前高就是供货区。失效看收盘站上前高并站住。",
              invalidation: "收盘站上前高且 OI/ETF 不恶化",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "日线上涨、4 小时破结构，或相反",
              then: "分周期写，不合成一句「变盘」",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "大周期和小周期在抢方向。标题写清你跟哪根线，别把震荡写成转折。",
              invalidation: "两个周期重新同向",
            }),
          ],
          templates: [
            tpl("ta.structure", "日线结构断了", "{品种}日线结构断了，小时线再漂亮也先降级成反抽。", {
              id: "ext_daily_broken",
              category: "极端",
              stance: "bear",
              analogy: "大周期断线，小周期再美也只是反抽",
            }),
            tpl("ta.structure", "高低点对倒", "高低点在同一段里对倒改写：现在没有趋势，只有争夺。", {
              id: "ext_hl_swap",
              category: "极端",
              analogy: "高低点乱套——没有趋势，只有争夺",
            }),
            tpl("ta.structure", "突破收回结构内", "{品种}突破后又收回结构内：这是失败，不是「回踩确认」。", {
              id: "ext_failed_break",
              category: "极端",
              stance: "bear",
              analogy: "突破收回去——失败，不是回踩确认",
            }),
            tpl("ta.structure", "更高低点还在", "更高低点还在，回踩不破前低：趋势还在，回调当观察。", {
              id: "common_hl_hold",
              category: "常见",
              stance: "bull",
              analogy: "前低还在——趋势还在，回调当观察",
            }),
            tpl("ta.structure", "4h 与日线相反", "4h 和日线方向相反：先标分歧，不合成一句「变盘」。", {
              id: "common_tf_conflict",
              category: "常见",
              analogy: "大小周期打架——标分歧，别写变盘",
            }),
            tpl("ta.structure", "结构成量能不足", "结构成型、量能不足：位置偏多/空，还不是进场。", {
              id: "common_structure_no_vol",
              category: "常见",
              analogy: "形有了、量没有——位置对，时机未到",
            }),
            tpl("ta.structure", "小服从大周期", "小周期抢方向，大周期没改，结果更常服从大周期。", {
              id: "likely_small_obey_large",
              category: "大概率",
              analogy: "小周期闹，大周期没改——常服从大周期",
            }),
            tpl("ta.structure", "收盘站上才升级", "收盘站上前高才升级趋势；影线假突破更常见。", {
              id: "likely_close_confirm",
              category: "大概率",
              analogy: "收盘才算——影线突破假的多",
            }),
            tpl("ta.structure", "两周期同向才改口", "两个周期重新同向，才允许改口。", {
              id: "likely_tf_align",
              category: "大概率",
              analogy: "两周期同向——才允许改口",
            }),
            tpl("ta.structure", "趋势健康结构", "高点上移、回踩不破前低、放量突破后收回踩稳。", {
              id: "bull_trend_intact",
              category: "看涨",
              stance: "bull",
              analogy: "高低点上移、回踩稳——趋势健康",
            }),
            tpl("ta.structure", "坏情况失效", "坏情况失效：收盘站上前高且前低还在。", {
              id: "bull_bad_invalidate",
              category: "看涨",
              stance: "bull",
              analogy: "站上高、低还在——空要小心",
            }),
            tpl("ta.structure", "跌势结构", "低点下移、反弹不过前高、假突破后加速。", {
              id: "bear_downtrend",
              category: "看跌",
              stance: "bear",
              analogy: "低移、高不过——跌势结构",
            }),
            tpl("ta.structure", "好情况失效", "好情况失效：收盘破前低且无法收回。", {
              id: "bear_good_invalidate",
              category: "看跌",
              stance: "bear",
              analogy: "破低收不回——好叙事失效",
            }),
          ],
        }),
        topic({
          id: "ta.funding_extreme",
          categoryId: "ta",
          name: "资金费极端",
          importance: 5,
          meaning:
            "永续费率到拥挤区，表示一边付钱一边加仓。极端本身偏反转，但要和价格、OI 一起看。与「市场结构」里的资金费/OI 互补：这里偏交易时机。",
          impactSummary:
            "极正不是看涨是多头拥挤；费率回中性挤压才告一段落，到期周费率会失真。",
          relatedThemes: [
            "structure.funding",
            "ta.liquidation",
            "ta.structure",
            "structure.options",
          ],
          talkingPoints: [
            "极正不是看涨，是多头拥挤",
            "费率回到中性，挤压才告一段落",
            "到期周费率会失真",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("爆仓 / 清算 cascade", "极端后反向针最容易连环", "分钟–小时"),
            impactOn("关键结构 / 趋势", "逆结构的极端费率更危险", "同步"),
            impactOn("现货 ETF 流入", "现货在买、费率极正，短线仍可能洗", "1 日"),
            impactOn("山寨季 vs 比特币季", "山寨费率常比 BTC 更极端", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（挤压对你有利）",
              if: "费率极负 + 价格不破关键支撑",
              then: "空头拥挤，反弹可期",
              coins: ["BTC"],
              stance: "bull",
              template:
                "空头在付钱，结构还没坏。短线偏向挤空，不是基本面反转。失效看费率还在极负时价格破位。",
              invalidation: "极负中跌破结构",
            }),
            scenario("bad", {
              name: "坏情况（拥挤在你这边）",
              if: "费率极正 + 价格滞涨 + OI 高",
              then: "先防挤多",
              coins: ["BTC"],
              stance: "bear",
              template:
                "涨不动还在付费，这是燃料不是动力。先等一次降费率的回撤。",
              invalidation: "ETF 大进并把结构做成突破回踩",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "费率极端但波动被墙/到期压住",
              then: "挤不出来就耗着",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "拥挤遇到到期墙，方向会被拖到墙倒。先标墙，再标费率。",
              invalidation: "墙过后费率仍极端并开始单向波动",
            }),
          ],
          templates: [
            tpl("ta.funding_extreme", "极值 OI 还在堆", "{品种}费率到极值，OI 还在堆：交易的是踩踏，不是叙事。", {
              id: "ext_funding_oi_stack",
              category: "极端",
              analogy: "费率极值 + OI 堆——交易踩踏不是故事",
            }),
            tpl("ta.funding_extreme", "极正价走平", "极正费率 + 价格走平：多头拥挤，差一根向下清算。", {
              id: "ext_pos_flat",
              category: "极端",
              stance: "bear",
              analogy: "极正还走平——多头挤，差一根针",
            }),
            tpl("ta.funding_extreme", "极负现货不跌", "极负费率 + 现货不跌：空头拥挤，逼空和踩踏只隔一根。", {
              id: "ext_neg_spot_hold",
              category: "极端",
              stance: "mixed",
              analogy: "极负价不跌——逼空和踩踏只隔一根",
            }),
            tpl("ta.funding_extreme", "费率回落价不崩", "费率从极端往回走、价格没崩：拥挤在缓解。", {
              id: "common_funding_ease",
              category: "常见",
              stance: "bull",
              analogy: "费率回落价不崩——拥挤在缓解",
            }),
            tpl("ta.funding_extreme", "结算前后剧本", "结算前缩量、结算后放量：常规剧本，不当反转。", {
              id: "common_settle_rhythm",
              category: "常见",
              analogy: "结算前后量换档——常规剧本",
            }),
            tpl("ta.funding_extreme", "费率领先节奏", "费率领先价格 1 拍常见，领先很久不兑现是噪声。", {
              id: "common_funding_lead",
              category: "常见",
              analogy: "领先一拍正常，领先三拍是噪声",
            }),
            tpl("ta.funding_extreme", "极端后常见回归", "极端后 {8h/24h} 更常见回归，而不是继续加速。", {
              id: "likely_mean_revert",
              category: "大概率",
              analogy: "极端后更常回归，不是继续加速",
            }),
            tpl("ta.funding_extreme", "拥挤与波动反向", "拥挤方向与短线相反，下一根更常打拥挤反面。", {
              id: "likely_crowd_vs_move",
              category: "大概率",
              analogy: "拥挤与短线反向——下一根常打拥挤面",
            }),
            tpl("ta.funding_extreme", "空拥挤结构在", "空费率拥挤 + 结构低点还在。", {
              id: "bull_short_crowd_low",
              category: "看涨",
              stance: "bull",
              analogy: "空拥挤 + 低点在——挤空结构",
            }),
            tpl("ta.funding_extreme", "费率回落守住", "费率回落且收盘守住拥挤区上沿。", {
              id: "bull_funding_ease_hold",
              category: "看涨",
              stance: "bull",
              analogy: "费率回落还守住——拥挤警报解除",
            }),
            tpl("ta.funding_extreme", "多费率烫手", "多费率烫手 + 收盘走平在高位。", {
              id: "bear_long_hot_flat",
              category: "看跌",
              stance: "bear",
              analogy: "费率烫 + 高位走平——挤多前夜",
            }),
            tpl("ta.funding_extreme", "费率新高或回吐", "费率继续新高或价格回吐平台。", {
              id: "bear_funding_new_high",
              category: "看跌",
              stance: "bear",
              analogy: "费率新高或价回吐——好情况失效",
            }),
          ],
        }),
        topic({
          id: "ta.liquidation",
          categoryId: "ta",
          name: "爆仓 / 清算 cascade",
          importance: 4,
          meaning:
            "强平单砸穿深度，引发下一波强平。看爆仓地图、杠杆分布、哪一侧堆积。大针常是清算，不是叙事反转。",
          impactSummary:
            "先分清洗盘还是连环；一轮清算后费率归零才谈新方向。",
          relatedThemes: [
            "structure.liquidity",
            "ta.funding_extreme",
            "ta.sr",
            "structure.exchange_flow",
          ],
          talkingPoints: [
            "先问爆的是多还是空",
            "一轮清算后费率归零，才谈新方向",
            "同一价位二次爆仓，往往更狠",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("流动性 / 深度", "薄盘口放大 cascade", "即时"),
            impactOn("关键结构 / 趋势", "扫完流动性再看是否收回", "1–4h"),
            impactOn("山寨季 vs 比特币季", "BTC 一针，山寨杠杆先死", "同步"),
            impactOn("内容", "爆仓数字适合做标题，结论要等收回", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（扫完就收回）",
              if: "刺破支撑/阻力后快速收回，爆仓一次性释放，费率回中性",
              then: "是洗盘",
              coins: ["BTC"],
              stance: "bull",
              template:
                "这是清算针，不是日线反转。收回关键位且费率降温，按原结构做。失效看收不回。",
              invalidation: "收盘留在扫穿一侧",
            }),
            scenario("bad", {
              name: "坏情况（连环）",
              if: "一波爆仓后 OI 不降、深度更薄、同向再扫",
              then: "cascade 没结束",
              coins: ["BTC"],
              stance: "bear",
              template:
                "仓位没卸干净。第二针往往对着同一群人。在 OI 下来之前不要喊抄底。",
              invalidation: "OI 明显下降且价差恢复",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "BTC 爆仓小、山寨爆仓大",
              then: "分层去杠杆",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "清算发生在高 Beta，不是比特币换季。写主导率，不写牛转熊。",
              invalidation: "BTC 自身出现大额同向爆仓并破结构",
            }),
          ],
          templates: [
            tpl("ta.liquidation", "墙近盘口薄", "{品种}下方清算墙近、盘口变薄：cascade 条件到齐。", {
              id: "ext_wall_thin",
              category: "极端",
              stance: "bear",
              analogy: "墙近 + 盘口薄——cascade 条件齐",
            }),
            tpl("ta.liquidation", "扫墙带出第二层", "一次扫墙带出第二层墙：这是连锁，不是单针。", {
              id: "ext_second_wall",
              category: "极端",
              stance: "bear",
              analogy: "一层墙扫出二层——连锁不是单针",
            }),
            tpl("ta.liquidation", "高费率 OI 墙近", "高费率 + 高 OI + 墙近：离瀑布只差方向。", {
              id: "ext_fuel_ready",
              category: "极端",
              stance: "bear",
              analogy: "燃料满、墙近——差一个方向",
            }),
            tpl("ta.liquidation", "扫过立刻收回", "墙被扫过、价格立刻收回：更像猎杀流动性。", {
              id: "common_sweep_reclaim",
              category: "常见",
              stance: "bull",
              analogy: "扫完立刻收回——猎杀流动性",
            }),
            tpl("ta.liquidation", "清算大结构未断", "清算数字很大、结构没断：先当事件，不改趋势口径。", {
              id: "common_big_liq_event",
              category: "常见",
              analogy: "爆得响但结构在——先当事件",
            }),
            tpl("ta.liquidation", "只扫一层就停", "只扫掉一层就停：燃料用完，不等于反转确认。", {
              id: "common_one_layer",
              category: "常见",
              analogy: "只扫一层——燃料用完，不是反转证",
            }),
            tpl("ta.liquidation", "墙近深度在 vs 薄", "墙近但深度还在，更常先磨；墙近且薄，更常一穿就滑。", {
              id: "likely_wall_depth",
              category: "大概率",
              analogy: "有墙有深度先磨，没深度一穿就滑",
            }),
            tpl("ta.liquidation", "cascade 后新区间", "cascade 后 OI 下台阶，更像新区间，不是立刻反转。", {
              id: "likely_post_cascade_range",
              category: "大概率",
              analogy: "OI 下台阶——新区间不是立刻反转",
            }),
            tpl("ta.liquidation", "低位扫完结构在", "低位多头清算扫完，结构低点还在，费率从极负收窄。", {
              id: "bull_low_sweep_hold",
              category: "看涨",
              stance: "bull",
              analogy: "扫完低多、底还在——空弹药减",
            }),
            tpl("ta.liquidation", "下方墙被吃买盘厚", "墙在下被吃掉后买盘增厚。", {
              id: "bull_wall_eaten_bid",
              category: "看涨",
              stance: "bull",
              analogy: "下方墙被吃、买盘补——有人在接",
            }),
            tpl("ta.liquidation", "高位墙穿费率正", "高位多头墙被打穿，费率仍正，OI 不降。", {
              id: "bear_high_wall_break",
              category: "看跌",
              stance: "bear",
              analogy: "高墙穿、费率还正——挤多开始",
            }),
            tpl("ta.liquidation", "第二层墙更近", "第一层墙破了，第二层更近：下跌刚开始计费。", {
              id: "bear_second_wall_closer",
              category: "看跌",
              stance: "bear",
              analogy: "一层破、二层近——下跌才计费",
            }),
          ],
        }),
        topic({
          id: "ta.sr",
          categoryId: "ta",
          name: "支撑 / 阻力",
          importance: 3,
          meaning:
            "供需区、前高前低、整数关口、期权墙、成交密集区。线要少，标 2–3 条关键位比画满网格有用。",
          impactSummary:
            "支撑是被测出来的；破了再收回才是真防守，期权墙叠前高时阻力更硬。",
          relatedThemes: [
            "ta.structure",
            "structure.options",
            "ta.volume",
            "structure.liquidity",
          ],
          talkingPoints: [
            "支撑是被测出来的，不是画出来的",
            "破了再收回，才是真防守",
            "期权墙和前高叠在一起时，阻力更硬",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("关键结构 / 趋势", "破位改变趋势定义", "收盘"),
            impactOn("期权到期 / Max Pain", "执行价墙会把阻力钉死到到期", "到期周"),
            impactOn("爆仓 / 清算 cascade", "杠杆堆在线上下方", "同步"),
            impactOn("内容", "给点位必须给失效", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "回踩支撑缩量，再起放量，收盘守住",
              then: "位还在",
              coins: ["BTC"],
              stance: "bull",
              template:
                "这条线被测过并守住。下一句写目标阻力，不要把测试写成跌破。",
              invalidation: "收盘在支撑下",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "多次下探、阴线收在线下、反抽不过线",
              then: "支撑变阻力",
              coins: ["BTC"],
              stance: "bear",
              template:
                "破了就别叫支撑。反抽不过原线，是确认不是机会。",
              invalidation: "重新收上并站稳",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "现货支撑与期权墙/资金费信号冲突",
              then: "写两套位，标主次",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "盘面上有线，衍生品上有墙。到期前听墙，到期后听线。",
              invalidation: "到期后价格选边并放量",
            }),
          ],
          templates: [
            tpl("ta.sr", "第三次测试", "{品种}关键位第三次测试仍不破：要么即将失效，要么要变成反转点。", {
              id: "ext_third_test",
              category: "极端",
              stance: "mixed",
              analogy: "第三次测试——要么失效要么反转",
            }),
            tpl("ta.sr", "支撑变阻力", "支撑变阻力的第一根收盘：角色已经换，别再用旧名字。", {
              id: "ext_role_flip",
              category: "极端",
              stance: "bear",
              analogy: "第一根收盘换角色——别叫旧名",
            }),
            tpl("ta.sr", "多周期位叠加", "多条周期的位叠在一起：这里才配写成「关键」。", {
              id: "ext_multi_tf_level",
              category: "极端",
              analogy: "多周期位叠在一起——才配叫关键",
            }),
            tpl("ta.sr", "前高变支撑", "回踩到前高变支撑：趋势健康的常规动作。", {
              id: "common_res_to_sup",
              category: "常见",
              stance: "bull",
              analogy: "前高变支撑——趋势常规动作",
            }),
            tpl("ta.sr", "阻力区长影", "阻力区上下影很多、实体很小：在消耗，不是已经突破。", {
              id: "common_res_wicks",
              category: "常见",
              analogy: "长影小实体——在消耗不是突破",
            }),
            tpl("ta.sr", "位对量没有", "位对了但量没有：观察，不升级。", {
              id: "common_level_no_vol",
              category: "常见",
              analogy: "位对了量没有——观察不升级",
            }),
            tpl("ta.sr", "收盘才算", "收盘站上/跌破才算，盘中刺穿更常失败。", {
              id: "likely_close_matters",
              category: "大概率",
              analogy: "收盘才算——刺穿常失败",
            }),
            tpl("ta.sr", "第二次更易过", "同一位第二次测试比第一次更容易过。", {
              id: "likely_second_test",
              category: "大概率",
              analogy: "第二次测试——比第一次更易过",
            }),
            tpl("ta.sr", "日线管 4h", "日线位管 4h，4h 位管不了日线。", {
              id: "likely_daily_over_4h",
              category: "大概率",
              analogy: "大周期位管小周期——反过来不行",
            }),
            tpl("ta.sr", "站上阻力回踩稳", "收盘站上阻力，回踩不破该位。", {
              id: "bull_break_hold",
              category: "看涨",
              stance: "bull",
              analogy: "站上阻力、回踩稳——位有效",
            }),
            tpl("ta.sr", "支撑三次守住", "支撑三次守住且低点抬高。", {
              id: "bull_sup_three_hold",
              category: "看涨",
              stance: "bull",
              analogy: "三次守住、低点抬——支撑有效",
            }),
            tpl("ta.sr", "阻力三次盖帽", "阻力三次盖帽且高点降低。", {
              id: "bear_res_three_cap",
              category: "看跌",
              stance: "bear",
              analogy: "三次盖帽、高点降——阻力有效",
            }),
            tpl("ta.sr", "支撑跌破回失", "支撑收盘跌破，反弹不过回失位。", {
              id: "bear_sup_break",
              category: "看跌",
              stance: "bear",
              analogy: "支撑破、反抽不过——变阻力",
            }),
          ],
        }),
        topic({
          id: "ta.volume",
          categoryId: "ta",
          name: "量价 / 订单流",
          importance: 3,
          meaning:
            "成交量、CVD、主动买卖、大单、是否有人在关键位接。无量突破和新高压量滞涨，比形态名字重要。",
          impactSummary:
            "无量新高要打折；CVD 与价格背离只升级观察，要等结构确认。",
          relatedThemes: [
            "ta.structure",
            "ta.sr",
            "structure.liquidity",
            "structure.etf_flow",
            "structure.exchange_flow",
          ],
          talkingPoints: [
            "无量新高要打折",
            "下跌放量、反弹缩量，还是跌势",
            "CVD 与价格背离要等结构确认，单独不交易",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("关键结构 / 趋势", "放量突破才升级结构", "当根/当日"),
            impactOn("现货 ETF 流入", "现货机构买应能在 CVD 上见到", "1 日"),
            impactOn("流动性 / 深度", "有量无深度仍会插针", "即时"),
            impactOn("Meme / 文化币", "量能只集中在一条梗，不是板块", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "突破放量、回踩缩量、CVD 与价格同向",
              then: "有人用真金认方向",
              coins: ["BTC"],
              stance: "bull",
              template:
                "量在认这个方向。回踩缩量是健康的。失效看下一根用放量阴线吞掉突破。",
              invalidation: "突破后量能立刻干涸并跌回",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "新高压量滞涨，或阴线放量阳线缩量",
              then: "供给占优",
              coins: ["BTC"],
              stance: "bear",
              template:
                "高位的量是出货不是人气。先等量价重新同向。",
              invalidation: "整理后再次放量收过前高",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "价格新高、CVD 走平或走弱",
              then: "背离预警，未确认",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "订单流和 K 线在吵架。背离只升级观察，不单独开方向。等结构破或量能跟上。",
              invalidation: "结构与 CVD 重新同向",
            }),
          ],
          templates: [
            tpl("ta.volume", "天量小实体", "{品种}天量小实体：这里在换手，先当战场。", {
              id: "ext_huge_vol_doji",
              category: "极端",
              analogy: "天量小实体——战场不是起点",
            }),
            tpl("ta.volume", "无量长针", "无量长针：流动性事件，不当起点。", {
              id: "ext_low_vol_wick",
              category: "极端",
              analogy: "无量长针——流动性事件",
            }),
            tpl("ta.volume", "主动买卖价停", "主动买/卖一边倒，价格却停：对手盘在吸收。", {
              id: "ext_absorption",
              category: "极端",
              stance: "mixed",
              analogy: "一边倒但价不动——有人在吸收",
            }),
            tpl("ta.volume", "小量大阳阴", "小量大阳/大阴：这段阻力小，是推进不是高潮。", {
              id: "common_small_vol_move",
              category: "常见",
              stance: "bull",
              analogy: "小量大阳——阻力小，是推进",
            }),
            tpl("ta.volume", "价涨量缩", "价涨量缩：动能在减，先降预期。", {
              id: "common_price_up_vol_down",
              category: "常见",
              stance: "bear",
              analogy: "价涨量缩——动能减，降预期",
            }),
            tpl("ta.volume", "量平价横", "量在、价横：换手，不是选边完成。", {
              id: "common_vol_flat_price",
              category: "常见",
              analogy: "有量无价——换手不是选边",
            }),
            tpl("ta.volume", "放量突破缩量回踩", "放量突破后缩量回踩，延续概率大于继续放量狂拉。", {
              id: "likely_break_pullback",
              category: "大概率",
              stance: "bull",
              analogy: "放量突破、缩量回踩——延续更常见",
            }),
            tpl("ta.volume", "背离等结构", "量价背离要等结构确认，单独不够反转。", {
              id: "likely_div_need_structure",
              category: "大概率",
              analogy: "量价背离——要等结构，不单反",
            }),
            tpl("ta.volume", "美盘量更真", "美盘放量比亚盘放量更像真换手。", {
              id: "likely_us_session_vol",
              category: "大概率",
              analogy: "美盘放量——比亚盘更像真换手",
            }),
            tpl("ta.volume", "跌放后缩量更高低", "下跌放量后出现缩量更高低点。", {
              id: "bull_vol_pullback_hl",
              category: "看涨",
              stance: "bull",
              analogy: "跌放后缩量更高低——有人在接",
            }),
            tpl("ta.volume", "突破放回踩缩", "突破放量、回踩缩量、深度还在。", {
              id: "bull_break_retest",
              category: "看涨",
              stance: "bull",
              analogy: "突破放、回踩缩——健康结构",
            }),
            tpl("ta.volume", "上涨放量停滞", "上涨放量停滞、上影增多。", {
              id: "bear_vol_stall",
              category: "看跌",
              stance: "bear",
              analogy: "涨时量滞、上影多——供给在出",
            }),
            tpl("ta.volume", "下跌放量低点移", "下跌放量且低点下移：这是推进，不是洗盘默认项。", {
              id: "bear_down_vol_push",
              category: "看跌",
              stance: "bear",
              analogy: "跌放量、低点移——是推进不是洗盘",
            }),
          ],
        }),
        topic({
          id: "ta.candlestick",
          categoryId: "ta",
          name: "K 线形态",
          importance: 3,
          meaning:
            "单根或组合 K 线（射击之星、吞没、锤子、晨星、黄昏之星）。只在关键位 + 放量时有用，单独出现是噪音。",
          impactSummary:
            "形态必须长在关键位上；射击之星在前高才叫供给，半山腰的上影不是见顶。",
          relatedThemes: [
            "ta.sr",
            "ta.structure",
            "ta.volume",
            "ta.funding_extreme",
          ],
          talkingPoints: [
            "形态没有位置，等于没有形态",
            "射击之星在前高才叫供给，在半山腰叫上影",
            "一根针不改日线结构",
            "常用：射击之星、看涨/看跌吞没、锤子、倒锤、晨星、黄昏之星、刺透、乌云盖顶",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("阻力", "射击之星/看跌吞没在阻力处加重", "当根–次日"),
            impactOn("支撑", "锤子/看涨吞没在支撑处加重", "当根–次日"),
            impactOn("关键结构 / 趋势", "只有收盘确认才升级", "收盘"),
            impactOn("内容", "形态适合配图，结论仍要失效位", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "关键阻力出现射击之星或看跌吞没，且放量、费率不低",
              then: "短线供给信号",
              coins: ["BTC"],
              stance: "bear",
              template:
                "上影发生在别人都能看见的阻力上。先减追多，等收盘是否确认。半山腰的上影不要写成见顶。",
              invalidation: "次日收过星线高点",
            }),
            scenario("bad", {
              name: "坏情况（误用）",
              if: "无量、非关键位、逆大周期硬解形态",
              then: "假信号",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "形态教材不能对抗趋势。4 小时射击之星打不败日线涨势。",
              invalidation: "大周期也同步出反转结构",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "形态看空、ETF/结构仍多",
              then: "K 线是节奏，资金是方向",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "星线管你今晚要不要追，ETF 管你这周还在不在。两套周期拆开写。",
              invalidation: "资金面也转",
            }),
          ],
          templates: [
            tpl("ta.candlestick", "关键位吞没长针", "{品种}关键位上的吞没 / 长针：事件级，仍要等下一根确认。", {
              id: "ext_key_pattern",
              category: "极端",
              stance: "mixed",
              analogy: "关键位大形态——事件级，等确认",
            }),
            tpl("ta.candlestick", "连续上下影", "连续上下影：波动在，方向不在。", {
              id: "ext_alternating_wicks",
              category: "极端",
              analogy: "上下影连出——有波动无方向",
            }),
            tpl("ta.candlestick", "突破收成十字", "突破 K 收成十字：形态自己否定突破。", {
              id: "ext_doji_break",
              category: "极端",
              stance: "bear",
              analogy: "突破变十字——形态否定突破",
            }),
            tpl("ta.candlestick", "趋势中锤子", "趋势中的锤子 / 倒锤：先当暂停，不当反转。", {
              id: "common_hammer_trend",
              category: "常见",
              analogy: "趋势里的锤子——暂停不是反转",
            }),
            tpl("ta.candlestick", "包线在边缘", "包线出现在区间边缘，比出现在区间中更有用。", {
              id: "common_engulf_edge",
              category: "常见",
              analogy: "包线在边缘——比中间有用",
            }),
            tpl("ta.candlestick", "形态有效期", "单根形态的有效期就是后面 1–3 根。", {
              id: "common_pattern_ttl",
              category: "常见",
              analogy: "形态只管后面 1–3 根",
            }),
            tpl("ta.candlestick", "无位置近随机", "没有位置的形态，胜率接近随机。", {
              id: "likely_no_location",
              category: "大概率",
              analogy: "没位置的形态——接近随机",
            }),
            tpl("ta.candlestick", "确认根同向", "确认根与信号根同向，才升级；反向就作废。", {
              id: "likely_confirm_bar",
              category: "大概率",
              analogy: "确认根同向才升级——反向作废",
            }),
            tpl("ta.candlestick", "日线管得更长", "日线形态管得比 15m 形态长，但信号更少。", {
              id: "likely_daily_longer",
              category: "大概率",
              analogy: "日线形态管得长——信号也少",
            }),
            tpl("ta.candlestick", "支撑看涨吞没", "支撑上的看涨吞没 + 下一根不破低点。", {
              id: "bull_bullish_engulf",
              category: "看涨",
              stance: "bull",
              analogy: "支撑吞没 + 不破低——有效",
            }),
            tpl("ta.candlestick", "下跌末端长下影", "下跌末端长下影，且 OI / 费率不再恶化。", {
              id: "bull_long_lower_wick",
              category: "看涨",
              stance: "bull",
              analogy: "末端长下影 + 仓位不恶化——反弹候选",
            }),
            tpl("ta.candlestick", "阻力看跌吞没", "阻力上的看跌吞没 + 下一根不破高点。", {
              id: "bear_bearish_engulf",
              category: "看跌",
              stance: "bear",
              analogy: "阻力吞没 + 不破高——有效",
            }),
            tpl("ta.candlestick", "上涨末端长上影", "上涨末端长上影，量在、结构高点降低。", {
              id: "bear_long_upper_wick",
              category: "看跌",
              stance: "bear",
              analogy: "末端长上影 + 高点降——供给信号",
            }),
          ],
        }),
        topic({
          id: "ta.divergence",
          categoryId: "ta",
          name: "背离",
          importance: 3,
          meaning:
            "价格新高/新低，指标或订单流不跟上：RSI、MACD、CVD。背离是预警，不是开仓指令，要等结构确认。",
          impactSummary:
            "背离是预警，破位才是信号；CVD 背离比 RSI 更接近真钱。",
          relatedThemes: [
            "ta.volume",
            "ta.structure",
            "onchain.mvrv",
            "ta.funding_extreme",
          ],
          talkingPoints: [
            "背离可以持续很久",
            "看涨背离出现在跌势里才有意义",
            "CVD 背离比 RSI 更接近真钱，仍要等破位",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("关键结构 / 趋势", "背离 + 破结构才算反转", "确认时"),
            impactOn("内容", "适合「注意」而不是「反手」", "同步"),
            impactOn("资金费极端", "顶背离叠极正费率，权重升", "同步"),
            impactOn("Meme / 文化币", "山寨背离更多是流动性差", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "底背离出现在支撑 + 结构不再创新低",
              then: "反弹概率升",
              coins: ["BTC"],
              stance: "bull",
              template:
                "指标不认这个新低。等收盘不再破，再把背离写成反弹，不写成牛转。",
              invalidation: "再创新低且指标跟上",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "顶背离出现在阻力 + 费率极正",
              then: "追高风险",
              coins: ["BTC"],
              stance: "bear",
              template:
                "价格在创新高，力气没有。先当减速带。失效看指标创新高把背离解除。",
              invalidation: "指标与价格重新同向新高",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "RSI 背离、CVD 不背离（或相反）",
              then: "振荡指标和真金在打架",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "两个背离不是一个东西。订单流不背，就不要用 RSI 反手。",
              invalidation: "两者同向",
            }),
          ],
          templates: [
            tpl("ta.divergence", "多层背离", "{品种}价格新高、动量/OI/费率全面落后：多层背离。", {
              id: "ext_multi_div",
              category: "极端",
              stance: "bear",
              analogy: "价新高、指标全落后——多层背离",
            }),
            tpl("ta.divergence", "背离后假突破", "背离后假突破再回来：这是背离兑现，不是洗盘完毕。", {
              id: "ext_div_fake_break",
              category: "极端",
              stance: "bear",
              analogy: "背离后假突破回来——背离在兑现",
            }),
            tpl("ta.divergence", "日线背离 15m 新高", "日线背离 vs 15m 新高：先写分歧，不写「顶部已定」。", {
              id: "ext_tf_div_conflict",
              category: "极端",
              analogy: "大周期背离、小周期新高——写分歧",
            }),
            tpl("ta.divergence", "RSI 背离不够卖", "RSI / MACD 背离在趋势中经常出现，单独不够卖。", {
              id: "common_rsi_not_enough",
              category: "常见",
              analogy: "趋势里 RSI 背离——单独不够卖",
            }),
            tpl("ta.divergence", "价 OI 背离更真", "价格与 OI 背离，比价格与 RSI 背离更接近仓位事实。", {
              id: "common_price_oi_div",
              category: "常见",
              analogy: "价 OI 背离——比 RSI 更接近仓位",
            }),
            tpl("ta.divergence", "区间里背离", "背离出现在区间里：噪声。", {
              id: "common_range_div",
              category: "常见",
              analogy: "区间里的背离——当噪声",
            }),
            tpl("ta.divergence", "背离加破位", "背离 + 结构破位，才像反转；只有背离更像减速。", {
              id: "likely_div_break",
              category: "大概率",
              analogy: "背离 + 破位才像反转——只有背离是减速",
            }),
            tpl("ta.divergence", "等更高低确认", "底背离要等更高低点，顶背离要等更低高点。", {
              id: "likely_wait_structure",
              category: "大概率",
              analogy: "底背离等更高低——顶背离等更低高",
            }),
            tpl("ta.divergence", "背离领先节奏", "指标背离领先 1 段常见，领先 3 段还不破位就失效。", {
              id: "likely_div_lead",
              category: "大概率",
              analogy: "领先一段正常——三段不破位就失效",
            }),
            tpl("ta.divergence", "下跌背离低点抬", "下跌背离 + 低点抬高 + 费率从极负收窄。", {
              id: "bull_bull_div",
              category: "看涨",
              stance: "bull",
              analogy: "底背离 + 低点抬——反弹候选",
            }),
            tpl("ta.divergence", "失效再创新低", "失效：背离还在但价格再创新低。", {
              id: "bull_div_fail",
              category: "看涨",
              stance: "bear",
              analogy: "背离还在价再新低——失效",
            }),
            tpl("ta.divergence", "上涨背离高点降", "上涨背离 + 高点降低 + 费率极正。", {
              id: "bear_bear_div",
              category: "看跌",
              stance: "bear",
              analogy: "顶背离 + 高点降——减速信号",
            }),
            tpl("ta.divergence", "失效再创新高", "失效：背离还在但价格再创新高且 OI 跟上。", {
              id: "bear_div_fail",
              category: "看跌",
              stance: "bull",
              analogy: "背离还在但价 OI 齐新高——失效",
            }),
          ],
        }),
        topic({
          id: "ta.oi",
          categoryId: "ta",
          name: "OI / 持仓量",
          importance: 4,
          meaning:
            "未平仓合约变化。价涨 OI 增 = 新开多；价涨 OI 降 = 空头回补；价跌 OI 增 = 新开空。比单独看资金费更接近「有没有新杠杆」。",
          impactSummary:
            "价和 OI 要一起读；资金费/OI（市场结构）管拥挤诊断，这里管价与持仓同向/背离。",
          relatedThemes: [
            "structure.funding",
            "ta.funding_extreme",
            "ta.liquidation",
            "structure.options",
          ],
          talkingPoints: [
            "先写 OI 增减，再写多空",
            "涨而 OI 降，是挤空不是新牛",
            "OI 新高不破价格，两边都在加，波动要来",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("爆仓 / 清算 cascade", "高 OI + 薄深度 = cascade 燃料", "即时"),
            impactOn("资金费 / OI", "同向极端才拥挤（那边管费率分位诊断）", "同步"),
            impactOn("关键结构 / 趋势", "顺势 OI 增更健康", "数日"),
            impactOn("期权到期 / Max Pain", "到期后 OI 掉是正常卸墙", "到期日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "趋势方向上价格与 OI 同增，费率温和",
              then: "真加仓",
              coins: ["BTC"],
              stance: "bull",
              template:
                "有人在用新杠杆认这个方向。回调先看成加仓。失效看 OI 还在升而价格不跟。",
              invalidation: "OI 新高、价格回吐",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "价格滞涨/滞跌，OI 却新高",
              then: "对赌过密",
              coins: ["BTC"],
              stance: "bear",
              template:
                "仓位在堆，价格不走。下一根容易两边打。先等一次降 OI。",
              invalidation: "价格选择方向且 OI 跟随",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "现货强、OI 降",
              then: "现货在买、杠杆在撤",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "衍生品在离场，现货还在。这种涨更干净，也更慢。不要用资金费去否定它。",
              invalidation: "现货转弱且 OI 重新堆上",
            }),
          ],
          templates: [
            tpl("ta.oi", "OI 新高价平", "{品种}OI 新高、价格走平：对峙加仓，炸药在堆。", {
              id: "ext_oi_high_flat",
              category: "极端",
              stance: "mixed",
              analogy: "OI 新高价不走——对峙加仓",
            }),
            tpl("ta.oi", "急涨急跌 OI 暴降", "急涨急跌里 OI 暴降：这是平仓推动，不是新趋势第一天。", {
              id: "ext_oi_crash",
              category: "极端",
              analogy: "急涨急跌 OI 暴降——平仓推动",
            }),
            tpl("ta.oi", "OI 数据缺失", "OI 数据缺失时，不要用持仓叙事硬写。", {
              id: "ext_oi_missing",
              category: "极端",
              analogy: "没 OI 数据——别硬写持仓故事",
            }),
            tpl("ta.oi", "价涨 OI 升", "价涨 OI 升：趋势单在加。", {
              id: "common_up_oi_up",
              category: "常见",
              stance: "bull",
              analogy: "价涨 OI 升——趋势在加",
            }),
            tpl("ta.oi", "价涨 OI 降", "价涨 OI 降：空头回补或多头撤。", {
              id: "common_up_oi_down",
              category: "常见",
              analogy: "价涨 OI 降——回补或撤离",
            }),
            tpl("ta.oi", "价横 OI 变", "价横 OI 升：两边加仓；价横 OI 降：在离场。", {
              id: "common_flat_oi",
              category: "常见",
              analogy: "价横 OI 升减——加仓或离场",
            }),
            tpl("ta.oi", "价 OI 齐升未极端", "价和 OI 一起新高、费率未极端：延续 > 反转。", {
              id: "likely_trend_continue",
              category: "大概率",
              stance: "bull",
              analogy: "价 OI 齐升费不烫——延续 > 反转",
            }),
            tpl("ta.oi", "价新高 OI 不新高", "价新高 OI 不新高：冲高回落 > 第二段主升。", {
              id: "likely_price_high_oi_not",
              category: "大概率",
              stance: "bear",
              analogy: "价新高 OI 不跟——冲高回落更常见",
            }),
            tpl("ta.oi", "清算后 OI 下台阶", "清算后 OI 下台阶：新区间 > 立刻反转。", {
              id: "likely_post_liq_oi",
              category: "大概率",
              analogy: "清算后 OI 下台阶——新区间不是立刻反",
            }),
            tpl("ta.oi", "回踩 OI 降不破低", "回踩 OI 降、价格不破前低：清洗。", {
              id: "bull_pullback_wash",
              category: "看涨",
              stance: "bull",
              analogy: "回踩 OI 降、低不破——清洗",
            }),
            tpl("ta.oi", "突破 OI 跟上", "突破时 OI 跟上来：有人用新仓确认。", {
              id: "bull_break_oi_up",
              category: "看涨",
              stance: "bull",
              analogy: "突破 OI 跟——新仓在确认",
            }),
            tpl("ta.oi", "涨 OI 不跟跌 OI 加", "上涨 OI 不跟、下跌 OI 反加：空头在投票。", {
              id: "bear_oi_vote_down",
              category: "看跌",
              stance: "bear",
              analogy: "涨不加、跌反加——空在投票",
            }),
            tpl("ta.oi", "高位 OI 堆价回吐", "高位 OI 还在堆、价格回吐：拥挤变趋势那一拍。", {
              id: "bear_crowd_giveback",
              category: "看跌",
              stance: "bear",
              analogy: "高位 OI 堆、价回吐——拥挤变趋势",
            }),
          ],
        }),
        topic({
          id: "ta.wyckoff",
          categoryId: "ta",
          name: "威科夫 / 筹码过程",
          importance: 3,
          meaning:
            "吸筹、拉升、派发、下跌；弹簧、上涨测试、SOS/SOW。本质是用区间和量价讲主力过程，不要玄学化成庄家故事。",
          impactSummary:
            "先标箱子再谈阶段；小币上的弹簧默认是流动性事故，不是主力吸筹。",
          relatedThemes: [
            "ta.structure",
            "ta.volume",
            "ta.sr",
            "onchain.exchange_balance",
            "structure.etf_flow",
          ],
          talkingPoints: [
            "先标区间上下沿，再猜阶段",
            "弹簧是假跌破后收回，不是随便一根针",
            "没有量价，威科夫只是事后复盘",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("关键结构 / 趋势", "阶段判断服务趋势定义", "数日–数周"),
            impactOn("现货 ETF 流入", "机构吸筹可当成现代版 accumulation", "数日"),
            impactOn("内容", "适合中线复盘，不适合 5 分钟喊单", "同步"),
            impactOn("山寨季 vs 比特币季", "流动性差时「弹簧」经常是真跌破", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况（吸筹后离开）",
              if: "长区间、下沿假跌破收回、放量上破并回踩站住",
              then: "过程更像 accumulation → markup",
              coins: ["BTC"],
              stance: "bull",
              template:
                "区间下沿测完了，上破才算离开。没放量离开之前，只是箱子。",
              invalidation: "再次收进区间下半",
            }),
            scenario("bad", {
              name: "坏情况（派发）",
              if: "高位区间、上沿假突破回落、放量跌破",
              then: "distribution → markdown",
              coins: ["BTC"],
              stance: "bear",
              template:
                "上面接不住了。把假突破写成派发，不写成洗盘。",
              invalidation: "跌破后迅速收回并创新高",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "形态像弹簧，但 OI 暴增或山寨深度极差",
              then: "可能是清算针，不是主力吸筹",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "先排除爆仓和插针，再写威科夫。小币上的弹簧默认是流动性事故。",
              invalidation: "收回后量价健康且现货在买",
            }),
          ],
          templates: [
            tpl("ta.wyckoff", "高位天量宽幅", "{品种}高位宽幅 + 天量：更像派发高潮，不像健康主升。", {
              id: "ext_distribution_climax",
              category: "极端",
              stance: "bear",
              analogy: "高位天量宽幅——派发高潮不是主升",
            }),
            tpl("ta.wyckoff", "弹簧后放量离开", "低位弹簧后立刻放量离开：吸筹结束的候选，仍要等更高低点。", {
              id: "ext_spring_leave",
              category: "极端",
              stance: "bull",
              analogy: "弹簧后放量走——吸筹候选，等更高低",
            }),
            tpl("ta.wyckoff", "上冲回落", "上冲回落（upthrust）扫过前高再收回：典型诱多。", {
              id: "ext_upthrust",
              category: "极端",
              stance: "bear",
              analogy: "扫高再收回——典型 upthrust 诱多",
            }),
            tpl("ta.wyckoff", "横盘缩量", "横盘缩量：在换筹码，阶段未完成前不改趋势名。", {
              id: "common_range_low_vol",
              category: "常见",
              analogy: "横盘缩量——换筹码，阶段未完",
            }),
            tpl("ta.wyckoff", "拉升中回撤缩量", "拉升中的小回撤缩量：强势回调。", {
              id: "common_markup_pullback",
              category: "常见",
              stance: "bull",
              analogy: "拉升中缩量回撤——强势回调",
            }),
            tpl("ta.wyckoff", "放量打出又收回", "同样的区间，放量打出又收回：还在测试，不是已经选边。", {
              id: "common_test_not_break",
              category: "常见",
              analogy: "放量打出收回——还在测试",
            }),
            tpl("ta.wyckoff", "吸筹区第一次突破", "吸筹区第一次向上突破假的多；第二次放量离开才像进入标记上涨。", {
              id: "likely_acc_first_fake",
              category: "大概率",
              stance: "bull",
              analogy: "吸筹区第一次突破常假——第二次才像 markup",
            }),
            tpl("ta.wyckoff", "派发区第一次跌破", "派发区第一次向下跌破也常假；收回失败才像进入标记下跌。", {
              id: "likely_dist_first_fake",
              category: "大概率",
              stance: "bear",
              analogy: "派发区第一次跌破常假——收回失败才 markdown",
            }),
            tpl("ta.wyckoff", "努力大结果小在边缘", "努力大结果小，出现在区间边缘，比出现在区间中更有阶段意义。", {
              id: "likely_effort_result_edge",
              category: "大概率",
              analogy: "边缘处努力大结果小——阶段信号更强",
            }),
            tpl("ta.wyckoff", "弹簧站回", "弹簧（假跌破）+ 缩量回踩 + 放量站回。", {
              id: "bull_spring_back",
              category: "看涨",
              stance: "bull",
              analogy: "弹簧 + 缩量回踩 + 放量站回——吸筹完成候选",
            }),
            tpl("ta.wyckoff", "低点抬高供给减", "低点抬高、供给测试量小于前一次砸盘。", {
              id: "bull_higher_low_supply",
              category: "看涨",
              stance: "bull",
              analogy: "低点抬、砸盘量减——供给在减",
            }),
            tpl("ta.wyckoff", "上冲回落破区间", "上冲回落 + 反弹量弱 + 跌破区间下沿。", {
              id: "bear_upthrust_break",
              category: "看跌",
              stance: "bear",
              analogy: "upthrust + 量弱 + 破下沿——派发",
            }),
            tpl("ta.wyckoff", "高点降低需求减", "高点降低、需求测试量小于前一次拉升。", {
              id: "bear_lower_high_demand",
              category: "看跌",
              stance: "bear",
              analogy: "高点降、拉升量减——需求在减",
            }),
          ],
        }),
      ],
    },
    {
      id: "onchain",
      name: "链上分析",
      desc: "余额、鲸鱼、估值指标与 stable 供应",
      topics: [
        topic({
          id: "onchain.exchange_balance",
          categoryId: "onchain",
          name: "交易所余额",
          importance: 4,
          meaning:
            "头部 CEX 上的 BTC/ETH 存量。余额降 = 币离开可出售库存；余额升 = 潜在卖压增加。看多日趋势，单日脉冲经常是搬仓。",
          impactSummary:
            "存量是慢变量；交易所净流入写流量，这里写库存。ETF 是场外库存，CEX 余额要分开看。",
          relatedThemes: [
            "structure.exchange_flow",
            "structure.etf_flow",
            "onchain.stable_supply",
            "onchain.whale",
            "structure.liquidity",
          ],
          talkingPoints: [
            "存量下降是慢变量，解释不了下一根 15 分钟",
            "余额升 + 价格涨，要问是不是充去卖",
            "ETF 是场外库存，CEX 余额要分开看",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("现货抛压", "余额连升抬砸盘弹性", "数日"),
            impactOn("现货 ETF 流入", "ETF 吸筹常伴随 CEX 余额降", "1–5 日"),
            impactOn("稳定币供应", "币进所、稳定币出所更差", "同步"),
            impactOn("内容", "余额创新低适合写供给紧缩，不适合写当日涨停", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "BTC 交易所余额多日下降，价格不破结构",
              then: "可出售库存在收缩",
              coins: ["BTC"],
              stance: "bull",
              template:
                "卖压库存在变薄。这是中线句子，不是今天就拉的理由。失效看余额重新走高或 ETF 转出。",
              invalidation: "前三大所余额 7 日转升",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "余额连升且大额充币进所",
              then: "供给回到盘口",
              coins: ["BTC"],
              stance: "bear",
              template:
                "币在回交易所。先当潜在卖压，等价格接不接得住。不要写成巨鲸看涨。",
              invalidation: "升完不卖、价格新高且 ETF 仍进",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "总余额降，但单所大增",
              then: "搬仓概率高",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "先排除搬砖。单所脉冲不写供需反转。",
              invalidation: "多所同向连动 3 日以上",
            }),
          ],
          templates: [
            tpl(
              "onchain.exchange_balance",
              "存量是慢变量",
              "余额降是库存离开可出售池，看多日趋势。单日脉冲经常是搬仓，不是供需反转。",
              { stance: "mixed" }
            ),
            tpl(
              "onchain.exchange_balance",
              "好情况（库存下降）",
              "若交易所余额持续下降且没有同步大额进所，则盘口可售供给在收。写成库存下降，不写成必涨。失效：24h 内余额 V 型回升。",
              {
                id: "inventory_drain",
                category: "看涨",
                stance: "bull",
                analogy: "货架空了，不等于已经涨完",
              }
            ),
            tpl(
              "onchain.exchange_balance",
              "坏情况（库存堆积）",
              "若余额连升、且来自老地址唤醒，则抛压在进场。先观察有没有主动卖，不先写崩盘。失效：余额升但价格同步被大额买单接住。",
              {
                id: "inventory_build",
                category: "看跌",
                stance: "bear",
                analogy: "仓库在进货，门口还不知道谁买",
              }
            ),
            tpl(
              "onchain.exchange_balance",
              "分裂（余额动、流向乱）",
              "若余额波动大，但进出来自内部搬仓/跨所，则对价格中性。先拆「内部转」和「真进出」。失效：净进出方向连续 2 日同向。",
              {
                id: "internal_shuffle",
                category: "混合",
                stance: "mixed",
                analogy: "货在仓库之间搬家，不是出了门",
              }
            ),
          ],
        }),
        topic({
          id: "onchain.whale",
          categoryId: "onchain",
          name: "鲸鱼 / 大额转账",
          importance: 3,
          meaning:
            "大额转入转出、沉睡地址唤醒、矿工/托管钱包移动。适合当线索，必须交叉标签：到交易所、到冷钱包、到 ETF 相关地址，含义完全不同。",
          impactSummary:
            "先问去哪再问多空；一条转账不够写成「庄家进场」。",
          relatedThemes: [
            "onchain.exchange_balance",
            "onchain.flow",
            "structure.etf_flow",
            "people.kol",
            "people.treasury",
          ],
          talkingPoints: [
            "先问去哪，再问看多看空",
            "唤醒不等于出货，也可能是换托管",
            "一条转账不够写成「庄家进场」",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("交易所余额", "进所大额会很快反映到库存", "小时–1 日"),
            impactOn("流动性 / 深度", "薄流动性时大额更易打出针", "即时"),
            impactOn("KOL / 舆论", "链上截图本身会带情绪", "即时"),
            impactOn("现货 ETF 流入", "到已知托管地址偏中性偏多", "1 日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "大额出所有到冷钱包/托管，且不是分散到发射盘",
              then: "锁仓预期",
              coins: ["BTC"],
              stance: "bull",
              template:
                "大额在出所，不是进所。写成供给离开盘口，不写成神秘庄家。失效看出所后又转回热钱包。",
              invalidation: "24h 内原路返回交易所",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "沉睡币唤醒并进所",
              then: "长线持有人变现",
              coins: ["BTC"],
              stance: "bear",
              template:
                "老筹码醒了而且去了交易所。这是风险提示，等有没有砸盘，不要等叙事。",
              invalidation: "进所后多日未售、余额再降",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "大额在链上转、标签不明",
              then: "信息不足",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "没有标签就没有方向。截图可以发，结论必须写「未知」。",
              invalidation: "地址被标注为交易所或 ETF 托管",
            }),
          ],
          templates: [
            tpl(
              "onchain.whale",
              "先问去哪，再问多空",
              "到交易所、冷钱包、ETF 托管含义完全不同。一条转账不够写成庄家进场。",
              {
                id: "ask_destination_first",
                category: "混合",
                stance: "mixed",
                analogy: "先看车子开去哪，再猜司机想干什么",
              }
            ),
            tpl(
              "onchain.whale",
              "好情况（锁仓预期）",
              "若大额出所有到冷钱包/托管，且不是分散到发射盘，则锁仓预期。写成供给离开盘口，不写成神秘庄家。失效：24h 内原路返回交易所。",
              {
                id: "outflow_to_cold",
                category: "看涨",
                stance: "bull",
                analogy: "筹码离开盘口，不是庄家显灵",
              }
            ),
            tpl(
              "onchain.whale",
              "坏情况（长线变现）",
              "若沉睡币唤醒并进所，则长线持有人变现。这是风险提示，先看有没有砸盘，不要先写叙事。失效：进所后多日未售、余额再降。",
              {
                id: "dormant_to_exchange",
                category: "看跌",
                stance: "bear",
                analogy: "老筹码醒了，而且去了可以卖的地方",
              }
            ),
            tpl(
              "onchain.whale",
              "分裂（标签不明）",
              "若大额在链上转、标签不明，则信息不足。截图可以发，结论必须写「未知」。失效：地址被标注为交易所或 ETF 托管。",
              {
                id: "unlabeled_transfer",
                category: "混合",
                stance: "mixed",
                analogy: "没有门牌就没有方向",
              }
            ),
            tpl(
              "onchain.whale",
              "进所会改库存",
              "进所大额会很快反映到交易所余额；小时到 1 日内把「转账」改写成「可售库存变了」。",
              {
                id: "inflow_hits_inventory",
                category: "常见",
                analogy: "货先入库，再谈会不会上架",
              }
            ),
            tpl(
              "onchain.whale",
              "薄账本打针",
              "薄流动性时大额更易打出针。先写深度，再写转账；否则一根针会被写成趋势。",
              {
                id: "thin_book_wick",
                category: "极端",
                analogy: "小池塘里推一块石头",
              }
            ),
            tpl(
              "onchain.whale",
              "截图带情绪",
              "链上截图本身会带情绪，即时生效。图可以发，方向仍要等标签和后续是否进所。",
              {
                id: "screenshot_sentiment",
                category: "常见",
                analogy: "先传的是画面，不是结论",
              }
            ),
            tpl(
              "onchain.whale",
              "进已知托管偏中性",
              "到已知 ETF/托管地址偏中性偏多，按 1 日窗口写，不按分钟级买卖写。",
              {
                id: "to_known_custody",
                category: "大概率",
                analogy: "进保险箱，不是进菜市场",
              }
            ),
          ],
        }),
        topic({
          id: "onchain.mvrv",
          categoryId: "onchain",
          name: "MVRV / SOPR",
          importance: 3,
          meaning:
            "MVRV：市值相对实现市值，衡量整体浮盈浮亏。SOPR：花费输出是否盈利卖出。用来判断是否进入狂欢或恐慌，不是日内信号。",
          impactSummary:
            "周期指标不当日内扳机；适合中线稿，不适合快讯标题当涨跌理由。",
          relatedThemes: [
            "ta.structure",
            "structure.etf_flow",
            "narrative.btc_gold",
            "onchain.stable_supply",
          ],
          talkingPoints: [
            "MVRV 高不是立刻见顶，是利润丰厚",
            "SOPR 在 1 附近反复，是成本价攻防",
            "这两个指标不要和 5 分钟图混用",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("关键结构 / 趋势", "MVRV 过高，回撤更深", "数周"),
            impactOn("抛压", "SOPR 远大于 1 说明获利盘在兑现", "数日"),
            impactOn("底部", "SOPR 跌破 1 后回到 1 常是投降结束", "数日–数周"),
            impactOn("内容", "适合周期稿，不适合快讯标题当涨跌理由", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "SOPR 从小于 1 回到 1，MVRV 处在历史中低位",
              then: "亏损盘清理，中线环境改善",
              coins: ["BTC"],
              stance: "bull",
              template:
                "亏的人已经卖过一轮，指标在回到成本线。这是周期句子。失效看 SOPR 再次跌破 1 且结构坏掉。",
              invalidation: "结构破位 + SOPR 再塌",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "MVRV 处在历史高分位，SOPR 持续显著高于 1",
              then: "获利盘活跃",
              coins: ["BTC"],
              stance: "bear",
              template:
                "账上利润太厚，卖是理性的。可以有趋势，但不要写「没有抛压」。",
              invalidation: "高位横盘消化后 SOPR 收敛、ETF 仍进",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "价格新高、MVRV 不高（实现价格也在抬）",
              then: "成本上移，未必过热",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "新高但实现成本在跟。过热程度比看起来低。仍然要看结构，不看单一阈值。",
              invalidation: "MVRV 快速冲向过热区而 ETF 流出",
            }),
          ],
          templates: [
            tpl(
              "onchain.mvrv",
              "周期指标，不当日内扳机",
              "MVRV/SOPR 判断狂欢或恐慌，不是 5 分钟图信号。写周期稿，别写快讯扳机。",
              { stance: "mixed" }
            ),
            tpl(
              "onchain.mvrv",
              "好情况（获利回吐未失控）",
              "若价格涨、SOPR > 1 但未到极端分位，MVRV 未进过热带，则是健康兑现。回调可当成换手。失效：SOPR 冲高同时成交量空翻。",
              {
                id: "healthy_realize",
                category: "看涨",
                stance: "bull",
                analogy: "有人兑现，但队伍还没挤爆",
              }
            ),
            tpl(
              "onchain.mvrv",
              "坏情况（亏损实现加速）",
              "若 SOPR 持续 < 1 且仍在下降，则亏损盘在认输。写成抛压兑现，不写成抄底信号。失效：SOPR 回到 1 上方并站住。",
              {
                id: "loss_realize",
                category: "看跌",
                stance: "bear",
                analogy: "亏着也要走，价格先给路",
              }
            ),
            tpl(
              "onchain.mvrv",
              "分裂（估值与实现背离）",
              "若 MVRV 显示估值偏高但 SOPR 接近 1、兑现很温和，则方向不明。先写「估值贵、卖压还不凶」。失效：两者重新同向。",
              {
                id: "value_vs_realize",
                category: "混合",
                stance: "mixed",
                analogy: "账面对得上，出手还对不上",
              }
            ),
          ],
        }),
        topic({
          id: "onchain.stable_supply",
          categoryId: "onchain",
          name: "稳定币供应",
          importance: 4,
          meaning:
            "USDT/USDC 等总供应量、铸造/赎回。供应升 = 场外美元进场潜力；赎回 = 美元离场。这是加密自己的「流动性表」。",
          impactSummary:
            "加密美元水龙头；铸造不等于立刻买币，供应升 + BTC.D 降才更容易山寨扩散。",
          relatedThemes: [
            "structure.etf_flow",
            "macro.dxy",
            "structure.exchange_flow",
            "narrative.stablechain",
            "narrative.altseason",
          ],
          talkingPoints: [
            "稳定币市值降，山寨很难有真季节",
            "铸造不等于立刻买币，要看进没进交易所",
            "USDT 与 USDC 分流，有时是监管和渠道问题",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("总市值", "稳定币收缩，加密美元流动性紧", "数日–数周"),
            impactOn("山寨季 vs 比特币季", "供应升 + BTC.D 降才更容易扩散", "数周"),
            impactOn("DXY / 实际利率", "风险关、赎回增", "宏观周"),
            impactOn("交易所净流入", "稳定币进所偏买盘预备", "1 日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "净铸造持续，稳定币进所，BTC 结构未坏",
              then: "弹药在增加",
              coins: ["BTC"],
              stance: "bull",
              template:
                "场外美元在变多。下一步看它进不进盘口。只铸造不进所，力度要打折。",
              invalidation: "随后连续赎回或只停在链上理财",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "连续赎回、稳定币市值下降",
              then: "流动性在撤",
              coins: ["BTC"],
              stance: "bear",
              template:
                "加密美元在变少。这种时候写山寨季是逆流动性。先等供应止跌。",
              invalidation: "赎回停止且 ETF 转流入",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "USDT 铸、USDC 赎（或相反）",
              then: "渠道和监管偏好，不是总闸门一边倒",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "两家稳定币在换座位。先看合计净供应，再看是不是监管搬家。",
              invalidation: "合计供应明确单边走",
            }),
          ],
          templates: [
            tpl(
              "onchain.stable_supply",
              "加密美元的水龙头",
              "供应升是场外美元潜力，赎回是离场。铸造不等于立刻买币，要看进没进交易所。",
              { stance: "mixed", coins: ["USDC", "BTC"] }
            ),
            tpl(
              "onchain.stable_supply",
              "好情况（干火药增加）",
              "若稳定币供应上升且留在链上/交易所，则潜在买盘增加。写成弹药变多，不写成已经开火。失效：增发后迅速流出到链下/赎回。",
              {
                id: "dry_powder_up",
                category: "看涨",
                stance: "bull",
                analogy: "子弹入库，扳机还没扣",
              }
            ),
            tpl(
              "onchain.stable_supply",
              "坏情况（赎回抽流动性）",
              "若稳定币供应下降、交易所稳定币余额同步掉，则买盘弹药在撤。先写流动性收缩。失效：赎回同时现货持续吸筹。",
              {
                id: "stable_redeem",
                category: "看跌",
                stance: "bear",
                analogy: "现金先离场，风险资产后定价",
              }
            ),
            tpl(
              "onchain.stable_supply",
              "分裂（增发但不到盘口）",
              "若总供应升，但交易所稳定币余额不升，则钱可能在链上空转或进了理财。结论写「未到盘口」。失效：交易所稳定币余额随后跟上。",
              {
                id: "mint_not_on_book",
                category: "混合",
                stance: "mixed",
                analogy: "钱印出来了，还没走到柜台",
              }
            ),
          ],
        }),
        topic({
          id: "onchain.flow",
          categoryId: "onchain",
          name: "链上资金流 / 聪明钱",
          importance: 3,
          meaning:
            "被标记的基金、做市、高频、赢面地址的净买入、新钱包爆发、跨桥。用作跟随线索，样本偏差大，不能当圣杯。",
          impactSummary:
            "标签是线索不是订单；过度跟踪后易拥挤，模板里要降权。",
          relatedThemes: [
            "onchain.whale",
            "onchain.exchange_balance",
            "narrative.l1",
            "narrative.meme",
            "people.kol",
          ],
          talkingPoints: [
            "聪明钱标签是事后的",
            "他们可以提前布局，也可以当对手盘",
            "新地址爆发要区分真实用户和女巫",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("短线情绪", "标注地址集中买某票会带流量", "当日"),
            impactOn("L1 / 公链竞争", "多地址同时布局同一叙事", "数日"),
            impactOn("活动 / 空投", "新钱包密集往往是农", "活动期"),
            impactOn("反向", "过度跟踪后拥挤", "1–3 日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "多个独立标注地址在同一现货上吸，且与 ETF/结构同向",
              then: "可当加分项",
              coins: ["BTC"],
              stance: "bull",
              template:
                "链上标签和更大的钱同向，才有意义。单独一条聪明钱不够开方向。",
              invalidation: "他们开始对倒或转进所",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "聪明钱在出、散户在进，或全是新钱包刷量",
              then: "你可能是对手盘",
              coins: ["BTC"],
              stance: "bear",
              template:
                "标注地址在发货，热度在升温。这是内容预警，不是跟单信号。",
              invalidation: "出货结束、价格站稳、现货深度回补",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "聪明钱内部分裂，或只在衍生品对冲",
              then: "无法读方向",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "同名标签里有人买有人套。跟单会自我打架。回到结构和 ETF。",
              invalidation: "净方向连续 3 日一致",
            }),
          ],
          templates: [
            tpl(
              "onchain.flow",
              "标签是线索，不是订单",
              "聪明钱标签是事后的，样本偏差大。单独一条不够开方向，要和 ETF/结构交叉验证。",
              { stance: "mixed" }
            ),
            tpl(
              "onchain.flow",
              "好情况（聪明钱吸筹）",
              "若标记良好的长期地址在跌时净买入、且不进所，则更像吸筹。写成行为，不写成必涨口号。失效：同一批地址 24–48h 内倒手进所。",
              {
                id: "smart_accumulate",
                category: "看涨",
                stance: "bull",
                analogy: "会买的人在买，而且没去柜台",
              }
            ),
            tpl(
              "onchain.flow",
              "坏情况（聪明钱分发）",
              "若高胜率地址在涨时分批进所或转给做市，则更像分发。先写供给回流盘口。失效：进所后余额再降、并未出现主动卖。",
              {
                id: "smart_distribute",
                category: "看跌",
                stance: "bear",
                analogy: "会卖的人把货送回了市场",
              }
            ),
            tpl(
              "onchain.flow",
              "分裂（标签打架）",
              "若「聪明钱」标签互相矛盾，或地址刚被标记、样本太短，则信息不足。只发流向，不下方向。失效：多源标签收敛到同一行为。",
              {
                id: "label_conflict",
                category: "混合",
                stance: "mixed",
                analogy: "名头比流水响时，先信流水",
              }
            ),
          ],
        }),
      ],
    },
    {
      id: "security",
      name: "安全、攻击与风险事件",
      desc: "黑客、脱锚、停机与钓鱼",
      topics: [
        topic({
          id: "security.hack",
          categoryId: "security",
          name: "黑客 / 漏洞 exploit",
          meaning: "智能合约或跨链桥被攻击，影响协议 trust 与同业 risk-off。",
          relatedThemes: ["security.depeg", "narrative.l1"],
          talkingPoints: [
            "被盗金额与可追回比例",
            "是否波及其他协议 contagion",
            "写清用户应对（revoke approval 等）",
          ],
          defaultStance: "bear",
        }),
        topic({
          id: "security.depeg",
          categoryId: "security",
          name: "脱锚 / 稳定币风险",
          meaning: "稳定币偏离 1 USD，引发 DeFi 清算与恐慌传导。",
          relatedThemes: ["policy.stable", "security.withdraw"],
          talkingPoints: [
            "脱锚深度与持续时间",
            "储备透明度与赎回通道",
            "别把所有稳定币写成同一风险",
          ],
          defaultStance: "bear",
        }),
        topic({
          id: "security.withdraw",
          categoryId: "security",
          name: "停提 / 挤兑",
          meaning: "交易所或协议暂停存取款，流动性危机信号。",
          relatedThemes: ["exchange.outage", "security.depeg"],
          talkingPoints: [
            "停提原因：维护 vs 流动性",
            "链上 proof of reserve 是否及时",
            "历史类比要谨慎",
          ],
          defaultStance: "bear",
        }),
        topic({
          id: "security.phishing",
          categoryId: "security",
          name: "钓鱼 / 假空投",
          meaning: "社会工程与恶意授权，造成用户资产损失与信任损伤。",
          relatedThemes: ["exchange.airdrop", "people.kol"],
          talkingPoints: [
            "教用户验证合约而非 panic",
            "假站点与真站点差异",
            "事件规模与链无关时别夸大",
          ],
          defaultStance: "neutral",
        }),
        topic({
          id: "security.bridge",
          categoryId: "security",
          name: "跨链桥风险",
          meaning: "桥是历史最高被盗品类之一，安全模型决定上限。",
          relatedThemes: ["security.hack", "narrative.l1"],
          talkingPoints: [
            "信任假设：多签/乐观/零知识",
            "被盗后 TVL 迁移路径",
            "别推荐具体桥，写选择框架",
          ],
          defaultStance: "bear",
        }),
      ],
    },
    {
      id: "exchange",
      name: "交易所、产品与交易基础设施",
      desc: "上币、活动、费率与系统",
      topics: [
        topic({
          id: "exchange.listing",
          categoryId: "exchange",
          name: "上市 / 下架",
          importance: 4,
          meaning:
            "CEX 现货/合约上币、交易对下架、区域下架。上币是流量和流动性事件，下架是通道关闭。看哪家所、是否合约同步、有没有充提。",
          impactSummary:
            "上币是通道不是基本面；TGE/上所写开盘定价，这里写交易所流动性与合规通道。",
          relatedThemes: [
            "calendar.tge",
            "structure.liquidity",
            "narrative.privacy",
            "policy.sec",
            "narrative.l1",
          ],
          talkingPoints: [
            "一线所上币 ≠ 基本面，是通道",
            "只有合约、没有现货，更容易被当赌场",
            "下架公告日先出，叙事后死",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("短线价格", "上币前抢筹、上币后出货", "公告–上线"),
            impactOn("流动性 / 深度", "一线所上币后滑点下降", "1–3 日"),
            impactOn("L1 / 公链竞争", "同赛道轮流上币会分流", "当周"),
            impactOn("SEC / 执法", "区域下架利空隐私/未注册代币", "公告日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "一线所现货+充提同步，流通合理",
              then: "流动性升一档",
              coins: ["BTC"],
              stance: "bull",
              template:
                "通道开了，不等于价格该再翻倍。上线后看深度和谁在卖。失效看上线即破发行区间。",
              invalidation: "上线放量跌破活动价",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "下架、仅某地区不可交易、或上的是高 FDV 零收入盘",
              then: "通道在关或接盘在增加",
              coins: ["BTC"],
              stance: "bear",
              template:
                "下架是流动性事件。先找还能出的路，再写项目好不好。",
              invalidation: "其他一线所立刻接盘且深度不差",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "A 所上、B 所下",
              then: "监管分区，不是全球共识",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "同一张币两套通道。别把单一交易所政策写成行业终审判决。",
              invalidation: "多家头部同向行动",
            }),
          ],
          templates: [
            tpl(
              "exchange.listing",
              "上币是通道，下架是关门",
              "【公告日–上线日：填日期】一线所上币是通道不是基本面。失效：上线放量破区间或下架无接盘。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "exchange.airdrop",
          categoryId: "exchange",
          name: "活动 / 空投",
          importance: 4,
          meaning:
            "交易赛、入金奖、Launchpool、积分、锁仓包、手续费抵扣。目的是拉量和拉存款。奖励常是平台币或锁定包，不是现金。",
          impactSummary:
            "名额 ≠ 美元，锁定包 ≠ 到账；先折现再谈空投，查链接默认当钓鱼。",
          relatedThemes: [
            "calendar.tge",
            "exchange.fee",
            "narrative.perp_dex",
            "strategy.airdrop",
            "security.phishing",
          ],
          talkingPoints: [
            "先算有效年化和解锁条件，再谈划算",
            "刷量会扭曲资金费和深度",
            "查空投链接默认当钓鱼",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("平台币", "活动奖池往往来自平台币通胀", "活动期"),
            impactOn("成交量", "虚假繁荣，结束后量塌", "结束日"),
            impactOn("用户风险", "锁仓、高杠杆、假页面", "全程"),
            impactOn("定价", "活动币短线有买盘，结束即失", "结束前后"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "规则透明、奖励可验算、不强制高杠杆、官方入口唯一",
              then: "可当低成本获客/小额补贴",
              coins: ["BTC"],
              stance: "bull",
              template:
                "把奖励折成真实 USDT，再减解锁和手续费。算不过就当广告，不算空投神话。",
              invalidation: "中途改规则或奖池来自高通胀",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "锁仓包、随机名额、必须净入金、假空投满天飞",
              then: "用户当流动性",
              coins: ["BTC"],
              stance: "bear",
              template:
                "名额是彩票，锁仓是库存。不要把 5000 个名额写成 5000 美元。",
              invalidation: "官方可提现、无锁、概率公示",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "活动拉的是交易量，盘面当基本面在涨",
              then: "量价会骗人",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "K 线热度来自比赛。活动一停，量先消失。结论等停赛后 48 小时。",
              invalidation: "停赛后现货深度和 OI 仍在",
            }),
          ],
          templates: [
            tpl(
              "exchange.airdrop",
              "先折现，再谈空投",
              "【活动期：填起止日】名额≠美元，锁仓包≠到账。失效：停赛 48h 后量塌且无深度。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "exchange.fee",
          categoryId: "exchange",
          name: "费率 / VIP",
          importance: 3,
          meaning:
            "挂单吃单费、资金费折扣、VIP 阶梯、返佣。决定做市和高频成本，也会改变用户该去 CEX 还是 Perp DEX。",
          impactSummary:
            "费率活动是价格战不是产品升级；VIP 把散户和机构拆成两个市场。",
          relatedThemes: [
            "structure.funding",
            "narrative.perp_dex",
            "exchange.airdrop",
            "ta.funding_extreme",
          ],
          talkingPoints: [
            "费率活动是价格战，不是产品升级",
            "VIP 门槛会把散户和机构拆成两个市场",
            "平台币抵扣等于变相通胀",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("资金费 / OI", "减免会让拥挤更极端", "活动期"),
            impactOn("Perp DEX", "CEX 降费会暂时抽走链上量", "数日"),
            impactOn("平台币", "抵扣需求短线托价", "政策日"),
            impactOn("流动性 / 深度", "真降成本会留下做市商", "数日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "结构性降费（不是三天活动）且深度变好",
              then: "该所流动性份额升",
              coins: ["BTC"],
              stance: "bull",
              template:
                "真降成本会留下做市商。看深度，不看海报天数。",
              invalidation: "活动结束费回升、深度回去",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "只对刷量返佣，普通用户更贵",
              then: "盘口被机器占领",
              coins: ["BTC"],
              stance: "bear",
              template:
                "VIP 让市场更薄给普通人。降费新闻要写清对谁降。",
              invalidation: "全档位公开下降",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "现货降费、合约加费（或相反）",
              then: "产品线在搬家",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "他们在选自己想要的客户。现货和合约的费率要拆开写。",
              invalidation: "双边同步、长期有效",
            }),
          ],
          templates: [
            tpl(
              "exchange.fee",
              "看对谁降费",
              "【政策日：填日期】费率活动是价格战。失效：活动结束深度回到原样。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "exchange.outage",
          categoryId: "exchange",
          name: "停机 / 延迟",
          importance: 4,
          meaning:
            "撮合停、充提慢、API 挂、指数异常。危机里最重要的基础设施风险。停机时价格在别的所继续走，用户无法平仓。",
          impactSummary:
            "停机是定价事故；提现延迟比 K 线更重要，只在一个所交易等于集中风险。",
          relatedThemes: [
            "ta.liquidation",
            "structure.liquidity",
            "security.withdraw",
            "security.hack",
            "onchain.exchange_balance",
          ],
          talkingPoints: [
            "停机是定价事故，不只是技术事故",
            "提现延迟比 K 线更重要",
            "只在一个所交易，等于把风险集中",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("爆仓 / 清算 cascade", "无法平仓会放大损失", "即时"),
            impactOn("流动性 / 深度", "该所与他所价差拉大", "即时"),
            impactOn("停提 / 挤兑", "重复发生会迁移用户", "数日"),
            impactOn("平台币", "事故周通常承压", "当日–3 日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "短暂停、提现正常、事后复盘清楚",
              then: "事件过，不升格",
              coins: ["BTC"],
              stance: "bull",
              template:
                "分钟级故障和提现暂停不是一类新闻。先报充提是否通。",
              invalidation: "延迟扩大到提现",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "行情剧烈时停机，或充提双停",
              then: "信任和连环强平",
              coins: ["BTC"],
              stance: "bear",
              template:
                "该平的仓平不了。这是风险事件。把资金分散写进建议，不写「维护一会儿」。",
              invalidation: "提现恢复且有储备证明更新",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "网页卡、链上充值其实已到",
              then: "前端事故",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "先区分前端、撮合、链上。三类写法完全不同。",
              invalidation: "官方承认撮合停或提现排队",
            }),
          ],
          templates: [
            tpl(
              "exchange.outage",
              "先问能不能提现",
              "【事故日：填日期】停机时别所价格仍在走。失效：提现仍延迟或充提双停。",
              { stance: "bear" }
            ),
          ],
        }),
        topic({
          id: "exchange.product",
          categoryId: "exchange",
          name: "新产品 / 杠杆档位",
          importance: 3,
          meaning:
            "新合约、新杠杆倍数、跟单、理财、预测市场、代币化股票、法币通道。新产品能开叙事，也能开风险。",
          impactSummary:
            "更高杠杆是事故预告；代币化股票要看辖区和是否真有底层。",
          relatedThemes: [
            "narrative.perp_dex",
            "narrative.rwa",
            "policy.cftc",
            "ta.liquidation",
            "exchange.airdrop",
          ],
          talkingPoints: [
            "更高杠杆是事故预告，不是功能胜利",
            "代币化股票要看辖区和是否真有底层",
            "跟单把新手和网红绑在同一条强平线上",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("资金费 / OI", "新品种分流或创造新拥挤", "1–7 日"),
            impactOn("爆仓 / 清算 cascade", "档位上调提高 cascade", "上线后首周"),
            impactOn("SEC / 执法", "合规产品能带来新用户", "政策周"),
            impactOn("平台币", "新产品若能收手续费则中线加分", "数周"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "新产品有真实需求（法币、合规美股、低杠杆现货）且辖区清楚",
              then: "通道扩展",
              coins: ["BTC"],
              stance: "bull",
              template:
                "能进来的钱变多了，才是产品。杠杆加一档不算创新。",
              invalidation: "有牌无量，或很快被监管叫停",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "突然开放超高杠杆或跟单无风控",
              then: "下一轮 cascade 的燃料",
              coins: ["BTC"],
              stance: "bear",
              template:
                "档位是风险开关。写成事故概率，不写成利好清单。",
              invalidation: "默认杠杆下降、强平规则更严",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "产品叙事很强，但只在灰色辖区",
              then: "增长和关停风险并存",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "用户会来，监管也可能来。把上线辖区写进第一段。",
              invalidation: "持牌区正式上线",
            }),
          ],
          templates: [
            tpl(
              "exchange.product",
              "新产品先标辖区和杠杆",
              "【上线日：填日期】更高杠杆是事故预告。失效：首周出现大额 cascade 或监管叫停。",
              { stance: "mixed" }
            ),
          ],
        }),
      ],
    },
    {
      id: "people",
      name: "人物、机构与舆论",
      desc: "KOL、财库、监管者与机构",
      topics: [
        topic({
          id: "people.kol",
          categoryId: "people",
          name: "KOL / 舆论",
          meaning: "意见领袖表态与社区共识，对 meme 与 short-term flow 影响大。",
          relatedThemes: ["narrative.meme", "security.phishing"],
          talkingPoints: [
            "表态 ≠ 持仓，区分 marketing",
            "反向指标何时失效",
            "多 KOL 共振才写「舆论转向」",
          ],
          defaultStance: "mixed",
        }),
        topic({
          id: "people.treasury",
          categoryId: "people",
          name: "财库公司 / DAT",
          meaning: "上市公司/机构 BTC 财库策略，连接 TradFi 与 crypto 叙事。",
          relatedThemes: ["metastory.institutional", "narrative.btc_gold"],
          talkingPoints: [
            "增持公告 vs 实际链上",
            "融资成本与 dilution",
            "股价 vs BTC beta",
          ],
          defaultCoins: ["BTC", "MSTR"],
          defaultStance: "bull",
        }),
        topic({
          id: "people.regulator",
          categoryId: "people",
          name: "监管官员讲话",
          meaning: "Fed、SEC、Treasury 官员口径变化影响预期。",
          relatedThemes: ["policy.sec", "macro.fomc"],
          talkingPoints: [
            "鹰派/鸽派要引用原话",
            "非投票委员 vs 主席权重",
            "market reaction 与 wording 对比",
          ],
          defaultStance: "mixed",
        }),
        topic({
          id: "people.founder",
          categoryId: "people",
          name: "创始人 / 团队动态",
          meaning: "关键人物离职、回归、诉讼对项目 governance 与信心影响。",
          relatedThemes: ["fundamental.tokenomics", "policy.enforcement"],
          talkingPoints: [
            "人事变动 ≠ 技术路线图变化",
            "创始人卖币与 unlock 分开写",
            "社区治理能否补位",
          ],
          defaultStance: "mixed",
        }),
        topic({
          id: "people.institution",
          categoryId: "people",
          name: "机构声明 / 配置",
          meaning: "资管、家办、对冲基金的 crypto 配置变化。",
          relatedThemes: ["structure.etf_flow", "metastory.institutional"],
          talkingPoints: [
            "survey vs 实际配置",
            "配置上限与 mandate 约束",
            "季度 rebalancing 节奏",
          ],
          defaultCoins: ["BTC", "ETH"],
        }),
      ],
    },
    {
      id: "infra",
      name: "矿业、质押与基础设施层",
      desc: "算力、质押、审查与 L2",
      topics: [
        topic({
          id: "infra.hashrate",
          categoryId: "infra",
          name: "算力 / 矿工",
          meaning: "哈希率、难度与矿工卖压影响 BTC 供给侧叙事。",
          relatedThemes: ["calendar.halving", "BTC"],
          talkingPoints: [
            "哈希率新高 vs 价格背离",
            "矿工投降指标",
            "能源价格与矿机迭代",
          ],
          defaultCoins: ["BTC"],
        }),
        topic({
          id: "infra.staking",
          categoryId: "infra",
          name: "质押 / 退出队列",
          meaning: "PoS 链质押率、解锁队列与 LST 流动性。",
          relatedThemes: ["fundamental.tokenomics", "ETH"],
          talkingPoints: [
            "退出队列长度 = 潜在卖压时钟",
            "LST depeg 与 staking 利率",
            "restaking 叠加风险",
          ],
          defaultCoins: ["ETH"],
          defaultStance: "mixed",
        }),
        topic({
          id: "infra.censorship",
          categoryId: "infra",
          name: "审查 / MEV",
          meaning: "区块构建者审查与 MEV 提取，影响「中性基础设施」叙事。",
          relatedThemes: ["narrative.privacy", "infra.sequencer"],
          talkingPoints: [
            "OFAC 相关占比趋势",
            "用户可选性（multiple relays）",
            "与 L2 sequencer 关联",
          ],
          defaultStance: "neutral",
        }),
        topic({
          id: "infra.sequencer",
          categoryId: "infra",
          name: "L2 / Sequencer",
          meaning: "Rollup 排序器去中心化进度与故障风险。",
          relatedThemes: ["narrative.l1", "security.outage"],
          talkingPoints: [
            "stage 升级路线图",
            "sequencer 宕机对用户影响",
            "与 ETH 主网安全边界",
          ],
          defaultCoins: ["ETH"],
        }),
      ],
    },
    {
      id: "metastory",
      name: "宏观叙事包装",
      desc: "机构化、链上美股、支付轨道与季节",
      topics: [
        topic({
          id: "metastory.institutional",
          categoryId: "metastory",
          name: "机构化 / 合法化",
          meaning: "crypto 作为资产类别被 TradFi 接纳的长期包装叙事。",
          relatedThemes: ["policy.etf", "people.treasury", "narrative.btc_gold"],
          talkingPoints: [
            "渠道开通 vs 配置比例",
            "监管 clarity 是前提不是结果",
            "回调时叙事是否断裂",
          ],
          defaultStance: "bull",
        }),
        topic({
          id: "metastory.onchain_equity",
          categoryId: "metastory",
          name: "链上美股 / RWA 权益",
          meaning: "代币化股票与 24/7 交易 TradFi 资产的愿景与合规边界。",
          relatedThemes: ["narrative.rwa", "policy.sec"],
          talkingPoints: [
            "合规发行方 vs 合成资产",
            "流动性与 oracle 风险",
            "与真实持股权利对比",
          ],
          defaultStance: "mixed",
        }),
        topic({
          id: "metastory.stable_rail",
          categoryId: "metastory",
          name: "稳定币支付轨道",
          meaning: "稳定币作为跨境支付与结算基础设施的宏观故事。",
          relatedThemes: ["policy.stable", "narrative.stablechain"],
          talkingPoints: [
            "商户采用 vs 链上 volume",
            "合规稳定币份额变化",
            "与 CEX 入金竞争关系",
          ],
          defaultCoins: ["USDC", "BTC"],
        }),
      ],
    },
    {
      id: "calendar",
      name: "日历与事件驱动",
      desc: "TGE、解锁、主网、减半与会议",
      topics: [
        topic({
          id: "calendar.tge",
          categoryId: "calendar",
          name: "TGE / 上所",
          importance: 5,
          meaning:
            "代币生成、开盘、CEX/DEX 上线。定价高峰常在预期阶段，开盘是流动性事件：解锁流通、做市、农抛压同时出现。",
          impactSummary:
            "日期本身不是多空，预期怎么被定价才是；上所是卖点日历，看流通盘和 FDV。",
          relatedThemes: [
            "fundamental.unlock",
            "narrative.perp_dex",
            "exchange.airdrop",
            "exchange.listing",
            "fundamental.fdv",
          ],
          talkingPoints: [
            "上所是卖点日历，不是基本面日历",
            "看流通盘和 FDV，不看开盘第一分钟颜色",
            "积分越肥，开盘抛压越大",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("币价", "TGE 日波动极大，方向常与预热相反", "当日"),
            impactOn("L1 / 公链竞争", "龙头上所会吸走同赛道流动性", "1–3 日"),
            impactOn("解锁 / Cliff", "TGE 常叠 cliff", "当日"),
            impactOn("上市 / 下架", "上所公告本身带流量", "公告日"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "低 FDV、真实收入、上所后有持续买盘（非纯农）",
              then: "开盘可以是起点",
              coins: ["BTC"],
              stance: "bull",
              template:
                "开盘不是终点的前提是：盘不贵、农不多、有人用。三者缺一，按事件交易。",
              invalidation: "开盘后 48h 跌破做市区间且量在出",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "高 FDV、高积分、上所即大额可卖",
              then: "利好落地",
              coins: ["BTC"],
              stance: "bear",
              template:
                "预热已经把价格付完。TGE 是把积分变成卖方。写风险，不写开盘必涨。",
              invalidation: "流通锁定严、上所后 OI/现货同步吸",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "产品强、开盘弱，或开盘强、链上用量立刻塌",
              then: "产品与筹码分离",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "能用和能囤是两件事。TGE 周只给事件仓位。",
              invalidation: "30 日留存和收入还在",
            }),
          ],
          templates: [
            tpl(
              "calendar.tge",
              "上所先算谁能卖",
              "【TGE 日：填日期】看流通/FDV 和积分抛压，不看开盘第一分钟。失效：48h 内跌破做市区且量出。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "calendar.unlock",
          categoryId: "calendar",
          name: "解锁日 / Cliff",
          importance: 5,
          meaning:
            "团队、VC、生态、顾问份额到期。看金额占流通比、归属曲线、是否场外接盘。大额 cliff 是供给冲击，不是 K 线形态。",
          impactSummary:
            "解锁占流通 5% 以上必须写进标题；解锁前涨常常是出货窗口。",
          relatedThemes: [
            "calendar.tge",
            "fundamental.unlock",
            "fundamental.fdv",
            "onchain.exchange_balance",
          ],
          talkingPoints: [
            "解锁占流通 5% 以上必须写进标题",
            "解锁前涨常常是出货窗口",
            "解锁当天没跌不等于消化完，看随后 5 日",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("供给", "流通突然变大", "当日–5 日"),
            impactOn("关键结构 / 趋势", "未消化前，前高是阻力", "1–2 周"),
            impactOn("L1 / 公链竞争", "同赛道几个项目叠解锁会一起弱", "当周"),
            impactOn("内容", "适合日历预告稿", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "占比小、线性解、有回购/锁仓声明且历史上没砸",
              then: "事件权降低",
              coins: ["BTC"],
              stance: "bull",
              template:
                "这笔解锁搬不走趋势。仍要盯地址进没进所，但不要写成末日。",
              invalidation: "解锁钱包开始进所",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "cliff 大、FDV 高、项目无收入",
              then: "供给过密",
              coins: ["BTC"],
              stance: "bear",
              template:
                "日历上已经写好卖盘。涨是送给卖方的流动性。失效看解锁钱包不卖并场外消化。",
              invalidation: "链上显示未进所且价格站稳",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "解锁量大但价格提前一周跌完",
              then: "可能已定价",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "冲击可能发生在日前。解锁日当天的阴线不一定是新空点。",
              invalidation: "落地后继续放量破位",
            }),
          ],
          templates: [
            tpl(
              "calendar.unlock",
              "先算占流通多少",
              "【解锁日：填日期】占流通 ≥5% 必须写标题。失效：解锁后 5 日内钱包进所或放量破位。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "calendar.mainnet",
          categoryId: "calendar",
          name: "主网 / 升级",
          importance: 4,
          meaning:
            "主网上线、硬分叉、性能升级、迁移。技术落地经常「买预期卖事实」，真正加分的是升级后费用、稳定性和开发者是否留下。",
          impactSummary:
            "主网日是庆典，留存才是基本面；升级失败/回滚是安全事件。",
          relatedThemes: [
            "narrative.l1",
            "narrative.stablechain",
            "calendar.tge",
            "fundamental.tvl",
            "exchange.airdrop",
          ],
          talkingPoints: [
            "主网日是庆典，留存才是基本面",
            "升级失败/回滚是安全事件，不只是技术新闻",
            "空投查询日的流量不是用户",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("代币", "预期升、落地分", "前后各 1 周"),
            impactOn("TVL / 协议收入", "gas、TVL、地址是否台阶", "7–30 日"),
            impactOn("黑客 / 漏洞 exploit", "升级窗口易出漏洞和假前端", "当日"),
            impactOn("跨链桥风险", "桥迁移期资金易停在半路", "当周"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "主网稳定、费用下降、真实应用迁入",
              then: "份额叙事成立",
              coins: ["ETH", "SOL"],
              stance: "bull",
              template:
                "升级之后数字还在。这才从事件变成基本面。失效看 14 日活跃和费用掉回原样。",
              invalidation: "庆典后曲线断崖",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "延期、故障、或只有积分用户",
              then: "卖事实",
              coins: ["BTC"],
              stance: "bear",
              template:
                "日期兑现了，用户没有。主网不是财报。",
              invalidation: "故障修复后用量创新高",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "技术成功、币价跌",
              then: "筹码和进度错位",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "链能跑，币在解。把升级稿和交易稿拆开。",
              invalidation: "解锁空窗 + 用量上台阶",
            }),
          ],
          templates: [
            tpl(
              "calendar.mainnet",
              "落地后看留存",
              "【主网日：填日期】庆典不是基本面。失效：14 日内活跃/费用掉回原样。",
              { stance: "mixed" }
            ),
          ],
        }),
        topic({
          id: "calendar.halving",
          categoryId: "calendar",
          name: "减半 / 供给冲击",
          importance: 3,
          meaning:
            "BTC 减半、类似的发行衰减、难度调整。四年一次的供给叙事。减半当下很少单独定价，更多是周期锚点和内容日历。",
          impactSummary:
            "已知供给要配需求；不要用减半解释当天 2% 波动。",
          relatedThemes: [
            "narrative.btc_gold",
            "infra.hashrate",
            "onchain.mvrv",
            "structure.etf_flow",
            "narrative.altseason",
          ],
          talkingPoints: [
            "减半是已知事件，路径早已部分定价",
            "矿工压力在减半后 3–12 个月更重要",
            "不要用减半解释当天 2% 波动",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("矿工卖压", "收入降则可能卖币/关机", "数月"),
            impactOn("内容", "减半前后流量大", "前后各 1 月"),
            impactOn("现货 ETF 流入", "供给减 vs 机构需求", "中期"),
            impactOn("山寨季 vs 比特币季", "BTC 减半不等于山寨减半", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "减半后 ETF/需求仍在，矿工未集中出货",
              then: "供给收缩叙事可用",
              coins: ["BTC"],
              stance: "bull",
              template:
                "已知的供给下降，要配上还在的需求。只喊减半不够。",
              invalidation: "ETF 流出 + 矿工余额进所",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "减半前过热抢跑，落地后无新需求",
              then: "买预期卖事实",
              coins: ["BTC"],
              stance: "bear",
              template:
                "日历兑现那天，往往是交易员离场日。减半不是自动涨价器。",
              invalidation: "落地后需求指标（ETF、稳定币）同步升",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "减半利多叙事 vs 宏观加息同期",
              then: "供给故事打不过流动性",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "四年周期碰上利率周期，先写流动性，再写区块奖励。",
              invalidation: "宏观缓和且 BTC.D 升着走趋势",
            }),
          ],
          templates: [
            tpl(
              "calendar.halving",
              "已知供给，要配需求",
              "【减半日：填日期】已知事件，路径已部分定价。失效：落地后 30 日 ETF/稳定币未同步升。",
              { stance: "mixed", coins: ["BTC"] }
            ),
          ],
        }),
        topic({
          id: "calendar.conference",
          categoryId: "calendar",
          name: "会议周 / 宏观周",
          importance: 5,
          meaning:
            "FOMC、CPI、杰克逊霍尔、国会听证、大型行业大会叠在同一周。波动率抬升，方向常在发言后才清晰。适合做日历预告和「先降杠杆」内容。",
          impactSummary:
            "会议周先写情景不写必到价；数据日和到期日叠在一起，日内不要赌方向。",
          relatedThemes: [
            "macro.fomc",
            "macro.cpi",
            "structure.options",
            "structure.etf_flow",
            "structure.funding",
          ],
          talkingPoints: [
            "会议周先写情景，不写点位必到",
            "数据日和到期日叠在一起，日内不要赌方向",
            "大会演讲是流量，不是基本面",
          ],
          defaultCoins: ["BTC"],
          defaultStance: "mixed",
          impactOn: [
            impactOn("波动率", "IV 升、针多", "当周"),
            impactOn("现货 ETF 流入", "机构周中观望，周后才下单", "1–3 日"),
            impactOn("资金费 / OI", "拥挤在会议前更危险", "同步"),
            impactOn("山寨季 vs 比特币季", "宏观周高 Beta 先被砍", "同步"),
          ],
          scenarios: [
            scenario("good", {
              name: "好情况",
              if: "利空落地但风险资产不跌、ETF 次日吸",
              then: "定价完毕",
              coins: ["BTC"],
              stance: "bull",
              template:
                "会议周最有用的句子是：利空出尽还是利空开始。看第二天 ETF 和 DXY，不看记者会第一句。",
              invalidation: "次日继续破位且美元走强",
            }),
            scenario("bad", {
              name: "坏情况",
              if: "点阵图/数据更鹰，或会议前费率极正",
              then: "拥挤遇上宏观",
              coins: ["BTC"],
              stance: "bear",
              template:
                "日历上有炸弹，仓位上还在拥挤。先减，再解释。",
              invalidation: "声明偏鸽且现货买入跟上",
            }),
            scenario("mixed", {
              name: "分裂",
              if: "宏观中性但到期墙把价格钉住",
              then: "周内无方向",
              coins: ["BTC"],
              stance: "mixed",
              template:
                "这周是日历，不是趋势。墙倒和声明结束之前，突破作废。",
              invalidation: "周收盘离开区间并放量",
            }),
          ],
          templates: [
            tpl(
              "calendar.conference",
              "先写情景，不写必到价",
              "【宏观周：填 CPI/FOMC 日期】先降杠杆，日内不赌方向。失效：周收盘仍卡区间且 ETF 不跟。",
              { stance: "mixed" }
            ),
          ],
        }),
      ],
    },
    {
      id: "strategy",
      name: "组合与策略话题",
      desc: "定投、套利、空投与轮动",
      topics: [
        topic({
          id: "strategy.dca",
          categoryId: "strategy",
          name: "定投 / 长期配置",
          meaning: "忽略短周期 noise 的分批买入策略叙事，适合 education 向内容。",
          relatedThemes: ["narrative.btc_gold", "metastory.institutional"],
          talkingPoints: [
            "DCA 不是永不卖，要写 exit 框架",
            "波动率环境改变 DCA 效率",
            "别承诺收益，写风险预算",
          ],
          defaultStance: "bull",
        }),
        topic({
          id: "strategy.funding_arb",
          categoryId: "strategy",
          name: "资金费套利",
          meaning: "现货-永续对冲赚取 funding，与 structure.funding 联动。",
          relatedThemes: ["structure.funding", "ta.funding_extreme"],
          talkingPoints: [
            "basis 风险与交易所风险",
            "费率反转时的 unwind",
            "不适合写成无风险",
          ],
          defaultStance: "neutral",
        }),
        topic({
          id: "strategy.airdrop",
          categoryId: "strategy",
          name: "空投耕作",
          meaning: "为潜在空投进行交互的策略，与 sybil、成本与 opportunity cost。",
          relatedThemes: ["exchange.airdrop", "narrative.l1"],
          talkingPoints: [
            "farm 成本 vs 预期 EV",
            "规则变更与 retroactive",
            "多钱包合规风险",
          ],
          defaultStance: "mixed",
        }),
        topic({
          id: "strategy.rotation",
          categoryId: "strategy",
          name: "板块轮动",
          meaning: "在 BTC、ETH、L1、Meme 等 basket 之间切换的配置叙事。",
          relatedThemes: ["narrative.altseason", "structure.btcd"],
          talkingPoints: [
            "轮动要有触发条件不是感觉",
            "相关性上升时轮动失效",
            "写清再平衡频率",
          ],
          defaultStance: "mixed",
        }),
        topic({
          id: "strategy.hedge",
          categoryId: "strategy",
          name: "对冲 / 保护",
          meaning: "期权、稳定币或反向 perp 用于下行保护。",
          relatedThemes: ["structure.options", "ta.structure"],
          talkingPoints: [
            "对冲成本 vs 保护范围",
            "永续对冲的 funding drag",
            "极端行情下 basis 行为",
          ],
          defaultStance: "neutral",
        }),
      ],
    },
  ];

  /** 大类内容权重（1–5 星） */
  const CATEGORY_META = {
    macro: { importance: 5, importanceNote: "定价主开关，CPI/FOMC/美元几乎周周用" },
    structure: { importance: 5, importanceNote: "ETF、资金费、OI 决定涨跌质量" },
    narrative: { importance: 5, importanceNote: "内容和引流的主战场" },
    policy: { importance: 4, importanceNote: "一周一爆，但不是每天都有" },
    calendar: { importance: 4, importanceNote: "TGE、解锁、会议周很好做钩子" },
    metastory: { importance: 4, importanceNote: "适合标题和系列，不适合每条新闻" },
    ta: { importance: 4, importanceNote: "可用交易句子变多，但仍次于宏观和资金流" },
    onchain: { importance: 3, importanceNote: "有数据才有差异，日常频率中等" },
    fundamental: { importance: 3, importanceNote: "解锁定期用，日常少" },
    people: { importance: 3, importanceNote: "适合爆款，持续性差" },
    exchange: { importance: 2, importanceNote: "活动/上币时用，日常弱" },
    security: { importance: 2, importanceNote: "爆发时极重要，平时空窗" },
    strategy: { importance: 2, importanceNote: "深度向，流量一般" },
    infra: { importance: 1, importanceNote: "圈层窄，除非减半/罚没" },
  };

  /** 小类内容权重覆盖（未列出的默认 3 星） */
  const TOPIC_IMPORTANCE = {
    "macro.fomc": { importance: 5 },
    "macro.dxy": { importance: 5 },
    "macro.cpi": { importance: 4, importanceNote: "PCE 对 Fed 更关键，但内容侧 CPI 传播更广" },
    "macro.equities": { importance: 4 },
    "macro.pce": { importance: 3 },
    "macro.nfp": { importance: 3 },
    "macro.geo": { importance: 3, importanceNote: "平时三星，开战/重大地缘再当五星用" },
    "structure.funding": { importance: 5 },
    "structure.etf_flow": { importance: 5 },
    "structure.exchange_flow": { importance: 4 },
    "structure.btcd": { importance: 5 },
    "structure.options": { importance: 4 },
    "structure.liquidity": { importance: 3 },
    "narrative.btc_gold": { importance: 5 },
    "narrative.altseason": { importance: 5 },
    "narrative.stablechain": { importance: 5 },
    "narrative.perp_dex": { importance: 5 },
    "narrative.l1": { importance: 4 },
    "narrative.rwa": { importance: 4 },
    "narrative.privacy": { importance: 4 },
    "narrative.ai": { importance: 3 },
    "narrative.meme": { importance: 3 },
    "ta.structure": { importance: 4 },
    "ta.funding_extreme": { importance: 5 },
    "ta.liquidation": { importance: 4 },
    "ta.sr": { importance: 3 },
    "ta.volume": { importance: 3 },
    "ta.candlestick": { importance: 3 },
    "ta.divergence": { importance: 3 },
    "ta.oi": { importance: 4 },
    "ta.wyckoff": { importance: 3 },
    "onchain.exchange_balance": { importance: 4 },
    "onchain.stable_supply": { importance: 4 },
    "onchain.mvrv": { importance: 3 },
    "onchain.whale": { importance: 3 },
    "onchain.flow": { importance: 3 },
    "calendar.tge": { importance: 5 },
    "calendar.unlock": { importance: 5 },
    "calendar.conference": { importance: 5 },
    "calendar.mainnet": { importance: 4 },
    "calendar.halving": { importance: 3 },
    "exchange.listing": { importance: 4 },
    "exchange.airdrop": { importance: 4 },
    "exchange.outage": { importance: 4 },
    "exchange.fee": { importance: 3 },
    "exchange.product": { importance: 3 },
  };

  for (const cat of categories) {
    const meta = CATEGORY_META[cat.id];
    if (meta) Object.assign(cat, meta);
    if (cat.importance == null) cat.importance = 3;
    for (const t of cat.topics || []) {
      if (t.importance == null) t.importance = 3;
      const ov = TOPIC_IMPORTANCE[t.id];
      if (ov) Object.assign(t, ov);
    }
  }

  /** 左栏大类分组（按中文 name 匹配，不依赖 id） */
  const categoryGroups = [
    {
      id: "macro_policy",
      name: "宏观政策",
      hint: "利率、监管、大故事，先定外部环境",
      names: ["宏观与传统金融", "监管、政策与司法", "宏观叙事包装"],
    },
    {
      id: "coin_tech",
      name: "币种或技术指标",
      hint: "资金、板块、基本面、盘面、链上",
      names: [
        "市场结构与资金流",
        "币种与板块叙事",
        "项目与代币基本面",
        "技术分析与微观结构",
        "链上分析",
      ],
    },
    {
      id: "periphery",
      name: "其他周边事件",
      hint: "日历、安全、交易所、人物、基建、策略",
      names: [
        "日历与事件驱动",
        "安全、攻击与风险事件",
        "交易所、产品与交易基础设施",
        "人物、机构与舆论",
        "矿业、质押与基础设施层",
        "组合与策略话题",
      ],
    },
  ];

  global.TaxonomyData = { categories, categoryGroups };
})(typeof window !== "undefined" ? window : globalThis);
