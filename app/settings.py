"""全局配置：路径、密钥、运行参数。

所有值都可以通过环境变量覆盖，便于 Docker 部署。
"""

from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path

# 项目根目录（app/ 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录：SQLite、缓存等可写文件都放这里
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))

# 多源配置文件（由用户维护，只读，不写回）
CONFIG_FILE = Path(os.getenv("CONFIG_FILE", str(BASE_DIR / "config.json")))

# 媒体代理签名密钥（/media、/hls、/img、/spider 的地址签名）
# 未配置时每次启动随机生成：避免使用公开弱默认值导致签名可被伪造；
# 代价是进程重启后旧的代理地址失效（播放列表缓存 TTL 到期后自动恢复）。
PROXY_SECRET = os.getenv("PROXY_SECRET", "").strip()
PROXY_SECRET_RANDOM = not PROXY_SECRET
if PROXY_SECRET_RANDOM:
    PROXY_SECRET = secrets.token_hex(16)
# 添加配置源的管理密码：由 Docker 环境变量注入，留空则禁止添加
SOURCE_PASSWORD = os.getenv("SOURCE_PASSWORD", "").strip()

# 日志级别
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()

# 模板与静态资源目录
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# 拉取远程配置的超时时间（秒）
CONFIG_TIMEOUT = float(os.getenv("CONFIG_TIMEOUT", "15"))

# 拉取配置时默认使用的 User-Agent
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# TVBox 客户端（okhttp）UA：部分配置站只对它返回 JSON
OKHTTP_UA = os.getenv("OKHTTP_UA", "okhttp/4.12.0")

# ---- spider jar 运行时（dex -> JVM）------------------------------------

SPIDER_DIR = BASE_DIR / "spider-runtime"
SPIDER_RUNTIME_CLASSES = Path(os.getenv("SPIDER_RUNTIME_CLASSES", str(SPIDER_DIR / "build/classes")))
SPIDER_LIB_DIR = Path(os.getenv("SPIDER_LIB_DIR", str(SPIDER_DIR / "lib")))
SPIDER_DATA_DIR = Path(os.getenv("SPIDER_DATA_DIR", str(DATA_DIR / "spider")))
SPIDER_OUT_DIR = Path(os.getenv("SPIDER_OUT_DIR", str(SPIDER_DATA_DIR / "out")))
SPIDER_JAR_DIR = Path(os.getenv("SPIDER_JAR_DIR", str(DATA_DIR / "jars")))
# 海报代理的落盘缓存：图片基本不变，滚页面时不重复回源
PIC_CACHE_DIR = Path(os.getenv("PIC_CACHE_DIR", str(DATA_DIR / "cache/pics")))
PIC_CACHE_MB = int(os.getenv("PIC_CACHE_MB", "128"))

# HLS 分片落盘缓存：拖动、重看、多设备共用时不再回源
SEGMENT_CACHE_DIR = Path(os.getenv("SEGMENT_CACHE_DIR", str(DATA_DIR / "cache/segments")))
SEGMENT_DISK_MB = int(os.getenv("SEGMENT_DISK_MB", "1024"))
JAVA_BIN = os.getenv("JAVA_BIN") or shutil.which("java") or "java"
# 常驻 Runner 的堆上限；容器内存紧张时调低
SPIDER_JVM_XMX = os.getenv("SPIDER_JVM_XMX", "512m")
# dex2jar 转换一次性的堆上限（大 jar 需要 1g 以上）
D2J_XMX = os.getenv("D2J_XMX", "1g")
# Runner 的构建命令，首次调用且 build/classes 缺失时执行
SPIDER_BUILD_CMD = ["bash", str(SPIDER_DIR / "build.sh")]
# 每个 spider jar 的常驻进程数（单进程更省内存，Docker 默认按 1 配置）
SPIDER_POOL_SIZE = int(os.getenv("SPIDER_POOL_SIZE", "1"))
# 单次 spider 调用超时（秒）
SPIDER_MAX_TIMEOUT = float(os.getenv("SPIDER_TIMEOUT", "45"))
# 多源搜索时单个站点的超时（秒），超时站点直接跳过，保证搜索页尽快出结果
SEARCH_SITE_TIMEOUT = float(os.getenv("SEARCH_TIMEOUT", "10"))
# 站点搜索结果的缓存时间（秒），重复搜索同一关键词可直接返回
SEARCH_CACHE_TTL = float(os.getenv("SEARCH_CACHE_TTL", "300"))
# 详情页等待上限（秒）：spider 卡住时不再白等 45 秒
DETAIL_TIMEOUT = float(os.getenv("DETAIL_TIMEOUT", "15"))
# 启动后是否在后台预热脚本与 spider JVM
WARMUP_ENABLED = os.getenv("WARMUP", "1").lower() not in {"0", "false", "no"}
# 空闲多久回收进程
SPIDER_IDLE_SECONDS = float(os.getenv("SPIDER_IDLE", "180"))

# ---- 加固（guard）jar 解包 ------------------------------------------------
# 是否允许用 qemu + ARM64 JRE 解包加固 jar；关闭时这类站点会给出明确提示
ARM_UNPACK_ENABLED = os.getenv("ARM_UNPACK", "1").lower() not in {"0", "false", "no"}
# 解包运行时目录：qemu / arm64 JRE / rootfs / 修补用的 libs 都放这里（可放挂载卷复用）
ARM_RUNTIME_DIR = Path(os.getenv("ARM_RUNTIME_DIR", str(DATA_DIR / "arm-runtime")))
# 指定 qemu-aarch64-static；留空则按 PATH 与运行时目录查找
ARM_QEMU_BIN = os.getenv("ARM_QEMU_BIN", "")
# 首次解包时自动下载（也可提前手工放进 ARM_RUNTIME_DIR/jre、/rootfs）
ARM_JRE_URL = os.getenv(
    "ARM_JRE_URL",
    "https://github.com/adoptium/temurin17-binaries/releases/download/"
    "jdk-17.0.21%2B9/OpenJDK17U-jre_aarch64_linux_hotspot_17.0.21_9.tar.gz",
)
ARM_ROOTFS_URL = os.getenv(
    "ARM_ROOTFS_URL",
    "https://cdimage.ubuntu.com/ubuntu-base/releases/22.04/release/"
    "ubuntu-base-22.04.5-base-arm64.tar.gz",
)
# 单次解包的超时（秒）：qemu 下跑 ARM JVM 比原生慢一个数量级
ARM_UNPACK_TIMEOUT = float(os.getenv("ARM_UNPACK_TIMEOUT", "180"))

# 首页单站等待上限与整页预算（秒）：坏站点不再让首页等 45 秒
HOME_TIMEOUT = float(os.getenv("HOME_TIMEOUT", "12"))
HOME_BUDGET = float(os.getenv("HOME_BUDGET", "30"))


def ensure_dirs() -> None:
    """确保数据目录存在。"""
    for path in (
        DATA_DIR,
        SPIDER_DATA_DIR,
        SPIDER_OUT_DIR,
        SPIDER_JAR_DIR,
        PIC_CACHE_DIR,
        SEGMENT_CACHE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
