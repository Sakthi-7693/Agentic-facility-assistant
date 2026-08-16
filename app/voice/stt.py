"""Speech-to-Text with faster-whisper.

Runs offline on the CPU, no PyTorch. The model is loaded lazily, so an app that
only ever receives typed text never loads it at all.
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.logging_setup import get_logger
from app.tracing import span, update_span

log = get_logger(__name__)

_model = None


@dataclass
class Transcript:
    text: str
    language: str = ""
    duration_seconds: float = 0.0


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        log.info("Loading faster-whisper '%s' (first run downloads it)", settings.whisper_model)
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    return _model


def transcribe_file(path: str | Path) -> Transcript:
    """Blocking. Call through transcribe_bytes instead."""
    segments, info = _load_model().transcribe(
        str(path),
        beam_size=5,
        vad_filter=True,  # drop silence: faster and cleaner
        language=None,    # auto-detect
        condition_on_previous_text=False,
    )
    return Transcript(
        text=" ".join(s.text.strip() for s in segments).strip(),
        language=getattr(info, "language", ""),
        duration_seconds=round(getattr(info, "duration", 0.0), 2),
    )


async def transcribe_bytes(audio: bytes, suffix: str = ".webm") -> Transcript:
    """Transcribe uploaded audio. Whisper reads from a path, so we write a temp
    file, and run it in a thread so the server keeps serving."""
    with span("voice.stt", input={"bytes": len(audio)}):
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio)
            temp_path = Path(handle.name)

        try:
            result = await asyncio.to_thread(transcribe_file, temp_path)
            update_span(output={"text": result.text, "language": result.language})
            log.info("Transcribed %.1fs: %s", result.duration_seconds, result.text)
            return result
        finally:
            temp_path.unlink(missing_ok=True)
