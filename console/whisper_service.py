# coding=utf-8
"""WhisprRT 流转写（逻辑对齐 deal-manage/manager/whisper_service.py，同步供 console Job 使用）。"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WHISPRT_ROOT = Path("/Users/maotouying/frontend/code/1.operations/WhisprRT")
SCRIPT_NAME = "batch_whisperx_nodownload.py"
OUTPUT_SUBDIR = "output"

_RUN_LOCK = threading.Lock()
LogCb = Optional[Callable[[str], None]]


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_app_config() -> Dict[str, Any]:
    path = PROJECT_ROOT / "config" / "config.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def load_whisper_settings(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = (config or load_app_config()).get("whisper") or {}
    root_raw = (
        os.environ.get("WHISPRT_ROOT", "").strip()
        or str(cfg.get("root") or "").strip()
        or str(DEFAULT_WHISPRT_ROOT)
    )
    root = Path(root_raw).expanduser().resolve()
    python_raw = (
        os.environ.get("WHISPRT_PYTHON", "").strip()
        or str(cfg.get("python") or "").strip()
        or ""
    )
    python = Path(python_raw).expanduser() if python_raw else _default_python(root)
    timeout = int(os.environ.get("WHISPRT_TIMEOUT_SECONDS", "") or cfg.get("timeout_seconds") or 3600)
    force_cpu = _truthy(os.environ.get("WHISPRT_CPU")) or _truthy(cfg.get("force_cpu"))
    return {
        "root": root,
        "script": root / SCRIPT_NAME,
        "python": Path(python),
        "timeout_seconds": max(60, timeout),
        "force_cpu": bool(force_cpu),
        "output_dir": root / OUTPUT_SUBDIR,
    }


def _default_python(root: Path) -> Path:
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / "venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return Path(sys.executable)


def sanitize_title(title: str | None, url: str) -> str:
    raw = (title or "").strip()
    if not raw:
        raw = _default_name_from_url(url)
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).strip(" ._")
    cleaned = re.sub(r"\s+", "_", cleaned)
    if not cleaned:
        cleaned = "video"
    return cleaned[:120]


def _default_name_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        seg = (p.path or "").rstrip("/").split("/")[-1] or "video"
        seg = seg.split("?")[0]
        seg = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", seg).strip("_")
        return (seg or "video")[:120]
    except Exception:
        return "video"


def collect_output_paths(root: Path, name: str) -> Dict[str, Optional[str]]:
    mapping = {
        "transcript": root / "subtitles" / f"{name}.txt",
        "log": root / "logs" / f"{name}.txt",
        "refined": root / OUTPUT_SUBDIR / f"{name}.txt",
    }
    return {k: str(p.resolve()) if p.is_file() else None for k, p in mapping.items()}


def _paths_exist(paths: Dict[str, Optional[str]]) -> bool:
    return bool(paths.get("refined") or paths.get("transcript"))


def _remove_existing(root: Path, name: str) -> None:
    for rel in ("subtitles", "logs", OUTPUT_SUBDIR):
        p = root / rel / f"{name}.txt"
        if p.is_file():
            p.unlink()


def _build_cmd(*, python: Path, script: Path, url: str, name: str, use_cpu: bool) -> list[str]:
    cmd = [str(python), "-u", str(script), "--mode", "file", "--url", url, "--name", name]
    if use_cpu:
        cmd.append("--cpu")
    return cmd


def _child_env(*, binance_cookies_file: str = "") -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.pop("PYTHONSTARTUP", None)
    if binance_cookies_file:
        env["BINANCE_COOKIES_FILE"] = binance_cookies_file
    return env


def normalize_binance_square_whisper_url(url: str) -> str:
    """WhisprRT bapi 需要 contentId；replay?id=live 常返回 data=null。"""
    from urllib.parse import parse_qs, urlparse

    u = (url or "").strip()
    if not u:
        return u
    parsed = urlparse(u)
    path = parsed.path or ""
    m = re.search(r"/square/post/(\d+)", path, re.I)
    if m:
        cid = m.group(1)
        return f"https://www.binance.com/zh-CN/square/post/{cid}"
    if "/square/audio/replay" in path.lower():
        qs = parse_qs(parsed.query)
        cid = (qs.get("contentId") or qs.get("content_id") or [""])[0].strip()
        if cid.isdigit():
            return f"https://www.binance.com/zh-CN/square/post/{cid}"
    return u


def _resolve_whisper_cdp_debugger_url() -> str:
    for key in ("SIGNALS_DEBUGGER_URL", "CDP_DEBUGGER_URL", "TRENDRADAR_CDP_URL"):
        env = os.environ.get(key, "").strip()
        if env:
            return env if "://" in env else f"http://{env}"
    try:
        from utils.crawl_cdp import resolve_crawl_debugger_url

        return resolve_crawl_debugger_url()
    except Exception:
        return "127.0.0.1:9223"


def _write_netscape_cookies(path: Path, cookies: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated by TrendRadar console whisper_service",
    ]
    for c in cookies:
        if not isinstance(c, dict):
            continue
        domain = str(c.get("domain") or "").strip()
        if "binance" not in domain.lower():
            continue
        name = str(c.get("name") or "")
        value = str(c.get("value") or "")
        if not name:
            continue
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        cpath = str(c.get("path") or "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        exp = str(int(c.get("expiry") or 0))
        lines.append("\t".join([domain, flag, cpath, secure, exp, name, value]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cdp_http_base(debugger_url: str) -> str:
    addr = (debugger_url or "").strip()
    if not addr:
        addr = "127.0.0.1:9223"
    if not addr.startswith("http"):
        addr = f"http://{addr}"
    return addr.rstrip("/")


def _cdp_pick_page_ws_url(debugger_url: str) -> str:
    import json
    import urllib.request

    base = _cdp_http_base(debugger_url)
    with urllib.request.urlopen(f"{base}/json/list", timeout=8) as resp:
        targets = json.loads(resp.read().decode("utf-8", errors="replace"))
    pages = [
        t
        for t in (targets or [])
        if isinstance(t, dict)
        and t.get("type") == "page"
        and str(t.get("webSocketDebuggerUrl") or "").strip()
    ]
    if not pages:
        with urllib.request.urlopen(f"{base}/json/version", timeout=8) as resp:
            meta = json.loads(resp.read().decode("utf-8", errors="replace"))
        ws_url = str(meta.get("webSocketDebuggerUrl") or "").strip()
        if ws_url:
            return ws_url
        raise RuntimeError("CDP 无可用 page 目标")
    for t in pages:
        url = str(t.get("url") or "").lower()
        if "binance.com" in url:
            return str(t["webSocketDebuggerUrl"]).strip()
    return str(pages[0]["webSocketDebuggerUrl"]).strip()


def _cdp_network_get_all_cookies(debugger_url: str) -> list[dict]:
    """经 CDP WebSocket 拉全站 Cookie，不依赖 Selenium。"""
    import json

    ws_url = _cdp_pick_page_ws_url(debugger_url)

    try:
        from websockets.sync.client import connect as ws_connect
    except ImportError as exc:
        raise RuntimeError("缺少 websockets 包，无法从 CDP 导出 Cookie") from exc

    cmd_id = 0

    def _send(ws, method: str, params: dict | None = None) -> dict:
        nonlocal cmd_id
        cmd_id += 1
        payload = {"id": cmd_id, "method": method}
        if params:
            payload["params"] = params
        ws.send(json.dumps(payload))
        while True:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == cmd_id:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                return msg.get("result") or {}

    with ws_connect(ws_url, open_timeout=10, close_timeout=5, proxy=None) as ws:
        _send(ws, "Network.enable")
        result = _send(ws, "Network.getAllCookies")
    cookies = result.get("cookies") or []
    out: list[dict] = []
    for c in cookies:
        if not isinstance(c, dict):
            continue
        domain = str(c.get("domain") or "")
        if "binance" not in domain.lower():
            continue
        exp = c.get("expires")
        expiry = int(exp) if isinstance(exp, (int, float)) and exp > 0 else 0
        out.append(
            {
                "domain": domain,
                "name": str(c.get("name") or ""),
                "value": str(c.get("value") or ""),
                "path": str(c.get("path") or "/"),
                "secure": bool(c.get("secure")),
                "expiry": expiry,
            }
        )
    return out


def _cdp_network_get_all_cookies_via_whispr_python(debugger_url: str, *, python: Path) -> list[dict]:
    """用 WhisprRT 虚拟环境的 Python 连 CDP（console 进程常缺 websockets）。"""
    if not python.is_file():
        raise RuntimeError(f"WhisprRT Python 不可用: {python}")
    snippet = r"""
