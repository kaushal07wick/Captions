# server/ssm_server.py

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


# === PATH SETUP ===
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
OUTPUTS_DIR = BASE_DIR / "outputs"
VIDEOS_DIR = OUTPUTS_DIR / "videos"
SRT_DIR = OUTPUTS_DIR / "srt"

for d in [VIDEOS_DIR, SRT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

if FRONTEND_DIR.exists():
    print(f"[INFO] Frontend found at: {FRONTEND_DIR}")
else:
    print(f"[WARN] Frontend not found at: {FRONTEND_DIR}. Running in API-only mode.")
    FRONTEND_DIR = None


# === FASTAPI APP ===
app = FastAPI(title="CaptionGen API", description="Local Whisper-based YouTube Shorts captioning")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === STATIC FILE SERVING ===
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
if FRONTEND_DIR:
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# === HEALTHCHECK ===
@app.get("/health")
def health_check():
    return {"status": "ok", "engine": "local", "mode": "offline"}


# === SERVE VIDEO ===
@app.get("/serve/{filename}")
def serve_video(filename: str):
    """Serve any captioned video."""
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


# === LOCAL VIDEO UPLOAD ===
@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video, run local captioning (Whisper + FFmpeg), and return final video."""
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="captiongen_"))
        tmp_path = tmp_dir / file.filename
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        srt_path = SRT_DIR / f"{tmp_path.stem}.srt"
        out_path = VIDEOS_DIR / f"{tmp_path.stem}_captioned.mp4"

        print(f"[INFO] 🎬 Processing local video: {tmp_path.name}")
        segments = generate_captions(str(tmp_path))
        save_srt(segments, srt_path)

        alignment = detect_face_position(str(tmp_path))
        burn_subtitles(tmp_path, srt_path, out_path, alignment)

        for _ in range(20):
            if out_path.exists() and out_path.stat().st_size > 5000:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"FFmpeg output not found: {out_path}")

        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[INFO] ✅ Captioned video ready: {out_path}")

        return FileResponse(out_path, media_type="video/mp4", filename=out_path.name)

    except Exception as e:
        print(f"[ERROR] Upload failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# === YOUTUBE CAPTIONING ===
@app.get("/generate")
def generate_from_youtube(youtube_url: str = Query(...)):
    """Fetch a YouTube Shorts, caption it, and return metadata."""
    try:
        print(f"[INFO] 📥 Fetching YouTube video: {youtube_url}")
        output_path, meta = process_caption_video(youtube_url)
        out_path = Path(output_path).resolve()

        for _ in range(30):
            if out_path.exists() and out_path.stat().st_size > 10000:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Output not found: {out_path}")

        score = validate_caption_quality(meta["srt_path"])
        alignment = detect_face_position(meta["video_path"])

        print(f"[INFO] ✅ Completed captioning for: {meta.get('title', 'Untitled')}")

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
    uvicorn.run("ssm_server:app", host="0.0.0.0", port=port, reload=True)
