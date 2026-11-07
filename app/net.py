"""URL 规范化。

TVBox 配置里常见中文域名与中文路径，httpx 只接受 ASCII URL，
这里统一把主机名转 punycode、路径与查询参数做百分号编码。
"""

from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit

_SAFE_PATH = "/%:@!$&'()*+,;="
_SAFE_QUERY = "=&%:@!$'()*+,;/?-._~"


def to_ascii_url(url: str) -> str:
    """返回可直接用于 HTTP 请求的 ASCII 地址；非 http(s) 原样返回。"""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    host = parts.hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass

    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"

    path = quote(parts.path, safe=_SAFE_PATH)
    query = quote(parts.query, safe=_SAFE_QUERY)
    return urlunsplit((parts.scheme, netloc, path, query, ""))
