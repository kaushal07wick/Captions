# 🎬 Captions 

**Auto-sync captions for YouTube Shorts — built to eliminate manual editing.**

This system uses **OpenAI Whisper + FFmpeg** to automatically generate, split, clean, and burn cinematic captions directly onto videos.  
Built to attack the exact bottleneck Varun Mayya described — *manual caption syncing* in short-form video production.

---

## ⚙️ Features
✅ Transcribes any YouTube Short directly (no manual upload)  
✅ 2–3 word micro-captions for natural rhythm  
✅ Automatic punctuation cleanup & overlap removal  
✅ Fade-in/fade-out transitions, no background boxes  
✅ Dynamic word highlights (e.g., “AI”, “build”, “video”)  


## 🚀 Usage
```bash
python3 auto_caption_online.py "https://www.youtube.com/shorts/vAv70iVDDTM"
````

Output:

```
✅ captioned.mp4 — clean, synced, ready-to-post short
```

---

## 🧩 Example (before vs after)

| Original                  | SmartSync Output                               |
| ------------------------- | ---------------------------------------------- |
| Manual captions, unsynced | Auto-timed, fade-in/out, white/yellow captions |

*(Attach sample frame or short Loom GIF here)*

---

## 🧱 Stack

* **Python 3.12**
* **Whisper (OpenAI)**
* **FFmpeg**
* **yt-dlp**
* **pysrt**

---

## 🧭 Vision (v2 Plan)

Integrate lightweight **vision models (CLIP / VideoLLaMA)** to understand motion & speaker focus → adapt caption placement and color dynamically.
