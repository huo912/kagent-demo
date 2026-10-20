# syntax=docker/dockerfile:1
# ------------------------------
# 构建阶段:使用 uv 创建带锁依赖的虚拟环境
# ------------------------------
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS build

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 先复制依赖清单,充分利用 Docker 层缓存
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ------------------------------
# 运行阶段:仅复制虚拟环境与代码,镜像最小化
# ------------------------------
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS runtime

WORKDIR /app

# 从构建阶段复制虚拟环境
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# 复制应用代码
COPY agent.py .

EXPOSE 8080

# kagent 控制器会访问 /health 进行健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=2)" || exit 1

# BYO Agent 必须监听 8080 端口并对外提供 A2A 协议
CMD ["python", "agent.py"]
