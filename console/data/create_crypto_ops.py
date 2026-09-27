from pathlib import Path
import json

root = Path("crypto-ops")
root.mkdir(exist_ok=True)

def w(rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip() + "\n", encoding="utf-8")

w("README.md", """
# crypto-ops
币圈运营话题库 v1.0（2026-09-26 冻结）
一篇一个 ID，关联用 [[P0-01]]。状态：[空] [草稿] [复盘] [过期]
""")

w("CHANGELOG.md", """
# CHANGELOG
## v1.0 - 2026-09-26
结构冻结。草稿见各文件 status。
""")

w("00-rules.md", """
---
id: 00
version: v1.0
status: [草稿]
---
# 字段约定
ID / 级别 / 大类 / 小类 / 标题 / 状态 / 变现方式 / 标的范围 / 共识 / 术语 / 刺激源 / 传导 / 影响标的 / 好情况 / 失效 / 内容钩子 / 案例 / 关联ID / 备注
禁止编造数字、禁止改 ID、禁止宏观利好直接落到土狗。
""")

w("01-priority.md", """
---
id: 01
version: v1.0
status: [草稿]
---
# 变现优先级
P0：BTC宏观ETF清算 / 上币合约热钱包 / Meme轮动
P1：AI Agent / ETH SOL / 空投积分
P2：RWA 稳定币 合规
P3：理念技术
失效：P2/P3 塞进每日栏目
关联：[[P0-01]] [[P0-03]] [[K-01]]
""")

w("glossary.md", """
---
id: glossary
version: v1.0
status: [草稿]
---
# 术语表
共识 / 叙事 / BTC.D / FDV / OI / 强度量级 / 未共振 / 轧空 / 分配 / 数字黄金打折
""")

w("p0/P0-01-etf.md", """
---
id: P0-01
version: v1.0
status: [草稿]
---
# ETF与BTC流向
共识：ETF连续流入=机构买储备；流出山寨先失血。不是山寨季开关。
传导：BTC → ETH → 山寨另看主导率与稳定币
失效：流入在但利率/DXY急升；BTC跟纳指黄金不跟
关联：[[A-01]] [[A-03]] [[K-01]]
""")

w("p0/P0-02-dominance.md", """
---
id: P0-02
version: v1.0
status: [草稿]
---
# 主导率与山寨季开关
共识：BTC.D升=大饼季。只涨狗不是山寨季。
关联：[[K-01]] [[A-04]]
""")

w("p0/P0-03-listing.md", """
---
id: P0-03
version: v1.0
status: [草稿]
---
# 上币与合约上线
共识：涨在传闻，跌在公告后流动性到位。
关联：[[C-01]] [[C-02]] [[D-02]]
""")

w("p0/P0-04-unlock.md", """
---
id: P0-04
version: v1.0
status: [空]
---
# 解锁日历
共识：无新叙事的大额解锁先当抛压
关联：[[I-01]] [[I-02]]
""")

w("p0/P0-05-heat.md", """
---
id: P0-05
version: v1.0
status: [草稿]
---
# 热钱强度与量级
共识：量级看金额，强度看自身分位。
关联：[[H-01]] [[H-02]] [[H-03]]
""")

w("p0/P0-06-liquidation.md", """
---
id: P0-06
version: v1.0
status: [空]
---
# 爆仓与清算地图
备注：待补口径
关联：[[H-01]]
""")

w("p0/P0-07-spot-lead.md", """
---
id: P0-07
version: v1.0
status: [草稿]
---
# 现货流入领先价格
规则：自身高分位流入 → 1-4根15m确认 → 合约不反向 → 流入不得滞后
关联：[[H-03]] [[P0-05]]
""")

w("a/A-01-digital-gold.md", """
---
id: A-01
version: v1.0
status: [草稿]
---
# 数字黄金成立
共识：成立时先写储备，不写山寨轮动。
失效：BTC跟纳指/SOX，黄金不跟
关联：[[A-02]] [[A-03]] [[A-04]] [[K-01]] [[P0-01]]
""")

w("a/A-02-dxy-rates.md", """
---
id: A-02
version: v1.0
status: [草稿]
---
# DXY与实际利率
刺激源：利率上，黄金与BTC受压
关联：[[A-01]]
""")

w("a/A-03-etf-flow.md", """
---
id: A-03
version: v1.0
status: [草稿]
---
# 现货ETF流入
关联：[[P0-01]] [[A-01]]
""")

w("a/A-04-btc-d.md", """
---
id: A-04
version: v1.0
status: [草稿]
---
# 主导率
关联：[[P0-02]] [[K-01]]
""")

w("a/A-05-halving.md", """
---
id: A-05
version: v1.0
status: [空]
---
# 减半与周期
备注：只写统计，不写宿命
关联：[[K-01]]
""")

for rel, id_, title in [
    ("b/B-01-eth-vs-btc.md","B-01","ETH相对BTC"),
    ("b/B-02-l2-fees.md","B-02","L2能否吃主网费用"),
    ("b/B-03-sol-beta.md","B-03","SOL零售贝塔"),
    ("b/B-04-new-l1.md","B-04","新L1上所泡沫"),
]:
    w(rel, f"""
---
id: {id_}
version: v1.0
status: [空]
---
# {title}
共识：[空]
关联：[空]
""")

