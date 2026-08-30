# coding=utf-8
"""E · 代币解锁空壳（可后续接 DefiLlama / 自建爬虫）。"""

from __future__ import annotations

from typing import Any, Dict, List

from realtime_info.collectors.base import Collector
from realtime_info.config import module_cfg


class UnlocksCollector(Collector):
    module = "unlock"

    def collect(self) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "Token unlocks 数据源未接入（计划周日 Cron）。"
            "规则见 settings modules.unlock；可用假数据测 rule_unlock。"
        )

    def top_n_placeholder(self) -> List[Dict[str, Any]]:
        """返回空列表占位，供调度器在 enabled 时打日志。"""
        cfg = module_cfg("unlock")
        _ = cfg.get("top_n")
        return []
