# coding=utf-8
"""帖子与归档数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any, Dict, List, Optional
import hashlib


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_post_id(platform: str, url: str, title: str = "") -> str:
    raw = f"{platform}|{(url or '').strip()}|{(title or '').strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class Post:
    platform: str
    title: str
    url: str
    author: str = ""
    summary: str = ""
    content: str = ""
    likes: int = 0
    comments: int = 0
    collects: int = 0
    shares: int = 0
    views: int = 0
    score: float = 0.0
    fetched_at: str = field(default_factory=_now)
    raw: Dict[str, Any] = field(default_factory=dict)
    post_id: str = ""

    def __post_init__(self) -> None:
        if not self.post_id:
            self.post_id = make_post_id(self.platform, self.url, self.title)
        for k in ("likes", "comments", "collects", "shares", "views"):
            try:
                setattr(self, k, int(getattr(self, k) or 0))
            except (TypeError, ValueError):
                setattr(self, k, 0)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Post":
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**kwargs)


@dataclass
class ArchiveRecord:
    post_id: str
    platform: str
    title: str
    url: str
    author: str = ""
    summary: str = ""
    content: str = ""
    likes: int = 0
    comments: int = 0
    collects: int = 0
    shares: int = 0
    views: int = 0
    score: float = 0.0
    archive_type: str = "auto"  # auto | manual
    reason: str = ""
    median_likes: Optional[float] = None
    median_comments: Optional[float] = None
    archived_at: str = field(default_factory=_now)
    # 后期要素分析填充
    factors: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_post(
        cls,
        post: Post,
        archive_type: str,
        reason: str = "",
        median_likes: Optional[float] = None,
        median_comments: Optional[float] = None,
    ) -> "ArchiveRecord":
        return cls(
            post_id=post.post_id,
            platform=post.platform,
            title=post.title,
            url=post.url,
            author=post.author,
            summary=post.summary,
            content=post.content or post.summary,
            likes=post.likes,
            comments=post.comments,
            collects=post.collects,
            shares=post.shares,
            views=post.views,
            score=post.score,
            archive_type=archive_type,
            reason=reason,
            median_likes=median_likes,
            median_comments=median_comments,
        )
