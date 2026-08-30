# coding=utf-8
"""A · Arkham / 付费源空壳（后续可换成自有免费站爬虫）。"""

from __future__ import annotations

from typing import Any, Dict, List

from realtime_info.collectors.base import Collector


class OnchainArkhamCollector(Collector):
    module = "onchain"

    def collect(self) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "Arkham/DeBank 付费源未接入。请用 onchain_free，"
            "或在本文件替换为自有免费网站爬虫。"
        )
