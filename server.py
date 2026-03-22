# main.py
import os
import asyncio
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from core import TMP_TTL, TMP_CLEAN_INTERVAL, cleanup_file
from routes import router as api_router

# --- Configuration & Initialization ---

app = FastAPI(title="Video Transcriber and Subtitle Burner")

# Allow browser to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static and temporary files
os.makedirs("tmp", exist_ok=True)
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
if os.path.isdir("tmp"):
    # This mount allows access to files in the 'tmp' directory via /tmp/file_id.ext
    app.mount("/tmp", StaticFiles(directory="tmp"), name="tmp")

# Include the API routes
app.include_router(api_router)


# --- Background Tasks & Lifespan Events ---

async def tmp_cleaner_loop():
    """Periodically cleans up old files in the 'tmp' directory."""
    while True:
        try:
            now = time.time()
            for entry in os.scandir("tmp"):
                if entry.is_file():
                    try:
                        mtime = entry.stat().st_mtime
                        if now - mtime > TMP_TTL:
                            cleanup_file(entry.path)
                    except Exception:
                        pass
        except Exception:
            # Handle potential errors during directory scan
            pass
        await asyncio.sleep(TMP_CLEAN_INTERVAL)


@app.on_event("startup")
async def start_background_tasks():
    """Starts the file cleaner loop on application startup."""
    asyncio.create_task(tmp_cleaner_loop())


# --- Root/Static UI Endpoints ---

@app.get("/")
def index():
    """Serve the static `index.html` UI when available."""
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Static UI not found. Place index.html in ./static/"}

# Static files are served from the `/static` mount configured at startup.
# Access assets using `/static/<filename>` (for example `/static/styles.css`).