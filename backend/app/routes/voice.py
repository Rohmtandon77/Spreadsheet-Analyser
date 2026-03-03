"""Voice endpoints: Speech-to-Text and Text-to-Speech."""

import asyncio
import io
import tempfile
from pathlib import Path

import edge_tts
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/voice", tags=["voice"])

_whisper_model = None
_whisper_lock = asyncio.Lock()

WHISPER_MODEL_SIZE = "large-v3"
WHISPER_DEVICE = "cuda"
WHISPER_DEVICE_INDEX = 4
TTS_VOICE = "en-US-AriaNeural"


async def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        async with _whisper_lock:
            if _whisper_model is None:
                from faster_whisper import WhisperModel
                _whisper_model = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: WhisperModel(
                        WHISPER_MODEL_SIZE,
                        device=WHISPER_DEVICE,
                        device_index=WHISPER_DEVICE_INDEX,
                        compute_type="float16",
                    ),
                )
    return _whisper_model


@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """Convert audio to text using Whisper."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        model = await _get_whisper()
        segments, info = await asyncio.get_event_loop().run_in_executor(
            None, lambda: model.transcribe(tmp_path, beam_size=5)
        )
        text = " ".join(seg.text.strip() for seg in segments)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT failed: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"text": text, "language": getattr(info, "language", "en")}


@router.post("/tts")
async def text_to_speech(
    text: str = Query(..., description="Text to synthesize"),
    voice: str = Query(default=TTS_VOICE, description="Edge TTS voice name"),
):
    """Convert text to speech audio (MP3)."""
    try:
        communicate = edge_tts.Communicate(text, voice)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

    return StreamingResponse(buf, media_type="audio/mpeg", headers={
        "Content-Disposition": "inline; filename=speech.mp3"
    })
