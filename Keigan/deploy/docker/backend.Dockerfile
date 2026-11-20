# Keigan backend image — used by both the API (uvicorn) and the worker (python -m keigan.worker_main).
# Build from the repository root:  docker build -f deploy/docker/backend.Dockerfile -t keigan-backend:0.1.0 .
# Bookworm is pinned because Microsoft's ODBC Driver 18 (Azure SQL) is published per Debian release.
FROM python:3.12-slim-bookworm AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY backend/pyproject.toml ./
COPY backend/keigan ./keigan
RUN pip wheel --wheel-dir /wheels ".[azuresql]"

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    ENVIRONMENT=prod AUTH_MODE=entra RUN_WORKERS_IN_PROCESS=false AUTO_CREATE_SCHEMA=false \
    DATA_DIRECTORY=/tmp/keigan-data
# Microsoft ODBC Driver 18 for SQL Server (used by aioodbc to reach Azure SQL).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list -o /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 keigan && useradd --system --uid 10001 --gid keigan --no-create-home keigan
COPY --from=build /wheels /wheels
RUN pip install --no-index --find-links=/wheels "keigan[azuresql]" && rm -rf /wheels
# Database migrations (run by the Helm pre-install/pre-upgrade job: python -m alembic upgrade head)
WORKDIR /app
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
USER 10001:10001
EXPOSE 8080
# Read-only root filesystem friendly: only /tmp is written (mount an emptyDir there).
CMD ["uvicorn", "keigan.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
