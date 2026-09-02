# coding=utf-8
"""通知：可插拔；默认 no-op。"""

from __future__ import annotations

from typing import Any, Dict, Protocol


class Notifier(Protocol):
    def notify(self, card: Dict[str, Any]) -> Dict[str, Any]: ...


class NoopNotifier:
    def notify(self, card: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": True, "skipped": True, "reason": "noop"}


class CardsApiNotifier:
    """预留：开启 value_push_enabled 时可接 Cards API。"""

    def notify(self, card: Dict[str, Any]) -> Dict[str, Any]:
        from signals.store import get_config

        cfg = get_config()
        if not cfg.get("value_push_enabled"):
            return {"success": True, "skipped": True, "reason": "value_push_enabled=false"}
        try:
            from signals.push import push_cards_batch

            return push_cards_batch([card])
        except Exception as e:
            return {"success": False, "error": str(e)}


def get_notifier() -> Notifier:
    from signals.store import get_config

    if get_config().get("value_push_enabled"):
        return CardsApiNotifier()
    return NoopNotifier()
