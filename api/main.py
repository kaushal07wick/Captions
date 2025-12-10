from fastapi import FastAPI, Query, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import tempfile
import os
import shutil
import time

# === LOCAL MODULES ===
from caption_whisper import process_caption_video, generate_captions, save_srt, burn_subtitles
from validate_captions import validate_caption_quality
from caption_position import detect_face_position

# # === PATH SETUP ===
# BASE_DIR = Path(__file__).resolve().parent           # /app  OR  /home/kaushal/captions/api
# PROJECT_ROOT = BASE_DIR.parent                      # /home/kaushal/captions
# FRONTEND_DIR = PROJECT_ROOT / "frontend"            # ✅ always correct
# OUTPUTS_DIR = PROJECT_ROOT / "outputs"              # /captions/outputs
# VIDEOS_DIR = OUTPUTS_DIR / "videos"
# SRT_DIR = OUTPUTS_DIR / "srt"

# for d in [VIDEOS_DIR, SRT_DIR]:
#     d.mkdir(parents=True, exist_ok=True)

# === PATH SETUP ===
BASE_DIR = Path(__file__).resolve().parent  # e.g. /app
FRONTEND_DIR = BASE_DIR / "frontend"        # /app/frontend (inside Docker)
OUTPUTS_DIR = Path("outputs")          
VIDEOS_DIR = OUTPUTS_DIR / "videos"
SRT_DIR = OUTPUTS_DIR / "srt"

for d in [VIDEOS_DIR, SRT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

if FRONTEND_DIR.exists():
    print(f"[INFO] Frontend found at: {FRONTEND_DIR}")
else:
    print(f"[WARN] Frontend not found at: {FRONTEND_DIR}. Running API-only mode.")
    FRONTEND_DIR = None


# === FASTAPI APP ===
app = FastAPI(title="Smart Captions API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === STATIC FILES ===
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
if FRONTEND_DIR:
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# === ROOT ENDPOINT ===
@app.get("/")
def serve_frontend():
    """Serve frontend index if present, else 404 message."""
    if not FRONTEND_DIR:
        return JSONResponse({"message": "Frontend not found"}, status_code=404)
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"message": "index.html missing"}, status_code=404)
    return FileResponse(index_file)


# === SERVE VIDEO FILE ===
@app.get("/serve/{filename}")
def serve_video(filename: str):
    """Serve a video file if it exists anywhere in known output paths."""
    possible_paths = [
        VIDEOS_DIR / filename,
        OUTPUTS_DIR / filename,
        BASE_DIR / filename,
    ]
    for path in possible_paths:
        if path.exists() and path.suffix == ".mp4":
            print(f"[INFO] Serving video: {path}")
            return FileResponse(path, media_type="video/mp4")
    raise HTTPException(status_code=404, detail=f"Video not found: {filename}")


# === UPLOAD LOCAL VIDEO ===
@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a local video, caption it, and burn subtitles."""
    try:
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_path = tmp_dir / file.filename
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        srt_path = SRT_DIR / f"{tmp_path.stem}.srt"
        out_path = VIDEOS_DIR / f"{tmp_path.stem}_captioned.mp4"

        print(f"[INFO] Generating captions for: {tmp_path.name}")
        segments = generate_captions(str(tmp_path))
        save_srt(segments, srt_path)

        alignment = detect_face_position(str(tmp_path))
        burn_subtitles(tmp_path, srt_path, out_path, alignment)

        # Wait for FFmpeg output to exist
        for _ in range(20):
            if out_path.exists() and out_path.stat().st_size > 5000:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"FFmpeg output not found: {out_path}")

        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[INFO] ✅ Captioned video created: {out_path}")

        return FileResponse(out_path, media_type="video/mp4", filename=out_path.name)

    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# === YOUTUBE CAPTIONING ===
@app.get("/generate")
def generate(youtube_url: str = Query(...)):
    """Download a YouTube video, caption it, and return metadata."""
    try:
        print(f"[INFO] Processing YouTube URL: {youtube_url}")
        output_path, meta = process_caption_video(youtube_url)
        out_path = Path(output_path).resolve()

        # Wait for FFmpeg output
        for _ in range(30):
            if out_path.exists() and out_path.stat().st_size > 10000:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Output not found: {out_path}")

        score = validate_caption_quality(meta["srt_path"])
        alignment = detect_face_position(meta["video_path"])

        print(f"[INFO] ✅ Captioned video ready at: {out_path}")

        return JSONResponse({
            "title": meta.get("title", "Untitled"),
            "alignment": alignment,
            "quality_score": score,
            "captioned_video": f"/serve/{out_path.name}",
            "srt_file": meta["srt_path"],
            "source": "youtube"
        })

    except Exception as e:
        print(f"[ERROR] YouTube captioning failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# === ENTRYPOINT ===
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
