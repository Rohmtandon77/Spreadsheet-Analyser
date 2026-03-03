"""Voice endpoints: Speech-to-Text and Text-to-Speech.

STT: faster-whisper (local, GPU 4)
TTS: Piper (local, no external APIs)
"""

import asyncio
import io
import tempfile
import wave
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/voice", tags=["voice"])

_whisper_model = None
_whisper_lock = asyncio.Lock()
_piper_voice = None
_piper_lock = asyncio.Lock()

WHISPER_MODEL_SIZE = "large-v3"
WHISPER_DEVICE = "cuda"
WHISPER_DEVICE_INDEX = 4
PIPER_VOICE_ID = "en_US-ryan-high"


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


async def _get_piper():
    global _piper_voice
    if _piper_voice is None:
        async with _piper_lock:
            if _piper_voice is None:
                from huggingface_hub import hf_hub_download

                def _load():
                    onnx = hf_hub_download(
                        repo_id="rhasspy/piper-voices",
                        filename=f"en/en_US/ryan/high/{PIPER_VOICE_ID}.onnx",
                    )
                    from piper import PiperVoice

                    return PiperVoice.load(Path(onnx), use_cuda=False)

                _piper_voice = await asyncio.get_event_loop().run_in_executor(None, _load)
    return _piper_voice


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
):
    """Convert text to speech audio (WAV). Local Piper TTS, no external APIs."""
    try:
        voice = await _get_piper()

        def _synth():
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                path = tmp.name
            try:
                with wave.open(path, "wb") as wav:
                    voice.synthesize_wav(text, wav)
                with open(path, "rb") as f:
                    return f.read()
            finally:
                Path(path).unlink(missing_ok=True)

        wav_data = await asyncio.get_event_loop().run_in_executor(None, _synth)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

    return StreamingResponse(
        io.BytesIO(wav_data),
        media_type="audio/wav",
        headers={"Content-Disposition": "inline; filename=speech.wav"},
    )
