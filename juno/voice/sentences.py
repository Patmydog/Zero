"""Chunk a streaming reply into speakable sentences.

The brain streams text (Tier 1) and ElevenLabs streams audio, so we can
start speaking the first sentence while the rest is still being written —
this is most of what makes voice feel responsive.
"""

from __future__ import annotations

import re

_BOUNDARY = re.compile(r"([.!?…]+[\s\"')\]]*\s|\n+)")
MIN_CHARS = 12  # don't ship comically tiny fragments to TTS


class SentenceSplitter:
    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> list[str]:
        """Add streamed text; return any complete sentences ready to speak."""
        self._buf += chunk
        out: list[str] = []
        while True:
            # First boundary far enough in to be worth speaking on its own;
            # short openers ("Hi!") ride along with the next sentence.
            cut = next(
                (m.end() for m in _BOUNDARY.finditer(self._buf) if m.end() >= MIN_CHARS),
                None,
            )
            if cut is None:
                break
            sentence = self._buf[:cut].strip()
            self._buf = self._buf[cut:]
            if sentence:
                out.append(sentence)
        return out

    def flush(self) -> list[str]:
        rest = self._buf.strip()
        self._buf = ""
        return [rest] if rest else []
