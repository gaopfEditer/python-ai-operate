# coding=utf-8
"""usememos 客户端：拉取文章列表、可选写回正文。"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "memos.yaml"
BJ_TZ = timezone(timedelta(hours=8))

_DEFAULTS: Dict[str, Any] = {
    "base_url": "http://127.0.0.1:5230",
    "access_token": "",
    "page_size": 50,
    "filter": "",
    "order_by": "create_time desc",
    "timeout_sec": 20,
    # 默认直连，不走系统/环境 HTTP(S)_PROXY（VPN/Clash 常导致 SSL EOF）
    "use_system_proxy": False,
}

_HASHTAG_RE = re.compile(r"(?:^|[\s\n])#([A-Za-z0-9_\u4e00-\u9fff][\w\u4e00-\u9fff/-]*)")


def _strip_md_title(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return "无标题"
    first = text.split("\n", 1)[0].strip()
    first = re.sub(r"^#+\s*", "", first)
    first = re.sub(r"^[*_`>\-\s]+", "", first)
    return (first[:80] or "无标题").strip()


def extract_hashtags(content: str) -> List[str]:
    seen = set()
    out: List[str] = []
    for m in _HASHTAG_RE.finditer(content or ""):
        tag = m.group(1).strip().strip(".,;:!?，。；：！？）)」』】\"'")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def load_config() -> Dict[str, Any]:
    cfg = dict(_DEFAULTS)
    if CONFIG_PATH.is_file():
        try:
            raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                cfg.update({k: raw[k] for k in raw if k in _DEFAULTS or k in raw})
        except Exception:
            pass
    env_url = os.environ.get("MEMOS_BASE_URL", "").strip()
    env_tok = os.environ.get("MEMOS_ACCESS_TOKEN", "").strip()
    if env_url:
        cfg["base_url"] = env_url
    if env_tok:
        cfg["access_token"] = env_tok
    cfg["base_url"] = str(cfg.get("base_url") or _DEFAULTS["base_url"]).rstrip("/")
    cfg["access_token"] = str(cfg.get("access_token") or "")
    try:
        cfg["page_size"] = max(1, min(200, int(cfg.get("page_size") or 50)))
    except Exception:
        cfg["page_size"] = 50
    try:
        cfg["timeout_sec"] = max(5, min(120, int(cfg.get("timeout_sec") or 20)))
    except Exception:
        cfg["timeout_sec"] = 20
    cfg["filter"] = str(cfg.get("filter") or "").strip()
    cfg["order_by"] = str(cfg.get("order_by") or "create_time desc").strip()
    if "display_time" in cfg["order_by"]:
        cfg["order_by"] = "create_time desc"
    env_proxy = os.environ.get("MEMOS_USE_SYSTEM_PROXY", "").strip().lower()
    if env_proxy in ("1", "true", "yes", "on"):
        cfg["use_system_proxy"] = True
    elif env_proxy in ("0", "false", "no", "off"):
        cfg["use_system_proxy"] = False
    else:
        cfg["use_system_proxy"] = bool(cfg.get("use_system_proxy", False))
    return cfg


def save_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()
    for key in ("base_url", "access_token", "filter", "order_by"):
        if key in patch and patch[key] is not None:
            cfg[key] = str(patch[key]).strip()
    if "page_size" in patch and patch["page_size"] is not None:
        try:
            cfg["page_size"] = max(1, min(200, int(patch["page_size"])))
        except Exception:
            pass
    if "timeout_sec" in patch and patch["timeout_sec"] is not None:
        try:
            cfg["timeout_sec"] = max(5, min(120, int(patch["timeout_sec"])))
        except Exception:
            pass
    if "use_system_proxy" in patch and patch["use_system_proxy"] is not None:
        v = patch["use_system_proxy"]
        if isinstance(v, str):
            cfg["use_system_proxy"] = v.strip().lower() in ("1", "true", "yes", "on")
        else:
            cfg["use_system_proxy"] = bool(v)
    cfg["base_url"] = str(cfg.get("base_url") or _DEFAULTS["base_url"]).rstrip("/")
    if "display_time" in str(cfg.get("order_by") or ""):
        cfg["order_by"] = "create_time desc"
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    dump = {
        "base_url": cfg["base_url"],
        "access_token": cfg["access_token"],
        "page_size": cfg["page_size"],
        "filter": cfg.get("filter") or "",
        "order_by": cfg.get("order_by") or "create_time desc",
        "timeout_sec": cfg["timeout_sec"],
        "use_system_proxy": bool(cfg.get("use_system_proxy")),
    }
    header = (
        "# usememos 实例配置（灵感碰撞 · Memos 文章）\n"
        "# Access Token：Memos 设置 → Access Tokens\n"
        "# 也可用环境变量覆盖：MEMOS_BASE_URL / MEMOS_ACCESS_TOKEN / MEMOS_USE_SYSTEM_PROXY\n"
        "# use_system_proxy: false 时直连，避开 VPN/Clash 代理导致的 SSL EOF\n\n"
    )
    CONFIG_PATH.write_text(
        header + yaml.safe_dump(dump, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return public_config(cfg)


def public_config(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    c = cfg or load_config()
    tok = str(c.get("access_token") or "")
    masked = ""
    if tok:
        masked = tok[:4] + "…" + tok[-4:] if len(tok) > 10 else "****"
    return {
        "base_url": c.get("base_url") or "",
        "access_token": tok,
        "access_token_masked": masked,
        "has_token": bool(tok),
        "page_size": c.get("page_size") or 50,
        "filter": c.get("filter") or "",
        "order_by": c.get("order_by") or "create_time desc",
        "timeout_sec": c.get("timeout_sec") or 20,
        "use_system_proxy": bool(c.get("use_system_proxy")),
    }


def _build_opener(*, use_system_proxy: bool) -> urllib.request.OpenerDirector:
    """默认绕过 HTTP(S)_PROXY；VPN/Clash 对自建域名常导致 SSL UNEXPECTED_EOF。"""
    if use_system_proxy:
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _request(
    method: str,
    path: str,
    *,
    query: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    c = cfg or load_config()
    base = str(c.get("base_url") or "").rstrip("/")
    if not base:
        raise ValueError("未配置 Memos base_url")
    url = f"{base}{path}"
    if query:
        q = {k: v for k, v in query.items() if v is not None and str(v) != ""}
        if q:
            url += "?" + urllib.parse.urlencode(q)
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "TrendRadar-lab-memos/1.0",
        "Connection": "close",
    }
    token = str(c.get("access_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    timeout = float(c.get("timeout_sec") or 20)
    use_proxy = bool(c.get("use_system_proxy"))
    opener = _build_opener(use_system_proxy=use_proxy)
    last_err: Optional[BaseException] = None
    attempts = 3
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw.strip():
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            msg = err_body[:300] or e.reason
            raise RuntimeError(f"Memos HTTP {e.code}: {msg}") from e
        except urllib.error.URLError as e:
            last_err = e
            reason = str(getattr(e, "reason", e) or e)
            transient = any(
                key in reason
                for key in (
                    "UNEXPECTED_EOF",
                    "EOF occurred",
                    "Connection reset",
                    "Connection refused",
                    "Timed out",
                    "timed out",
                    "Temporary failure",
                    "Broken pipe",
                    "Remote end closed",
                    "SSLEOFError",
                    "Wrong version number",
                    "Tunnel connection failed",
                    "ProxyError",
                    "Forbidden",
                )
            )
            if attempt + 1 < attempts and transient:
                time.sleep(0.35 * (attempt + 1))
                continue
            hint = ""
            if not use_proxy and ("proxy" in reason.lower() or "Tunnel" in reason):
                hint = "（已尝试直连；若仍失败可检查本机 DNS）"
            elif use_proxy:
                hint = "（当前走系统代理；自建 Memos 建议 use_system_proxy: false）"
            raise RuntimeError(f"无法连接 Memos：{e.reason}{hint}") from e
        except TimeoutError as e:
            last_err = e
            if attempt + 1 < attempts:
                time.sleep(0.35 * (attempt + 1))
                continue
            raise RuntimeError(f"无法连接 Memos：{e}") from e
        except OSError as e:
            last_err = e
            if attempt + 1 < attempts:
                time.sleep(0.35 * (attempt + 1))
                continue
            raise RuntimeError(f"无法连接 Memos：{e}") from e
    raise RuntimeError(f"无法连接 Memos：{last_err}")


def _parse_since_until(
    since: str = "", until: str = "", range_key: str = ""
) -> tuple:
    """返回 (since_ts, until_ts)，Unix 秒；基于北京时间日界。"""
    range_key = (range_key or "").strip().lower()
    now = datetime.now(BJ_TZ)
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if range_key in ("today", "今日"):
        return int(today0.timestamp()), int(now.timestamp()) + 1
    if range_key in ("7d", "week", "近7天"):
        return int((today0 - timedelta(days=6)).timestamp()), int(now.timestamp()) + 1
    if range_key in ("30d", "month30", "近30天"):
        return int((today0 - timedelta(days=29)).timestamp()), int(now.timestamp()) + 1
    if range_key in ("month", "本月"):
        month0 = today0.replace(day=1)
        return int(month0.timestamp()), int(now.timestamp()) + 1

    def _to_ts(raw: str, *, end_of_day: bool = False):
        s = (raw or "").strip()
        if not s:
            return None
        if re.fullmatch(r"\d{9,12}", s):
            return int(s)
        s = s.replace("Z", "+00:00")
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
                dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=BJ_TZ)
                if end_of_day:
                    dt = dt + timedelta(days=1)
                return int(dt.timestamp())
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BJ_TZ)
            return int(dt.timestamp())
        except Exception:
            return None

    return _to_ts(since, end_of_day=False), _to_ts(until, end_of_day=True)


def build_filter_expr(
    *,
    base_filter: str = "",
    keyword: str = "",
    tag: str = "",
    since: str = "",
    until: str = "",
    range_key: str = "",
) -> str:
    parts: List[str] = []
    base = (base_filter or "").strip()
    if base:
        parts.append(f"({base})" if "||" in base or "&&" in base else base)

    keyword = (keyword or "").strip()
    if keyword:
        esc = keyword.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'content.contains("{esc}")')

    tag = (tag or "").strip().lstrip("#")
    if tag:
        esc = tag.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'("{esc}" in tags || content.contains("#{esc}"))')

    since_ts, until_ts = _parse_since_until(since, until, range_key)
    if since_ts is not None:
        parts.append(f"created_ts >= {int(since_ts)}")
    if until_ts is not None:
        parts.append(f"created_ts < {int(until_ts)}")

    return " && ".join(parts)


def normalize_memo(raw: Dict[str, Any]) -> Dict[str, Any]:
    name = str(raw.get("name") or "")
    memo_id = name.split("/")[-1] if "/" in name else name
    content = str(raw.get("content") or "")
    api_tags = (
        [str(t) for t in (raw.get("tags") or []) if str(t).strip()]
        if isinstance(raw.get("tags"), list)
        else []
    )
    hash_tags = extract_hashtags(content)
    tags: List[str] = []
    seen = set()
    for t in api_tags + hash_tags:
        if t not in seen:
            seen.add(t)
            tags.append(t)
    return {
        "name": name,
        "id": memo_id,
        "content": content,
        "title": _strip_md_title(content),
        "hook": _strip_md_title(content),
        "label": _strip_md_title(content),
        "tags": tags,
        "visibility": str(raw.get("visibility") or ""),
        "pinned": bool(raw.get("pinned")),
        "create_time": str(raw.get("createTime") or raw.get("create_time") or ""),
        "update_time": str(raw.get("updateTime") or raw.get("update_time") or ""),
        "display_time": str(raw.get("displayTime") or raw.get("display_time") or ""),
        "snippet": content[:240],
    }


def list_memos(
    *,
    page_size: Optional[int] = None,
    page_token: str = "",
    filter_expr: Optional[str] = None,
    order_by: Optional[str] = None,
    keyword: str = "",
    tag: str = "",
    since: str = "",
    until: str = "",
    range_key: str = "",
) -> Dict[str, Any]:
    cfg = load_config()
    base = filter_expr if filter_expr is not None else (cfg.get("filter") or "")
    filt = build_filter_expr(
        base_filter=str(base or ""),
        keyword=keyword,
        tag=tag,
        since=since,
        until=until,
        range_key=range_key,
    )
    size = page_size if page_size is not None else cfg.get("page_size")
    try:
        size = max(1, min(200, int(size or 50)))
    except Exception:
        size = 50
    order = (order_by if order_by is not None else cfg.get("order_by")) or "create_time desc"
    if "display_time" in order:
        order = "create_time desc"
    query = {
        "pageSize": size,
        "pageToken": page_token or None,
        "filter": filt or None,
        "orderBy": order,
    }
    data = _request("GET", "/api/v1/memos", query=query, cfg=cfg)
    memos_raw = data.get("memos") if isinstance(data.get("memos"), list) else []
    items = [normalize_memo(m) for m in memos_raw if isinstance(m, dict)]
    return {
        "success": True,
        "items": items,
        "next_page_token": str(data.get("nextPageToken") or data.get("next_page_token") or ""),
        "count": len(items),
        "filter": filt,
        "config": public_config(cfg),
    }


def collect_tags(*, page_size: int = 100, max_pages: int = 3) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    token = ""
    scanned = 0
    for _ in range(max(1, max_pages)):
        result = list_memos(page_size=page_size, page_token=token)
        for it in result.get("items") or []:
            scanned += 1
            for t in it.get("tags") or []:
                counts[t] = counts.get(t, 0) + 1
        token = str(result.get("next_page_token") or "")
        if not token:
            break
    tags = [{"tag": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    return {"success": True, "tags": tags, "scanned": scanned}


def update_memo_content(name: str, content: str) -> Dict[str, Any]:
    name = str(name or "").strip()
    if not name:
        raise ValueError("缺少 memo name")
    if not name.startswith("memos/"):
        name = f"memos/{name}"
    path = f"/api/v1/{urllib.parse.quote(name, safe='/')}"
    body = {"name": name, "content": content}
    data = _request(
        "PATCH",
        path,
        query={"updateMask": "content"},
        body=body,
        cfg=load_config(),
    )
    memo = data.get("memo") if isinstance(data.get("memo"), dict) else data
    if not isinstance(memo, dict) or not memo.get("content"):
        memo = {"name": name, "content": content, **(memo if isinstance(memo, dict) else {})}
    return {"success": True, "item": normalize_memo(memo)}


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext, "application/octet-stream")


def upload_attachment(
    file_path: str | Path,
    *,
    memo_name: str = "",
    filename: str = "",
) -> Dict[str, Any]:
    """上传本地文件为 Memos attachment，可选绑定 memo。"""
    import base64
    import mimetypes

    src = Path(file_path)
    if not src.is_file():
        raise FileNotFoundError(f"图片不存在: {src}")
    raw = src.read_bytes()
    if not raw:
        raise ValueError("图片文件为空")
    name = str(memo_name or "").strip()
    if name and not name.startswith("memos/"):
        name = f"memos/{name}"
    fname = (filename or src.name or "image.png").strip() or "image.png"
    mime = mimetypes.guess_type(fname)[0] or _guess_mime(src)
    body: Dict[str, Any] = {
        "filename": fname,
        "type": mime,
        "content": base64.b64encode(raw).decode("ascii"),
    }
    if name:
        body["memo"] = name
    data = _request("POST", "/api/v1/attachments", body=body, cfg=load_config())
    att = data.get("attachment") if isinstance(data.get("attachment"), dict) else data
    if not isinstance(att, dict) or not att.get("name"):
        raise RuntimeError(f"上传附件失败: {data}")
    return att


def attachment_markdown(att: Dict[str, Any], *, absolute: bool = False) -> str:
    """生成 Memos 可识别的图片 Markdown。"""
    name = str(att.get("name") or "")
    aid = name.split("/")[-1] if "/" in name else name
    fname = str(att.get("filename") or "image.png")
    rel = f"/file/attachments/{aid}/{urllib.parse.quote(fname)}"
    if absolute:
        base = str(load_config().get("base_url") or "").rstrip("/")
        return f"![配图]({base}{rel})"
    return f"![配图]({rel})"


def fetch_asset(path_or_url: str) -> Dict[str, Any]:
    """拉取 Memos 附件（带 Token、默认直连），供 Console 预览代理。"""
    raw = str(path_or_url or "").strip()
    if not raw:
        raise ValueError("缺少附件路径")
    cfg = load_config()
    base = str(cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise ValueError("未配置 Memos base_url")

    if re.match(r"^https?://", raw, re.I):
        parsed = urllib.parse.urlparse(raw)
        base_p = urllib.parse.urlparse(base)
        if parsed.netloc and base_p.netloc and parsed.netloc.lower() != base_p.netloc.lower():
            raise ValueError("只允许代理当前 Memos 域名下的附件")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
    else:
        path = raw if raw.startswith("/") else f"/{raw}"

    if not path.startswith("/file/"):
        raise ValueError("仅允许 /file/ 附件路径")

    url = f"{base}{path}"
    headers = {
        "Accept": "*/*",
        "User-Agent": "TrendRadar-lab-memos/1.0",
        "Connection": "close",
    }
    token = str(cfg.get("access_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    opener = _build_opener(use_system_proxy=bool(cfg.get("use_system_proxy")))
    timeout = float(cfg.get("timeout_sec") or 20)
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read()
            ctype = (
                resp.headers.get("Content-Type")
                or _guess_mime(Path(urllib.parse.urlparse(path).path))
                or "application/octet-stream"
            )
            return {"data": data, "content_type": ctype.split(";")[0].strip(), "url": url}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"Memos 附件 HTTP {e.code}: {(err_body or e.reason)[:200]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法拉取 Memos 附件：{e.reason}") from e


_LAB_MEDIA_MD_RE = re.compile(
    r"\n*!\[([^\]]*)\]\(/api/corpus/lab/media\?rel=[^\)]+\)\s*",
    re.MULTILINE,
)


def push_local_images_to_memo(
    memo_name: str,
    content: str,
    image_paths: List[str],
    *,
    absolute_url: bool = False,
) -> Dict[str, Any]:
    """上传本地配图为附件，写入正文 Markdown，并 PATCH 回源 memo。"""
    memo_name = str(memo_name or "").strip()
    if not memo_name:
        raise ValueError("缺少 memo name")
    # 去掉本机 lab_media 链接，避免写回无效 URL
    base_content = _LAB_MEDIA_MD_RE.sub("", content or "").rstrip()
    attachments: List[Dict[str, Any]] = []
    md_lines: List[str] = []
    for p in image_paths or []:
        att = upload_attachment(p, memo_name=memo_name)
        attachments.append(att)
        line = attachment_markdown(att, absolute=absolute_url)
        if line not in base_content and line not in md_lines:
            md_lines.append(line)
    new_content = base_content
    if md_lines:
        new_content = base_content + "\n\n" + "\n".join(md_lines)
    updated = update_memo_content(memo_name, new_content)
    return {
        "success": True,
        "content": new_content,
        "attachments": attachments,
        "item": updated.get("item"),
    }


def apply_image_results_to_memos(
    variants: List[Dict[str, Any]],
    batch_result: Dict[str, Any],
) -> Dict[str, Any]:
    """把 batch_generate_images 的结果上传并写回对应 memo。"""
    rows = list(batch_result.get("results") or [])
    sync_ok = 0
    sync_fail = 0
    for row in rows:
        if not row.get("success"):
            continue
        idx = int(row.get("index") or -1)
        if idx < 0 or idx >= len(variants):
            row["synced"] = False
            row["sync_error"] = "变体索引无效"
            sync_fail += 1
            continue
        v = variants[idx]
        memo_name = str(v.get("name") or v.get("memo") or "").strip()
        if not memo_name:
            mid = str(v.get("id") or "").strip()
            if mid:
                memo_name = mid if mid.startswith("memos/") else f"memos/{mid}"
        if not memo_name:
            row["synced"] = False
            row["sync_error"] = "缺少 memo name"
            sync_fail += 1
            continue
        paths = [str(p) for p in (row.get("media_paths") or []) if p]
        if not paths:
            imgs = row.get("images") or []
            paths = [str(im.get("path")) for im in imgs if isinstance(im, dict) and im.get("path")]
        try:
            pushed = push_local_images_to_memo(
                memo_name,
                str(v.get("content") or row.get("content") or ""),
                paths,
            )
            row["content"] = pushed.get("content") or row.get("content")
            row["synced"] = True
            row["attachments"] = pushed.get("attachments") or []
            sync_ok += 1
        except Exception as e:
            row["synced"] = False
            row["sync_error"] = str(e)
            sync_fail += 1
    batch_result["sync_ok"] = sync_ok
    batch_result["sync_fail"] = sync_fail
    batch_result["synced"] = sync_ok > 0
    return batch_result


def sync_images_to_memos(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """items: [{name, content, media_paths?}] — 有本地图则上传附件，否则只写正文。"""
    results: List[Dict[str, Any]] = []
    ok = 0
    for it in items:
        name = str(it.get("name") or "")
        content = str(it.get("content") or "")
        paths = [str(p) for p in (it.get("media_paths") or []) if p]
        try:
            if paths:
                r = push_local_images_to_memo(name, content, paths)
            else:
                r = update_memo_content(name, content)
                r = {"success": True, "item": r.get("item"), "content": content, "attachments": []}
            ok += 1
            results.append(
                {
                    "name": name,
                    "success": True,
                    "item": r.get("item"),
                    "attachments": r.get("attachments") or [],
                }
            )
        except Exception as e:
            results.append({"name": name, "success": False, "error": str(e)})
    return {
        "success": ok > 0,
        "ok_count": ok,
        "fail_count": len(results) - ok,
        "results": results,
    }
