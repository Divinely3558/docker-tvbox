"""SQLite 持久层。

使用 aiosqlite，每次操作独立连接，满足轻量部署场景。
注意：配置源的启用切换只写入数据库，**不回写 config.json**。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from .models import SourceEntry
from .settings import DATA_DIR

DB_PATH = DATA_DIR / "docktvbox.db"
ACTIVE_SOURCE_KEY = "active_source_id"
ALIYUN_TOKEN_KEY = "aliyun_token"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@asynccontextmanager
async def _connect() -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    async with _connect() as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS source (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                file TEXT NOT NULL DEFAULT '',
                headers TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1,
                ord INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                origin TEXT NOT NULL DEFAULT 'config'
            );

            CREATE TABLE IF NOT EXISTS site_cache (
                source_id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL,
                site_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES source(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS favorite (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                site_key TEXT NOT NULL,
                vod_id TEXT NOT NULL,
                name TEXT NOT NULL,
                pic TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE (site_key, vod_id)
            );

            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                site_key TEXT NOT NULL,
                vod_id TEXT NOT NULL,
                name TEXT NOT NULL,
                pic TEXT NOT NULL DEFAULT '',
                flag TEXT NOT NULL DEFAULT '',
                episode TEXT NOT NULL DEFAULT '',
                position REAL NOT NULL DEFAULT 0,
                duration REAL NOT NULL DEFAULT 0,
                device TEXT NOT NULL DEFAULT 'web',
                updated_at TEXT NOT NULL,
                UNIQUE (site_key, vod_id)
            );

            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_source_ord ON source(ord);
            """
        )
        cursor = await db.execute("PRAGMA table_info(source)")
        columns = {row["name"] for row in await cursor.fetchall()}
        if "origin" not in columns:
            # 旧库升级：config.json 里的源标记为 config，网页添加的源标记为 manual
            await db.execute(
                "ALTER TABLE source ADD COLUMN origin TEXT NOT NULL DEFAULT 'config'"
            )
        await db.commit()


async def sync_sources(entries: list[SourceEntry]) -> None:
    """把 config.json 里的源同步进数据库，保留已有记录的主键。"""
    async with _connect() as db:
        matched: list[int] = []
        for ord_, entry in enumerate(entries):
            name, url, file = entry.title, entry.url, entry.file
            cursor = await db.execute(
                "SELECT id FROM source WHERE name = ? AND url = ? AND file = ?"
                " AND origin = 'config'",
                (name, url, file),
            )
            row = await cursor.fetchone()
            headers_json = json.dumps(entry.headers, ensure_ascii=False)
            if row:
                await db.execute(
                    "UPDATE source SET headers = ?, enabled = ?, ord = ?, updated_at = ? WHERE id = ?",
                    (headers_json, int(entry.enabled), ord_, _now(), row["id"]),
                )
                matched.append(int(row["id"]))
            else:
                cursor = await db.execute(
                    "INSERT INTO source (name, url, file, headers, enabled, ord, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (name, url, file, headers_json, int(entry.enabled), ord_, _now()),
                )
                matched.append(int(cursor.lastrowid))
        # 清理 config.json 中已经移除的旧源；网页手动添加的源（origin=manual）保留
        if matched:
            placeholders = ",".join("?" * len(matched))
            await db.execute(
                f"DELETE FROM source WHERE origin = 'config' AND id NOT IN ({placeholders})",
                matched,
            )
        else:
            await db.execute("DELETE FROM source WHERE origin = 'config'")
        await db.commit()


async def list_sources() -> list[dict[str, Any]]:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT s.id, s.name, s.url, s.file, s.headers, s.enabled, s.ord, s.origin,"
            " COALESCE(c.site_count, 0) AS site_count, c.updated_at AS cached_at"
            " FROM source s LEFT JOIN site_cache c ON c.source_id = s.id"
            " ORDER BY s.ord, s.id"
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_source(source_id: int) -> dict[str, Any] | None:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT id, name, url, file, headers, enabled, ord, origin FROM source WHERE id = ?",
            (source_id,),
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


