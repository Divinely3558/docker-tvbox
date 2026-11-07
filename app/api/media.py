"""媒体代理接口：/media、/img、/hls、/spider 与代理缓存清理。"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from .. import proxy
from ..net import to_ascii_url

router = APIRouter()


def _proxy_target(u: str, r: str, s: str, *, label: str = "代理") -> tuple[str, str]:
    if not proxy.verify(u, r, s):
        raise HTTPException(status_code=403, detail=f"{label}地址签名无效")
    url, referer = proxy.decode(u), proxy.decode(r)
    if not url.startswith(("http://", "https://")) or proxy.is_internal(url):
        raise HTTPException(status_code=400, detail=f"{label}地址不合法")
    return to_ascii_url(url), referer


@router.get("/media", response_model=None)
async def media(
    request: Request, u: str, r: str = "", s: str = ""
) -> Response | StreamingResponse:
    url, referer = _proxy_target(u, r, s)
    range_header = request.headers.get("range")
    if range_header:
        proxy.mark_urgent()
    else:
        proxy.note_segment(url, referer)
        hit = _cached_playlist(url, referer)
        if hit:
            return hit
        # 正好命中后台预取中的分片时，等它落盘，避免重复回源。
        await proxy.wait_prefetch(url)
        cached = await proxy.read_segment(url)
        if cached:
            data, content_type = cached
            return Response(
                content=data,
                media_type=content_type,
                headers={
                    "Content-Length": str(len(data)),
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "private, max-age=600",
                },
            )

    headers = proxy.request_headers(referer)
    headers["Accept-Encoding"] = "identity"
    for name in ("range", "if-range", "accept"):
        value = request.headers.get(name)
        if value:
            headers[name.title()] = value

    client = await proxy.get_client()
    try:
        upstream = await client.send(client.build_request("GET", url, headers=headers), stream=True)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"媒体请求失败：{exc.__class__.__name__}") from exc

    if upstream.status_code >= 400:
        status = upstream.status_code
        await upstream.aclose()
        raise HTTPException(status_code=502, detail=f"媒体源返回 HTTP {status}")

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    length = upstream.headers.get("content-length") or ""
    cacheable = bool(
        not range_header
        and upstream.status_code == 200
        and length.isdigit()
        and int(length) <= proxy.SEGMENT_MAX_ITEM
    )

    # 不少 spider 的播放列表地址没有 .m3u8 后缀，按首块内容识别后按列表处理。
    stream = upstream.aiter_raw()
    first = b""
    if not range_header and not upstream.headers.get("content-encoding"):
        try:
            first = await stream.__anext__()
        except StopAsyncIteration:
            first = b""
        if first.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"#EXTM3U"):
            chunks = [first]
            async for chunk in stream:
                chunks.append(chunk)
            text = b"".join(chunks).decode("utf-8", "ignore")
            final_url = str(upstream.url)
            await upstream.aclose()
            ttl = proxy.store_playlist(url, final_url, text, referer)
            return _playlist_response(proxy.rewrite_m3u8(text, final_url, referer), ttl)

    async def body():
        chunks: list[bytes] = []
        total = 0
        complete = False
        if first:
            yield first
            chunks.append(first)
            total += len(first)
        try:
            async for chunk in stream:
                yield chunk
                if cacheable and total + len(chunk) <= proxy.SEGMENT_MAX_ITEM:
                    chunks.append(chunk)
                    total += len(chunk)
            complete = True
        finally:
            await upstream.aclose()
        if complete and cacheable and chunks:
            await asyncio.to_thread(proxy.store_segment, url, b"".join(chunks), content_type)

    passthrough = {}
    for name in ("content-length", "content-range", "accept-ranges", "content-type"):
        value = upstream.headers.get(name)
        if value:
            passthrough[name] = value
    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        media_type=content_type,
        headers=passthrough,
    )


@router.get("/img")
async def image(u: str, r: str = "", s: str = "") -> Response:
    """海报图代理：带上站点要求的 Referer 抓图，并在本地留一份缓存。"""
    url, referer = _proxy_target(u, r, s, label="图片")

    hit = proxy.cached_pic(url)
    if hit:
        data, mime = hit
    else:
        headers = proxy.request_headers(referer)
        headers["Accept"] = "image/avif,image/webp,image/*,*/*;q=0.8"
        client = await proxy.get_client()
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=404, detail=f"图片返回 HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"图片请求失败：{exc.__class__.__name__}") from exc
        data = response.content
        mime = proxy.image_type(data, response.headers.get("content-type", ""))
        if not mime or not data:
            raise HTTPException(status_code=404, detail="目标地址不是图片")
        proxy.store_pic(url, data)

    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )


def _cached_playlist(url: str, referer: str) -> StreamingResponse | None:
    hit = proxy.cached_playlist(url, referer)
    if not hit:
        return None
    text, final_url = hit
    ttl = proxy.PLAYLIST_TTL_VOD if "#EXT-X-ENDLIST" in text else proxy.PLAYLIST_TTL_LIVE
    return _playlist_response(proxy.rewrite_m3u8(text, final_url, referer), ttl)


@router.get("/hls")
async def hls(u: str, r: str = "", s: str = "") -> Any:
    url, referer = _proxy_target(u, r, s)
    headers = proxy.request_headers(referer)

    cached = _cached_playlist(url, referer)
    if cached:
        return cached

    client = await proxy.get_client()
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        text = response.text
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"m3u8 返回 HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"m3u8 请求失败：{exc.__class__.__name__}") from exc

    if "#EXTM3U" not in text:
        raise HTTPException(status_code=502, detail="目标地址不是有效的 m3u8")

    ttl = proxy.store_playlist(url, str(response.url), text, referer)
    return _playlist_response(proxy.rewrite_m3u8(text, str(response.url), referer), ttl)


def _playlist_response(body: str, ttl: float) -> StreamingResponse:
    return StreamingResponse(
        iter([body.encode("utf-8")]),
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": f"private, max-age={int(ttl)}"},
    )


# 小代理体（m3u8/JSON）先读进内存判断类型，大文件直接流式返回。
SPIDER_SNIFF_BYTES = 512 * 1024


@router.get("/spider")
@router.get("/spider/index.m3u8")
async def spider_body(f: str, b: str = "", h: str = "", s: str = "") -> Response:
    try:
        path, headers, base = proxy.spider_body(f, b, h, s)
    except ValueError as exc:
        status = 403 if "签名" in str(exc) else 404
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    content_type = ""
    for name, value in list(headers.items()):
        if name.lower() == "content-type":
            content_type = value
            headers.pop(name)
    if path.stat().st_size <= SPIDER_SNIFF_BYTES:
        raw = path.read_bytes()
        if raw.lstrip().startswith(b"#EXTM3U"):
            text = proxy.rewrite_m3u8(raw.decode("utf-8", "ignore"), base)
            return _playlist_response(text, 5.0)
    return FileResponse(
        path,
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )


@router.post("/api/cache/clear")
async def clear_cache() -> dict[str, Any]:
    return {"ok": True, "files": proxy.clear_caches()}
