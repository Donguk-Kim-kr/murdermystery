# 화면(React)을 빌드한 뒤, 백엔드(FastAPI) 이미지에 담아 한 서버가 둘 다 서비스한다.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
# 마이그레이션 실행기(db/scripts/migrate.py)가 psql 을 쓴다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app backend/app
COPY backend/scripts backend/scripts
COPY db/migrations db/migrations
COPY db/scripts db/scripts
COPY --from=web /web/dist /app/static
ENV MM_STATIC_DIR=/app/static \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "backend/scripts/docker_start.py"]
