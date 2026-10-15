# Build the existing React/Vite dashboard, then package it with the FastAPI backend.
FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Playwright's base image includes the OS libraries Chromium needs.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble AS app
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium
COPY backend/ ./backend/
COPY --from=frontend-build /frontend/dist ./backend/static
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    PLAYWRIGHT_NO_SANDBOX=true \
    DATA_DIR=/var/data \
    DATABASE_URL=sqlite:////var/data/watchtower.db \
    SCREENSHOTS_DIR=/var/data/screenshots
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
