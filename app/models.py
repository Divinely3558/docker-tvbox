"""数据模型。

只建模本项目实际会用到的字段；TVBox 配置里其余字段通过
``extra="allow"`` 原样保留，避免因上游新增字段而解析失败。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceEntry(BaseModel):
    """config.json 里的一条配置源。"""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    url: str = ""
    file: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    @property
    def title(self) -> str:
        return self.name or self.url or self.file or "未命名源"


class SourceIndex(BaseModel):
    """config.json 的根结构。"""

    model_config = ConfigDict(extra="allow")

    sources: list[SourceEntry] = Field(default_factory=list)


class SiteConfig(BaseModel):
    """TVBox 配置里的 sites 条目。"""

    model_config = ConfigDict(extra="allow")

    key: str = ""
    name: str = ""
    type: int = 0
    api: str = ""
    ext: Any = ""
    jar: str = ""
    searchable: bool = True
    quickSearch: bool = True
    filterable: bool = True
    playerType: int = 0
    playerUrl: str = ""
    extHeader: str = ""
    changeable: bool = True
    timeOut: int = 0
    ua: str = ""

    @field_validator("searchable", "quickSearch", "filterable", mode="before")
    @classmethod
    def _default_bool(cls, value: Any) -> bool:
        """TVBox 配置里这些开关经常写成 0/1/null，null 视为开启。"""
        return True if value is None else bool(value)

    @property
    def title(self) -> str:
        return self.name or self.key or "未命名站点"

    @property
    def api_host(self) -> str:
        """站点 API 的主机名，用于列表展示。"""
        api = self.api.strip()
        if api.startswith(("csp_", "js", "py")):
            return api.split("://")[0][:24]
        try:
            host = urlparse(api).netloc
        except ValueError:
            host = ""
        return host or api[:24]

    @property
    def runtime(self) -> str:
        """站点运行时类型：json / spider / js / py / drpy / unknown。"""
        api = self.api.strip().lower()
        if api.startswith("csp_"):
            return "spider"
        if "drpy" in api:
            return "drpy"
        if api.endswith(".js") or api.startswith(("js:", "js/")):
            return "js"
        if api.endswith(".py") or api.startswith(("py:", "py/")):
            return "py"
        if self.type == 3:
            return "spider"
        if self.type in (0, 1, 4):
            return "json"
        return "unknown"

    @property
    def supported(self) -> bool:
        """直连 JSON、Python/JS/drpy 脚本、jar spider 四种运行时可用。"""
        return self.runtime in ("json", "py", "js", "drpy", "spider")

    @property
    def runtime_label(self) -> str:
        return {
            "json": "直连",
            "spider": "Spider",
            "js": "JS",
            "py": "Python",
            "drpy": "Drpy",
            "unknown": "未知",
        }.get(self.runtime, "未知")


class ParseConfig(BaseModel):
    """解析插件（M3 使用）。"""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    type: int = 0
    url: str = ""
    ext: Any = ""


class VodConfig(BaseModel):
    """一份完整的 TVBox 配置。"""

    model_config = ConfigDict(extra="allow")

    spider: str = ""
    sites: list[SiteConfig] = Field(default_factory=list)
    lives: list[Any] = Field(default_factory=list)
    parses: list[ParseConfig] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    wallpaper: str = ""
    logo: str = ""
    notice: str = ""
    danmaku: str = ""
    headers: list[Any] = Field(default_factory=list)
    proxy: list[Any] = Field(default_factory=list)
    rules: list[Any] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)
    ads: list[str] = Field(default_factory=list)
    urls: list[Any] = Field(default_factory=list)

    @property
    def supported_sites(self) -> list[SiteConfig]:
        return [site for site in self.sites if site.supported]


class Vod(BaseModel):
    """影片条目，字段沿用 TVBox 的 vod_* 命名。"""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    vod_id: str = ""
    vod_name: str = ""
    vod_pic: str = ""
    vod_year: str = ""
    vod_area: str = ""
    vod_remarks: str = ""
    vod_content: str = ""
    vod_play_from: str = ""
    vod_play_url: str = ""

    @property
    def type_name(self) -> str:
        """部分源用 type_name 表示分类。"""
        return str(getattr(self, "type_name", "") or getattr(self, "vod_type", "") or "")
