# routes.py
import uuid
import os
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException
from core import (
    safe_tmp_path, extract_audio, cleanup_file, transcribe_and_segment,
    write_subtitle_files, write_srt, write_ass, burn_subtitles_to_video
)

router = APIRouter()

@router.post("/transcribe")
async def transcribe_video(file: UploadFile = File(...)):
    """Handles video upload, audio extraction, transcription, and initial subtitle generation."""
    file_id = uuid.uuid4().hex
    video_path = f"tmp/{file_id}.mp4"
    audio_path = f"tmp/{file_id}.wav"
    
    # 1. Save video and extract audio
    try:
        with open(video_path, "wb") as f:
            f.write(await file.read())
        
        # Audio extraction
        extract_audio(video_path, audio_path)
    except HTTPException as e:
        cleanup_file(video_path)
        cleanup_file(audio_path)
        raise e
    except Exception as e:
        cleanup_file(video_path)
        cleanup_file(audio_path)
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")
    
    # 2. Transcribe and segment
    try:
        transcription_data = transcribe_and_segment(audio_path, video_path)
        full_text = transcription_data["transcript"]
        segments = transcription_data["segments"]
        duration = transcription_data["duration"]
    except HTTPException as e:
        cleanup_file(video_path)
        cleanup_file(audio_path)
        raise e
    
    # 3. Save subtitles and cleanup intermediate audio
    write_subtitle_files(file_id, full_text, segments, duration)
    cleanup_file(audio_path)

    # 4. Return result
    return {
        "transcript": full_text,
        "segments": segments,
        "file_id": file_id,
        "json": f"tmp/{file_id}.json",
        "ass": f"tmp/{file_id}.ass",
        "video": f"tmp/{file_id}.mp4"
    }


@router.post("/burn")
def burn_subtitles(payload: Dict[str, Any]):
    """Burns the provided segments (subtitles) onto the original video file."""
    file_id = payload.get("file_id")
    segments = payload.get("segments")
    customization = payload.get("customization")  # Full customization object from frontend

    if not file_id or not segments:
        raise HTTPException(status_code=400, detail="Missing file_id or segments payload")

    video_path = safe_tmp_path(f"{file_id}.mp4")
    ass_path = safe_tmp_path(f"{file_id}.ass")

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Original video not found")

    # Build and write ASS with customization applied (or fallback to classic style)
    write_ass(segments, ass_path, customization=customization)

    if not os.path.exists(ass_path):
        raise HTTPException(status_code=400, detail="ASS subtitle file not found; required for burning")

    # Run ffmpeg to burn subtitles onto video
    try:
        burned_path = burn_subtitles_to_video(file_id, video_path, ass_path)
    except HTTPException:
        raise

    return {"file_id": file_id, "burned": f"/tmp/{file_id}_burned.mp4"}