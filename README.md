# 🎬 Video Transcription & Subtitle Editor

A local web app that uploads a video, transcribes it with OpenAI Whisper, lets you customise the subtitle style, and burns them directly onto the video — all in the browser.

---

## Features

- **Upload & Transcribe** — drag-and-drop or file-select a video; Whisper returns a full transcript with timestamps
- **Segment viewer** — browse every timestamped subtitle segment
- **Subtitle Customisation Panel**
  - Font family & size
  - Text colour (colour picker → CSS hex)
  - Position: Top / Middle / Bottom
  - Animation style: Instant, Fade In, Pop, Slide Up, Slide Down, Typewriter
  - Display duration & animation speed
  - Decorative icon augmentation (checkbox)
  - Live preview that reflects every change instantly
- **Burn subtitles** — sends the customisation object to the backend which generates a styled ASS subtitle file and burns it onto the video with FFmpeg
- **Re-burn** — change any property and burn again; the player refreshes automatically
- **Download** — download the generated `.ass` subtitle file directly

---

## Requirements

- Python 3.9+
- `ffmpeg` on your `PATH` → <https://ffmpeg.org/download.html>
- An OpenAI API key with access to `whisper-1`

---

## Quick Start

```powershell
# 1. Clone / open the folder
cd VideoSubtitles

# 2. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your OpenAI API key (or edit core.py directly for dev)
$env:OPENAI_API_KEY = "sk-..."

# 5. Start the server
uvicorn server:app --reload
```

Open **http://localhost:8000** in your browser.

---

## API Endpoints

| Method | Path          | Description                                                                   |
| ------ | ------------- | ----------------------------------------------------------------------------- |
| `POST` | `/transcribe` | Upload a video file; returns `transcript`, `segments`, and `file_id`          |
| `POST` | `/burn`       | Accept `{ file_id, segments, customization }` JSON; returns burned video path |

### Customisation object schema

```json
{
  "font": "Arial",
  "fontSize": 24,
  "position": "bottom",
  "cadence": "fade-in",
  "duration": 2,
  "animationSpeed": 1,
  "color": "#ffffff",
  "augmentation": false
}
```

---

## Project Structure

```
VideoSubtitles/
├── server.py          # FastAPI app, CORS, static files, background cleanup
├── routes.py          # /transcribe and /burn endpoints
├── core.py            # Audio extraction, Whisper, ASS generation, FFmpeg burn
├── requirements.txt
├── styles/            # Fallback ASS style templates (classic, neon, shadow)
├── static/
│   ├── index.html
│   ├── script.js
│   └── styles.css
└── tmp/               # Temporary files (auto-cleaned after 1 hour)
```

---

## Notes

- Temporary files in `tmp/` are auto-deleted after 1 hour (configurable via `TMP_TTL_SECONDS` env var)
- The ASS header is built dynamically from the customisation object — font, size, colour, and alignment are all applied before burning
- FFmpeg uses `-y` to overwrite on re-burn, so changing settings and burning again always produces a fresh output
