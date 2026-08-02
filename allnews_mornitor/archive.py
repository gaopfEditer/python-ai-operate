# coding=utf-8
"""头部流量判定：中位数以上自动归档 + 手动归档。"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

from allnews_mornitor.models import ArchiveRecord, Post
from allnews_mornitor import store


def compute_score(post: Post, weights: Optional[Dict[str, float]] = None) -> float:
    w = weights or {
        "likes": 1.0,
        "comments": 2.0,
        "collects": 1.5,
        "shares": 1.2,
        "views": 0.01,
    }
    return (
        post.likes * float(w.get("likes", 1.0))
        + post.comments * float(w.get("comments", 2.0))
        + post.collects * float(w.get("collects", 1.5))
        + post.shares * float(w.get("shares", 1.2))
        + post.views * float(w.get("views", 0.01))
    )


def _median(values: List[float]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    return float(statistics.median(vals))


def estimate_medians(
    platform: str,
    batch: List[Post],
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """返回 (median_likes, median_comments, median_score)。"""
    cfg = cfg or (store.load_config().get("archive") or {})
    min_likes = int(cfg.get("min_likes_for_stats") or 0)
    min_comments = int(cfg.get("min_comments_for_stats") or 0)

    samples = store.platform_samples(platform)
    # 合并本批
    rows = list(samples)
    for p in batch:
        rows.append(
            {
                "likes": p.likes,
                "comments": p.comments,
                "score": p.score,
            }
        )

    likes = [
        int(r.get("likes") or 0)
        for r in rows
        if int(r.get("likes") or 0) >= min_likes
    ]
    comments = [
        int(r.get("comments") or 0)
        for r in rows
        if int(r.get("comments") or 0) >= min_comments
    ]
    scores = [float(r.get("score") or 0) for r in rows]
    return _median(likes), _median(comments), _median(scores)


def should_auto_archive(
    post: Post,
    median_likes: Optional[float],
    median_comments: Optional[float],
    median_score: Optional[float],
    mode: str = "both",
) -> Tuple[bool, str]:
    mode = (mode or "both").strip().lower()
    if mode == "likes":
        if median_likes is None:
            return False, "样本不足，无法估点赞中位数"
        ok = post.likes >= median_likes
        return ok, f"likes {post.likes} {'≥' if ok else '<'} median {median_likes:.0f}"
    if mode == "score":
        if median_score is None:
            return False, "样本不足，无法估综合分中位数"
        ok = post.score >= median_score
        return ok, f"score {post.score:.1f} {'≥' if ok else '<'} median {median_score:.1f}"

    # both：点赞与评论都过线（评论中位数为 0 时仍要求 comments>=0）
    if median_likes is None or median_comments is None:
        return False, "样本不足，无法估中位数"
    ok = post.likes >= median_likes and post.comments >= median_comments
    return (
        ok,
        f"likes {post.likes}/med {median_likes:.0f}, comments {post.comments}/med {median_comments:.0f}",
    )


def apply_scores(posts: List[Post], cfg: Optional[Dict[str, Any]] = None) -> List[Post]:
    archive_cfg = (cfg or store.load_config()).get("archive") or {}
    weights = archive_cfg.get("weights") or {}
    for p in posts:
        p.score = compute_score(p, weights)
    return posts


def resolve_candidate_threshold(platform: str, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """合并全局 defaults.candidate 与平台 candidate。"""
    cfg = cfg or store.load_config()
    defaults = ((cfg.get("defaults") or {}).get("candidate") or {})
    plat = ((cfg.get("platforms") or {}).get(platform) or {}).get("candidate") or {}
    out = {
        "min_likes": int(defaults.get("min_likes") or 0),
        "min_comments": int(defaults.get("min_comments") or 0),
        "min_score": float(defaults.get("min_score") or 0),
        "require": str(defaults.get("require") or "all").lower(),
    }
    for k in ("min_likes", "min_comments", "min_score", "require"):
        if k in plat and plat[k] is not None:
            if k == "require":
                out[k] = str(plat[k]).lower()
            elif k == "min_score":
                out[k] = float(plat[k] or 0)
            else:
                out[k] = int(plat[k] or 0)
    return out


def resolve_crawl_interval_min(platform: str, cfg: Optional[Dict[str, Any]] = None) -> int:
    cfg = cfg or store.load_config()
    defaults = cfg.get("defaults") or {}
    plat = (cfg.get("platforms") or {}).get(platform) or {}
    val = plat.get("crawl_interval_min")
    if val is None or val == "":
        val = defaults.get("crawl_interval_min", 60)
    try:
        return max(5, int(val))
    except (TypeError, ValueError):
        return 60


def passes_candidate_threshold(post: Post, cfg: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """热度是否达到进入候选池的门槛。"""
    th = resolve_candidate_threshold(post.platform, cfg)
    checks = []
    if th["min_likes"] > 0:
        checks.append(("likes", post.likes >= th["min_likes"], f"赞≥{th['min_likes']}"))
    if th["min_comments"] > 0:
        checks.append(("comments", post.comments >= th["min_comments"], f"评≥{th['min_comments']}"))
    if th["min_score"] > 0:
        checks.append(("score", post.score >= th["min_score"], f"分≥{th['min_score']}"))
    if not checks:
        return True, "无门槛"
    require = th.get("require") or "all"
    if require == "any":
        ok = any(c[1] for c in checks)
    else:
        ok = all(c[1] for c in checks)
    detail = ", ".join(
        f"{c[2]}{'✓' if c[1] else '✗'}" for c in checks
    )
    return ok, detail


def filter_candidates(posts: List[Post], cfg: Optional[Dict[str, Any]] = None) -> Tuple[List[Post], List[Dict[str, Any]]]:
    """返回 (进入候选池的帖子, 被门槛过滤的摘要)。"""
    cfg = cfg or store.load_config()
    kept: List[Post] = []
    rejected: List[Dict[str, Any]] = []
    for p in posts:
        ok, reason = passes_candidate_threshold(p, cfg)
        if ok:
            kept.append(p)
        else:
            rejected.append(
                {
                    "post_id": p.post_id,
                    "platform": p.platform,
                    "title": p.title,
                    "likes": p.likes,
                    "comments": p.comments,
                    "score": p.score,
                    "reason": reason,
                }
            )
    return kept, rejected


def auto_archive_batch(posts: List[Post]) -> Dict[str, Any]:
    """
    打分 → 热度门槛入候选池 → 中位数自动归档。
    """
    if not posts:
        return {
            "archived": 0,
            "candidates": 0,
            "rejected": 0,
            "by_platform": {},
            "items": [],
            "candidate_items": [],
        }

    cfg = store.load_config()
    archive_cfg = cfg.get("archive") or {}
    mode = str(archive_cfg.get("mode") or "both")
    posts = apply_scores(posts, cfg)

    # 全量样本仍写入滚动窗口（含未过门槛的），便于中位数稳定
    by_plat: Dict[str, List[Post]] = {}
    for p in posts:
        by_plat.setdefault(p.platform, []).append(p)
    for platform, batch in by_plat.items():
        store.append_platform_samples(platform, batch)

    candidate_posts, rejected = filter_candidates(posts, cfg)
    cand_n = store.upsert_candidates(candidate_posts)

    archived = 0
    details = []
    cand_by_plat: Dict[str, List[Post]] = {}
    for p in candidate_posts:
        cand_by_plat.setdefault(p.platform, []).append(p)

    for platform, batch in cand_by_plat.items():
        ml, mc, ms = estimate_medians(platform, batch, archive_cfg)
        for p in batch:
            ok, reason = should_auto_archive(p, ml, mc, ms, mode=mode)
            if not ok:
                continue
            rec = ArchiveRecord.from_post(
                p,
                archive_type="auto",
                reason=reason,
                median_likes=ml,
                median_comments=mc,
            )
            is_new = store.save_archive_record(rec)
            archived += 1 if is_new else 0
            details.append(
                {
                    "post_id": p.post_id,
                    "platform": platform,
                    "title": p.title,
                    "reason": reason,
                    "new": is_new,
                }
            )

    # 卡片展示：优先展示进入候选的，附带门槛信息
    cand_ids = {p.post_id for p in candidate_posts}
    items = []
    for p in posts:
        d = p.to_dict()
        d["in_candidates"] = p.post_id in cand_ids
        if not d["in_candidates"]:
            ok, reason = passes_candidate_threshold(p, cfg)
            d["gate_reason"] = reason
        else:
            d["gate_reason"] = "已入候选"
        items.append(d)
    items.sort(
        key=lambda x: (
            1 if x.get("in_candidates") else 0,
            float(x.get("score") or 0),
            int(x.get("likes") or 0),
        ),
        reverse=True,
    )

    store.save_last_batch(
        items,
        meta={
            "archived": archived,
            "candidates": cand_n,
            "rejected": len(rejected),
            "total_fetched": len(posts),
        },
    )

    return {
        "archived": archived,
        "candidates": cand_n,
        "rejected": len(rejected),
        "details": details,
        "rejected_samples": rejected[:20],
        "by_platform": {k: len(v) for k, v in by_plat.items()},
        "candidate_by_platform": {k: len(v) for k, v in cand_by_plat.items()},
        "items": items,
        "candidate_items": [p.to_dict() for p in candidate_posts],
        "total_fetched": len(posts),
    }


def manual_archive(post_id: str = "", post: Optional[Dict[str, Any]] = None, note: str = "") -> Dict[str, Any]:
    """手动归档：从候选池按 id 取，或直接提交帖子 JSON。"""
    src = None
    if post_id:
        for it in store.load_candidates():
            if str(it.get("post_id")) == post_id:
                src = it
                break
        if src is None:
            for it in store.load_archive():
                if str(it.get("post_id")) == post_id:
                    return {"success": False, "error": "已在归档库中"}
            return {"success": False, "error": "候选中未找到该帖子"}
    elif post:
        src = post
    else:
        return {"success": False, "error": "需要 post_id 或 post"}

    p = Post.from_dict(src)
    p = apply_scores([p])[0]
    rec = ArchiveRecord.from_post(
        p,
        archive_type="manual",
        reason=note or "手动归档",
    )
    is_new = store.save_archive_record(rec)
    return {"success": True, "new": is_new, "record": rec.to_dict()}
