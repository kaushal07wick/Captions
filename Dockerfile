# Lightweight Python base
FROM python:3.10-slim

WORKDIR /app

# Install ONLY essential system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies efficiently
COPY api/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Expose Railway port
ENV PORT=8000
EXPOSE 8000

# Start FastAPI server
CMD ["python", "-m", "api.main"]
