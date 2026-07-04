"""The mouth seam: give me text, play it aloud — and let me be cut off.

ElevenLabs streaming TTS, requested as raw PCM so playback can start
before synthesis finishes. The voice id is config, not code; the key
lives in ELEVENLABS_API_KEY.
"""

from __future__ import annotations

import os
import queue
import threading

import requests

SAMPLE_RATE = 22050  # matches output_format=pcm_22050


class SpeechError(Exception):
    pass


class Speaker:
    """A queue-fed speaker. speak() enqueues sentences; a worker thread
    streams synthesis + playback; interrupt() stops everything now."""

    def __init__(self, voice_id: str, model: str = "eleven_turbo_v2_5"):
        self.voice_id = voice_id
        self.model = model
        self._q: queue.Queue[str | None] = queue.Queue()
        self._interrupted = threading.Event()
        self._speaking = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True, name="speaker")
        self._worker.start()

    # ------------------------------------------------------------------ API

    def speak(self, text: str) -> None:
        if text.strip():
            self._q.put(text)

    def interrupt(self) -> None:
        """Stop talking immediately and drop anything queued."""
        self._interrupted.set()
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def wait_until_done(self) -> None:
        self._q.join()

    @property
    def speaking(self) -> bool:
        return self._speaking.is_set() or not self._q.empty()

    # --------------------------------------------------------------- worker

    def _run(self) -> None:
        while True:
            text = self._q.get()
            if text is None:
                self._q.task_done()
                return
            self._interrupted.clear()
            self._speaking.set()
            try:
                self._synthesize_and_play(text)
            except Exception as e:
                print(f"[voice: playback problem: {e}]")
            finally:
                self._speaking.clear()
                self._q.task_done()

    def _synthesize_and_play(self, text: str) -> None:
        key = os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            raise SpeechError("ELEVENLABS_API_KEY is not set.")
        import numpy as np
        import sounddevice as sd

        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
            f"?output_format=pcm_22050"
        )
        with requests.post(
            url,
            headers={"xi-api-key": key},
            json={"text": text, "model_id": self.model},
            stream=True,
            timeout=30,
        ) as resp:
            resp.raise_for_status()
            with sd.RawOutputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16"
            ) as out:
                leftover = b""
                for chunk in resp.iter_content(chunk_size=4096):
                    if self._interrupted.is_set():
                        return
                    data = leftover + chunk
                    usable = len(data) - (len(data) % 2)  # int16 alignment
                    out.write(np.frombuffer(data[:usable], dtype=np.int16))
                    leftover = data[usable:]
