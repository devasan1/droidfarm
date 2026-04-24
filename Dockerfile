# =============================================================
#  DroidFarm — containerized backend + frontend
#
#  Build:    docker build -t droidfarm .
#  Run:      docker run --rm -p 7870:7870 -v droidfarm-data:/data droidfarm
#  Or:       docker compose up
#
#  The image bundles the React frontend (pre-built) and the
#  Python FastAPI backend. On Linux, LDPlayer isn't available so
#  the mock driver is used by default — set DROIDFARM_DRIVER=redroid
#  and wire up redroid containers on the host if you want to
#  drive real Android instances.
# =============================================================

# -------- frontend builder --------
FROM node:20-alpine AS frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# -------- backend image --------
FROM python:3.11-slim
WORKDIR /app

# System deps: adb (for future redroid driver), curl for healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         android-tools-adb curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Backend
COPY backend/ /app/backend/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e /app/backend

# Frontend bundle (served from the backend)
COPY --from=frontend /app/dist /app/frontend/dist

ENV DROIDFARM_DATA_DIR=/data \
    DROIDFARM_STATIC_DIR=/app/frontend/dist \
    DROIDFARM_HOST=0.0.0.0 \
    DROIDFARM_PORT=7870

VOLUME ["/data"]
EXPOSE 7870

HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -f http://127.0.0.1:7870/api/health || exit 1

CMD ["uvicorn", "droidfarm.main:app", "--host", "0.0.0.0", "--port", "7870"]
