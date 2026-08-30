# coding=utf-8
"""各模块规则（显式模块路径，便于单测 import）。"""

from realtime_info.filters import (  # noqa: F401
    rule_kol_prefilter,
    rule_liq,
    rule_oi_funding_oi_surge,
    rule_oi_funding_squeeze,
    rule_onchain,
    rule_tv,
    rule_unlock,
)
