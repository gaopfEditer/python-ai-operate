# coding=utf-8
"""B · 清算热力图空壳。"""

from __future__ import annotations

from typing import Any, Dict, List

from realtime_info.collectors.base import Collector


class CoinglassCollector(Collector):
    module = "liq"

    def collect(self) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "Coinglass 付费/未配置。可用假数据测 filters.rule_liq；"
            "后续替换免费数据源。"
        )
