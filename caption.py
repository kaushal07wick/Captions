"""
Generates clean, synced captions for YouTube Shorts using:
- Whisper (speech-to-text)
- yt-dlp (stream fetch)
- FFmpeg (caption rendering)

Core features:
    2 - 3 word micro-captions for natural rhythm
    No overlapping text between frames
    Clean white/yellow text (no background)
    Cinematic fade-in/out caption transitions
"""
import os
import sys
import subprocess
import tempfile
import whisper
import pysrt
import re

# audio -> text -> captions
def generate_captions(audio_path, model_size="small"):
    """
    Transcribes speech into readable, synchronized caption chunks.

    Process:
    1. Run Whisper to get timestamps + text segments.
    2. Split long sentences into 2 - 3 word “micro-segments”.
    3. Remove mid-line punctuation (for smoother reading).
    4. Fix timestamp overlaps between micro-segments.

    Args:
        audio_path (str): Path to audio file (.mp3)
        model_size (str): Whisper model size (tiny, small, base, etc.)

    Returns:
        list[dict]: Each dict → {"start": float, "end": float, "text": str}
    """
    print(f"[+] Loading Whisper model: {model_size}")
    model = whisper.load_model(model_size)

    print(f"[+] Transcribing audio ...")
    result = model.transcribe(audio_path)
    segments = result["segments"]

    micro_segments = []

    for seg in segments:
        raw_text = seg["text"].strip()
        raw_text = re.sub(r"\s+", " ", raw_text)  # Normalize whitespace
        words = re.findall(r"\S+", raw_text)
        total_words = len(words)
        duration = seg["end"] - seg["start"]

        if total_words == 0:
            continue

        time_per_word = duration / total_words
        chunk_len = 3  # 2–3 words per caption
        gap = 0.08  # 80ms gap between captions

        for i in range(0, total_words, chunk_len):
            chunk_words = words[i:i + chunk_len]
            chunk_start = seg["start"] + i * time_per_word
            chunk_end = chunk_start + len(chunk_words) * time_per_word + 0.3

            chunk_start = round(chunk_start, 2)
            chunk_end = round(chunk_end, 2)

            # Remove punctuation inside intermediate chunks
            text = " ".join(chunk_words)
            if i > 0 and i + chunk_len < total_words:
                text = re.sub(r"[,\"“”‘’:;?!-]", "", text)

            # Highlight meaningful keywords with ASS color tags
            text = re.sub(
                r"\b(AI|work|money|content|effort|manual|shorts|video|build|create)\b",
                r"{\\c&H00FFFF&}\\1{\\c&HFFFFFF&}",  # Cyan highlight
                text,
                flags=re.IGNORECASE,
            )

            # Prevent overlapping timestamps
            if micro_segments and chunk_start <= micro_segments[-1]["end"]:
                chunk_start = micro_segments[-1]["end"] + gap
                chunk_end = max(chunk_start + 0.3, chunk_end)

            micro_segments.append({
                "start": chunk_start,
                "end": chunk_end,
                "text": text.strip()
            })

    # Ensure ascending order and spacing consistency
    for i in range(1, len(micro_segments)):
        if micro_segments[i]["start"] <= micro_segments[i-1]["end"]:
            micro_segments[i]["start"] = micro_segments[i-1]["end"] + gap

    print(f"[+] Generated {len(micro_segments)} refined captions.")
    return micro_segments

#save captions into srt
def save_srt(segments, output_path="captions.srt"):
    """
    Writes caption data to an SRT file compatible with FFmpeg subtitle filters.

    Args:
        segments (list[dict]): Caption list from generate_captions()
        output_path (str): Destination path for the SRT file
    """
    subs = pysrt.SubRipFile()
    for i, seg in enumerate(segments, start=1):
        clean_text = seg["text"].strip().replace("\n", " ")
        subs.append(
            pysrt.SubRipItem(
                index=i,
                start=pysrt.SubRipTime(seconds=seg["start"]),
                end=pysrt.SubRipTime(seconds=seg["end"]),
                text=clean_text
            )
        )
    subs.save(output_path, encoding="utf-8")
    print(f"[+] Saved styled captions to {output_path}")

# burn captions in video
def burn_subtitles(video_path, srt_path, output_path="captioned.mp4"):
    """
    Burns captions directly into the video using FFmpeg.
    Adds fade transitions and removes background blocks.

    Style:
        - White text
        - Yellow highlights for key terms
        - No background box
        - Soft fade-in/fade-out transitions

    Args:
        video_path (str): Input video file
        srt_path (str): Subtitle file (.srt)
        output_path (str): Final captioned video output path
    """
    print("[+] Burning captions with cinematic fade effect ...")
    try:
        # Define style: center-bottom alignment, clean text, small outline
        fade_filter = (
            "subtitles="
            f"{srt_path}:force_style='"
            "Alignment=2,Fontname=Arial,Fontsize=28,"
            "PrimaryColour=&HFFFFFF&,BorderStyle=1,"
            "OutlineColour=&H000000&,Outline=1,Shadow=0,MarginV=60'"
        )

        # Apply fade-in/fade-out and ensure correct encoding format
        vf_filter = (
            f"{fade_filter},"
            "format=yuva444p,"
            "fade=t=in:st=0:d=0.25:alpha=1,"
            "fade=t=out:st=0:d=0.25:alpha=1,"
            "format=yuv420p"
        )

        subprocess.run([
            "ffmpeg",
            "-i", video_path,
            "-vf", vf_filter,
            "-c:a", "copy",
            output_path,
            "-y"
        ], check=True)

    except subprocess.CalledProcessError:
        raise RuntimeError("❌ Failed to burn faded subtitles with FFmpeg.")

    print(f"[+] Created cinematic output: {output_path}")

# main pipeline
def main():
    """
    Command-line entrypoint.

    Usage:
        python3 auto_caption_online.py <YouTube URL>

    Flow:
        1. Downloads audio/video streams to temp dir.
        2. Generates captions via Whisper.
        3. Saves SRT subtitles.
        4. Burns styled captions into final MP4.
    """
    if len(sys.argv) < 2:
        print("Usage: python3 auto_caption_online.py <YouTube URL>")
        sys.exit(1)

    yt_url = sys.argv[1]

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")
        video_path = os.path.join(tmpdir, "video.mp4")

        print("[+] Fetching streams ...")
        subprocess.run([
            "yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "mp3",
            "-o", audio_path, yt_url
        ], check=True)
        subprocess.run([
            "yt-dlp", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "-o", video_path, yt_url
        ], check=True)

        print("[+] Streams ready, generating captions ...")
        segments = generate_captions(audio_path)
        srt_path = os.path.join(tmpdir, "captions.srt")
        save_srt(segments, srt_path)

        print("[+] Burning captions into final video ...")
        burn_subtitles(video_path, srt_path, "captioned.mp4")

        print("\n Done. Output saved as captioned.mp4")

if __name__ == "__main__":
    main()
