FROM python:3.10-slim

WORKDIR /app

# --- System dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git curl libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# --- Configure pip caching ---
# This enables persistent caching across Docker layers
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=100
ENV PIP_CACHE_DIR=/root/.cache/pip

# --- Copy only requirements first (for layer caching) ---
COPY api/requirements.txt ./requirements.txt

# --- Install CPU-only PyTorch + Whisper (cached layer) ---
# Torch 2.1.2 CPU wheel link (no CUDA)
RUN pip install torch==2.1.2+cpu torchvision==0.16.2+cpu torchaudio==2.1.2+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html

# --- Install project dependencies (cached layer) ---
# Keep whisper after deps to avoid downgrading torch
RUN pip install -r requirements.txt && \
    pip install openai-whisper==20231117

# --- Copy backend & frontend (invalidates cache only when files change) ---
COPY api /app
COPY frontend /app/frontend

# --- Create output directories ---
RUN mkdir -p /app/outputs/videos /app/outputs/srt

# --- Expose and run app ---
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
 