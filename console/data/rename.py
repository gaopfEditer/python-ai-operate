from pathlib import Path

root = Path("crypto-ops")

folder_map = {
    "p0": "每日栏目",
    "a": "A-BTC宏观",
    "b": "B-ETH与公链",
    "c": "C-交易所",
    "d": "D-Meme",
    "e": "E-AI",
    "f": "F-稳定币",
    "g": "G-RWA",
    "h": "H-热钱盘面",
    "i": "I-代币结构",
    "j": "J-监管安全",
    "k": "K-周期",
    "m": "M-总表",
}

file_map = {
    "00-rules.md": "00-字段约定.md",
    "01-priority.md": "01-变现优先级.md",
    "glossary.md": "术语表.md",
    "P0-01-etf.md": "P0-01-ETF与BTC流向.md",
    "P0-02-dominance.md": "P0-02-主导率与山寨季开关.md",
    "P0-03-listing.md": "P0-03-上币与合约上线.md",
    "P0-04-unlock.md": "P0-04-解锁日历.md",
    "P0-05-heat.md": "P0-05-热钱强度与量级.md",
    "P0-06-liquidation.md": "P0-06-爆仓与清算地图.md",
    "P0-07-spot-lead.md": "P0-07-现货流入领先价格.md",
    "A-01-digital-gold.md": "A-01-数字黄金成立.md",
    "A-02-dxy-rates.md": "A-02-DXY与实际利率.md",
    "A-03-etf-flow.md": "A-03-现货ETF流入.md",
    "A-04-btc-d.md": "A-04-比特币主导率.md",
    "A-05-halving.md": "A-05-减半与周期.md",
    "B-01-eth-vs-btc.md": "B-01-ETH相对BTC.md",
    "B-02-l2-fees.md": "B-02-L2能否吃主网费用.md",
    "B-03-sol-beta.md": "B-03-SOL零售贝塔.md",
    "B-04-new-l1.md": "B-04-新L1上所泡沫.md",
    "C-01-listing-pricing.md": "C-01-上币公告定价.md",
    "C-02-hot-wallet.md": "C-02-热钱包异动.md",
    "C-03-exchange-token.md": "C-03-平台币回购与罚单.md",
    "D-01-chain-rotation.md": "D-01-主战场换链.md",
    "D-02-copycat.md": "D-02-同叙事仿盘.md",
    "D-03-listing-trap.md": "D-03-上所流动性陷阱.md",
    "D-04-revival.md": "D-04-老币复活.md",
    "E-01-ai-skin.md": "E-01-AI皮与真订单.md",
    "E-02-agent-pay.md": "E-02-Agent支付.md",
    "E-03-depin.md": "E-03-DePIN利用率.md",
    "F-01-mint-redeem.md": "F-01-稳定币铸造赎回.md",
    "F-02-depeg.md": "F-02-脱锚应急.md",
    "G-01-reserve.md": "G-01-机构认储备.md",
    "G-02-tbill.md": "G-02-国债上链.md",
    "H-01-oi-diverge.md": "H-01-价与OI未共振.md",
    "H-02-spot-out-price-up.md": "H-02-现货流出价格不跌.md",
    "H-03-inflow-price.md": "H-03-流入量价齐升.md",
    "I-01-fdv.md": "I-01-高FDV低流通.md",
    "I-02-team-wallet.md": "I-02-团队钱包.md",
    "J-01-enforcement.md": "J-01-执法点名.md",
    "J-02-hack.md": "J-02-桥与黑客.md",
    "K-01-altseason.md": "K-01-山寨季判定.md",
    "M-table.md": "M-消息刺激总表.md",
}

for p in root.rglob("*"):
    if p.is_file() and p.name in file_map:
        p.rename(p.with_name(file_map[p.name]))

for old, new in folder_map.items():
    src = root / old
    if src.exists():
        src.rename(root / new)

print("done")
for p in sorted(root.rglob("*.md")):
    print(p.relative_to(root))