import json, sys, urllib.request
from websockets.sync.client import connect as ws_connect

def pick_ws(dbg):
    with urllib.request.urlopen(dbg + "/json/list", timeout=8) as resp:
        targets = json.loads(resp.read().decode())
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    for t in pages:
        if "binance.com" in str(t.get("url") or "").lower():
            return t["webSocketDebuggerUrl"]
    if pages:
        return pages[0]["webSocketDebuggerUrl"]
    with urllib.request.urlopen(dbg + "/json/version", timeout=8) as resp:
        meta = json.loads(resp.read().decode())
    return meta.get("webSocketDebuggerUrl") or ""

def main():
    dbg = sys.argv[1].strip()
    if not dbg.startswith("http"):
        dbg = "http://" + dbg
    dbg = dbg.rstrip("/")
    ws_url = pick_ws(dbg)
    if not ws_url:
        raise SystemExit("no webSocketDebuggerUrl")
    cmd_id = 0
    def send(ws, method, params=None):
        nonlocal cmd_id
        cmd_id += 1
        payload = {"id": cmd_id, "method": method}
        if params:
            payload["params"] = params
        ws.send(json.dumps(payload))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == cmd_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result") or {}
    with ws_connect(ws_url, open_timeout=10, close_timeout=5, proxy=None) as ws:
        send(ws, "Network.enable")
        result = send(ws, "Network.getAllCookies")
    out = []
    for c in result.get("cookies") or []:
        dom = str(c.get("domain") or "")
        if "binance" not in dom.lower():
            continue
        exp = c.get("expires")
        expiry = int(exp) if isinstance(exp, (int, float)) and exp > 0 else 0
        out.append({
            "domain": dom,
            "name": str(c.get("name") or ""),
            "value": str(c.get("value") or ""),
            "path": str(c.get("path") or "/"),
            "secure": bool(c.get("secure")),
            "expiry": expiry,
        })
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    main()
"""
    env = os.environ.copy()
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        env.pop(key, None)
    proc = subprocess.run(
        [str(python), "-c", snippet, debugger_url],
        capture_output=True,
        text=True,
        timeout=45,
        env=env,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        raise RuntimeError(err or f"Cookie 导出子进程退出 {proc.returncode}")
    raw = (proc.stdout or "").strip()
    data = json.loads(raw) if raw else []
    if not isinstance(data, list):
        raise RuntimeError("Cookie 导出结果格式异常")
    return [x for x in data if isinstance(x, dict)]


def ensure_binance_cookies_file(root: Path, on_log: LogCb = None) -> Optional[Path]:
    """从 9223 已登录 Chrome 导出 binance_cookies.txt 供 WhisprRT 调 bapi。"""
    dest = (root / "binance_cookies.txt").resolve()
    if dest.is_file() and dest.stat().st_size > 80:
        mtime = dest.stat().st_mtime
        if time.time() - mtime < 6 * 3600:
            return dest
    try:
        dbg = _resolve_whisper_cdp_debugger_url()
        try:
            relevant = _cdp_network_get_all_cookies(dbg)
        except Exception as exc:
            _log(on_log, f">>> 本进程 CDP Cookie 失败: {exc}，改用 WhisprRT Python…")
            wh_py = _default_python(root)
            relevant = _cdp_network_get_all_cookies_via_whispr_python(dbg, python=wh_py)
        if len(relevant) < 2:
            _log(on_log, ">>> 9223 Chrome 未检测到足够 binance Cookie，请先在浏览器登录币安")
            return dest if dest.is_file() else None
        _write_netscape_cookies(dest, relevant)
        _log(on_log, f">>> 已从 CDP 导出 binance Cookie（{len(relevant)} 条）→ {dest.name}")
        return dest
    except Exception as exc:
        _log(on_log, f">>> 导出 binance Cookie 失败: {exc}")
        return dest if dest.is_file() else None


def _failure_message(*, returncode: int | None, log_parts: list[str]) -> str:
    tail = "\n".join(log_parts)[-4000:]
    for line in reversed(tail.splitlines()):
        s = line.strip()
        if "RuntimeError:" in s:
            msg = s.split("RuntimeError:", 1)[-1].strip()
            return (msg or s)[:500]
    for line in reversed(tail.splitlines()):
        s = line.strip()
        if not s:
            continue
        if s.startswith("[ERROR]") or "RuntimeError:" in s or "Traceback" in s:
            continue
        if "币安" in s or "Cookie" in s or "ffmpeg" in s.lower() or "cuda" in s.lower():
            return s[:500]
        if "失败" in s or "error" in s.lower():
            return s[:500]
    for line in reversed(tail.splitlines()):
        s = line.strip()
        if s.startswith("[ERROR]"):
            return s.replace("[ERROR]", "", 1).strip()[:500]
    if returncode not in (0, None):
        return f"转写脚本退出码 {returncode}"
    return "脚本执行失败或未生成转写文件（常见：未登录币安 / replay 链接无效，请用 square/post 或配置 Cookie）"


def _log(cb: LogCb, line: str) -> None:
    if cb and line:
        cb(line)


def transcribe_url_sync(
    *,
    url: str,
    title: str | None = None,
    force: bool = False,
    force_cpu: bool | None = None,
    config: Dict[str, Any] | None = None,
    on_log: LogCb = None,
) -> Dict[str, Any]:
    url = normalize_binance_square_whisper_url(url)
    if not url:
        raise ValueError("url 不能为空")

    settings = load_whisper_settings(config)
    root: Path = settings["root"]
    script: Path = settings["script"]
    python: Path = settings["python"]
    timeout = int(settings["timeout_seconds"])
    use_cpu = settings["force_cpu"] if force_cpu is None else bool(force_cpu)

    if not root.is_dir():
        raise FileNotFoundError(f"Whisper 引擎目录不存在: {root}")
    if not script.is_file():
        raise FileNotFoundError(f"Whisper 引擎脚本缺失: {script.name}")
    if not python.is_file():
        raise FileNotFoundError(f"Whisper Python 不可用: {python}")

    name = sanitize_title(title, url)
    output_dir = (root / OUTPUT_SUBDIR).resolve()
    paths = collect_output_paths(root, name)

    _log(on_log, ">>> [WhisprRT] 开始转写")
    _log(on_log, f">>> name={name!r}  force={force}  cpu={use_cpu}")
    _log(on_log, f">>> URL: {url}")
    _log(on_log, f">>> 成品目录: {output_dir}")
    _log(on_log, f">>> 目标: {output_dir / f'{name}.txt'}")

    if _paths_exist(paths) and not force:
        _log(on_log, f">>> 跳过：已存在成品 {output_dir / f'{name}.txt'}")
        return {
            "ok": True,
            "status": "skipped_existing",
            "name": name,
            "url": url,
            "message": "成品已存在，未重新转写",
            "paths": paths,
            "workdir": str(root),
            "output_dir": str(output_dir),
        }

    if force:
        _remove_existing(root, name)
        _log(on_log, ">>> 已清除同名旧文件")

    cmd = _build_cmd(python=python, script=script, url=url, name=name, use_cpu=use_cpu)
    _log(on_log, ">>> 启动转写引擎…")

    cookie_file = ""
    if "binance.com" in url.lower() and "/square/" in url.lower():
        ck = ensure_binance_cookies_file(root, on_log)
        if ck is not None and ck.is_file() and ck.stat().st_size > 80:
            cookie_file = str(ck)
        else:
            _log(
                on_log,
                ">>> 警告：未生成 binance_cookies.txt，bapi 可能返回空数据；"
                "请保持 9223 Chrome 已登录币安后重试",
            )

    log_parts: list[str] = []
    returncode: int | None = None
    deadline = time.monotonic() + timeout

    with _RUN_LOCK:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=_child_env(binance_cookies_file=cookie_file),
            start_new_session=(os.name != "nt"),
        )
        assert proc.stdout is not None
        buf = ""
        while True:
            if time.monotonic() > deadline:
                proc.kill()
                proc.wait(timeout=30)
                raise TimeoutError(f"转写超时（>{timeout}s）: {name}")
            chunk = proc.stdout.read(512)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
            buf += text
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                log_parts.append(line)
                _log(on_log, line)
        if buf:
            log_parts.append(buf)
            _log(on_log, buf)
        returncode = proc.wait(timeout=max(1.0, deadline - time.monotonic()))

    paths = collect_output_paths(root, name)
    ok = returncode == 0 and _paths_exist(paths)
    out_path = (root / OUTPUT_SUBDIR / f"{name}.txt").resolve()
    if ok:
        _log(on_log, f"✅ 成品已写入: {out_path}")
    return {
        "ok": ok,
        "status": "success" if ok else "error",
        "name": name,
        "url": url,
        "returncode": returncode,
        "paths": paths,
        "workdir": str(root),
        "output_dir": str(output_dir),
        "stdout_tail": "\n".join(log_parts)[-8000:],
        "message": None if ok else _failure_message(returncode=returncode, log_parts=log_parts),
    }
