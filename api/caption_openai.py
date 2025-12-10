import re
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any
from pydub import AudioSegment
import pysrt
from openai import OpenAI
from dotenv import load_dotenv
import os
from caption_position import detect_face_position


# === ENV SETUP ===
load_dotenv(override=False)
_client = None


def get_openai_client() -> OpenAI:
    """Lazy-load OpenAI client with project-aware credentials."""
    global _client
    api_key = os.getenv("OPENAI_API_KEY")
    project_id = os.getenv("OPENAI_PROJECT_ID")
    org_id = os.getenv("OPENAI_ORG_ID", None)

    if not api_key:
        raise RuntimeError("❌ OPENAI_API_KEY not set — please enter it in the UI or .env.")
    if not project_id:
        raise RuntimeError("❌ OPENAI_PROJECT_ID not set — required for project-based API keys.")

    if _client is None:
        print(f"[INFO] Initializing OpenAI client → project={project_id}, org={org_id or 'default'}")
        _client = OpenAI(
            api_key=api_key,
            project=project_id,
            organization=org_id
        )
    return _client


# === PATHS ===
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
VIDEOS_DIR = OUTPUTS_DIR / "videos"
SRT_DIR = OUTPUTS_DIR / "srt"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
SRT_DIR.mkdir(parents=True, exist_ok=True)


# === HELPERS ===
def clean_title(t: str) -> str:
    return re.sub(r"\s+", "_", re.sub(r"[^\w\s-]", "", t)).strip("_")


def ffmpeg_escape(p: Path) -> str:
    return str(p).replace("\\", "\\\\").replace(":", "\\:").replace("'", r"\'").replace(",", r"\,")


def chunk_audio(f: Path, max_ms=9 * 60 * 1000) -> List[Path]:
    """Split long audio for API chunking."""
    audio = AudioSegment.from_file(str(f))
    out = []
    for i in range(0, len(audio), max_ms):
        tmp = Path(tempfile.mkstemp(suffix=f".chunk{i//max_ms+1}.mp3")[1])
        audio[i:i + max_ms].export(tmp, format="mp3")
        out.append(tmp)
    return out


def _to_dict(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict):
        return x
    for m in ("model_dump", "dict", "to_dict"):
        fn = getattr(x, m, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    try:
        return json.loads(str(x))
    except Exception:
        return {}


def trim_leading_silence(filepath: str, silence_threshold=-30.0, chunk_ms=10):
    """Remove initial silence to help Whisper start cleanly."""
    audio = AudioSegment.from_file(filepath)
    trim_ms = 0
    while trim_ms < len(audio) and audio[trim_ms:trim_ms+chunk_ms].dBFS < silence_threshold:
        trim_ms += chunk_ms
    trimmed = audio[trim_ms:]
    trimmed.export(filepath, format="mp3")
    if trim_ms > 0:
        print(f"[INFO] Trimmed {trim_ms/1000:.2f}s of leading silence from {filepath}")


# === FALLBACK SEGMENTATION ===
def fallback_segment_text(text: str, audio_path: str, words_per_segment: int = 7) -> List[Dict[str, Any]]:
    """Generate synthetic timestamped segments when Whisper returns text only."""
    audio = AudioSegment.from_file(audio_path)
    duration_sec = len(audio) / 1000
    words = text.split()
    if not words:
        return []
    n_segments = max(1, len(words) // words_per_segment)
    avg_dur = duration_sec / n_segments
    segments = []
    start = 0.0

    for i in range(0, len(words), words_per_segment):
        end = start + avg_dur
        chunk_words = words[i:i + words_per_segment]
        seg_text = " ".join(chunk_words).strip()
        segments.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "text": seg_text
        })
        start = end

    print(f"[INFO] 🔄 Fallback segmentation produced {len(segments)} timed chunks")
    return segments


