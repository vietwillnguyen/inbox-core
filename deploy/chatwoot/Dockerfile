# The inbox-core Chatwoot service. Built from this repository's source.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY src ./src
RUN uv sync --locked --no-dev --extra chatwoot

RUN useradd --system --uid 10001 inboxcore && mkdir -p /data && chown inboxcore /data
USER inboxcore
EXPOSE 8000
CMD ["/app/.venv/bin/python", "-m", "inbox_core.chatwoot", "serve", "--port", "8000"]
