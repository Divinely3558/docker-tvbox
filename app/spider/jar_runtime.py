"""Spider jar 站点运行时：常驻 JVM 进程的 JSON-line 客户端。

协议见 spider-runtime/runner/com/docktvbox/spider/Runner.java：
一行请求 -> 一行响应，响应按 ``id`` 匹配。进程按 spider jar 分组，
每个 jar 维护 ``SPIDER_POOL`` 个进程，取当前在途请求最少的一个。
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import itertools
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from ..settings import (
    JAVA_BIN,
    SPIDER_BUILD_CMD,
    SPIDER_DATA_DIR,
    SPIDER_IDLE_SECONDS,
    SPIDER_JVM_XMX,
    SPIDER_LIB_DIR,
    SPIDER_MAX_TIMEOUT,
    SPIDER_OUT_DIR,
    SPIDER_POOL_SIZE,
    SPIDER_RUNTIME_CLASSES,
)
from .errors import JarError

logger = logging.getLogger("docktvbox.jar")

# 浏览器访问本站用的源地址（scheme://host:port）；spider 用它拼本地代理链接。
BASE_URL: contextvars.ContextVar[str] = contextvars.ContextVar("base_url", default="")


class _Process:
    """一个常驻 Runner 进程。"""

    _ids = itertools.count(1)

    def __init__(self, jar: str) -> None:
        self.jar = jar
        self.proc: asyncio.subprocess.Process | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.ready: asyncio.Event | None = None
        self.reader: asyncio.Task | None = None
        self.err_reader: asyncio.Task | None = None
        self.inflight = 0
        self.last_use = 0.0
        self.lock = asyncio.Lock()

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def start(self) -> None:
        cmd = [
            JAVA_BIN,
            "-Xverify:none",
            f"-Xmx{SPIDER_JVM_XMX}",
            "-cp",
            f"{SPIDER_RUNTIME_CLASSES}:{SPIDER_LIB_DIR}/*",
            f"-Dspider.data.dir={SPIDER_DATA_DIR}",
            f"-Dspider.out.dir={SPIDER_OUT_DIR}",
            f"-Dspider.lib.dir={SPIDER_LIB_DIR}",
            "-Dfile.encoding=UTF-8",
            "com.docktvbox.spider.Runner",
        ]
        Path(SPIDER_OUT_DIR).mkdir(parents=True, exist_ok=True)
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise JarError(f"未找到 java（JAVA_BIN={JAVA_BIN}），spider jar 站点需要 JDK 17+，Docker 镜像已内置") from exc
        self.ready = asyncio.Event()
        self.reader = asyncio.create_task(self._pump())
        self.err_reader = asyncio.create_task(self._drain_stderr())
        await asyncio.wait_for(self.ready.wait(), timeout=30)

    async def _pump(self) -> None:
        proc = self.proc
        assert proc is not None and proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                resp = json.loads(line.decode("utf-8", "ignore"))
            except json.JSONDecodeError:
                continue
            if resp.get("ready"):
                if self.ready is not None:
                    self.ready.set()
                continue
            future = self.pending.pop(resp.get("id"), None)
            if future is not None and not future.done():
                future.set_result(resp)
        self._fail_all(JarError("spider 运行时进程已退出"))
        self.proc = None

    async def _drain_stderr(self) -> None:
        proc = self.proc
        if proc is None or proc.stderr is None:
            return
        with contextlib.suppress(Exception):
            while proc.returncode is None:
                line = await proc.stderr.readline()
                if not line:
                    break
                logger.debug("jar: %s", line.decode("utf-8", "ignore").rstrip())

    def _fail_all(self, exc: Exception) -> None:
        for future in self.pending.values():
            if not future.done():
                future.set_exception(exc)
        self.pending.clear()

    def stop(self) -> None:
        self._fail_all(JarError("spider 运行时已关闭"))
        if self.proc is not None and self.proc.returncode is None:
            self.proc.kill()
        if self.reader is not None:
            self.reader.cancel()
        if self.err_reader is not None:
            self.err_reader.cancel()
        self.proc = None
        self.reader = None
        self.err_reader = None

    async def request(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        async with self.lock:
            if not self.alive:
                self.stop()
                await self.start()
        assert self.proc is not None and self.proc.stdin is not None
        req_id = next(self._ids)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending[req_id] = future
        self.inflight += 1
        self.last_use = asyncio.get_running_loop().time()
        try:
            self.proc.stdin.write((json.dumps(dict(payload, id=req_id), ensure_ascii=False) + "\n").encode())
            await self.proc.stdin.drain()
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            self.stop()
            raise JarError(f"spider 调用超时（{timeout:.0f}s）") from exc
        finally:
            self.pending.pop(req_id, None)
            self.inflight -= 1


class JarRuntime:
    """按 jar 管理常驻进程池。"""

    def __init__(self) -> None:
        self._procs: dict[str, list[_Process]] = {}
        self._reaper: asyncio.Task | None = None

    def _pool(self, jar: str) -> list[_Process]:
        pool = self._procs.setdefault(jar, [])
        while len(pool) < SPIDER_POOL_SIZE:
            pool.append(_Process(jar))
        return pool

    def _pick(self, jar: str) -> _Process:
        pool = self._pool(jar)
        return min(pool, key=lambda p: p.inflight)

    def ensure_built(self) -> None:
        if Path(SPIDER_RUNTIME_CLASSES).is_dir():
            return
        logger.info("编译 spider-runtime：%s", " ".join(SPIDER_BUILD_CMD))
        subprocess.run(SPIDER_BUILD_CMD, check=False)

    async def call(
        self,
        jar: str,
        api: str,
        ext: str,
        method: str,
        args: list[Any] | None = None,
        *,
        params: dict[str, str] | None = None,
        flag: str = "",
        fresh: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """调用一个 spider 方法，返回反序列化后的 TVBox JSON。"""
        if not jar or not Path(jar).exists():
            raise JarError("配置源没有可用的 spider jar")
        self.ensure_built()
        timeout = timeout or SPIDER_MAX_TIMEOUT
        payload: dict[str, Any] = {
            "jar": jar,
            "api": api,
            "ext": ext,
            "method": method,
            "args": args or [],
            "flag": flag,
            "fresh": fresh,
            "base": BASE_URL.get(),
        }
        if params is not None:
            payload["params"] = params
        resp = await self._pick(jar).request(payload, timeout)
        if not resp.get("ok"):
            raise JarError(_brief(str(resp.get("error", "spider 调用失败"))))
        return _decode(resp.get("result"), resp)

    async def prewarm(self, jar: str) -> None:
        """提前启动一个常驻 Runner 进程，省掉首次调用的 JVM 启动等待。"""
        if not jar or not Path(jar).exists():
            return
        self.ensure_built()
        proc = self._pick(jar)
        # 与 request 共用同一把锁：并发启动会出现两个 _pump 抢读同一个 stdout。
        async with proc.lock:
            if not proc.alive:
                proc.stop()
                await proc.start()

    def start_reaper(self) -> None:
        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.create_task(self._reap())

    async def _reap(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = asyncio.get_running_loop().time()
            for pool in self._procs.values():
                for proc in pool:
                    if proc.alive and proc.inflight == 0 and now - proc.last_use > SPIDER_IDLE_SECONDS:
                        proc.stop()

    def shutdown(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
        for pool in self._procs.values():
            for proc in pool:
                proc.stop()
        self._procs.clear()


def _brief(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else "spider 调用失败"
    return first[:240]


def _decode(result: Any, resp: dict[str, Any]) -> Any:
    """Runner 可能回字符串、对象，或 proxy 的文件引用。"""
    if isinstance(result, dict) and result.get("kind") == "proxy":
        return result
    if isinstance(result, str):
        text = result.strip()
        if text.startswith(("{", "[")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return result
        return result
    return result


runtime = JarRuntime()
