from fastapi import FastAPI, Query, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from caption import process_caption_video, generate_captions, save_srt, burn_subtitles
from validate_captions import validate_caption_quality
from caption_position import detect_face_position
from pathlib import Path
import tempfile
import os
  
# PATH SETUP
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
OUTPUTS_DIR = BASE_DIR / "outputs"
VIDEOS_DIR = OUTPUTS_DIR / "videos"
SRT_DIR = OUTPUTS_DIR / "srt"

VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
SRT_DIR.mkdir(parents=True, exist_ok=True)

if not FRONTEND_DIR.exists():
    raise RuntimeError(f"Frontend directory not found: {FRONTEND_DIR}")

  
# FASTAPI APP
app = FastAPI(title="Smart Captions API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend + generated outputs
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# FRONTEND
@app.get("/")
def serve_frontend():
    """Serve main frontend HTML."""
    return FileResponse(FRONTEND_DIR / "index.html")

# API: UPLOAD
@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """
    Handle direct video upload and return binary MP4 with Content-Disposition.
    """
    try:
        # Create temporary directory
        tmp_dir = Path(tempfile.mkdtemp())
        tmp_path = tmp_dir / file.filename
        
        # Save uploaded file
        with open(tmp_path, "wb") as f:
            f.write(await file.read())
        
        # Generate paths
        srt_path = SRT_DIR / f"{tmp_path.stem}.srt"
        out_path = VIDEOS_DIR / f"{tmp_path.stem}_captioned.mp4"
        
        # Generate captions
        segments = generate_captions(str(tmp_path))
        save_srt(segments, srt_path)
        
        # Detect face position
        alignment = detect_face_position(str(tmp_path))
        
        # Burn subtitles
        burn_subtitles(tmp_path, srt_path, out_path, alignment)
        
        # Clean up temp file
        try:
            tmp_path.unlink()
            tmp_dir.rmdir()
        except:
            pass
        
        # ✅ Return the binary video with proper headers
        return FileResponse(
            path=out_path,
            media_type="video/mp4",
            filename=f"{tmp_path.stem}_captioned.mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{tmp_path.stem}_captioned.mp4"'
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

  
# API: YOUTUBE
@app.get("/generate")
def generate(youtube_url: str = Query(..., description="YouTube Shorts URL")):
    """Generate captions, burn them, and return JSON metadata."""
    try:
        output_path, meta = process_caption_video(youtube_url)
        score = validate_caption_quality(meta["srt_path"])
        alignment = detect_face_position(meta["video_path"])
        
        # Make sure the path is relative to the outputs directory
        relative_path = str(output_path).replace(str(OUTPUTS_DIR), "/outputs")
        
        return JSONResponse({
            "title": meta["title"],
            "alignment": alignment,
            "quality_score": score,
            "captioned_video": relative_path,
            "srt_file": str(meta["srt_path"]),
            "source": "youtube"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)