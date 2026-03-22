# core.py
import os
import shutil
import subprocess
import json
import wave
import contextlib
import re
import uuid
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from openai import OpenAI
import imageio_ffmpeg as iio_ffmpeg
from dotenv import load_dotenv

load_dotenv()  # loads OPENAI_API_KEY (and others) from .env if present

# --- Configuration ---
if not os.environ.get("OPENAI_API_KEY"):
    raise RuntimeError(
        "OPENAI_API_KEY is not set. "
        "Create a .env file with OPENAI_API_KEY=sk-... or set the environment variable."
    )
client = OpenAI()

# Cleanup settings (seconds)
TMP_TTL = int(os.environ.get("TMP_TTL_SECONDS", 60 * 60)) # default 1 hour
TMP_CLEAN_INTERVAL = int(os.environ.get("TMP_CLEAN_INTERVAL", 60 * 10)) # default 10 minutes

# --- Utility Functions (File and System) ---

def get_ffmpeg_exe() -> str:
    """Finds and returns the path to the ffmpeg executable."""
    try:
        ffmpeg_exe = iio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_exe:
            return ffmpeg_exe
    except Exception:
        pass
    
    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg executable not found. Install ffmpeg or ensure it's on PATH."
        )
    return ffmpeg_exe

def extract_audio(video_path: str, audio_path: str) -> str:
    """Uses ffmpeg to extract and convert audio to a 16kHz WAV file."""
    ffmpeg_exe = get_ffmpeg_exe()
    
    cmd = [
        ffmpeg_exe, '-y', '-i', video_path, '-vn', '-ac', '1', '-ar', '16000',
        '-acodec', 'pcm_s16le', audio_path,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode('utf-8') if isinstance(e.stderr, (bytes, bytearray)) else str(e)
        raise HTTPException(status_code=500, detail=f"ffmpeg failed: {stderr}")

    return audio_path

def burn_subtitles_to_video(file_id: str, video_path: str, ass_path: str) -> str:
    """Uses ffmpeg to burn ASS subtitles onto a video."""
    ffmpeg_exe = get_ffmpeg_exe()
    burned_path = safe_tmp_path(f"{file_id}_burned.mp4")

    # Copy ASS to CWD as ffmpeg's ass filter can be sensitive to complex paths
    local_name = f"burn_{file_id}.ass"
    local_sub = os.path.join(os.getcwd(), local_name)
    shutil.copyfile(ass_path, local_sub)
    vf = f"ass='{local_name}'"
    
    cmd = [
        ffmpeg_exe, '-y', '-i', video_path, '-vf', vf,
        '-c:v', 'libx264', '-crf', '23', # Recommended default quality setting
        '-c:a', 'copy', burned_path,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode('utf-8') if isinstance(e.stderr, (bytes, bytearray)) else str(e)
        cmd_str = ' '.join(cmd)
        raise HTTPException(status_code=500, detail=f"ffmpeg burn failed: {stderr}\nCMD: {cmd_str}")
    finally:
        cleanup_file(local_sub)

    return burned_path

def get_wav_duration(audio_path: str) -> float:
    """Calculates the duration of a WAV file in seconds."""
    try:
        with contextlib.closing(wave.open(audio_path, 'r')) as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate) if rate else 0.0
    except Exception:
        return 0.0

def safe_tmp_path(name: str) -> str:
    """Returns a secure, absolute path within the 'tmp' directory."""
    base = os.path.abspath('tmp')
    target = os.path.abspath(os.path.join(base, name))
    if not target.startswith(base):
        raise HTTPException(status_code=400, detail='Invalid filename or path traversal attempt')
    return target

def cleanup_file(path: str):
    """Safely removes a file."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

# --- Utility Functions (Text Processing and Subtitling) ---

def split_into_word_chunks(text: str, max_words: int = 3) -> List[str]:
    """Splits text into chunks of maximum `max_words`."""
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return [""]
    chunks = []
    for i in range(0, len(words), max_words):
        chunks.append(" ".join(words[i:i+max_words]))
    return chunks

def split_sentences(text: str) -> List[str]:
    """Splits a block of text into sentence-like parts."""
    parts = [p.strip() for p in re.split(r'(?<=[\.\!\?\,])\s+', text) if p.strip()]
    if not parts:
        parts = [t.strip() for t in re.split(r',', text) if t.strip()]
    if not parts:
        parts = [text]
    return parts

def generate_proportional_segments(full_text: str, duration: float) -> List[Dict[str, Any]]:
    """Generates time-proportional segments when API doesn't provide timestamps."""
    parts = split_sentences(full_text)
    n = len(parts)
    segments = []
    if duration and n:
        bucket = duration / n
        for i, p in enumerate(parts):
            part_start = round(max(0.0, bucket * i), 2)
            part_end = round(min(duration, bucket * (i + 1)), 2) if i < n - 1 else round(duration, 2)
            part_dur = max(0.0, part_end - part_start)
            
            chunks = split_into_word_chunks(p, 4)
            m = len(chunks)
            
            for j, chunk in enumerate(chunks):
                c_start = part_start + (part_dur * j / m)
                c_end = part_start + (part_dur * (j + 1) / m) if j < m - 1 else part_end
                segments.append({"start": round(c_start, 2), "end": round(c_end, 2), "text": chunk})
    else:
        for p in parts:
            chunks = split_into_word_chunks(p, 4)
            for chunk in chunks:
                segments.append({"start": None, "end": None, "text": chunk})
                
    return segments

def format_srt_timestamp(seconds: float) -> str:
    """Formats seconds into SRT timestamp (HH:MM:SS,mmm)."""
    if seconds is None: seconds = 0.0
    s = int(seconds)
    ms = int((seconds - s) * 1000)
    hours = s // 3600
    minutes = (s % 3600) // 60
    secs = s % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

def write_srt(segments: List[Dict[str, Any]], srt_path: str):
    """Writes segments to an SRT file."""
    try:
        with open(srt_path, 'w', encoding='utf-8') as sf:
            for i, seg in enumerate(segments, start=1):
                start = seg.get('start', 0.0)
                end = seg.get('end', start + 3.0)
                txt = seg.get('text', '') or ''
                
                sf.write(f"{i}\n")
                sf.write(f"{format_srt_timestamp(float(start))} --> {format_srt_timestamp(float(end))}\n")
                sf.write(f"{txt.lstrip('}')}\n\n")
    except Exception:
        pass
        
def format_ass_timestamp(seconds: float) -> str:
    """Formats seconds into ASS timestamp (H:MM:SS.cc)."""
    if seconds is None: seconds = 0.0
    total_cs = int(round(seconds * 100))
    cs = total_cs % 100
    s = (total_cs // 100) % 60
    m = (total_cs // 6000) % 60
    h = total_cs // 360000
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def hex_to_ass_color(hex_color: str, alpha: int = 0) -> str:
    """Converts CSS hex (#RRGGBB) to ASS color format (&HAABBGGRR)."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 3:
        hex_color = ''.join(c * 2 for c in hex_color)
    if len(hex_color) != 6:
        return '&H00FFFFFF'
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f'&H{alpha:02X}{b:02X}{g:02X}{r:02X}'

def build_ass_header(customization: Dict[str, Any]) -> str:
    """Builds a complete ASS header from a customization dict."""
    font = customization.get('font', 'Arial')
    # Scale CSS px to ASS points (approx 2.5x for 1920x1080)
    font_size = max(14, int(float(customization.get('fontSize', 24)) * 2.5))
    primary_color = hex_to_ass_color(customization.get('color', '#ffffff'))
    position = customization.get('position', 'bottom')
    alignment = {'top': 8, 'middle': 5, 'bottom': 2}.get(position, 2)
    margin_v = 50 if position in ('top', 'bottom') else 0

    style_line = (
        f"Style: Default,{font},{font_size},"
        f"{primary_color},&H000000FF,&H00000000,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,3,2,{alignment},10,10,{margin_v},1"
    )
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        + style_line + "\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

def load_style_header(style_name: str = "classic") -> str:
    """Loads an ASS header from the styles/ directory. Falls back to default if not found."""
    style_file = os.path.join("styles", f"{style_name}.txt")
    if os.path.exists(style_file):
        try:
            with open(style_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            pass
    # Fallback: return default header if file not found
    return """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H0000A5FF,&H00000000,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,6,4,5,10,10,10,2

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def write_ass(segments: List[Dict[str, Any]], ass_path: str, style: str = "classic", customization: Optional[Dict[str, Any]] = None):
    """Writes segments to an ASS file. Uses customization dict if provided, otherwise loads style from file."""
    if customization:
        header = build_ass_header(customization)
        # Map cadence to ASS fade tag
        cadence_tags: Dict[str, str] = {
            'fade-in':    r'\fad(400,0)',
            'pop':        r'\fad(200,200)',
            'slide-up':   r'\fad(300,0)',
            'slide-down': r'\fad(300,0)',
            'typewriter': r'\fad(150,0)',
        }
        fad_tag = cadence_tags.get(customization.get('cadence', 'instant'), '')
    else:
        header = load_style_header(style)
        fad_tag = r'\fad(200,200)'

    try:
        with open(ass_path, 'w', encoding='utf-8') as af:
            af.write(header)
            for seg in segments:
                start = seg.get('start', 0.0)
                end = seg.get('end', start + 3.0)
                text = seg.get('text', '')
                st = format_ass_timestamp(start)
                et = format_ass_timestamp(end)
                raw = text or ''
                safe_text = raw.replace('\n', '\\N')  # ASS line break
                if customization:
                    override = ('{' + fad_tag + '}') if fad_tag else ''
                else:
                    override = r'{\fad(200,200)\fs72\bord6\shad4}'
                af.write(f"Dialogue: 0,{st},{et},Default,,0,0,0,,{override}{safe_text}\n")
    except Exception:
        pass

def write_subtitle_files(file_id: str, full_text: str, segments: List[Dict[str, Any]], duration: Optional[float] = None):
    """Consolidated function to save JSON, SRT, and ASS files."""
    data = {"transcript": full_text.strip(), "segments": segments}
    if duration is not None:
        data["duration"] = duration

    # Save JSON
    json_path = f"tmp/{file_id}.json"
    try:
        with open(json_path, 'w', encoding='utf-8') as jf:
            json.dump(data, jf, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # Save ASS (preferred for burning)
    ass_path = f"tmp/{file_id}.ass"
    write_ass(segments, ass_path)

    # Save SRT (optional, for compatibility)
    srt_path = f"tmp/{file_id}.srt"
    write_srt(segments, srt_path)


# --- Core Logic Function ---

def transcribe_and_segment(audio_path: str, video_path: str) -> Dict[str, Any]:
    """
    Performs the transcription via OpenAI API and generates time-stamped segments.
    Uses proportional timing as a fallback if the API doesn't return segment timestamps.
    """
    # 1. Whisper API call
    try:
        with open(audio_path, "rb") as a:
            result = client.audio.transcriptions.create(
                # Change the model to a standard Whisper model like 'whisper-1'
                # or a newer one that supports detailed timestamps.
                model="whisper-1", 
                file=a,
                # CRITICAL: Use verbose_json to get the segments array with timestamps.
                response_format="verbose_json" 
            )
            print(result)
    except Exception as e:
        print("OpenAI API transcription ERROR:", e)
        raise HTTPException(status_code=500, detail=f"OpenAI API transcription failed: {str(e)}")
    
    # 2. Process result and generate segments
    segments: List[Dict[str, Any]] = []
    full_text: str = ""
    duration: Optional[float] = None
    
    # --- New Logic to extract segments from API response ---
    if isinstance(result, dict) and 'segments' in result:
        print("here")
        full_text = result.get('text', '') or result.get('transcript', '')
        segments = result['segments']
    else:
        # Fallback to current proportional timing if API result is unexpected
        text_value = (getattr(result, "text", None) or getattr(result, "transcript", None) 
                      or (isinstance(result, dict) and (result.get("text") or result.get("transcript"))))
        full_text = text_value or str(result)
        duration = get_wav_duration(audio_path)
        segments = generate_proportional_segments(full_text, duration)
        
    return {
        "transcript": full_text.strip(), 
        "segments": segments, 
        "duration": duration
    }