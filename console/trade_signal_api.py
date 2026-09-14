# coding=utf-8
"""Telegram 交易信号 → AI + OI 截图 → CDP 发布 API。"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, List, Optional

from console.publish_api import _as_list, _json_bytes, _truthy, require_token


def handle(
    method: str,
    path: str,
    query: Dict[str, List[str]],
    body: Dict[str, Any],
    headers: Optional[Any] = None,
) -> tuple[bytes, int, str]:
    denied = require_token(headers, query, body or {})
    if denied:
        return denied

    if path.startswith("/api/v1/trade-signal/jobs/") and method == "GET":
        from console.app import _get_job

        job_id = path[len("/api/v1/trade-signal/jobs/") :].strip("/")
        job = _get_job(job_id)
        if not job:
            return _json_bytes({"success": False, "error": "任务不存在"}, 404)
        return _json_bytes({"success": True, "job": job})

    if path != "/api/v1/trade-signal/publish" or method != "POST":
        return _json_bytes({"success": False, "error": "Not Found"}, 404)

    payload = dict(body or {})
    if not str(payload.get("symbol") or "").strip():
        return _json_bytes({"success": False, "error": "缺少 symbol"}, 400)
    if not str(payload.get("direction") or "").strip():
        return _json_bytes({"success": False, "error": "缺少 direction"}, 400)

    if "platforms" in payload:
        payload["platforms"] = _as_list(payload.get("platforms"))
    async_mode = _truthy(payload.get("async"), True)

    if not async_mode:
        from signals.trade_signal_publish import run_trade_signal_pipeline

        try:
            result = run_trade_signal_pipeline(payload)
        except Exception as e:  # noqa: BLE001
            return _json_bytes({"success": False, "error": str(e)}, 500)
        status = 200 if result.get("success") else 500
        if result.get("error") and "正在进行" in str(result.get("error")):
            status = 429
        return _json_bytes(result, status)

    from console.app import _set_job

    job_id = uuid.uuid4().hex
    _set_job(
        job_id,
        status="queued",
        type="trade_signal_publish",
        message="排队中…",
        symbol=str(payload.get("symbol") or ""),
        event=str(payload.get("event") or "entry"),
    )

    def _worker() -> None:
        import time

        from console.app import _set_job as set_job
        from signals.trade_signal_publish import run_trade_signal_pipeline

        set_job(job_id, status="running", message="OI 截图 + CDP 发布…")
        t0 = time.perf_counter()
        try:
            result = run_trade_signal_pipeline(payload)
            ok = bool(result.get("success"))
            elapsed_ms = int(result.get("elapsed_ms") or (time.perf_counter() - t0) * 1000)
            timings = result.get("timings") or {}
            detail = (
                f"总{elapsed_ms}ms"
                f"/截图{timings.get('screenshot_ms', 0)}ms"
                f"/发布{timings.get('publish_ms', 0)}ms"
            )
            set_job(
                job_id,
                status="done" if ok else "error",
                message=(
                    f"{'完成' if ok else str(result.get('error') or '失败')} · {detail}"
                ),
                result=result,
                elapsed_ms=elapsed_ms,
                timings=timings,
            )
        except Exception as e:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            set_job(
                job_id,
                status="error",
                message=f"{e} · {elapsed_ms}ms",
                elapsed_ms=elapsed_ms,
            )

    threading.Thread(
        target=_worker, daemon=True, name=f"trade-signal-{job_id[:8]}"
    ).start()
    return _json_bytes(
        {
            "success": True,
            "job_id": job_id,
            "status": "queued",
            "poll": f"/api/v1/trade-signal/jobs/{job_id}",
        }
    )
