# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.13-slim-trixie
ARG STOCKFISH_VERSION=latest

# --- Resolve the Stockfish tag. Runs on every build, so `latest` really is the latest:
# the ADD of a remote URL is re-checked on each build, while a RUN alone would stay cached.
FROM ${PYTHON_IMAGE} AS stockfish-tag
ARG STOCKFISH_VERSION
ADD https://github.com/official-stockfish/Stockfish/releases/latest /tmp/cache-buster
COPY docker/fetch_stockfish.py /tmp/fetch_stockfish.py
RUN python /tmp/fetch_stockfish.py resolve "$STOCKFISH_VERSION" /tmp/stockfish-tag

# --- Download the binary. Cached by tag: COPY compares content, so an unchanged tag
# skips the 80 MB download.
FROM ${PYTHON_IMAGE} AS stockfish
ARG TARGETARCH
COPY --from=stockfish-tag /tmp/stockfish-tag /tmp/stockfish-tag
COPY docker/fetch_stockfish.py /tmp/fetch_stockfish.py
RUN --mount=type=secret,id=github_token,required=false \
    python /tmp/fetch_stockfish.py download "$(cat /tmp/stockfish-tag)" "$TARGETARCH" /opt/stockfish

# --- Python dependencies.
FROM ${PYTHON_IMAGE} AS deps
RUN pip install --quiet --no-cache-dir --root-user-action=ignore "uv==0.12.23"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

# --- Final image.
FROM ${PYTHON_IMAGE}
ARG STOCKFISH_VERSION
LABEL org.opencontainers.image.title="chess-trainer" \
      org.opencontainers.image.description="Local chess trainer: play Stockfish, drill your openings and review your games" \
      org.opencontainers.image.source="https://github.com/nielsencampos/chess-trainer" \
      org.opencontainers.image.licenses="GPL-3.0-only" \
      io.github.nielsencampos.chess-trainer.stockfish-requested="${STOCKFISH_VERSION}"

RUN useradd --create-home --uid 1000 app \
    && install -d -o app -g app /app/data

COPY --from=stockfish /opt/stockfish /opt/stockfish
RUN ln -s /opt/stockfish/stockfish /usr/local/bin/stockfish
COPY --from=deps /app/.venv /app/.venv
COPY app /app/app
COPY catalog /app/catalog
COPY openings /app/openings
COPY evals /app/evals
COPY web /app/web
COPY LICENSE THIRD_PARTY_LICENSES.md /app/

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
# A single worker on purpose: DuckDB allows one writing process per file (brief §3).
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
