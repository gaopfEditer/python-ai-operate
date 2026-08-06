# coding=utf-8
"""平台适配器基类与注册表。"""

from __future__ import annotations

from typing import Any, Dict, List, Type

from allnews_mornitor.models import Post
from allnews_mornitor import archive, store


class BasePlatform:
    id: str = ""
    name: str = ""

    def enabled(self) -> bool:
        cfg = store.load_config().get("platforms") or {}
        p = cfg.get(self.id) or {}
        return bool(p.get("enabled", True))

    def entry_urls(self) -> List[str]:
        cfg = store.load_config().get("platforms") or {}
        p = cfg.get(self.id) or {}
        urls = p.get("entry_urls") or []
        return [str(u) for u in urls if str(u).strip()]

    def fetch(self, driver=None) -> List[Post]:
        raise NotImplementedError


_REGISTRY: Dict[str, Type[BasePlatform]] = {}


def register(cls: Type[BasePlatform]) -> Type[BasePlatform]:
    _REGISTRY[cls.id] = cls
    return cls


def get_platform(platform_id: str) -> BasePlatform:
    cls = _REGISTRY.get(platform_id)
    if not cls:
        raise KeyError(f"未知平台: {platform_id}")
    return cls()


def list_platforms() -> List[Dict[str, Any]]:
    cfg = store.load_config()
    plats_cfg = cfg.get("platforms") or {}
    defaults = cfg.get("defaults") or {}
    schedule = (store.load_schedule_state().get("platforms") or {})
    rows = []
    for pid, cls in _REGISTRY.items():
        meta = plats_cfg.get(pid) or {}
        th = archive.resolve_candidate_threshold(pid, cfg)
        interval = archive.resolve_crawl_interval_min(pid, cfg)
        last = schedule.get(pid) or {}
        rows.append(
            {
                "id": pid,
                "name": meta.get("name") or cls.name or pid,
                "enabled": bool(meta.get("enabled", True)),
                "entry_urls": meta.get("entry_urls") or [],
                "crawl_interval_min": interval,
                "crawl_interval_inherited": meta.get("crawl_interval_min") in (None, ""),
                "default_interval_min": int(defaults.get("crawl_interval_min") or 60),
                "candidate": th,
                "last_crawl_at": last.get("last_crawl_at") or "",
            }
        )
    return rows


def all_enabled_ids() -> List[str]:
    return [p["id"] for p in list_platforms() if p.get("enabled")]


def update_platform_config(platform_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """更新单个平台配置并写回 yaml。"""
    cfg = store.load_config()
    plats = cfg.setdefault("platforms", {})
    cur = dict(plats.get(platform_id) or {})
    if "enabled" in patch:
        cur["enabled"] = bool(patch["enabled"])
    if "name" in patch and str(patch["name"]).strip():
        cur["name"] = str(patch["name"]).strip()
    if "crawl_interval_min" in patch:
        v = patch["crawl_interval_min"]
        if v is None or v == "" or v == "default":
            cur["crawl_interval_min"] = None
        else:
            cur["crawl_interval_min"] = max(5, int(v))
    if "candidate" in patch and isinstance(patch["candidate"], dict):
        cand = dict(cur.get("candidate") or {})
        for k in ("min_likes", "min_comments", "min_score", "require"):
            if k in patch["candidate"]:
                cand[k] = patch["candidate"][k]
        cur["candidate"] = cand
    if "entry_urls" in patch and isinstance(patch["entry_urls"], list):
        cur["entry_urls"] = [str(u).strip() for u in patch["entry_urls"] if str(u).strip()]
    plats[platform_id] = cur
    store.save_config(cfg)
    return next((p for p in list_platforms() if p["id"] == platform_id), cur)


def update_defaults(patch: Dict[str, Any]) -> Dict[str, Any]:
    cfg = store.load_config()
    defaults = dict(cfg.get("defaults") or {})
    if "crawl_interval_min" in patch:
        defaults["crawl_interval_min"] = max(5, int(patch["crawl_interval_min"]))
    if "candidate" in patch and isinstance(patch["candidate"], dict):
        cand = dict(defaults.get("candidate") or {})
        for k in ("min_likes", "min_comments", "min_score", "require"):
            if k in patch["candidate"]:
                cand[k] = patch["candidate"][k]
        defaults["candidate"] = cand
    cfg["defaults"] = defaults
    store.save_config(cfg)
    return defaults
