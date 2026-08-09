# coding=utf-8
"""
发布平台模块
"""

from public.platforms.typecho_publisher import TypechoPublisher

__all__ = ["TypechoPublisher", "XPublisher", "BinanceSquarePublisher"]


def __getattr__(name: str):
    if name == "XPublisher":
        from public.platforms.x_publisher import XPublisher

        return XPublisher
    if name == "BinanceSquarePublisher":
        from public.platforms.binance_square_publisher import BinanceSquarePublisher

        return BinanceSquarePublisher
    raise AttributeError(name)






































