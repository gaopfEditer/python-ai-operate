# coding=utf-8
"""任务系统 API：/api/tasks/*"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from console.tasks_db import STATE_KEYS, get_state, patch_state


def _json_bytes(payload: Any, status: int = 200) -> tuple[bytes, int, str]:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8"), status, "application/json"


def handle(
    method: str,
    path: str,
    query: Dict[str, List[str]],
    body: Dict[str, Any],
) -> tuple[bytes, int, str]:
    if path == "/api/tasks/state":
        if method == "GET":
            keys_raw = (query.get("keys") or [None])[0]
            keys = None
            if keys_raw:
                keys = [k.strip() for k in str(keys_raw).split(",") if k.strip()]
                keys = [k for k in keys if k in STATE_KEYS] or None
            return _json_bytes({"success": True, "state": get_state(keys)})

        if method == "PUT":
            patch = body.get("patch") if isinstance(body, dict) else None
            if not isinstance(patch, dict):
                return _json_bytes({"success": False, "error": "缺少 patch 对象"}, 400)
            filtered = {k: v for k, v in patch.items() if k in STATE_KEYS}
            if not filtered:
                return _json_bytes({"success": False, "error": "patch 无有效键"}, 400)
            state = patch_state(filtered)
            return _json_bytes({"success": True, "state": state})

    return _json_bytes({"success": False, "error": "Not Found"}, 404)
