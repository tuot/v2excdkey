FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 安装必要的系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    curl && rm -rf /var/lib/apt/lists/*

ENV UV_PROJECT_ENVIRONMENT=/usr/local
# 复制依赖文件
COPY pyproject.toml uv.lock* ./

# 安装依赖（使用 uv）
RUN uv sync

# 复制项目源代码
COPY . .

ENV PYTHONUNBUFFERED=1

# 运行应用
CMD ["python", "main.py"]
