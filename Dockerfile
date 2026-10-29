# The API image. The same file is what Render builds later.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev

FROM python:3.12-slim
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
COPY --chown=app:app cards ./cards
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
# the app is not root, and the spending ledger writes its file and lock here
RUN mkdir -p /app/data && chown app:app /app/data
USER app
EXPOSE 8000
CMD ["python", "-m", "werewolf.cli", "app", "serve", "--host", "0.0.0.0", "--port", "8000"]
