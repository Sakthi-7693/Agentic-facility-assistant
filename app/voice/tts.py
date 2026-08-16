"""Text-to-Speech with pyttsx3.

Uses the voice already installed in the OS (SAPI5 on Windows, espeak on Linux)
so nothing needs downloading. Swap this file for Piper or Coqui for a more
natural voice.

Synthesis failure is never fatal: it returns None and the caller shows the text.
Losing the audio is a small problem; losing the answer is a big one.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

from app.config import AUDIO_OUT_DIR, settings
from app.logging_setup import get_logger
from app.tracing import span

log = get_logger(__name__)

SPEECH_RATE = 175  # the default 200 sounds rushed


def clean_for_speech(text: str) -> str:
    """Strip markdown - "star star Chiller star star" ruins a demo."""
    cleaned = re.sub(r"[*_`#]+", "", text)
    cleaned = re.sub(r"^\s*[-•]\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _init_com() -> None:
    """Windows only: SAPI5 is a COM component and COM must be initialised on
    whichever thread uses it. Silently skipped elsewhere."""
    try:
        import comtypes  # type: ignore

        comtypes.CoInitialize()
    except Exception:  # noqa: BLE001 - not Windows, or already initialised
        pass


def synthesise_to_file(text: str, out_path: Path) -> Path | None:
    """Blocking. Call through speak() instead."""
    try:
        _init_com()

        import pyttsx3

        # A fresh engine per call: the SAPI5 driver dislikes being reused across
        # threads, and creating one is cheap.
        engine = pyttsx3.init()
        engine.setProperty("rate", SPEECH_RATE)
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()
        engine.stop()

        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path

        log.warning("TTS produced an empty file")
        return None

    except Exception as exc:  # noqa: BLE001 - audio is optional, never fatal
        log.warning("Text-to-speech failed (%s) - returning text only", exc)
        return None


async def speak(text: str) -> str | None:
    """Returns the generated file name, or None if disabled or synthesis failed."""
    if not settings.tts_enabled or not text.strip():
        return None

    with span("voice.tts", input={"chars": len(text)}):
        out_path = AUDIO_OUT_DIR / f"reply-{uuid.uuid4().hex[:10]}.wav"
        result = await asyncio.to_thread(synthesise_to_file, clean_for_speech(text), out_path)
        return result.name if result else None


def cleanup_old_audio(keep_last: int = 40) -> None:
    """Stop the audio folder growing without limit."""
    files = sorted(AUDIO_OUT_DIR.glob("reply-*.wav"), key=lambda p: p.stat().st_mtime)
    for path in files[:-keep_last]:
        path.unlink(missing_ok=True)
