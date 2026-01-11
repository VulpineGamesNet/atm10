FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY *.py ./

# Create keys directory
RUN mkdir -p /app/keys && chmod 777 /app/keys

ENV UV_CACHE_DIR=/app/.cache/uv
ENV PYTHONUNBUFFERED=1

RUN chmod -R 777 /app

CMD ["uv", "run", "python", "main.py"]
