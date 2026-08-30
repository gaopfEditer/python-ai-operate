# coding=utf-8
"""Collector 基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class Collector(ABC):
    module: str = "unknown"

    @abstractmethod
    def collect(self) -> List[Dict[str, Any]]:
        """返回候选 raw payload 列表（尚未入库）。"""

    def name(self) -> str:
        return self.__class__.__name__
