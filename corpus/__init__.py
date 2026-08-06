# coding=utf-8
"""语料库：爆款帖子拆解模板的 SQLite 资产层。"""

from .db import (
    DEFAULT_DB_PATH,
    archive_template,
    create_generation,
    create_template,
    delete_template,
    get_generation,
    get_template,
    init_db,
    list_generations,
    list_templates,
    stats,
    update_template,
)
from .deconstruct import deconstruct_post, import_and_deconstruct
from .generate import regenerate_from_template

__all__ = [
    "DEFAULT_DB_PATH",
    "init_db",
    "create_template",
    "get_template",
    "list_templates",
    "update_template",
    "delete_template",
    "archive_template",
    "stats",
    "create_generation",
    "list_generations",
    "get_generation",
    "deconstruct_post",
    "import_and_deconstruct",
    "regenerate_from_template",
]
