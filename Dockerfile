# new_stock_crawler의 DB SSOT + Docker 전환 가이드(docs 참고)와 동일한 패턴 적용
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

# Setup a non-root user
RUN groupadd --system --gid 999 nonroot \
    && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_TOOL_BIN_DIR=/usr/local/bin

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

ENV PATH="/app/.venv/bin:$PATH"

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Cron (컨테이너 내장 스케줄러 - docker-compose의 gainer-cron 서비스에서 사용)
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron tzdata \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Seoul

COPY docker/crontab /etc/cron.d/gainer-cron
RUN chmod 0644 /etc/cron.d/gainer-cron \
    && chmod +x /app/docker/run-sync.sh /app/docker/cron-entrypoint.sh

RUN chown -R nonroot:nonroot /app

ENTRYPOINT []

# gainer-cron 서비스는 docker-compose.yml에서 user: root로 오버라이드
# (cron 데몬 기동에 root 필요, 실제 작업은 run-sync.sh 안에서 su로 nonroot로 낮춤)
USER nonroot

CMD ["python", "main.py", "--help"]