async def add_source(
    name: str, url: str, file: str = "", headers: dict[str, str] | None = None
) -> int:
    """新增网页手动添加的源（origin=manual），重启后不会被 config.json 同步清掉。"""
    async with _connect() as db:
        cursor = await db.execute("SELECT COALESCE(MAX(ord), -1) AS top FROM source")
        row = await cursor.fetchone()
        ord_ = int(row["top"]) + 1 if row else 0
        cursor = await db.execute(
            "INSERT INTO source (name, url, file, headers, enabled, ord, updated_at, origin)"
            " VALUES (?, ?, ?, ?, 1, ?, ?, 'manual')",
            (
                name,
                url,
                file,
                json.dumps(headers or {}, ensure_ascii=False),
                ord_,
                _now(),
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def delete_source(source_id: int) -> None:
    async with _connect() as db:
        # favorite/history 的外键未启用（SQLite 默认关 PRAGMA foreign_keys），手动级联
        await db.execute("DELETE FROM source WHERE id = ?", (source_id,))
        await db.execute("DELETE FROM site_cache WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM favorite WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM history WHERE source_id = ?", (source_id,))
        await db.commit()


async def get_state(key: str, default: str = "") -> str:
    """读取一个界面可改的键值（当前：当前源、阿里云盘 token）。"""
    async with _connect() as db:
        cursor = await db.execute("SELECT value FROM app_state WHERE key = ?", (key,))
        row = await cursor.fetchone()
    return str(row["value"]) if row and row["value"] is not None else default


async def set_state(key: str, value: str) -> None:
    async with _connect() as db:
        await db.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()


def mask_secret(value: str) -> str:
    """密钥只露尾串，完整值不回浏览器。"""
    return value[-8:].rjust(len(value), "*") if value else ""


async def aliyun_token_view() -> dict[str, Any]:
    token = await get_state(ALIYUN_TOKEN_KEY)
    return {"aliyun_token": mask_secret(token), "aliyun_token_set": bool(token)}


async def set_aliyun_token(token: str) -> dict[str, Any]:
    await set_state(ALIYUN_TOKEN_KEY, token.strip())
    return await aliyun_token_view()


async def get_active_source_id() -> int | None:
    try:
        return int(await get_state(ACTIVE_SOURCE_KEY))
    except (TypeError, ValueError):
        return None


async def set_active_source(source_id: int) -> None:
    await set_state(ACTIVE_SOURCE_KEY, str(source_id))


async def save_site_cache(
    source_id: int,
    payload: list[dict[str, Any]],
    meta: dict[str, Any],
    raw_sites: list[dict[str, Any]] | None = None,
) -> None:
    """缓存站点列表。``raw_sites`` 保留完整站点配置，内容接口据此构造驱动。"""
    data: dict[str, Any] = {"sites": payload, "meta": meta}
    if raw_sites:
        data["raw_sites"] = raw_sites
    async with _connect() as db:
        await db.execute(
            "INSERT INTO site_cache (source_id, payload, site_count, updated_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(source_id) DO UPDATE SET payload = excluded.payload,"
            " site_count = excluded.site_count, updated_at = excluded.updated_at",
            (source_id, json.dumps(data, ensure_ascii=False), len(payload), _now()),
        )
        await db.commit()


async def load_site_cache(source_id: int) -> dict[str, Any] | None:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT payload, updated_at FROM site_cache WHERE source_id = ?", (source_id,)
        )
        row = await cursor.fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["payload"])
    except json.JSONDecodeError:
        return None
    data["cached_at"] = row["updated_at"]
    return data


# ---------- 收藏 ----------


async def add_favorite(
    source_id: int, site_key: str, vod_id: str, name: str, pic: str = ""
) -> None:
    async with _connect() as db:
        await db.execute(
            "INSERT INTO favorite (source_id, site_key, vod_id, name, pic, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(site_key, vod_id) DO UPDATE SET name = excluded.name, pic = excluded.pic",
            (source_id, site_key, str(vod_id), name, pic, _now()),
        )
        await db.commit()


async def remove_favorite(site_key: str, vod_id: str) -> None:
    async with _connect() as db:
        await db.execute(
            "DELETE FROM favorite WHERE site_key = ? AND vod_id = ?", (site_key, str(vod_id))
        )
        await db.commit()


async def is_favorite(site_key: str, vod_id: str) -> bool:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT 1 FROM favorite WHERE site_key = ? AND vod_id = ?", (site_key, str(vod_id))
        )
        return bool(await cursor.fetchone())


async def list_favorites(limit: int = 100) -> list[dict[str, Any]]:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT source_id, site_key, vod_id, name, pic, created_at FROM favorite"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


# ---------- 历史 ----------


async def add_history(
    source_id: int,
    site_key: str,
    vod_id: str,
    name: str,
    pic: str = "",
    flag: str = "",
    episode: str = "",
    position: float = 0,
    duration: float = 0,
    device: str = "web",
) -> None:
    async with _connect() as db:
        await db.execute(
            "INSERT INTO history (source_id, site_key, vod_id, name, pic, flag, episode,"
            " position, duration, device, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(site_key, vod_id) DO UPDATE SET flag = excluded.flag,"
            " episode = excluded.episode, position = excluded.position,"
            " duration = excluded.duration, device = excluded.device,"
            " updated_at = excluded.updated_at, pic = excluded.pic, name = excluded.name",
            (
                source_id,
                site_key,
                str(vod_id),
                name,
                pic,
                flag,
                episode,
                float(position or 0),
                float(duration or 0),
                device,
                _now(),
            ),
        )
        await db.commit()


async def list_history(limit: int = 30) -> list[dict[str, Any]]:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT source_id, site_key, vod_id, name, pic, flag, episode, position,"
            " duration, device, updated_at FROM history ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_history(site_key: str, vod_id: str) -> dict[str, Any] | None:
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT source_id, site_key, vod_id, name, pic, flag, episode, position,"
            " duration, device, updated_at FROM history WHERE site_key = ? AND vod_id = ?",
            (site_key, str(vod_id)),
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


async def delete_history(site_key: str, vod_id: str) -> None:
    async with _connect() as db:
        await db.execute(
            "DELETE FROM history WHERE site_key = ? AND vod_id = ?", (site_key, str(vod_id))
        )
        await db.commit()
