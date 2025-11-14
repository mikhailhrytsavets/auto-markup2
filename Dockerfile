FROM proxy-registry.3opinion.ai/python:3.13.9-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential \
        python3-dev \
        libxml2-dev \
        libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip \
    && pip install "uv>=0.9,<1"

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen

COPY . .

RUN python -m compileall -q .


FROM proxy-registry.3opinion.ai/python:3.13.9-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m app

COPY --chown=app:app --from=builder /app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "5"]
