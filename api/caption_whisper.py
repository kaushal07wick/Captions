"""
caption_whisper.py — Whisper-based captioning and rendering module.
Saves final videos in /outputs/videos and SRT files in /outputs/srt.
"""

import re
import subprocess
import tempfile
from pathlib import Path
import whisper
import pysrt
from caption_position import detect_face_position


# === PATH SETUP ===
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
VIDEOS_DIR = OUTPUTS_DIR / "videos"
SRT_DIR = OUTPUTS_DIR / "srt"

VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
SRT_DIR.mkdir(parents=True, exist_ok=True)


# === HELPERS ===
def clean_title(title: str) -> str:
    """Sanitize a YouTube title to be filesystem-safe."""
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"\s+", "_", title)
    return title.strip("_")


# === CAPTION GENERATION ===
def generate_captions(audio_path: str, model_size: str = "small"):
    """Generate timestamped captions using Whisper."""
    model = whisper.load_model(model_size)
    result = model.transcribe(audio_path)
    segments = result.get("segments", [])

    micro_segments = []
    for seg in segments:
        words = re.findall(r"\S+", re.sub(r"\s+", " ", seg["text"].strip()))
        if not words:
            continue

        dur = seg["end"] - seg["start"]
        per_word = dur / len(words)
        gap = 0.08

        for i in range(0, len(words), 3):
            chunk = words[i:i + 3]
            start = seg["start"] + i * per_word
            end = start + len(chunk) * per_word + 0.25
            text = " ".join(chunk)

            if 0 < i < len(words) - 3:
                text = re.sub(r'[,\"""\'?:;!-]', "", text)

            # Highlight key words
            text = re.sub(
                r"\b(AI|work|money|content|effort|manual|shorts|video|build|create)\b",
                r"{\\c&H00FFFF&}\1{\\c&HFFFFFF&}",
                text,
                flags=re.IGNORECASE,
            )

            if micro_segments and start <= micro_segments[-1]["end"]:
                start = micro_segments[-1]["end"] + gap
                end = max(start + 0.25, end)

            micro_segments.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "text": text.strip()
            })
    return micro_segments


# === SAVE CAPTIONS ===
def save_srt(segments, srt_path: Path):
    """Save caption segments as an SRT file."""
    subs = pysrt.SubRipFile()
    for i, seg in enumerate(segments, start=1):
        subs.append(
            pysrt.SubRipItem(
                index=i,
                start=pysrt.SubRipTime(seconds=seg["start"]),
                end=pysrt.SubRipTime(seconds=seg["end"]),
                text=seg["text"]
            )
        )
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    subs.save(srt_path, encoding="utf-8")


# === BURN CAPTIONS INTO VIDEO ===
def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path, alignment=2, margin=None):
    """
    Burn captions into a video with proper positioning.
    Saves output to /outputs/videos.
    """
    if margin is None:
        if alignment in [1, 2, 3]:
            margin = 100  # bottom
        elif alignment in [4, 5, 6]:
            margin = 20   # middle
        else:
            margin = 150  # top

    style = (
        f"Fontname=Arial Black,"
        f"Fontsize=20,"
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
            "-y", str(output_path)
        ],
        check=True
    )


# === FULL CAPTION PIPELINE ===
def process_caption_video(youtube_url: str):
    """Download video, transcribe, burn captions, save into /outputs/videos."""
    tmpdir = Path(tempfile.mkdtemp())

    raw_title = subprocess.run(
        ["yt-dlp", "--get-title", youtube_url],
        capture_output=True, text=True, check=True
    ).stdout.strip()
    title = clean_title(raw_title)

    # Paths
    audio_path = tmpdir / "audio.mp3"
    video_path = tmpdir / "video.mp4"
    srt_path = SRT_DIR / f"{title}.srt"
    out_video = VIDEOS_DIR / f"{title}_captioned.mp4"

    # Download both audio & video
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "mp3", "-o", str(audio_path), youtube_url],
        check=True
    )
    subprocess.run(
        ["yt-dlp", "-f", "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/mp4", "-o", str(video_path), youtube_url],
        check=True
    )

    if not video_path.exists() or video_path.stat().st_size == 0:
        raise RuntimeError(f"Video download failed for {youtube_url}")
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError(f"Audio download failed for {youtube_url}")

    # Generate captions
    segments = generate_captions(str(audio_path))
    save_srt(segments, srt_path)

    # Determine alignment
    alignment = detect_face_position(str(video_path))

    # Burn and export into outputs/videos
    burn_subtitles(video_path, srt_path, out_video, alignment)

    meta = {
        "title": title,
        "video_path": str(video_path),
        "srt_path": str(srt_path),
    }

    print(f"[INFO] ✅ Captioned video saved at: {out_video}")
    return str(out_video), meta
