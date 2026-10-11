# coding=utf-8
"""WhisprRT 流转写（逻辑对齐 deal-manage/manager/whisper_service.py，同步供 console Job 使用）。"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
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


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.pop("PYTHONSTARTUP", None)
    return env


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
    url = (url or "").strip()
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
            env=_child_env(),
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
        "message": None if ok else "脚本执行失败或未生成转写文件",
    }
