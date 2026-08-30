# coding=utf-8
"""写入各素材类目的「结构模板 + 案例」，供灵感碰撞按类目生成。

运行：
  python -m corpus.seed_category_templates
  或：python corpus/seed_category_templates.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corpus.db import create_template, init_db


# 每条 = 一个类目结构模板（is_category_template=True）+ 可直接仿写的案例
SEED_TEMPLATES: List[Dict[str, Any]] = [
    # ── 量价技术 30% ──────────────────────────────────────────
    {
        "source_key": "cat_tpl:market:wyckoff_range",
        "source_platform": "seed",
        "source_title": "【模板】威科夫区间 + 假突破",
        "raw_text": (
            "结构：① 区间高低点与阶段标签（吸筹/派发）② 假突破/弹簧 ③ 量能确认 ④ 无效条件。\n"
            "写作要点：先画区间再谈方向；用「如果跌破则…」写失效；配图优先 TradingView。"
        ),
        "hooks": "区间上沿假突破后回落，下一步看哪里？",
        "pattern": "区间界定 → 假突破判定 → 量价确认 → 失效条件",
        "emotion": "冷静",
        "tension": "关键位博弈",
        "keywords": ["威科夫", "区间", "假突破", "量价"],
        "tags": ["类目模板", "量价技术", "威科夫"],
        "factors": {
            "material_category": "market",
            "is_category_template": True,
            "use_case": "日更短推 / 关键位预警",
            "structure": [
                "标出区间高低点与当前阶段（吸筹/派发/再吸筹）",
                "描述假突破或弹簧：突破→收回→量能",
                "给出观察位与失效条件（一句即可）",
                "可选：下一根K线确认后再表态",
            ],
            "hook_patterns": [
                "XX 在区间上沿假突破后收回，量能说明什么？",
                "弹簧出现了，但还缺一个确认信号",
            ],
            "example": {
                "title": "BTC 4H 区间假突破案例",
                "hook": "BTC 扫了区间上沿又收回——这更像派发试探，不是突破确认。",
                "body": (
                    "4H 看，BTC 在 67.2k–69.8k 横盘近两周。\n"
                    "昨夜刺破 69.8k 后 1 小时内收回，成交量放大但收盘仍在区间内 → 典型上假突破。\n"
                    "观察：若重新站稳 69.2k 且量能萎缩，才谈向上拓展；跌破 67.2k 则区间失效，先看 65.5k。\n"
                    "先等确认，不抢跑。"
                ),
            },
            "content_mix_pct": 30,
            "narrative_type": "技术",
            "core_concept": "假突破优先于方向喊单",
        },
    },
    {
        "source_key": "cat_tpl:market:key_level_alert",
        "source_platform": "seed",
        "source_title": "【模板】关键位预警短推",
        "raw_text": "结构：标的+周期 → 关键价位 → 多空两种剧本 → 一句纪律。适合开盘前后 30 秒读完。",
        "hooks": "明天开盘前，只盯这一个价位",
        "pattern": "价位 → 多剧本 → 纪律",
        "emotion": "克制",
        "tension": "开盘博弈",
        "keywords": ["关键位", "预警", "多空剧本"],
        "tags": ["类目模板", "量价技术"],
        "factors": {
            "material_category": "market",
            "is_category_template": True,
            "use_case": "开盘前短推",
            "structure": [
                "一个标的 + 一个价位（不要堆指标）",
                "站上/跌破各自意味着什么（各一句）",
                "个人仓位纪律（不喊单）",
            ],
            "example": {
                "title": "ETH 关键位双剧本",
                "hook": "开盘前只盯 ETH 3520。",
                "body": (
                    "4H 收盘站稳 3520：区间上沿打开，下一阻力 3680。\n"
                    "跌破并 1H 收在下方：回测失败，先看 3380。\n"
                    "我这边：突破不追，回踩确认再考虑；假突破直接减。"
                ),
            },
            "narrative_type": "技术",
            "core_concept": "一个价位两种剧本",
        },
    },
    # ── 链上聪明钱 ───────────────────────────────────────────
    {
        "source_key": "cat_tpl:onchain:whale_move",
        "source_platform": "seed",
        "source_title": "【模板】巨鲸/做市商地址异动",
        "raw_text": (
            "结构：谁（地址标签）→ 做了什么（充提/转账规模）→ 历史含义 → 谨慎结论。\n"
            "配图：Arkham / DeBank / 浏览器截图。禁止编造地址余额。"
        ),
        "hooks": "Jump / Wintermute 刚往交易所充了什么？",
        "pattern": "主体 → 动作 → 含义 → 免",
        "emotion": "警惕",
        "tension": "砸盘/吸筹悬念",
        "keywords": ["巨鲸", "做市商", "充值", "提现", "Arkham"],
        "tags": ["类目模板", "链上聪明钱", "巨鲸"],
        "factors": {
            "material_category": "onchain",
            "is_category_template": True,
            "use_case": "链上异动快讯短推",
            "structure": [
                "点名主体（Jump / Wintermute / DWF / 已标注巨鲸）+ 链",
                "动作：充值进所 / 提现冷钱包 / 大额转账 + 金额与代币",
                "同类历史：充值偏抛压、提现偏囤积（标注为常见解读非必然）",
                "结论用概率语言 + 提醒截图来源时间",
            ],
            "hook_patterns": [
                "标注地址刚把 XX 万枚 $TOKEN 充进币安",
                "做市商钱包连续 3 笔提现——吸筹还是搬砖？",
            ],
            "example": {
                "title": "巨鲸充值交易所案例",
                "hook": "某 Jump 关联地址 40 分钟内向 Binance 充入 2,100 ETH。",
                "body": (
                    "来源：Arkham 标签 + 浏览器哈希（附图）。\n"
                    "动作：冷钱包 → 交易所热钱包，约 $XXm。\n"
                    "常见解读：大额充值常被市场解读为潜在抛压；也可能是做市库存调仓——两者都要写进推文。\n"
                    "我怎么用：不据此开空，只提高短线波动预期；若现货同步放量阴线再降仓。\n"
                    "数据时间：截图时刻 UTC。"
                ),
            },
            "tools": ["Arkham", "DeBank", "Etherscan"],
            "narrative_type": "链上",
            "core_concept": "充提异动 = 波动预警，不是喊单",
        },
    },
    {
        "source_key": "cat_tpl:onchain:smart_wallet",
        "source_platform": "seed",
        "source_title": "【模板】DEX 聪明钱钱包拆解",
        "raw_text": "结构：钱包胜率/战绩 → 建仓成本 → 持仓变动 → 可复制的观察框架（非跟单）。配 GMGN/Debank。",
        "hooks": "这个不知名钱包又提前埋伏了",
        "pattern": "战绩 → 成本 → 变动 → 框架",
        "emotion": "好奇",
        "tension": "Alpha 悬念",
        "keywords": ["聪明钱", "DEX", "GMGN", "建仓成本"],
        "tags": ["类目模板", "链上聪明钱", "聪明钱"],
        "factors": {
            "material_category": "onchain",
            "is_category_template": True,
            "use_case": "Thread 或长推拆解",
            "structure": [
                "展示钱包近期胜率/代表性交易（截图）",
                "当前标的：买入均价、仓位占比、持有时长",
                "近 24–72h 加减仓轨迹",
                "读者可学的一点：如何设监控，而不是「跟这个地址买」",
            ],
            "example": {
                "title": "聪明钱早期埋伏案例",
                "hook": "一个没粉丝的钱包，30 天胜率 70%+，又在 $XXX 上加仓了。",
                "body": (
                    "GMGN 筛：近 30 天已实现盈亏为正、胜率高、非狙击机器人特征。\n"
                    "该地址在 TGE 前 2 天进场，成本约 $0.08；现价 $0.21，仓位仍占其组合 ~18%。\n"
                    "近 48h：小额加仓而非出货。\n"
                    "我用法：把地址加入监控列表，只跟踪「是否开始分批出货」；不复制仓位。\n"
                    "风险：聪明钱也会错，截图只代表过去。"
                ),
            },
            "tools": ["GMGN", "DeBank", "Arkham"],
            "narrative_type": "链上",
            "core_concept": "拆框架不跟单",
        },
    },
    {
        "source_key": "cat_tpl:onchain:liq_heatmap",
        "source_platform": "seed",
        "source_title": "【模板】清算热力图读盘",
        "raw_text": "结构：当前价 → 上下清算密集区 → 插针偏好解读 → 交易上如何避坑。工具：Coinglass。",
        "hooks": "流动性在上方还是下方？做市商最爱扫哪里",
        "pattern": "现价 → 密集区 → 扫损逻辑 → 应对",
        "emotion": "紧张",
        "tension": "插针预期",
        "keywords": ["清算", "热力图", "Coinglass", "流动性"],
        "tags": ["类目模板", "链上聪明钱", "清算"],
        "factors": {
            "material_category": "onchain",
            "is_category_template": True,
            "use_case": "波动前预警短推",
            "structure": [
                "贴热力图截图，标出现价",
                "上方/下方哪一侧清算更厚",
                "一句：厚的一侧更易成为插针目标（概率语言）",
                "仓位建议：止损避开明显密集带",
            ],
            "example": {
                "title": "BTC 清算密集区案例",
                "hook": "Coinglass 显示现价上方 72k 一带空单清算堆得很厚。",
                "body": (
                    "附图：BTC 清算热力图。现价下方 66k–67k 也有多单密集区。\n"
                    "短线含义：波动放大时，价格常向「流动性更厚」的一侧狩猎。\n"
                    "我怎么用：不做窄止损夹在两堆清算中间；突破/跌破密集区后再评估趋势，而不是猜插针方向。"
                ),
            },
            "tools": ["Coinglass"],
            "narrative_type": "链上",
            "core_concept": "清算密集区 = 流动性磁铁",
        },
    },
    # ── 情绪衍生品 ───────────────────────────────────────────
    {
        "source_key": "cat_tpl:derivatives:funding_squeeze",
        "source_platform": "seed",
        "source_title": "【模板】资金费率与逼空/多头踩踏",
        "raw_text": "结构：费率极值 → 价格是否同向确认 → 逼空或踩踏剧本 → 失效条件。结合 OI 更佳。",
        "hooks": "费率极负但价格不跌，空头危险了？",
        "pattern": "费率 → 价格确认 → 剧本 → 失效",
        "emotion": "紧绷",
        "tension": "极端情绪反转",
        "keywords": ["资金费率", "逼空", "OI", "爆仓"],
        "tags": ["类目模板", "情绪衍生品", "资金费率"],
        "factors": {
            "material_category": "derivatives",
            "is_category_template": True,
            "use_case": "极端行情短推",
            "structure": [
                "报全网/主流所 funding 数值与方向",
                "价格是否配合（极负却横盘/上涨 → 逼空讨论）",
                "OI 是升是降：杠杆堆积还是去杠杆",
                "两种剧本 + 你站哪边观望",
            ],
            "example": {
                "title": "负费率逼空观察案例",
                "hook": "全网 BTC 资金费率极负，现货却纹丝不动——空头在送钱还是在埋伏？",
                "body": (
                    "Funding 深度负值 + 价格横盘：空头持续付费，逼空燃料在堆积。\n"
                    "但若 OI 同步下降，更像空头认输离场，而非新空堆积。\n"
                    "剧本 A：一根放量阳线戳穿空头 → 短挤。\n"
                    "剧本 B：现货补跌，费率修复 → 空头暂时正确。\n"
                    "我：不预判方向，只把杠杆降到「挨得住插针」的水平。"
                ),
            },
            "narrative_type": "情绪",
            "core_concept": "极值费率看对手盘压力",
        },
    },
    {
        "source_key": "cat_tpl:derivatives:fear_greed_retail",
        "source_platform": "seed",
        "source_title": "【模板】恐慌贪婪 + 散户多空比",
        "raw_text": "结构：指数/多空比读数 → 历史分位 → 主力可能怎么洗 → 个人应对。站在对手盘角度写。",
        "hooks": "散户一边倒做多的时候，谁在另一边？",
        "pattern": "读数 → 分位 → 洗盘逻辑 → 应对",
        "emotion": "反直觉",
        "tension": "羊群 vs 主力",
        "keywords": ["恐慌贪婪", "多空比", "散户", "对手盘"],
        "tags": ["类目模板", "情绪衍生品"],
        "factors": {
            "material_category": "derivatives",
            "is_category_template": True,
            "use_case": "情绪周报短推",
            "structure": [
                "报 Fear&Greed 或散户多空人数比",
                "说明是否处于极端区（附时间框）",
                "对手盘视角：拥挤方向往往是洗盘对象",
                "操作：减拥挤侧风险，而非无脑反向开仓",
            ],
            "example": {
                "title": "散户多空拥挤案例",
                "hook": "散户多空比已经极端偏多——这通常不是「安全确认」。",
                "body": (
                    "数据：主流所散户账户多头占比显著高于空头（附图）。\n"
                    "含义：拥挤的多头侧成为洗盘成本更低的一侧。\n"
                    "不等于立刻做空；而是：追高杠杆多单的性价比变差。\n"
                    "我：降低市价追多频率，等回踩或情绪降温再评估。"
                ),
            },
            "narrative_type": "情绪",
            "core_concept": "拥挤侧 = 洗盘成本更低",
        },
    },
    # ── KOL 复盘 20% ──────────────────────────────────────────
    {
        "source_key": "cat_tpl:kol:opinion_compass",
        "source_platform": "seed",
        "source_title": "【模板】Top KOL 观点罗盘",
        "raw_text": "结构：采样 N 位大 V → 多空占比可视化描述 → 共识拥挤点 → 你的独立判断一句。可引流私域细报。",
        "hooks": "本周头部大 V 到底几多几空？",
        "pattern": "采样 → 占比 → 拥挤点 → 独立观点",
        "emotion": "客观",
        "tension": "共识 vs 独立",
        "keywords": ["KOL", "观点罗盘", "共识", "周报"],
        "tags": ["类目模板", "KOL复盘", "观点罗盘"],
        "factors": {
            "material_category": "kol_review",
            "is_category_template": True,
            "use_case": "周报 / 私域引流钩子",
            "structure": [
                "说明样本：几位、哪类账号、统计窗口",
                "多/空/中性占比（可文字版罗盘）",
                "共识最拥挤的一句话或价位",
                "你的差异化观点 + 「完整名单在…」轻引流",
            ],
            "example": {
                "title": "KOL 观点罗盘案例",
                "hook": "抽了 12 位交易向大 V：7 多 3 空 2 观望——多头共识有点拥挤。",
                "body": (
                    "窗口：过去 7 天公开推文/Space 立场（主观标注，附名单逻辑）。\n"
                    "罗盘：偏多 58%｜偏空 25%｜中性 17%。\n"
                    "拥挤点：多数点名「BTC 站上 XX 看 XXX」。\n"
                    "我的偏差：更关心资金费率与现货溢价是否支持这份乐观，而不是人数投票。\n"
                    "完整标注表放在私域周报，这里只给结论框架。"
                ),
            },
            "narrative_type": "复盘",
            "core_concept": "共识拥挤时独立定价",
        },
    },
    {
        "source_key": "cat_tpl:kol:call_audit",
        "source_platform": "seed",
        "source_title": "【模板】战绩打码 / 马后炮打假",
        "raw_text": "结构：原话引用 → 时间戳 → 事后价格 → 客观评分。树立可信度，避免人身攻击。",
        "hooks": "把「早就说过」放到时间线里对质",
        "pattern": "原话 → 时间 → 结果 → 评分",
        "emotion": "锋利但克制",
        "tension": "可信度审判",
        "keywords": ["打假", "复盘", "时间戳", "战绩"],
        "tags": ["类目模板", "KOL复盘", "打假"],
        "factors": {
            "material_category": "kol_review",
            "is_category_template": True,
            "use_case": "信任建设长推",
            "structure": [
                "截图原话 + 发推时间",
                "对照事后走势（不截取有利片段）",
                "区分：方向对了但点位飘 / 完全相反 / 含糊话术",
                "结尾：自己同类错误也认一笔，平衡人设",
            ],
            "example": {
                "title": "马后炮对质案例",
                "hook": "「我早就看空」——把时间戳打开对一下。",
                "body": (
                    "原推：某账号在价格已跌 12% 后发「风险提示」。\n"
                    "时间线：真正拐点前 48h 其内容仍偏多。\n"
                    "评分：事后风险提示 ≠ 事前信号。\n"
                    "对我自己：上周某某位置的判断也偏早，已在线程置顶勘误。\n"
                    "看人看时间戳，不看剪辑。"
                ),
            },
            "narrative_type": "复盘",
            "core_concept": "时间戳 > 叙事",
        },
    },
    # ── 工具投研（高收藏）────────────────────────────────────
    {
        "source_key": "cat_tpl:toolkit:cheat_sheet",
        "source_platform": "seed",
        "source_title": "【模板】每日必看工具 Cheat Sheet",
        "raw_text": "结构：场景 → 5 个工具卡片（干什么/免费点）→ 我的使用顺序。目标：书签收藏。",
        "hooks": "我每天必看的 5 个免费链上工具",
        "pattern": "场景 → 工具列表 → 使用顺序",
        "emotion": "实用",
        "tension": "省时间",
        "keywords": ["工具", "Cheat Sheet", "收藏", "免费"],
        "tags": ["类目模板", "工具投研", "收藏"],
        "factors": {
            "material_category": "toolkit",
            "is_category_template": True,
            "use_case": "高收藏短推 / 图文",
            "structure": [
                "一句使用场景（早盘扫描 / 找 Alpha）",
                "3–5 个工具：名称 + 一句话用途 + 是否免费",
                "推荐浏览顺序（1→2→3）",
                "CTA：收藏本推 / 要扩展清单",
            ],
            "example": {
                "title": "5 个免费链上工具案例",
                "hook": "早盘 15 分钟扫描，我只开这 5 个标签页。",
                "body": (
                    "1) Coinglass — 清算/资金费率\n"
                    "2) Arkham — 标注资金流向\n"
                    "3) DeBank — 组合与授权风险\n"
                    "4) GMGN — 新池与聪明钱\n"
                    "5) TradingView — 关键位预警\n"
                    "顺序：费率情绪 → 链上异动 → 图表确认。\n"
                    "收藏这条，免得到处问「用啥」。"
                ),
            },
            "narrative_type": "工具",
            "core_concept": "清单体 = 收藏率",
        },
    },
    {
        "source_key": "cat_tpl:toolkit:tv_alert",
        "source_platform": "seed",
        "source_title": "【模板】TradingView 预警配置",
        "raw_text": "结构：要监控的结构 → 逐步点击路径 → 报警条件 → 常见坑。极简可复制。",
        "hooks": "如何用 TradingView 设置威科夫区间预警",
        "pattern": "目标 → 步骤 → 条件 → 坑",
        "emotion": "教学",
        "tension": "可立刻上手",
        "keywords": ["TradingView", "预警", "威科夫", "教程"],
        "tags": ["类目模板", "工具投研", "TradingView"],
        "factors": {
            "material_category": "toolkit",
            "is_category_template": True,
            "use_case": "教程向长推",
            "structure": [
                "监控目标（区间上下沿/弹簧确认）",
                "3–5 步设置路径（可编号）",
                "报警触发条件写清楚",
                "坑：周期选错、报警刷屏、只看影线不看收盘",
            ],
            "example": {
                "title": "区间预警设置案例",
                "hook": "别盯盘：让 TradingView 在假突破收回时喊你。",
                "body": (
                    "目标：4H 收盘跌破区间下沿或刺破后收回。\n"
                    "步骤：画水平线 → Alert on line → 条件选 Once Per Bar Close → Webhook/App 通知。\n"
                    "建议：上下沿各一条；另加「收盘确认」避免影线误报。\n"
                    "坑：用 1m 收盘会刷爆通知。"
                ),
            },
            "narrative_type": "工具",
            "core_concept": "收盘确认预警",
        },
    },
    {
        "source_key": "cat_tpl:toolkit:psychology",
        "source_platform": "seed",
        "source_title": "【模板】仓位与交易心态",
        "raw_text": "结构：原则公式 → 反例故事 → 可执行规则一条。收藏向。",
        "hooks": "仓位公式比「看涨看跌」更能活下来",
        "pattern": "公式 → 反例 → 规则",
        "emotion": "沉稳",
        "tension": "生存",
        "keywords": ["凯利", "仓位", "止损", "心态"],
        "tags": ["类目模板", "工具投研", "心态"],
        "factors": {
            "material_category": "toolkit",
            "is_category_template": True,
            "use_case": "认知向短推",
            "structure": [
                "给出可记的一条规则（固定风险 0.5%–1% 等）",
                "违反时会发生什么（短故事）",
                "本周可执行检查清单一句",
            ],
            "example": {
                "title": "固定风险比案例",
                "hook": "方向对了却爆仓，通常不是技术问题，是仓位问题。",
                "body": (
                    "规则：单笔风险 ≤ 账户 1%（止损距离反推仓位）。\n"
                    "反例：3x 信念仓 + 窄止损 = 两次正常回撤出局。\n"
                    "本周清单：开仓前先写「亏多少钱离场」，再下单。"
                ),
            },
            "narrative_type": "心态",
            "core_concept": "风险预算先于方向",
        },
    },
    {
        "source_key": "cat_tpl:toolkit:automation",
        "source_platform": "seed",
        "source_title": "【模板】资讯/监控自动化极简指南",
        "raw_text": "结构：痛点 → 工具栈（AI/脚本/TG Bot）→ 最小配置步骤 → 安全提醒。",
        "hooks": "用 Bot 盯开仓，而不是人肉刷新",
        "pattern": "痛点 → 栈 → 步骤 → 安全",
        "emotion": "极客",
        "tension": "效率差",
        "keywords": ["Bot", "自动化", "监控", "AI"],
        "tags": ["类目模板", "工具投研", "自动化"],
        "factors": {
            "material_category": "toolkit",
            "is_category_template": True,
            "use_case": "高收藏教程",
            "structure": [
                "痛点：错过开盘异动 / 信息过载",
                "最小栈：例如 RSS/API + TG Bot + 过滤关键词",
                "3 步配置（不写可被滥用的攻击性内容）",
                "安全：密钥、只读权限、勿把私钥放脚本",
            ],
            "example": {
                "title": "TG 监控极简案例",
                "hook": "我把「大额链上转账」推进 Telegram，而不是刷 20 个浏览器标签。",
                "body": (
                    "栈：数据源 webhook → 过滤（金额阈值/代币白名单）→ TG Bot。\n"
                    "步骤：① 建 Bot ② 只读 API/webhook ③ 关键词与静默时段。\n"
                    "安全：永远不把种子短语写进脚本；交易所只用提现白名单地址。"
                ),
            },
            "narrative_type": "工具",
            "core_concept": "监控自动化减信息税",
        },
    },
    # ── 代币 Alpha ────────────────────────────────────────────
    {
        "source_key": "cat_tpl:tokenomics:unlock_calendar",
        "source_platform": "seed",
        "source_title": "【模板】代币大额解锁日历",
        "raw_text": "结构：时间窗 → 币种与解锁量/% → 谁解锁（VC/团队）→ 风险提示。平淡行情优质长推。",
        "hooks": "本周哪些币要迎来 Cliff Unlock？",
        "pattern": "窗口 → 清单 → 谁抛 → 风险",
        "emotion": "审慎",
        "tension": "抛压倒计时",
        "keywords": ["解锁", "Cliff", "VC", "抛压"],
        "tags": ["类目模板", "代币Alpha", "解锁"],
        "factors": {
            "material_category": "tokenomics",
            "is_category_template": True,
            "use_case": "周更 Thread",
            "structure": [
                "本周/本月时间范围",
                "表格感清单：代币、解锁量、占流通比、类别",
                "历史：同类解锁后 7 日常见表现（注明样本局限）",
                "操作：规避/对冲/观望，不号召恶意做空叙事",
            ],
            "example": {
                "title": "本周解锁清单案例",
                "hook": "未来 7 天，这 3 个币的解锁量值得标在日历上。",
                "body": (
                    "窗口：本周一至周日（UTC）。\n"
                    "1) $AAA — 团队份额释放，约流通 x%\n"
                    "2) $BBB — VC 轮 cliff，绝对金额高\n"
                    "3) $CCC — 生态基金线性解锁\n"
                    "用法：事件前减波动敞口；解锁不等于必跌，但流动性差的小币更敏感。\n"
                    "数据请以 TokenUnlocks 等源复核。"
                ),
            },
            "narrative_type": "投研",
            "core_concept": "解锁 = 风险日历",
        },
    },
    {
        "source_key": "cat_tpl:tokenomics:real_yield",
        "source_platform": "seed",
        "source_title": "【模板】Real Yield 与 FDV 合理性",
        "raw_text": "结构：协议收入 → 活跃度 → FDV/市值 → 贵不贵的一句话。适合深度 Thread。",
        "hooks": "日费收入撑得住这个 FDV 吗？",
        "pattern": "收入 → 活跃 → 估值 → 结论",
        "emotion": "理性",
        "tension": "估值争议",
        "keywords": ["Real Yield", "FDV", "手续费", "活跃地址"],
        "tags": ["类目模板", "代币Alpha", "估值"],
        "factors": {
            "material_category": "tokenomics",
            "is_category_template": True,
            "use_case": "深度拆解 Thread",
            "structure": [
                "日/周协议收入或费用（注明来源）",
                "活跃地址/TVL 趋势",
                "FDV 与同类协议对比",
                "贵/便宜的条件句 + 主要风险",
            ],
            "example": {
                "title": "协议收入 vs FDV 案例",
                "hook": "年化费用看着光鲜，除以 FDV 之后呢？",
                "body": (
                    "费用：近 7 日日均协议收入约 $X（来源：DefiLlama）。\n"
                    "活跃：日活地址环比 +/– y%。\n"
                    "估值：FDV $Z，费用/FDV 低于同类中位。\n"
                    "结论：叙事强但现金流折价一般；要买的是增长加速，不是静态收益率海报。\n"
                    "风险：激励停止后费用是否塌方。"
                ),
            },
            "narrative_type": "投研",
            "core_concept": "收入相对 FDV",
        },
    },
    {
        "source_key": "cat_tpl:tokenomics:airdrop_guide",
        "source_platform": "seed",
        "source_title": "【模板】空投/测试网极简交互",
        "raw_text": "结构：项目一句话 → 步骤清单 → 成本与风险 → 反女巫注意。合规表述，不承诺收益。",
        "hooks": "未发币协议：一套极简埋伏清单",
        "pattern": "介绍 → 步骤 → 成本 → 风险",
        "emotion": "务实",
        "tension": "早参与窗口",
        "keywords": ["空投", "测试网", "交互", "反女巫"],
        "tags": ["类目模板", "代币Alpha", "空投"],
        "factors": {
            "material_category": "tokenomics",
            "is_category_template": True,
            "use_case": "教程 Thread",
            "structure": [
                "项目定位一句话（非投资建议）",
                "3–7 步交互清单",
                "预估 Gas/时间成本",
                "风险：合约、钓鱼、女巫、无空投可能",
            ],
            "example": {
                "title": "测试网交互极简案例",
                "hook": "想参与交互可以，但先把「可能没有空投」写进预期。",
                "body": (
                    "项目：某某测试网，定位 L2/DeFi（自查官网）。\n"
                    "步骤：领水 → 兑换 → 加流动性 → 治理签名（示例，以官网为准）。\n"
                    "成本：时间 + 测试币；主网交互另计 Gas。\n"
                    "风险：假站点、授权钓鱼、多号女巫导致零分配。\n"
                    "本文不保证空投。"
                ),
            },
            "narrative_type": "投研",
            "core_concept": "清单 + 风险并列",
        },
    },
    # ── 模因互动 10% ──────────────────────────────────────────
    {
        "source_key": "cat_tpl:engagement:meme",
        "source_platform": "seed",
        "source_title": "【模板】行情梗图/自嘲",
        "raw_text": "结构：场景梗 → 一句自嘲 → 轻相关观察（可无）。破圈与人格化。",
        "hooks": "插针那天我的表情包",
        "pattern": "梗 → 自嘲 → 轻观察",
        "emotion": "自嘲",
        "tension": "共鸣",
        "keywords": ["Meme", "梗图", "自嘲", "插针"],
        "tags": ["类目模板", "模因互动", "Meme"],
        "factors": {
            "material_category": "engagement",
            "is_category_template": True,
            "use_case": "破圈短推",
            "structure": [
                "配一张强共鸣图（踏空/插针/爆仓表情）",
                "一句不装的自嘲",
                "可选：半句正经观察，避免说教",
            ],
            "example": {
                "title": "踏空自嘲案例",
                "hook": "等回调买的人，已经等到新高三连了。",
                "body": (
                    "（配图：盯盘青蛙）\n"
                    "我不是没看到突破，我是在等「更完美的回踩」。\n"
                    "完美回踩可能死在新高里——记一笔，明天继续。"
                ),
            },
            "narrative_type": "互动",
            "core_concept": "人格化 > 每天硬核",
        },
    },
    {
        "source_key": "cat_tpl:engagement:poll",
        "source_platform": "seed",
        "source_title": "【模板】每日/每周复盘投票",
        "raw_text": "结构：清晰问题 → 2–4 选项 → 次日复盘承诺。直接拉评论与投票率。",
        "hooks": "本周 BTC 能否突破 XX？投票",
        "pattern": "问题 → 选项 → 复盘预告",
        "emotion": "挑衅式好奇",
        "tension": "站队",
        "keywords": ["投票", "Poll", "互动", "复盘"],
        "tags": ["类目模板", "模因互动", "投票"],
        "factors": {
            "material_category": "engagement",
            "is_category_template": True,
            "use_case": "周末或关键节点",
            "structure": [
                "一个可证伪的问题 + 价位/时间",
                "A/B/C 选项互斥",
                "承诺：周末公布结果与简短复盘",
            ],
            "example": {
                "title": "关口突破投票案例",
                "hook": "本周 BTC 能否收盘站上 70k？",
                "body": (
                    "A. 站稳大涨\n"
                    "B. 假突破回落\n"
                    "C. 继续横盘耗着\n"
                    "周日发复盘：对照资金费率与现货溢价，看看投票多数派是否拥挤。"
                ),
            },
            "narrative_type": "互动",
            "core_concept": "投票 = 互动率引擎",
        },
    },
    # ── 交易信号 / 长推 / 快捕（保留并加强案例）──────────────
    {
        "source_key": "cat_tpl:signal:entry_invalid",
        "source_platform": "seed",
        "source_title": "【模板】入场逻辑 + 失效条件",
        "raw_text": "结构：方向与周期 → 触发条件 → 失效条件 → 风险提示。禁止保证收益话术。",
        "hooks": "多单思路可以有，但先写失效条件",
        "pattern": "方向 → 触发 → 失效 → 风险",
        "emotion": "专业克制",
        "tension": "盈亏同源",
        "keywords": ["信号", "失效", "入场", "风险"],
        "tags": ["类目模板", "交易信号"],
        "factors": {
            "material_category": "signal",
            "is_category_template": True,
            "use_case": "信号短推",
            "structure": [
                "标的 + 周期 + 倾向（多/空/观望）",
                "触发：价格/结构条件",
                "失效：一触即否定的条件",
                "风险：杠杆与仓位一句",
            ],
            "example": {
                "title": "带失效条件的信号案例",
                "hook": "ETH 偏多可以，但先把「什么情况下我错了」写出来。",
                "body": (
                    "ETH 4H 偏多观察：回踩 3480–3520 企稳可考虑。\n"
                    "触发：该区间收盘不破 + 再收回 3560。\n"
                    "失效：4H 收盘跌破 3440。\n"
                    "风险：仅作结构记录，非投资建议；杠杆自控。"
                ),
            },
            "narrative_type": "信号",
            "core_concept": "失效条件优先",
        },
    },
    {
        "source_key": "cat_tpl:thread:deep_dive",
        "source_platform": "seed",
        "source_title": "【模板】深度 Thread 骨架",
        "raw_text": "结构：钩子推 → 背景 1 → 证据 2–3 → 风险 → CTA。适合代币/框架长文。",
        "hooks": "一条能让人读完 8 推的钩子",
        "pattern": "钩子 → 背景 → 证据 → 风险 → CTA",
        "emotion": "沉浸",
        "tension": "求知",
        "keywords": ["Thread", "长推", "深度"],
        "tags": ["类目模板", "长推Thread"],
        "factors": {
            "material_category": "thread",
            "is_category_template": True,
            "use_case": "周末深度",
            "structure": [
                "1/N 钩子：反常识或强利益",
                "2–3：背景与定义",
                "4–6：数据/图表证据",
                "7：风险与反方观点",
                "8：结论 + 关注/收藏 CTA",
            ],
            "example": {
                "title": "Thread 钩子案例",
                "hook": "1/8 大多数人看错了这个协议的「真实收益率」。",
                "body": (
                    "2/8 先定义 Real Yield：…\n"
                    "3/8 费用数据来自…\n"
                    "4–6/8 三张图：收入、活跃、FDV 对比\n"
                    "7/8 反方：激励停止后的情景\n"
                    "8/8 结论 + 收藏线程方便复盘"
                ),
            },
            "narrative_type": "长推",
            "core_concept": "钩子决定完读率",
        },
    },
    {
        "source_key": "cat_tpl:capture:flash",
        "source_platform": "seed",
        "source_title": "【模板】快捕碎片升级",
        "raw_text": "结构：原句 → 为什么值得发 → 补一句立场。把灵感碰撞快捕变成可发推草稿。",
        "hooks": "把一句灵感补成可发短推",
        "pattern": "原句 → 价值 → 立场",
        "emotion": "轻快",
        "tension": "稍纵即逝",
        "keywords": ["快捕", "碎片", "灵感"],
        "tags": ["类目模板", "快捕碎片"],
        "factors": {
            "material_category": "capture",
            "is_category_template": True,
            "use_case": "快捕后一键生成",
            "structure": [
                "保留原始金句",
                "补：场景或数据锚点",
                "补：你的一句判断或问题",
            ],
            "example": {
                "title": "快捕升级案例",
                "hook": "原句：流动性在上方。",
                "body": (
                    "升级：Coinglass 显示上方清算更厚——插针偏好向上扫的概率讨论。\n"
                    "立场：不猜方向，止损避开密集区。"
                ),
            },
            "narrative_type": "灵感",
            "core_concept": "碎片 → 可发推",
        },
    },
    {
        "source_key": "cat_tpl:general:storytelling",
        "source_platform": "seed",
        "source_title": "【模板】通用叙事四段",
        "raw_text": "结构：冲突 → 证据 → 洞察 → 行动。万金油类目。",
        "hooks": "先给冲突，再给结论",
        "pattern": "冲突 → 证据 → 洞察 → 行动",
        "emotion": "中性",
        "tension": "认知差",
        "keywords": ["叙事", "结构", "通用"],
        "tags": ["类目模板", "通用灵感"],
        "factors": {
            "material_category": "general",
            "is_category_template": True,
            "use_case": "未归类灵感",
            "structure": ["冲突/反差", "1–2 个证据", "洞察一句", "读者可执行的微行动"],
            "example": {
                "title": "叙事四段案例",
                "hook": "大家都在喊突破，成交量却在下降。",
                "body": (
                    "冲突：价格新高 vs 量能背离。\n"
                    "证据：近 5 根 4H 量能递减。\n"
                    "洞察：趋势还在，但追价赔率变差。\n"
                    "行动：等回踩或量能放大再评估。"
                ),
            },
            "narrative_type": "通用",
            "core_concept": "冲突开头",
        },
    },
]


def seed_category_templates(*, db_path=None, dry_run: bool = False) -> Dict[str, Any]:
    init_db(db_path)
    written = 0
    keys: List[str] = []
    for item in SEED_TEMPLATES:
        keys.append(str(item["source_key"]))
        if dry_run:
            continue
        create_template(
            source_platform=str(item.get("source_platform") or "seed"),
            source_key=str(item["source_key"]),
            source_title=str(item.get("source_title") or ""),
            raw_text=str(item.get("raw_text") or ""),
            pattern=str(item.get("pattern") or ""),
            emotion=str(item.get("emotion") or ""),
            tension=str(item.get("tension") or ""),
            keywords=item.get("keywords") or [],
            hooks=str(item.get("hooks") or ""),
            tags=item.get("tags") or [],
            factors=item.get("factors") if isinstance(item.get("factors"), dict) else {},
            quality="seed",
            status="active",
            provenance={"kind": "category_template_seed"},
            db_path=db_path,
        )
        written += 1
    return {
        "dry_run": dry_run,
        "planned": len(SEED_TEMPLATES),
        "written": written,
        "source_keys": keys,
        "by_category": _count_by_category(),
    }


def _count_by_category() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for item in SEED_TEMPLATES:
        factors = item.get("factors") or {}
        cat = str(factors.get("material_category") or "unknown")
        out[cat] = out.get(cat, 0) + 1
    return out


def main(argv: List[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    dry = "--dry-run" in args
    result = seed_category_templates(dry_run=dry)
    print(
        f"[seed_category_templates] dry_run={result['dry_run']} "
        f"planned={result['planned']} written={result['written']}"
    )
    print(f"  by_category={result['by_category']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
