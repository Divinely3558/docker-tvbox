"""spider 运行时的统一异常类型。"""

from __future__ import annotations


class JarError(Exception):
    """JVM 侧返回的错误或 jar 下载/转换失败，消息直接用于界面提示。"""


class JarBroken(JarError):
    """spider 文件本身不是 jar/dex（通常是网盘返回了网页），重试也没用。"""
