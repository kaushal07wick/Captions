"""
caption.py — Core caption generation + rendering module
using OpenAI gpt-4o-mini-transcribe for speech-to-text.
Automatically chunks audio >25 MB, saves .srt, and burns captions with FFmpeg.
"""

import re
import math
import subprocess
import tempfile
from pathlib import Path
from pydub import AudioSegment
import pysrt
from openai import OpenAI
from caption_position import detect_face_position
from dotenv import load_dotenv
import os

# === Load environment ===
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in environment (.env)")

# === Paths ===
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
VIDEOS_DIR = OUTPUTS_DIR / "videos"
SRT_DIR = OUTPUTS_DIR / "srt"

VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
SRT_DIR.mkdir(parents=True, exist_ok=True)

# === OpenAI client ===
client = OpenAI(api_key=OPENAI_API_KEY)


# === Helpers ===
def clean_title(title: str) -> str:
    """Sanitize title for safe filenames."""
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"\s+", "_", title)
    return title.strip("_")


# === Caption Generation ===
def generate_captions(audio_path: str):
    """
    Generate timestamped captions using gpt-4o-mini-transcribe.
    Splits >25 MB files into ~9-minute chunks.
    """
    print(f"[INFO] Transcribing via gpt-4o-mini-transcribe → {audio_path}")

    audio = AudioSegment.from_file(audio_path)
    max_chunk_ms = 9 * 60 * 1000  # ~9 minutes, keeps file <25MB
    chunks = [audio[i:i + max_chunk_ms] for i in range(0, len(audio), max_chunk_ms)]

    all_segments = []
    offset = 0.0

    for i, chunk in enumerate(chunks, start=1):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_chunk:
            chunk.export(tmp_chunk.name, format="mp3")
            tmp_chunk.flush()

            with open(tmp_chunk.name, "rb") as f:
                result = client.audio.transcriptions.create(
                    model="gpt-4o-transcribe",
                    file=f,
                    response_format="json",  # ✅ FIXED: use 'json'
                )

            print(f"[INFO] Chunk {i}/{len(chunks)} transcribed.")
            text = result.text.strip()
            if not text:
                continue

            # Since `json` response doesn't include timestamps, we’ll fake-segment by duration proportionally.
            seg = {
                "start": offset,
                "end": offset + chunk.duration_seconds,
                "text": text,
            }
            all_segments.append(seg)

        offset += chunk.duration_seconds

    # === Fine-grain micro-segmentation ===
    micro_segments = []
    for seg in all_segments:
        text = seg["text"].strip()
        if not text:
            continue

        words = re.findall(r"\S+", re.sub(r"\s+", " ", text))
        dur = seg["end"] - seg["start"]
        per_word = dur / len(words) if len(words) > 0 else 0.5
        gap = 0.08

        for i in range(0, len(words), 3):
            chunk_words = words[i:i + 3]
            start = seg["start"] + i * per_word
            end = start + len(chunk_words) * per_word + 0.25
            text_chunk = " ".join(chunk_words)

            if 0 < i < len(words) - 3:
                text_chunk = re.sub(r'[,"\'“”‘’:;?!-]', "", text_chunk)

            text_chunk = re.sub(
                r"\b(AI|work|money|content|manual|shorts|video|build|create)\b",
                r"{\\c&H00FFFF&}\1{\\c&HFFFFFF&}",
                text_chunk,
                flags=re.IGNORECASE,
            )

            if micro_segments and start <= micro_segments[-1]["end"]:
                start = micro_segments[-1]["end"] + gap
                end = max(start + 0.25, end)

            micro_segments.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "text": text_chunk.strip(),
            })

    # --- 🩵 FIX: extend the last caption slightly so it isn’t cut off ---
    if micro_segments:
        micro_segments[-1]["end"] += 2.0  # add 2s of tail buffer

    return micro_segments



# === Save Captions ===
def save_srt(segments, srt_path: Path):
    """Write caption segments to .srt file."""
    subs = pysrt.SubRipFile()
    for i, seg in enumerate(segments, start=1):
        subs.append(
            pysrt.SubRipItem(
                index=i,
                start=pysrt.SubRipTime(seconds=seg["start"]),
                end=pysrt.SubRipTime(seconds=seg["end"]),
                text=seg["text"],
            )
        )
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    subs.save(srt_path, encoding="utf-8")


# === Burn Captions ===
def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path, alignment=2, margin=None):
    """Embed captions into the video using FFmpeg with styling."""
    if margin is None:
        if alignment in [1, 2, 3]:
            margin = 100
        elif alignment in [4, 5, 6]:
            margin = 20
        else:
            margin = 150

    style = (
        f"Fontname=Arial Black,"
        f"Fontsize=16,"
        f"Bold=1,"
        f"PrimaryColour=&HFFFFFF&,"
        f"BorderStyle=1,"
        f"OutlineColour=&H000000&,"
        f"Outline=1,"
        f"BackColour=&H80000000&,"
        f"Shadow=2,"
        f"Alignment={alignment},"
        f"MarginV={margin},"
        f"MarginL=20,"
        f"MarginR=20,"
        f"WrapStyle=2"
    )

    vf = f"subtitles='{srt_path}':force_style='{style}',format=yuv420p"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "ffmpeg",
            "-loglevel", "error",
            "-i", str(video_path),
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y", str(output_path),
        ],
        check=True,
    )


# === Main Captioning Pipeline ===
def process_caption_video(youtube_url: str):
    """Download → transcribe → align → burn → return metadata."""
    tmpdir = Path(tempfile.mkdtemp())

    # Get and sanitize title
    raw_title = subprocess.run(
        ["yt-dlp", "--get-title", youtube_url],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    title = clean_title(raw_title)

    # Paths
    audio_path = tmpdir / "audio.mp3"
    video_path = tmpdir / "video.mp4"
    srt_path = SRT_DIR / f"{title}.srt"
    out_video = VIDEOS_DIR / f"{title}_captioned.mp4"

    # Download audio/video
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "mp3", "-o", str(audio_path), youtube_url],
        check=True,
    )
    subprocess.run(
        ["yt-dlp", "-f", "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/mp4", "-o", str(video_path), youtube_url],
        check=True,
    )

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("Audio download failed.")
    if not video_path.exists() or video_path.stat().st_size == 0:
        raise RuntimeError("Video download failed.")

    # Transcribe
    segments = generate_captions(str(audio_path))
    save_srt(segments, srt_path)

    # Detect face for alignment
    alignment = detect_face_position(str(video_path))

    # Burn captions
    burn_subtitles(video_path, srt_path, out_video, alignment)

    meta = {
        "title": title,
        "video_path": str(video_path),
        "srt_path": str(srt_path),
        "alignment": alignment,
        "source": "youtube",
    }

    return str(out_video), meta
