# coding=utf-8
"""配置加载与本地 JSON 存储。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from allnews_mornitor.models import ArchiveRecord, Post

PKG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PKG_DIR.parent
CONFIG_PATH = PKG_DIR / "config.yaml"
DATA_DIR = PROJECT_ROOT / "output" / "allnews_mornitor"
CANDIDATES_PATH = DATA_DIR / "candidates.json"
ARCHIVE_PATH = DATA_DIR / "archive.json"
STATS_PATH = DATA_DIR / "platform_stats.json"

_LOCK = threading.Lock()


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(cfg: Dict[str, Any]) -> None:
    with _LOCK:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


LAST_BATCH_PATH = DATA_DIR / "last_batch.json"
SCHEDULE_PATH = DATA_DIR / "schedule_state.json"


def save_last_batch(posts: List[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None) -> None:
    with _LOCK:
        _write_json(
            LAST_BATCH_PATH,
            {
                "items": posts,
                "count": len(posts),
                "meta": meta or {},
            },
        )


def load_last_batch() -> Dict[str, Any]:
    with _LOCK:
        return _read_json(LAST_BATCH_PATH, {"items": [], "count": 0, "meta": {}})


def load_schedule_state() -> Dict[str, Any]:
    with _LOCK:
        return _read_json(SCHEDULE_PATH, {"platforms": {}})


def touch_schedule(platform_id: str, when: Optional[str] = None) -> None:
    from datetime import datetime

    with _LOCK:
        data = _read_json(SCHEDULE_PATH, {"platforms": {}})
        plats = data.setdefault("platforms", {})
        plats[str(platform_id)] = {
            "last_crawl_at": when or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        _write_json(SCHEDULE_PATH, data)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    ensure_data_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_candidates() -> List[Dict[str, Any]]:
    with _LOCK:
        data = _read_json(CANDIDATES_PATH, {"items": []})
        return list(data.get("items") or [])


def save_candidates(items: List[Dict[str, Any]]) -> None:
    with _LOCK:
        _write_json(CANDIDATES_PATH, {"items": items, "count": len(items)})


def upsert_candidates(posts: List[Post]) -> int:
    """合并候选池（按 post_id 去重，保留互动更高者）。"""
    with _LOCK:
        existing = {
            str(x.get("post_id")): x
            for x in (_read_json(CANDIDATES_PATH, {"items": []}).get("items") or [])
            if isinstance(x, dict) and x.get("post_id")
        }
        n = 0
        for p in posts:
            d = p.to_dict()
            pid = d["post_id"]
            prev = existing.get(pid)
            if not prev or float(d.get("score") or 0) >= float(prev.get("score") or 0):
                existing[pid] = d
                n += 1
        items = sorted(
            existing.values(),
            key=lambda x: (float(x.get("score") or 0), int(x.get("likes") or 0)),
            reverse=True,
        )
        _write_json(CANDIDATES_PATH, {"items": items, "count": len(items)})
        return n


def load_archive() -> List[Dict[str, Any]]:
    with _LOCK:
        data = _read_json(ARCHIVE_PATH, {"items": []})
        return list(data.get("items") or [])


def save_archive_record(rec: ArchiveRecord) -> bool:
    """写入归档；已存在同 post_id 则更新（保留更早 archived_at / 合并 factors）。"""
    with _LOCK:
        data = _read_json(ARCHIVE_PATH, {"items": []})
        items = list(data.get("items") or [])
        found = False
        for i, old in enumerate(items):
            if str(old.get("post_id")) == rec.post_id:
                merged = rec.to_dict()
                if old.get("archived_at"):
                    merged["archived_at"] = old["archived_at"]
                factors = dict(old.get("factors") or {})
                factors.update(rec.factors or {})
                merged["factors"] = factors
                if old.get("archive_type") == "manual" and rec.archive_type == "auto":
                    merged["archive_type"] = "manual"
                items[i] = merged
                found = True
                break
        if not found:
            items.insert(0, rec.to_dict())
        _write_json(ARCHIVE_PATH, {"items": items, "count": len(items)})
        return not found


def update_archive_item(post_id: str, patch: Dict[str, Any]) -> bool:
    with _LOCK:
        data = _read_json(ARCHIVE_PATH, {"items": []})
        items = list(data.get("items") or [])
        for i, old in enumerate(items):
            if str(old.get("post_id")) == str(post_id):
                merged = dict(old)
                merged.update(patch or {})
                items[i] = merged
                _write_json(ARCHIVE_PATH, {"items": items, "count": len(items)})
                return True
        return False


def append_platform_samples(platform: str, posts: List[Post]) -> None:
    """滚动样本，供中位数估算。"""
    cfg = load_config()
    window = int((cfg.get("archive") or {}).get("rolling_window") or 200)
    with _LOCK:
        data = _read_json(STATS_PATH, {"platforms": {}})
        plats = data.setdefault("platforms", {})
        bucket = list(plats.get(platform) or [])
        for p in posts:
            bucket.append(
                {
                    "likes": p.likes,
                    "comments": p.comments,
                    "collects": p.collects,
                    "shares": p.shares,
                    "views": p.views,
                    "score": p.score,
                    "post_id": p.post_id,
                    "fetched_at": p.fetched_at,
                }
            )
        plats[platform] = bucket[-window:]
        _write_json(STATS_PATH, data)


def platform_samples(platform: str) -> List[Dict[str, Any]]:
    with _LOCK:
        data = _read_json(STATS_PATH, {"platforms": {}})
        return list((data.get("platforms") or {}).get(platform) or [])
