# coding=utf-8
"""动态门槛：当日滑动窗口百分位。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return 7.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    p = max(0.0, min(100.0, p))
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def classify_value_kind(eval_result: Dict[str, Any]) -> str:
    """时效爆发 vs 长青知识。"""
    cat = str(eval_result.get("category") or "").lower()
    fmt = str(eval_result.get("format") or "").lower()
    if cat in ("news",) or "时效" in str(eval_result.get("reason") or ""):
        return "timely"
    if cat in ("playbook", "insight") or fmt in ("list", "thread", "case"):
        return "evergreen"
    return "mixed"


def compute_dynamic_threshold(
    scores_today: List[float],
    *,
    kind: str = "mixed",
    default: float = 7.0,
    lo: float = 5.5,
    hi: float = 8.5,
) -> float:
    """
    取当日分数约 P85–P90 作为门槛；样本不足用 default。
    长青略降门槛，时效略抬高。
    """
    vals = sorted(float(s) for s in scores_today if s is not None)
    if len(vals) < 5:
        base = default
    else:
        # 前 10%–15% ≈ P85–P90
        p = 88.0 if kind == "timely" else (85.0 if kind == "evergreen" else 87.0)
        base = percentile(vals, p)
    if kind == "evergreen":
        base -= 0.3
    elif kind == "timely":
        base += 0.2
    return round(max(lo, min(hi, base)), 2)


def load_today_value_scores() -> List[float]:
    """从 DB 取今日 value_return 分数。"""
    from signals.card_db import connect, init_db

    init_db()
    now = datetime.now(timezone.utc).astimezone()
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ts = int(day0.timestamp())
    scores: List[float] = []
    try:
        with connect() as conn:
            # 优先列；若无列则从 extra 不好扫，用 value_score 列
            cols = {r[1] for r in conn.execute("PRAGMA table_info(signal_cards)").fetchall()}
            if "value_score" not in cols:
                return scores
            rows = conn.execute(
                """
                SELECT value_score FROM signal_cards
                WHERE value_score IS NOT NULL AND created_at_ts >= ?
                """,
                (start_ts,),
            ).fetchall()
            for r in rows:
                try:
                    scores.append(float(r[0]))
                except Exception:
                    pass
    except Exception:
        pass
    return scores


def resolve_threshold_for_eval(eval_result: Dict[str, Any]) -> Dict[str, Any]:
    kind = classify_value_kind(eval_result)
    today = load_today_value_scores()
    # 把当前分也计入窗口直觉（未入库前）
    cur = eval_result.get("score")
    if cur is not None:
        try:
            today = list(today) + [float(cur)]
        except Exception:
            pass
    thr = compute_dynamic_threshold(today, kind=kind)
    return {"kind": kind, "threshold": thr, "sample_n": len(today)}
