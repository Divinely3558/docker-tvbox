# docker-tvbox（影迷网页版）

**最新版本：v1.0.0**

TVBox 配置源的网页版聚合播放器：一个 Docker 镜像跑完整套服务，浏览器打开即用，PC 与手机自适应。复刻影迷 v2.6.5 APK 的交互与三爬虫运行时，无需安装任何 App。

## 功能特性

- **多配置源聚合**：`config.json` 定义多个订阅源，网页端一键切换，切换结果存 SQLite，不回写配置文件（支持只读挂载）
- **三爬虫运行时统一适配**：
  - Java jar spider（dex2jar 现场转换 + 常驻 Runner 进程池）
  - drpy / cat 系 JS spider（Node 桥接）
  - csp\_\* Python spider（原生桥接协议）
- **加固 jar 统一解包**：qemu + ARM64 JRE 运行 jar 自带 `Init.init()` 完成 dex 解密，缓存为普通 jar，新源零适配
- **全链路播放**：首页 / 分类 / 详情 / 搜索 / 播放，支持 HLS（hls.js）、直链、本地代理与解析器
- **媒体代理**：签名 URL 防滥用，HLS 分片与海报落盘缓存，支持 Range 拖动
- **站点健康度**：熔断、超时预算、失效站点自动降权与切换
- **用户数据**：观看历史、收藏、搜索历史（服务端 SQLite + 浏览器本地）
- **管理管控**：网页添加/删除配置源由 `SOURCE_PASSWORD` 环境变量控制

## 快速开始（Docker Compose，推荐）

克隆仓库：

```bash
git clone https://gitee.com/Portly6152/docker-tvbox.git
cd docker-tvbox
```

配置管理密码（用于网页添加配置源；不需要该功能可跳过）：

```bash
cp .env.example .env 2>/dev/null || echo "SOURCE_PASSWORD=你的密码" > .env
```

构建并启动：

```bash
docker compose up -d --build
```

访问：

```
http://127.0.0.1:8080
```

数据（SQLite、jar 缓存、ARM 运行时）持久化在 `./data` 目录，删除容器不丢数据。

## 本地开发

安装依赖并启动开发服务：

```bash
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8787
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SOURCE_PASSWORD` | 空 | 网页添加/删除配置源的管理密码，留空则关闭该功能 |
| `PROXY_SECRET` | 空 | 媒体代理签名密钥；留空每次启动随机生成（重启后旧代理地址失效） |
| `LOG_LEVEL` | `info` | 日志级别 |
| `WARMUP` | `1` | 启动后后台预热脚本与 spider JVM，置 `0` 关闭 |
| `ARM_UNPACK` | `1` | 允许 qemu 解包加固 jar，置 `0` 关闭 |
| `SPIDER_TIMEOUT` | `45` | 单次 spider 调用超时（秒） |
| `SEARCH_TIMEOUT` | `10` | 多源搜索单站超时（秒） |
| `DETAIL_TIMEOUT` | `15` | 详情页等待上限（秒） |
| `HOME_TIMEOUT` / `HOME_BUDGET` | `12` / `30` | 首页单站超时 / 整页预算（秒） |
| `SPIDER_JVM_XMX` | `512m` | 常驻 Runner 堆上限 |
| `SEGMENT_DISK_MB` / `PIC_CACHE_MB` | `1024` / `128` | 分片 / 海报磁盘缓存上限（MB） |
| `WEB_CONCURRENCY` | `1` | uvicorn worker 数 |

完整列表见 [app/settings.py](app/settings.py)。

## 配置源格式

`config.json` 的 `sources` 数组定义订阅源，**数组顺序即网页展示顺序，第一个为默认源**：

```json
{
  "sources": [
    { "name": "盒子迷", "url": "https://example.com/tvbox.json" },
    { "name": "本地样例", "file": "configs/local.json" }
  ]
}
```

支持 `url`（远程）或 `file`（本地文件）。配置源返回 HTML 留言页时会给出明确提示，并自动用 okhttp UA 重试。

## 目录结构

```
app/                FastAPI 后端
  api/              接口层（内容 / 媒体代理 / 配置源 / 用户数据）
  sites/            站点驱动（JSON API / jar / JS / Python 统一抽象）
  spider/           Java 与 JS 爬虫运行时、加固解包
spider-runtime/     JVM Runner、dex2jar、Android 兼容桩
static/             前端（ES module：js/api、ui、sources、pages/*）
templates/          Jinja2 页面
configs/            本地配置样例
config.json         订阅源配置（只读挂载）
data/               运行时数据（SQLite / 缓存 / jar，git 已忽略）
```

## 技术栈

- 后端：Python 3.13 · FastAPI · Jinja2 · aiosqlite · httpx
- 爬虫：OpenJDK 17（dex2jar + Runner）· Node.js（JS spider）· qemu-aarch64（加固解包）
- 前端：原生 ES module · hls.js
- 部署：Docker 多阶段构建（镜像约 550MB）· docker-compose

## 安全说明

- `.env`、`data/`（含 SQLite 中的阿里云盘 token）、参考资料目录均已 gitignore，不会进入仓库
- 媒体代理地址全部 HMAC 签名，内部地址段拒绝代理（防 SSRF）
- 请勿将包含真实 token 的 `data/` 目录提交到任何远程仓库

## 更新日志

### v1.0.0

**新增**

- TVBox 配置源聚合：多源管理、网页切换、切换结果存 SQLite 支持只读挂载
- 三爬虫运行时：Java jar（dex2jar + 常驻 Runner）、drpy/cat JS（Node 桥接）、csp\_\* Python（原生桥接）
- 加固 jar 统一解包：qemu + ARM64 JRE 运行 `Init.init()`，解密缓存复用
- 首页 / 分类 / 详情 / 搜索 / 播放全链路：首页加载第一个分类与 APK 对齐、无按钮自动加载、全站并发流式搜索按站分组折叠
- 媒体代理：签名 URL、HLS 分片与海报缓存、Range 支持、防 SSRF
- 观看历史、收藏、搜索历史、阿里云盘 token 设置
- 网页添加/删除配置源（`SOURCE_PASSWORD` 管控）
- Docker 一体化部署（docktvbox:lite），compose 最简配置
- 站点健康度：熔断、分层超时、失效站点自动降权与切换
