# Production Dockerfile — Day09 Multi-Agent

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY src/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Stage 2: Runtime
FROM python:3.11-slim AS runtime

RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

COPY --from=builder /root/.local /home/agent/.local
COPY src/ ./src/
COPY data/ ./data/

RUN mkdir -p /app/src/.chroma /app/src/artifacts/traces \
    && chown -R agent:agent /app

USER agent

ENV PYTHONUSERBASE=/home/agent/.local
ENV PATH=/home/agent/.local/bin:$PATH
ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD sh -c 'python -c "import os,urllib.request; urllib.request.urlopen(\"http://localhost:\"+os.environ.get(\"PORT\",\"8000\")+\"/health\")"' \
    || exit 1

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