w("c/C-01-listing-pricing.md", """
---
id: C-01
version: v1.0
status: [草稿]
---
# 上币公告定价
共识：传闻涨、公告跌
关联：[[P0-03]]
""")
w("c/C-02-hot-wallet.md", """
---
id: C-02
version: v1.0
status: [空]
---
# 热钱包异动
关联：[[P0-03]] [[C-01]]
""")
w("c/C-03-exchange-token.md", """
---
id: C-03
version: v1.0
status: [空]
---
# 平台币回购与罚单
""")

w("d/D-01-chain-rotation.md", """
---
id: D-01
version: v1.0
status: [空]
---
# 主战场换链
关联：[[D-02]]
""")
w("d/D-02-copycat.md", """
---
id: D-02
version: v1.0
status: [草稿]
---
# 同叙事仿盘
共识：第3个仿盘多是出货工具
关联：[[P0-03]] [[D-01]]
""")
w("d/D-03-listing-trap.md", """
---
id: D-03
version: v1.0
status: [空]
---
# 上所流动性陷阱
关联：[[P0-03]]
""")
w("d/D-04-revival.md", """
---
id: D-04
version: v1.0
status: [空]
---
# 老币复活
关联：[[D-01]]
""")

w("e/E-01-ai-skin.md", """
---
id: E-01
version: v1.0
status: [草稿]
---
# AI皮与真订单
共识：先买标签，再验谁付钱。
失效：只有融资和改名
禁止：AI发布=全板块隔夜
关联：[[E-02]] [[E-03]] [[D-02]]
""")
w("e/E-02-agent-pay.md", """
---
id: E-02
version: v1.0
status: [空]
---
# Agent支付
关联：[[E-01]]
""")
w("e/E-03-depin.md", """
---
id: E-03
version: v1.0
status: [空]
---
# DePIN利用率
关联：[[E-01]]
""")

w("f/F-01-mint-redeem.md", """
---
id: F-01
version: v1.0
status: [草稿]
---
# 铸造赎回
共识：大赎回先砸山寨
关联：[[K-01]]
""")
w("f/F-02-depeg.md", """
---
id: F-02
version: v1.0
status: [空]
---
# 脱锚应急
关联：[[F-01]]
""")

w("g/G-01-reserve.md", """
---
id: G-01
version: v1.0
status: [草稿]
---
# 机构认储备
失效：写成山寨季引擎
关联：[[A-01]] [[G-02]]
""")
w("g/G-02-tbill.md", """
---
id: G-02
version: v1.0
status: [空]
---
# 国债上链
关联：[[G-01]] [[F-01]]
""")

w("h/H-01-oi-diverge.md", """
---
id: H-01
version: v1.0
status: [草稿]
---
# 价与OI未共振
共识：价升OI降，优先当轧空
案例：SENA（待复盘）
关联：[[P0-05]] [[H-02]]
""")
w("h/H-02-spot-out-price-up.md", """
---
id: H-02
version: v1.0
status: [草稿]
---
# 现货流出价格不跌
共识：现货净卖不等于交易所流出；永续可单独定价
案例：SENA（待复盘）
关联：[[H-01]] [[H-03]]
""")
w("h/H-03-inflow-price.md", """
---
id: H-03
version: v1.0
status: [草稿]
---
# 流入量价齐升
案例：$PUMP 15m 两段现货净买入领先、价格后确认
关联：[[P0-05]] [[P0-07]] [[H-01]] [[H-02]]
""")

w("i/I-01-fdv.md", """
---
id: I-01
version: v1.0
status: [空]
---
# 高FDV低流通
关联：[[P0-04]]
""")
w("i/I-02-team-wallet.md", """
---
id: I-02
version: v1.0
status: [空]
---
# 团队钱包
关联：[[P0-04]] [[C-02]]
""")

w("j/J-01-enforcement.md", """
---
id: J-01
version: v1.0
status: [空]
---
# 执法点名
""")
w("j/J-02-hack.md", """
---
id: J-02
version: v1.0
status: [空]
---
# 桥与黑客
""")

w("k/K-01-altseason.md", """
---
id: K-01
version: v1.0
status: [草稿]
---
# 山寨季判定
三件套：BTC.D下降或走平；稳定币净铸造；ETF/BTC稳定
失效：只有meme；RWA/ETF写成山寨引擎
关联：[[P0-02]] [[A-04]] [[F-01]]
""")

w("m/M-table.md", """
---
id: M
version: v1.0
status: [草稿]
---
# 消息刺激总表
M-01 ETF连续流入 → BTC → ETH
M-02 一线所上币 → 该小币 → 仿盘
M-03 名人转推 → meme
M-04 AI大厂发布 → AI皮
M-05 大额解锁 → 该币
M-06 稳定币大赎回 → 全市场
""")

(root / "taxonomy.json").write_text(json.dumps({
  "version": "v1.0",
  "daily": ["P0-01","P0-02","P0-03","P0-04","P0-05","P0-06","P0-07"],
  "categories": {
    "A": ["A-01","A-02","A-03","A-04","A-05"],
    "B": ["B-01","B-02","B-03","B-04"],
    "C": ["C-01","C-02","C-03"],
    "D": ["D-01","D-02","D-03","D-04"],
    "E": ["E-01","E-02","E-03"],
    "F": ["F-01","F-02"],
    "G": ["G-01","G-02"],
    "H": ["H-01","H-02","H-03"],
    "I": ["I-01","I-02"],
    "J": ["J-01","J-02"],
    "K": ["K-01"]
  }
}, ensure_ascii=False, indent=2), encoding="utf-8")

print("created", root.resolve())
print("files", len(list(root.rglob("*"))))