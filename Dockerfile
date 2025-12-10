FROM python:3.10-slim

# --- Set working directory ---
WORKDIR /app

# --- System dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git curl libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# --- Configure pip caching ---
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=100
ENV PIP_CACHE_DIR=/root/.cache/pip

# --- Copy requirements early (for caching) ---
COPY api/requirements.txt ./requirements.txt

# --- Install CPU-only PyTorch + Whisper ---
RUN pip install torch==2.1.2+cpu torchvision==0.16.2+cpu torchaudio==2.1.2+cpu \
    -f https://download.pytorch.org/whl/torch_stable.html
RUN pip install -r requirements.txt && \
    pip install openai-whisper==20231117

# --- Pre-download Whisper model for faster runtime ---
RUN python3 -c "import whisper; whisper.load_model('base')"

# --- Copy backend, frontend, and start script ---
COPY api /app/api
COPY frontend /app/frontend
COPY start.sh /app/start.sh

# --- Permissions ---
RUN chmod +x /app/start.sh

# --- Create output folders ---
RUN mkdir -p /outputs/videos /outputs/srt

# --- Expose FastAPI port ---
EXPOSE 8000

# --- Default entrypoint ---
CMD ["./start.sh"]
