"""JavaScript 站点脚本运行时（Node 子进程 + vm）。

每次调用拉起一个 node 进程：写入脚本缓存文件与任务文件，执行脚本的
``init(cfg)`` 后调用目标函数，只回传 JSON 结果。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ..models import SiteConfig
from ..settings import DATA_DIR
from .framework import fetch_script

logger = logging.getLogger("docktvbox.jsscript")

SCRIPT_TIMEOUT = 30
RESULT_MARK = "__DOCKTV_RESULT__"
ERROR_MARK = "__DOCKTV_ERROR__"
BRIDGE = Path(__file__).with_name("js_bridge.js")

_code_cache: dict[str, tuple[float, str]] = {}
_node_bin: str | None = None


class JsRuntimeError(Exception):
    """Node 运行时不可用或脚本执行失败。"""


def _node() -> str:
    global _node_bin
    if _node_bin:
        return _node_bin
    candidates = [os.getenv("NODE_BIN") or "", shutil.which("node") or "", "/usr/local/bin/node", "/usr/bin/node"]
    # 开发机常用 nvm 安装，不在服务进程的 PATH 里。
    nvm = Path.home() / ".nvm/versions/node"
    if nvm.is_dir():
        candidates += [str(path) for path in sorted(nvm.glob("*/bin/node"), reverse=True)]
    for path in candidates:
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            _node_bin = path
            return path
    raise JsRuntimeError("未找到 node，请安装 Node.js 18+（Docker 镜像默认已包含）")


def _cache_dir() -> Path:
    path = DATA_DIR / "cache" / "js"
    path.mkdir(parents=True, exist_ok=True)
    return path


_IMPORT_RE = re.compile(
    r"^[ \t]*import\s+([^'\";]*?)\s+from\s+(['\"])([^'\"]+)\2\s*;?",
    re.MULTILINE,
)
_SIDE_IMPORT_RE = re.compile(r"^[ \t]*import\s*(['\"])([^'\"]+)\1\s*;?", re.MULTILINE)
_EXPORT_LIST_RE = re.compile(r"^[ \t]*export\s*(?:\*|\{[\s\S]*?\})\s*(?:from\s*['\"][^'\"]+['\"])?\s*;?[ \t]*$", re.MULTILINE)
_EXPORT_STAR_RE = re.compile(r"^[ \t]*export\s*\*[\s\S]*?;?[ \t]*$", re.MULTILINE)


def _import_bindings(clause: str, spec: str) -> str:
    """把 ``import { Crypto as e } from 'x'`` 摊平成 __docktv_import 赋值。"""
    source = json.dumps(spec)
    out: list[str] = []
    rest = clause.strip()
    if not rest:
        return ""
    if not rest.startswith(("{", "*")):
        match = re.match(r"^([^\s,{}*]+)\s*(?:,\s*([\s\S]*))?$", rest)
        if match:
            out.append(f"const {match.group(1)} = __docktv_import({source}, 'default');")
            rest = (match.group(2) or "").strip()
    if rest.startswith("*"):
        match = re.match(r"^\*\s*as\s+([^\s,{}]+)$", rest)
        if match:
            out.append(f"const {match.group(1)} = __docktv_import({source}, '*');")
    elif rest.startswith("{") and rest.endswith("}"):
        for entry in rest[1:-1].split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = re.split(r"\s+as\s+", entry)
            name = parts[0].strip()
            local = parts[1].strip() if len(parts) > 1 else name
            if name and local:
                out.append(f"const {local} = __docktv_import({source}, {json.dumps(name)});")
    return "\n".join(out)


def _strip_imports(code: str) -> str:
    """ES Module 脚本按普通脚本执行：import 转为全局绑定，export 关键字去掉。"""

    def replace_import(match: re.Match[str]) -> str:
        return _import_bindings(match.group(1), match.group(3))

    code = _IMPORT_RE.sub(replace_import, code)
    code = _SIDE_IMPORT_RE.sub("", code)
    code = _EXPORT_LIST_RE.sub("", code)
    code = _EXPORT_STAR_RE.sub("", code)
    code = re.sub(r"^([ \t]*)export\s+default\s+", r"\1", code, flags=re.MULTILINE)
    code = re.sub(r"^([ \t]*)export\s+", r"\1", code, flags=re.MULTILINE)
    return code


async def _script_code(site: SiteConfig, module: bool) -> str:
    cache_key = f"{'module' if module else 'script'}\x00{(site.api or '').strip()}"
    return await fetch_script(
        site,
        _code_cache,
        cache_key,
        error_cls=JsRuntimeError,
        timeout_floor=SCRIPT_TIMEOUT,
        transform=None if module else _strip_imports,
    )


def _script_path(key: str, code: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    path = _cache_dir() / f"{digest}.js"
    if not path.exists() or path.read_text(encoding="utf-8", errors="ignore") != code:
        path.write_text(code, encoding="utf-8")
    return path


def _cfg(site: SiteConfig) -> dict[str, Any]:
    return {"skey": site.key or site.api, "stype": site.type, "ext": site.ext}


def _state_path(site: SiteConfig) -> Path:
    digest = hashlib.sha1(f"{site.key}\x00{site.api}".encode("utf-8")).hexdigest()[:16]
    path = _cache_dir() / "state" / f"{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _parse_output(stdout: str, stderr: str) -> Any:
    result = None
    error = ""
    for line in stdout.splitlines():
        if line.startswith(RESULT_MARK):
            try:
                result = json.loads(line[len(RESULT_MARK):])
            except json.JSONDecodeError as exc:
                raise JsRuntimeError(f"脚本返回内容不是合法 JSON：{exc}") from exc
        elif line.startswith(ERROR_MARK):
            try:
                error = str(json.loads(line[len(ERROR_MARK):]).get("message") or "")
            except (json.JSONDecodeError, AttributeError):
                error = line[len(ERROR_MARK):]
    if error:
        raise JsRuntimeError(error.strip().splitlines()[0][:500])
    if result is None:
        detail = (stderr or "").strip().splitlines()
        message = detail[-1] if detail else "脚本没有返回结果"
        raise JsRuntimeError(f"脚本执行失败：{message[:300]}")
    return result


async def _run_job(job_path: Path, timeout: float) -> Any:
    node = _node()
    process = await asyncio.create_subprocess_exec(
        node,
        str(BRIDGE),
        str(job_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(BRIDGE.parent),
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise JsRuntimeError(f"脚本执行超时（{int(timeout)} 秒）") from exc
    return _parse_output(
        stdout.decode("utf-8", "ignore"), stderr.decode("utf-8", "ignore")
    )


async def call(site: SiteConfig, fn: str, args: list[Any] | None = None) -> Any:
    """执行脚本函数，返回脚本原始结果（dict / list）。"""
    try:
        module = site.runtime == "drpy"
        code = await _script_code(site, module)
        key = f"{'module' if module else 'script'}\x00{site.api.strip()}"
        script_path = _script_path(key, code)
        job: dict[str, Any] = {
            "script": str(script_path),
            "fn": fn,
            "args": list(args or []),
            "cfg": _cfg(site),
            "state": str(_state_path(site)),
        }
        if module:
            job["module"] = {"url": site.api.strip()}
            job["drpy"] = True
        fd, job_name = tempfile.mkstemp(prefix="job-", suffix=".json", dir=str(_cache_dir()))
        job_path = Path(job_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(job, handle, ensure_ascii=False)
            default_timeout = 90 if module else 20
            timeout = max(float(site.timeOut or 0), default_timeout)
            return await _run_job(job_path, timeout)
        finally:
            job_path.unlink(missing_ok=True)
    except JsRuntimeError:
        raise
    except FileNotFoundError as exc:
        raise JsRuntimeError(f"站点「{site.title}」脚本执行环境不完整：{exc}") from exc


async def prewarm(site: SiteConfig) -> None:
    """后台提前下载并落盘脚本，避免首次搜索时才去下载。"""
    module = site.runtime == "drpy"
    code = await _script_code(site, module)
    key = f"{'module' if module else 'script'}\x00{site.api.strip()}"
    _script_path(key, code)


def clear_cache() -> None:
    _code_cache.clear()
