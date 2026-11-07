"""站点熔断：连续失败的站点短暂停用，避免拖慢首页与聚合搜索。"""

from __future__ import annotations

import threading
import time

from .models import SiteConfig

FAILURE_THRESHOLD = 3
COOLDOWN = 300  # 秒
SEARCH_WINDOW = 600  # 搜索表现的统计窗口（秒）

_failures: dict[str, int] = {}
_open_until: dict[str, float] = {}
_lock = threading.Lock()
# key -> (最近成功时间, 耗时秒, 结果条数)
_search_stats: dict[str, tuple[float, float, int]] = {}
# key -> 最近一次搜索超时时间
_search_timeout: dict[str, float] = {}


def site_key(site: SiteConfig) -> str:
    return site.key or site.api


def is_open(site: SiteConfig) -> bool:
    """站点是否处于熔断冷却中（冷却结束后自动放行一次）。"""
    key = site_key(site)
    with _lock:
        until = _open_until.get(key)
        if not until:
            return False
        if until <= time.monotonic():
            _open_until.pop(key, None)
            _failures.pop(key, None)
            return False
        return True


def remaining(site: SiteConfig) -> int:
    key = site_key(site)
    with _lock:
        until = _open_until.get(key) or 0
    return max(0, int(until - time.monotonic()))


def record_failure(site: SiteConfig) -> None:
    key = site_key(site)
    with _lock:
        count = _failures.get(key, 0) + 1
        if count >= FAILURE_THRESHOLD:
            _open_until[key] = time.monotonic() + COOLDOWN
            _failures[key] = 0
        else:
            _failures[key] = count


def record_success(site: SiteConfig) -> None:
    key = site_key(site)
    with _lock:
        _failures.pop(key, None)
        _open_until.pop(key, None)


def record_search(site: SiteConfig, duration: float, count: int) -> None:
    """记录一次成功的站点搜索，用于给站点排序与调整超时。"""
    key = site_key(site)
    with _lock:
        _search_stats[key] = (time.monotonic(), float(duration), int(count))
        _search_timeout.pop(key, None)


def record_search_timeout(site: SiteConfig) -> None:
    key = site_key(site)
    with _lock:
        _search_timeout[key] = time.monotonic()


def search_rank(site: SiteConfig) -> float:
    """搜索时的站点优先级（越小越先搜）。

    近期有结果的快站最优先，其次是能响应但没结果的站点，再次是没记录的站点，
    最近超时的站点排最后，避免它们继续占用并发名额。
    """
    key = site_key(site)
    now = time.monotonic()
    with _lock:
        stats = _search_stats.get(key)
        failed = _search_timeout.get(key)
    if stats and now - stats[0] <= SEARCH_WINDOW:
        return 0.0 if stats[2] > 0 else 1.0 + stats[1]
    if failed and now - failed <= SEARCH_WINDOW:
        return 3.0
    return 2.0


def search_timeout(site: SiteConfig, default: float) -> float:
    """按站点历史表现给出本次搜索的等待上限。"""
    key = site_key(site)
    now = time.monotonic()
    with _lock:
        stats = _search_stats.get(key)
    if stats and now - stats[0] <= SEARCH_WINDOW:
        # 已知耗时：给 2.5 倍余量，并夹在 4 秒到默认值之间。
        return max(4.0, min(default, stats[1] * 2.5))
    # 没记录过的站点先给 6 秒，避免冷启动站点把首屏拖满默认超时。
    return min(default, 6.0)


def reset() -> None:
    with _lock:
        _failures.clear()
        _open_until.clear()
        _search_stats.clear()
        _search_timeout.clear()
