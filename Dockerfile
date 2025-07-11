FROM node:18-slim as frontend-builder

WORKDIR /app/frontend

# Copy frontend files
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Python backend stage
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -s /bin/bash app

WORKDIR /app

# Copy requirements and install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./

# Copy frontend build from first stage
COPY --from=frontend-builder /app/frontend/build ./static

# Create necessary directories
RUN mkdir -p data \
    && chown -R app:app /app

USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]