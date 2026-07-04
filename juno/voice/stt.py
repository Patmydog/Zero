"""The ears seam: give me audio, get back text.

Deepgram's prerecorded REST endpoint — one small function so the
transcriber can be swapped without touching anything else. The key lives
in DEEPGRAM_API_KEY, never in code.
"""

from __future__ import annotations

import os

import requests


class TranscriptionError(Exception):
    pass


def transcribe(wav_bytes: bytes, model: str = "nova-2") -> str:
    key = os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        raise TranscriptionError("DEEPGRAM_API_KEY is not set.")
    try:
        resp = requests.post(
            "https://api.deepgram.com/v1/listen",
            params={"model": model, "smart_format": "true"},
            headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"},
            data=wav_bytes,
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TranscriptionError(f"Transcription failed: {e}") from e
    try:
        return resp.json()["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    except (KeyError, IndexError) as e:
        raise TranscriptionError("Deepgram returned an unexpected response shape.") from e
