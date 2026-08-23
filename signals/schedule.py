# coding=utf-8
"""列表信号 CDP 分时频率（北京时间 UTC+8）。

时段与建议触发间隔：
  20:00–01:30  主高峰   3–5 分钟
  07:30–10:30  次高峰   5–8 分钟
  10:30–15:30  午后     15–20 分钟
  15:30–20:00  欧盘过渡 10–15 分钟
  01:30–07:30  深度垃圾 休眠 或 30–60 分钟巡检
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

BJ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class Slot:
    id: str
    label: str
    weight: str
    # 建议区间（分钟）；sleep=True 表示本时段默认不触发
    min_min: float
    max_min: float
    sleep: bool = False
    # 巡检模式（仅 deep 槽）用的区间
    patrol_min: float = 30.0
    patrol_max: float = 60.0


# 按「日起点分钟」闭开区间表，跨午夜用两段 peak
SLOTS: Dict[str, Slot] = {
    "peak": Slot("peak", "主高峰（美盘）", "★★★★★", 3.0, 5.0),
    "morning": Slot("morning", "次高峰（早报）", "★★★★", 5.0, 8.0),
    "afternoon": Slot("afternoon", "午后平缓", "★★", 15.0, 20.0),
    "europe": Slot("europe", "欧盘过渡", "★★★", 10.0, 15.0),
    "deep": Slot(
        "deep",
        "深度垃圾时间",
        "★",
        30.0,
        60.0,
        sleep=True,
        patrol_min=30.0,
        patrol_max=60.0,
    ),
}


def now_beijing(now: Optional[datetime] = None) -> datetime:
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(BJ)


def _minutes_of_day(dt: datetime) -> int:
    local = now_beijing(dt)
    return local.hour * 60 + local.minute


def resolve_slot_id(now: Optional[datetime] = None) -> str:
    """根据北京时间落在哪个业务时段。"""
    m = _minutes_of_day(now)
    # 01:30=90 … 07:30=450 … 10:30=630 … 15:30=930 … 20:00=1200
    if 90 <= m < 450:
        return "deep"
    if 450 <= m < 630:
        return "morning"
    if 630 <= m < 930:
        return "afternoon"
    if 930 <= m < 1200:
        return "europe"
    # 20:00–24:00 与 00:00–01:30
    return "peak"


def get_slot(now: Optional[datetime] = None) -> Slot:
    return SLOTS[resolve_slot_id(now)]


def _pick_minutes(lo: float, hi: float) -> float:
    lo = float(lo)
    hi = float(hi)
    if hi < lo:
        lo, hi = hi, lo
    if hi <= lo:
        return max(1.0, lo)
    return random.uniform(lo, hi)


def next_wait_seconds(
    now: Optional[datetime] = None,
    *,
    deep_mode: str = "sleep",
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    计算距离下一次应触发 CDP 的等待秒数。

    deep_mode:
      - sleep: 01:30–07:30 完全休眠，等到 07:30
      - patrol: 该时段按 30–60 分钟巡检
    overrides: 可选覆盖各槽 min/max，如 {"peak": {"min": 3, "max": 5}}
    """
    local = now_beijing(now)
    slot = get_slot(local)
    ov = (overrides or {}).get(slot.id) if isinstance(overrides, dict) else None
    if not isinstance(ov, dict):
        ov = {}

    mode = (deep_mode or "sleep").strip().lower()
    if mode not in ("sleep", "patrol"):
        mode = "sleep"

    sleeping = False
    reason = slot.label

    if slot.id == "deep" and mode == "sleep":
        sleeping = True
        # 等到今日 07:30（北京）
        wake = local.replace(hour=7, minute=30, second=0, microsecond=0)
        if local >= wake:
            wake = wake + timedelta(days=1)
        # 若当前已过 01:30，wake 就是今天 07:30
        wait = max(30.0, (wake - local).total_seconds())
        minutes = wait / 60.0
        reason = f"{slot.label} · 休眠至 {wake.strftime('%H:%M')}（北京）"
    else:
        if slot.id == "deep":
            lo = float(ov.get("min", ov.get("patrol_min", slot.patrol_min)))
            hi = float(ov.get("max", ov.get("patrol_max", slot.patrol_max)))
            reason = f"{slot.label} · 巡检"
        else:
            lo = float(ov.get("min", slot.min_min))
            hi = float(ov.get("max", slot.max_min))
        minutes = _pick_minutes(lo, hi)
        wait = max(30.0, minutes * 60.0)

    next_at = local + timedelta(seconds=wait)
    return {
        "slot_id": slot.id,
        "slot_label": slot.label,
        "weight": slot.weight,
        "sleeping": sleeping,
        "deep_mode": mode,
        "wait_seconds": int(wait),
        "wait_minutes": round(minutes, 2),
        "beijing_now": local.isoformat(timespec="seconds"),
        "next_run_at": next_at.isoformat(timespec="seconds"),
        "reason": reason,
        "slot": asdict(slot),
    }


def describe_schedule() -> List[Dict[str, Any]]:
    """给前端展示的时段表。"""
    rows = [
        {
            "id": "peak",
            "range": "20:00 ～ 次日 01:30",
            "label": SLOTS["peak"].label,
            "interval": "3～5 分钟",
            "weight": SLOTS["peak"].weight,
        },
        {
            "id": "morning",
            "range": "07:30 ～ 10:30",
            "label": SLOTS["morning"].label,
            "interval": "5～8 分钟",
            "weight": SLOTS["morning"].weight,
        },
        {
            "id": "afternoon",
            "range": "10:30 ～ 15:30",
            "label": SLOTS["afternoon"].label,
            "interval": "15～20 分钟",
            "weight": SLOTS["afternoon"].weight,
        },
        {
            "id": "europe",
            "range": "15:30 ～ 20:00",
            "label": SLOTS["europe"].label,
            "interval": "10～15 分钟",
            "weight": SLOTS["europe"].weight,
        },
        {
            "id": "deep",
            "range": "01:30 ～ 07:30",
            "label": SLOTS["deep"].label,
            "interval": "休眠 或 30～60 分钟巡检",
            "weight": SLOTS["deep"].weight,
        },
    ]
    return rows


def estimate_daily_runs(deep_mode: str = "sleep") -> Dict[str, Any]:
    """粗算全天触发次数（取区间中值）。"""
    mid = {
        "peak": 4.0,  # 5.5h
        "morning": 6.5,  # 3h
        "afternoon": 17.5,  # 5h
        "europe": 12.5,  # 4.5h
    }
    hours = {"peak": 5.5, "morning": 3.0, "afternoon": 5.0, "europe": 4.5, "deep": 6.0}
    total = 0.0
    detail = {}
    for sid, h in hours.items():
        if sid == "deep":
            if (deep_mode or "sleep").lower() == "patrol":
                n = h * 60 / 45.0
            else:
                n = 0.0
        else:
            n = h * 60 / mid[sid]
        detail[sid] = round(n, 1)
        total += n
    return {"approx_runs": int(round(total)), "by_slot": detail, "deep_mode": deep_mode}
