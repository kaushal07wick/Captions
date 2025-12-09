# Base image
FROM python:3.10-slim

# --- System dependencies ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# --- Set work directory ---
WORKDIR /app

# --- Copy dependency list and install first (for better caching) ---
COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# --- Copy entire project ---
COPY . .

# --- Environment variables ---
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# --- Start the FastAPI app ---
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000"]
