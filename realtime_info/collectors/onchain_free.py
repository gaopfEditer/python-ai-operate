# coding=utf-8
"""A · 免费链上路径：Etherscan 大额 ETH 转账 + 白名单/CEX 流向粗分。"""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Set

from realtime_info.collectors.base import Collector
from realtime_info.config import env_or, load_entities, module_cfg, module_enabled
from realtime_info.filters import rule_onchain
from realtime_info.pipeline import ingest_event

logger = logging.getLogger(__name__)

ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"


def _addr_set(entities: Dict[str, Any], key: str) -> Dict[str, str]:
    """address(lower) -> label"""
    out: Dict[str, str] = {}
    for item in entities.get(key) or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "")
        for a in item.get("addresses") or []:
            out[str(a).lower()] = label
    return out


def _blacklist(entities: Dict[str, Any]) -> Set[str]:
    block = entities.get("cex_internal_blacklist") or {}
    addrs = block.get("addresses") if isinstance(block, dict) else []
    return {str(a).lower() for a in (addrs or [])}


def _get_json(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "realtime_info/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        import json

        return json.loads(resp.read().decode("utf-8"))


def fetch_eth_price_usd() -> float:
    try:
        data = _get_json(
            "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT"
        )
        return float(data.get("price") or 0)
    except Exception as e:
        logger.warning("eth price: %s", e)
        return 0.0


def fetch_large_eth_txs(api_key: str, min_eth: float = 1000.0) -> List[Dict[str, Any]]:
    """
    使用 Etherscan 账户模块轮询已配置鲸鱼地址的 txlist。
    无鲸鱼地址时：仅记录日志并返回空（避免无差别扫全链）。
    """
    entities = load_entities()
    whales = _addr_set(entities, "whales")
    if not whales:
        logger.info(
            "onchain_free: entities.yaml 中 whales.addresses 为空，跳过轮询"
            "（可后续换成自有免费站爬虫）"
        )
        return []
    if not api_key:
        logger.info("onchain_free: 未设置 ETHERSCAN_API_KEY，跳过")
        return []

    eth_px = fetch_eth_price_usd()
    out: List[Dict[str, Any]] = []
    for addr, label in list(whales.items())[:20]:
        q = urllib.parse.urlencode(
            {
                "chainid": 1,
                "module": "account",
                "action": "txlist",
                "address": addr,
                "page": 1,
                "offset": 20,
                "sort": "desc",
                "apikey": api_key,
            }
        )
        # v2 与 v1 兼容尝试
        urls = [
            f"{ETHERSCAN_V2}?{q}",
            f"https://api.etherscan.io/api?{urllib.parse.urlencode({k: v for k, v in urllib.parse.parse_qsl(q) if k != 'chainid'})}",
        ]
        data = None
        for url in urls:
            try:
                data = _get_json(url)
                break
            except Exception as e:
                logger.debug("etherscan %s: %s", url[:60], e)
        if not isinstance(data, dict):
            continue
        rows = data.get("result")
        if not isinstance(rows, list):
            continue
        for tx in rows:
            try:
                value_wei = int(tx.get("value") or 0)
            except Exception:
                continue
            eth = value_wei / 1e18
            if eth < min_eth:
                continue
            usd = eth * eth_px if eth_px else 0.0
            out.append(
                {
                    "txhash": tx.get("hash"),
                    "from": str(tx.get("from") or "").lower(),
                    "to": str(tx.get("to") or "").lower(),
                    "eth": eth,
                    "usd_value": usd,
                    "symbol": "ETH",
                    "whale_label": label,
                    "whale_address": addr,
                    "timeStamp": tx.get("timeStamp"),
                }
            )
    return out


def classify_flow(
    payload: Dict[str, Any],
    cex: Dict[str, str],
    blacklist: Set[str],
) -> Dict[str, Any]:
    fr = str(payload.get("from") or "").lower()
    to = str(payload.get("to") or "").lower()
    if fr in blacklist or to in blacklist:
        payload["blacklisted"] = True
        payload["flow"] = "internal"
        return payload
    from_cex = fr in cex
    to_cex = to in cex
    if to_cex and not from_cex:
        payload["flow"] = "to_cex"
        payload["flow_label"] = "Whale -> CEX（砸盘预警观察）"
        payload["cex_label"] = cex.get(to, "")
    elif from_cex and not to_cex:
        payload["flow"] = "from_cex"
        payload["flow_label"] = "CEX -> Wallet（吸筹/囤币观察）"
        payload["cex_label"] = cex.get(fr, "")
    else:
        payload["flow"] = "unknown"
        payload["flow_label"] = "未知流向"
    return payload


class OnchainFreeCollector(Collector):
    module = "onchain"

    def collect(self) -> List[Dict[str, Any]]:
        if not module_enabled("onchain"):
            return []
        entities = load_entities()
        cex = _addr_set(entities, "cex_hot_wallets")
        bl = _blacklist(entities)
        api_key = env_or("ETHERSCAN_API_KEY")
        cfg = module_cfg("onchain")
        min_usd = float(cfg.get("min_usd_major") or 5_000_000)
        eth_px = fetch_eth_price_usd() or 3000.0
        min_eth = max(100.0, min_usd / eth_px * 0.5)  # 略放宽抓取，再由 rule 卡死
        raws = fetch_large_eth_txs(api_key, min_eth=min_eth)
        out = []
        for r in raws:
            r = classify_flow(r, cex, bl)
            out.append(r)
        return out

    def run_and_ingest(self, *, skip_llm: bool = True, db_path=None) -> List[Dict[str, Any]]:
        results = []
        for payload in self.collect():
            ok, reason = rule_onchain(payload)
            if not ok:
                results.append({"ok": False, "reason": reason, "tx": payload.get("txhash")})
                continue
            tx = str(payload.get("txhash") or "")
            fp = f"eth:{tx}".lower() if tx else f"eth:{payload.get('from')}:{payload.get('to')}:{payload.get('timeStamp')}"
            title = (
                f"[链上] {payload.get('whale_label') or 'Whale'} "
                f"{payload.get('flow_label') or ''} · "
                f"${payload.get('usd_value', 0):,.0f} ETH"
            )
            draft = (
                f"{title}\n"
                f"from {payload.get('from')}\n"
                f"to {payload.get('to')}\n"
                f"tx {tx}\n"
                f"常见解读仅供观察，非投资建议。"
            )
            r = ingest_event(
                module="onchain",
                fingerprint=fp,
                raw=payload,
                title=title.strip(),
                draft_text=draft,
                severity="high",
                skip_llm=skip_llm,
                db_path=db_path,
            )
            results.append(
                {
                    "ok": r.get("ok"),
                    "skipped": r.get("skipped"),
                    "event_id": getattr(r.get("event"), "id", None),
                    "tx": tx,
                }
            )
        return results


def run_onchain_once(*, skip_llm: bool = True, db_path=None) -> List[Dict[str, Any]]:
    return OnchainFreeCollector().run_and_ingest(skip_llm=skip_llm, db_path=db_path)