# === CAPTION GENERATION ===
def generate_captions(audio_path: str) -> List[Dict[str, Any]]:
    print(f"[INFO] Transcribing with Whisper API → {audio_path}")
    trim_leading_silence(audio_path)
    client = get_openai_client()
    chunks = chunk_audio(Path(audio_path))
    segments_all = []
    offset = 0.0

    def _dedup(prev_text, new_text):
        """Remove overlap between consecutive segments."""
        overlap_len = 0
        for i in range(min(len(prev_text), len(new_text)), 0, -1):
            if prev_text[-i:].lower() == new_text[:i].lower():
                overlap_len = i
                break
        return new_text[overlap_len:].strip()

    last_text = ""

    for i, ch in enumerate(chunks, 1):
        if not ch.exists() or ch.stat().st_size == 0:
            raise RuntimeError(f"Invalid audio chunk: {ch}")

        with open(ch, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"],
                language="en"
            )

        d = _to_dict(result)
        segs = d.get("segments") or []

        # Fallback path (no timestamp data)
        if not segs:
            text = d.get("text", "").strip()
            if not text:
                raise RuntimeError("❌ No transcription text returned from Whisper API.")

            print("⚠️ Fallback: no timestamp granularity available for this project key.")
            try:
                gpt_resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Add punctuation and capitalization to the given English text."},
                        {"role": "user", "content": text}
                    ],
                    temperature=0
                )
                punctuated = gpt_resp.choices[0].message.content.strip()
                print("[INFO] Punctuation enhancement done via GPT.")
            except Exception as e:
                print(f"[WARN] GPT punctuation failed: {e}")
                punctuated = text

            segments_all.extend(fallback_segment_text(punctuated, audio_path))
            continue

        # Normal segmentation path
        for seg in segs:
            if "words" not in seg or not seg["words"]:
                continue

            words = seg["words"]
            chunk, chunk_start = [], None

            for w in words:
                word_text = w["word"].strip()
                word_start = float(w["start"])
                word_end = float(w["end"])

                if chunk_start is None:
                    chunk_start = word_start

                chunk.append(word_text)
                # chunk cutoff: 3 words or punctuation
                if len(chunk) >= 3 or re.search(r"[.!?]$", word_text):
                    chunk_end = word_end
                    text = " ".join(chunk).strip()
                    # deduplicate overlapping continuation
                    text = _dedup(last_text, text)
                    if text:
                        segments_all.append({
                            "start": round(chunk_start + offset, 2),
                            "end": round(chunk_end + offset, 2),
                            "text": text
                        })
                        last_text = text
                    chunk, chunk_start = [], None

            # Flush any remainder words
            if chunk:
                chunk_end = words[-1]["end"]
                text = " ".join(chunk).strip()
                text = _dedup(last_text, text)
                if text:
                    segments_all.append({
                        "start": round(chunk_start + offset, 2),
                        "end": round(chunk_end + offset, 2),
                        "text": text
                    })
                    last_text = text

        offset += segs[-1].get("end", 0)
        ch.unlink(missing_ok=True)
        print(f"[INFO] Chunk {i}/{len(chunks)} processed ({len(segs)} segments)")

    if not segments_all:
        raise RuntimeError("❌ No segments returned from Whisper API.")

    # smoothing
    for j in range(1, len(segments_all)):
        if segments_all[j]["start"] < segments_all[j-1]["end"]:
            segments_all[j]["start"] = segments_all[j-1]["end"] + 0.08
    if segments_all:
        segments_all[-1]["end"] += 0.4

    print(f"[INFO] ✅ {len(segments_all)} clean caption chunks generated.")
    return segments_all


# === SAVE SRT ===
def save_srt(segments: List[Dict[str, Any]], srt_path: Path):
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


# === BURN SUBTITLES ===
def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path, alignment=2, margin=None):
    if margin is None:
        if alignment in [1, 2, 3]:
            margin = 100
        elif alignment in [4, 5, 6]:
            margin = 20
        else:
            margin = 150

    style = (
        f"Fontname=Arial Black,"
        f"Fontsize=18,"
        f"Bold=1,"
        f"PrimaryColour=&HFFFFFF&,"
        f"BorderStyle=1,"
        f"OutlineColour=&H000000&,"
        f"Outline=2,"
        f"BackColour=&H80000000&,"
        f"Shadow=2,"
        f"Alignment={alignment},"
        f"MarginV={margin},MarginL=20,MarginR=20,WrapStyle=2"
    )
    vf = f"subtitles='{ffmpeg_escape(srt_path)}':force_style='{style}',format=yuv420p"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error",
            "-i", str(video_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            "-y", str(output_path)
        ],
        check=True
    )


# === MAIN PIPELINE ===
def process_caption_video(youtube_url: str):
    tmpdir = Path(tempfile.mkdtemp())
    raw_title = subprocess.run(
        ["yt-dlp", "--get-title", youtube_url],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    title = clean_title(raw_title) or "video"

    audio_path = tmpdir / "audio.mp3"
    video_path = tmpdir / "video.mp4"
    srt_path = SRT_DIR / f"{title}.srt"
    out_video = VIDEOS_DIR / f"{title}_captioned.mp4"

    subprocess.run(
        ["yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "mp3",
         "-o", str(audio_path), youtube_url],
        check=True
    )
    subprocess.run(
        ["yt-dlp", "-f", "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/mp4",
         "-o", str(video_path), youtube_url],
        check=True
    )

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("Audio download failed")
    if not video_path.exists() or video_path.stat().st_size == 0:
        raise RuntimeError("Video download failed")

    segments = generate_captions(str(audio_path))
    save_srt(segments, srt_path)

    try:
        align = int(detect_face_position(str(video_path)))
        if align not in range(1, 10):
            align = 2
    except Exception:
        align = 2

    burn_subtitles(video_path, srt_path, out_video, align)

    meta = {
        "title": title,
        "video_path": str(video_path),
        "srt_path": str(srt_path),
        "alignment": align,
        "source": "youtube",
    }

    print(f"[INFO] Returning relative path: {out_video}")
    return str(out_video), meta
