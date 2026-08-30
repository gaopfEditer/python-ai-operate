# coding=utf-8
"""F · KOL 推文：薄封装 signals 抓取 + 正则初筛 + 入库。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from realtime_info.collectors.base import Collector
from realtime_info.config import load_kol_watchlist, module_cfg, module_enabled
from realtime_info.filters import rule_kol_prefilter
from realtime_info.pipeline import ingest_event

logger = logging.getLogger(__name__)


class KolCollector(Collector):
    module = "kol"

    def collect(self) -> List[Dict[str, Any]]:
        if not module_enabled("kol"):
            return []
        watch = load_kol_watchlist()
        users = [
            u
            for u in (watch.get("users") or [])
            if isinstance(u, dict) and u.get("enabled") and u.get("handle")
        ]
        if not users:
            logger.info("kol: watchlist 无 enabled 用户，跳过")
            return []

        cfg = module_cfg("kol")
        limit = int(cfg.get("max_tweets_per_user") or 20)
        out: List[Dict[str, Any]] = []
        try:
            from datetime import datetime, timedelta, timezone

            from signals.crawl import crawl_user_timeline
        except Exception as e:
            logger.warning("kol: 无法导入 signals.crawl: %s", e)
            return []

        since = datetime.now(timezone.utc) - timedelta(hours=48)
        for u in users:
            handle = str(u["handle"]).lstrip("@")
            try:
                result = crawl_user_timeline(
                    handle, since=since, max_tweets=limit
                ) or {}
            except Exception as e:
                logger.warning("kol crawl @%s: %s", handle, e)
                continue
            tweets = []
            if isinstance(result, dict):
                tweets = result.get("items") or result.get("tweets") or []
            elif isinstance(result, list):
                tweets = result
            for t in tweets:
                if not isinstance(t, dict):
                    continue
                text = str(t.get("text") or t.get("full_text") or t.get("content") or "")
                if not rule_kol_prefilter(text):
                    continue
                tid = str(t.get("id") or t.get("tweet_id") or t.get("rest_id") or "")
                out.append(
                    {
                        "handle": handle,
                        "tweet_id": tid,
                        "text": text,
                        "url": t.get("url")
                        or (f"https://x.com/{handle}/status/{tid}" if tid else ""),
                        "created_at": t.get("created_at") or t.get("time") or "",
                    }
                )
        return out

    def run_and_ingest(self, *, skip_llm: Optional[bool] = None, db_path=None) -> List[Dict[str, Any]]:
        cfg = module_cfg("kol")
        if skip_llm is None:
            skip_llm = not bool(cfg.get("use_llm", True))
        results = []
        for payload in self.collect():
            handle = payload["handle"]
            tid = payload.get("tweet_id") or "na"
            fp = f"{handle}:{tid}".lower()
            title = f"[@{handle}] 交易向观点"
            draft = (
                f"@{handle}:\n{payload.get('text')}\n"
                f"{payload.get('url') or ''}\n"
                f"— 待本地审阅，非投资建议"
            )
            r = ingest_event(
                module="kol",
                fingerprint=fp,
                raw=payload,
                title=title,
                draft_text=draft.strip(),
                severity="info",
                skip_llm=bool(skip_llm),
                db_path=db_path,
            )
            results.append(
                {
                    "ok": r.get("ok"),
                    "skipped": r.get("skipped"),
                    "event_id": getattr(r.get("event"), "id", None),
                    "handle": handle,
                }
            )
        return results


def run_kol_once(*, skip_llm: Optional[bool] = None, db_path=None) -> List[Dict[str, Any]]:
    return KolCollector().run_and_ingest(skip_llm=skip_llm, db_path=db_path)
