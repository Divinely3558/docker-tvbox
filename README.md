# docker-tvbox（影迷网页版）

**最新版本：v1.1.0**

TVBox 配置源的网页版播放器：一个 Docker 镜像跑完整套服务，浏览器打开即用，PC 与手机自适应。复刻影迷 v2.6.5 APK 的交互与三爬虫运行时，无需安装任何 App。

当前版本以**单源轻量**为目标：只维护一份配置源，屏蔽所有换源入口，关闭启动预热与整源 jar 预转换，把 CPU 与内存占用压到最低。仓库与镜像都不携带任何真实源，`config.json` 为空模板，由使用者自行填写。

## 功能特性

- **单源轻量模式**：默认只加载一份配置源，不提供网页换源/多源切换入口；启动不预热，jar 按需转换，空闲时常驻 JVM 最少
- **低占用搜索**：搜索直接走当前源里的直连 API 站（零 JVM），需要固定站点时用 `LITE_SEARCH_SITE` 指定
- **三爬虫运行时统一适配**：
  - Java jar spider（dex2jar 现场转换 + 常驻 Runner 进程池）
  - drpy / cat 系 JS spider（Node 桥接）
  - csp\_\* Python spider（原生桥接协议）
- **加固 jar 统一解包**：qemu + ARM64 JRE 运行 jar 自带 `Init.init()` 完成 dex 解密，缓存为普通 jar
- **全链路播放**：首页 / 分类 / 详情 / 搜索 / 播放，支持 HLS（hls.js）、直链、本地代理与解析器
- **媒体代理**：签名 URL 防滥用，HLS 分片与海报落盘缓存，支持 Range 拖动
- **站点健康度**：熔断、超时预算、失效站点自动降权
- **用户数据**：观看历史、收藏、搜索历史（服务端 SQLite + 浏览器本地）
- **旧多源代码归档**：多源管理与换源实现保留在 `olddata/`，不再参与构建，方便后续继续适配

## 快速开始（Docker Compose，推荐）

克隆仓库：

```bash
git clone https://gitee.com/Portly6152/docker-tvbox.git
cd docker-tvbox
```

构建并启动：

```bash
docker compose up -d --build
```

首次启动会在 `./data` 自动生成空的 `config.json`：

```json
{
  "url": ""
}
```

编辑该文件，把 `url` 换成自己的源地址：

```json
{
  "url": "https://example.com/tvbox.json"
}
```

也可以写本地文件 `"file": "/data/my-tvbox.json"`。

保存后重启容器生效：

```bash
docker compose restart
```

访问：

```
http://127.0.0.1:8080
```

数据（SQLite、配置、jar 缓存、ARM 运行时）持久化在 `./data` 目录，删除容器不丢数据。

## 本地开发

安装依赖并启动开发服务：

```bash
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8787
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LITE_MODE` | `1` | 轻量模式：单源、无换源入口、不预热、不整源预转换；置 `0` 可回到旧的多源逻辑（相关文件在 `olddata/`） |
| `LITE_SEARCH_SITE` | 空 | 轻量模式搜索使用的站点名；留空则搜索当前源里的第一个可用站点 |
| `PROXY_SECRET` | 空 | 媒体代理签名密钥；留空每次启动随机生成（重启后旧代理地址失效） |
| `LOG_LEVEL` | `info` | 日志级别 |
| `WARMUP` | `1` | 启动后后台预热脚本与 spider JVM；轻量模式下不生效，置 `0` 关闭 |
| `ARM_UNPACK` | `1` | 允许 qemu 解包加固 jar，置 `0` 关闭 |
| `SPIDER_TIMEOUT` | `45` | 单次 spider 调用超时（秒） |
| `SEARCH_TIMEOUT` | `10` | 搜索单站超时（秒） |
| `DETAIL_TIMEOUT` | `15` | 详情页等待上限（秒） |
| `HOME_TIMEOUT` / `HOME_BUDGET` | `20` / `30` | 首页单站超时 / 整页预算（秒） |
| `SPIDER_JVM_XMX` | `512m` | 常驻 Runner 堆上限 |
| `SEGMENT_DISK_MB` / `PIC_CACHE_MB` | `1024` / `128` | 分片 / 海报磁盘缓存上限（MB） |
| `WEB_CONCURRENCY` | `1` | uvicorn worker 数 |

