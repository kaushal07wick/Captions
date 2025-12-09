# ===========================
# STAGE 1: Base
# ===========================
FROM python:3.10-alpine AS base

WORKDIR /app

# Install ffmpeg and system dependencies
RUN apk add --no-cache ffmpeg bash

# Copy and install only requirements first for cache efficiency
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY api/ ./api/
COPY frontend/ ./frontend/

# Expose FastAPI port
EXPOSE 8000

# Run FastAPI app
CMD ["python", "-m", "api.main"]
