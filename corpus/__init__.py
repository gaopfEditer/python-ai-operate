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
    get_templates_by_ids,
    init_db,
    list_generations,
    list_template_history,
    list_templates,
    snapshot_template,
    stats,
    update_template,
)
from .deconstruct import deconstruct_post, import_and_deconstruct
from .generate import compose_from_templates, regenerate_from_template
from .synthesize import pick_random_posts, synthesize_from_posts
from .viral_deconstruct import deconstruct_viral_post
from .xgrowth import run_xgrowth_viral_pipeline

__all__ = [
    "DEFAULT_DB_PATH",
    "init_db",
    "create_template",
    "get_template",
    "get_templates_by_ids",
    "list_templates",
    "list_template_history",
    "snapshot_template",
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
    "compose_from_templates",
    "synthesize_from_posts",
    "pick_random_posts",
    "deconstruct_viral_post",
    "run_xgrowth_viral_pipeline",
]