完整列表见 [app/settings.py](app/settings.py)。

## 配置源格式

`config.json` 默认只放一个源，直接写 `url`（远程）或 `file`（本地文件）：

```json
{
  "url": "https://example.com/tvbox.json"
}
```

配置默认位于数据目录（Docker 内为 `/data/config.json`），可通过 `CONFIG_FILE` 覆盖。需要写多个源时仍可使用 `sources` 数组（按顺序加载，第一个为默认源），但轻量模式只会使用第一个。

配置源返回 HTML 留言页时会给出明确提示，并自动用 okhttp UA 重试。

## 目录结构

```
app/                FastAPI 后端
  api/              接口层（内容 / 媒体代理 / 用户数据）
  sites/            站点驱动（JSON API / jar / JS / Python 统一抽象）
  spider/           Java 与 JS 爬虫运行时、加固解包
spider-runtime/     JVM Runner、dex2jar、Android 兼容桩
static/             前端（ES module：js/api、ui、pages/*）
templates/          Jinja2 页面
olddata/            已归档的多源管理代码，不参与构建
config.json         空模板（仓库内不携带真实源，只有 url/file 字段）
data/               运行时数据（SQLite / config.json / 缓存 / jar，git 已忽略）
```

## 技术栈

- 后端：Python 3.13 · FastAPI · Jinja2 · aiosqlite · httpx
- 爬虫：OpenJDK 17（dex2jar + Runner）· Node.js（JS spider）· qemu-aarch64（加固解包）
- 前端：原生 ES module · hls.js
- 部署：Docker 多阶段构建 · docker-compose

## 安全说明

- `.env`、`data/`（含 SQLite 中的阿里云盘 token）、参考资料目录均已 gitignore，不会进入仓库
- 媒体代理地址全部 HMAC 签名，内部地址段拒绝代理（防 SSRF）
- 请勿将包含真实 token 或真实源地址的 `data/` 目录提交到任何远程仓库

## 更新日志

### v1.1.0

**新增**

- 轻量模式 `LITE_MODE`：单源运行，关闭启动预热、整源 jar 预转换与多站并发搜索
- 搜索站点可用 `LITE_SEARCH_SITE` 指定，默认搜索当前源里的第一个可用站点
- 首次启动自动在数据目录生成空 `config.json` 模板
- 直连源详情页自动把 m3u8 媒体线路排到最前

**变更**

- 仓库与镜像不再携带真实配置源，由使用者在 `data/config.json` 自行填写；配置简化为单个 `url` 或 `file`
- Docker 构建移除 `configs/`，安装依赖后卸载 uv 并清理缓存，镜像更小
- 首页、分类、搜索统一走单站逻辑，减少重复请求

**移除**

- 网页添加/删除配置源与换源入口
- `SOURCE_PASSWORD` 管理密码相关配置
- 多源并发搜索与换源弹层

**归档**

- 多源管理代码移至 `olddata/`：配置源接口、前端换源模块、`sources.css`、本地配置样例

### v1.0.0

**新增**

- TVBox 配置源聚合：多源管理、网页切换、切换结果存 SQLite 支持只读挂载
- 三爬虫运行时：Java jar（dex2jar + 常驻 Runner）、drpy/cat JS（Node 桥接）、csp\_\* Python（原生桥接）
- 加固 jar 统一解包：qemu + ARM64 JRE 运行 `Init.init()`，解密缓存复用
- 首页 / 分类 / 详情 / 搜索 / 播放全链路：首页加载第一个分类与 APK 对齐、无按钮自动加载
- 媒体代理：签名 URL、HLS 分片与海报缓存、Range 支持、防 SSRF
- 观看历史、收藏、搜索历史、阿里云盘 token 设置
- 网页添加/删除配置源（`SOURCE_PASSWORD` 管控）
- Docker 一体化部署（docktvbox:lite），compose 最简配置
- 站点健康度：熔断、分层超时、失效站点自动降权与切换
