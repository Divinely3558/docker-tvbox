# 加固 jar 解包需要在 x86 容器里跑 ARM64 JVM，只取一个静态 qemu 二进制（约 8MB）
FROM multiarch/qemu-user-static:latest AS qemu

# bookworm 而不是 trixie：dex2jar/Runner 在 openjdk-17 上验证过，Debian 13 已不再提供 17
FROM python:3.13-slim-bookworm AS spider-builder

# dex->JVM spider 运行时需要 javac 编译 Runner 与 android 兼容桩
RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

COPY spider-runtime /spider-runtime
RUN bash /spider-runtime/build.sh


FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    CONFIG_FILE=/app/config.json

WORKDIR /app

RUN pip install --no-cache-dir uv

# node：JS 脚本站点；jre + unzip：csp_ 站点（jar 在运行时用 dex2jar 现场转换）
# patchelf：加固 jar 的 ARM64 .so 要去掉 Android 专有依赖后才能被 glibc 加载
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs openjdk-17-jre-headless unzip patchelf \
    && rm -rf /var/lib/apt/lists/*

COPY --from=qemu /usr/bin/qemu-aarch64-static /usr/local/bin/qemu-aarch64-static

COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache -r pyproject.toml

COPY app ./app
COPY templates ./templates
COPY static ./static
COPY configs ./configs
COPY config.json ./config.json
COPY spider-runtime ./spider-runtime
COPY --from=spider-builder /spider-runtime/build/classes ./spider-runtime/build/classes

RUN mkdir -p /data

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers ${WEB_CONCURRENCY:-1}"]
