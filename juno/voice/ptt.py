"""Push-to-talk: hold the key, speak, release.

This wraps the existing brain — the transcribed text goes into the exact
same Agent.run_turn a typed message uses. The only new parts are the two
ends of the turn: capture+transcribe on the way in, speech on the way out.

Push-to-talk means we never guess when you started or finished, and we
never capture while Juno is talking (no listening to itself). Pressing
the key while Juno is mid-reply interrupts it and listens.
"""

from __future__ import annotations

import io
import queue
import wave

from ..provider import ProviderError
from . import stt
from .sentences import SentenceSplitter
from .tts import Speaker

SAMPLE_RATE = 16000


def _resolve_key(name: str):
    from pynput import keyboard

    special = getattr(keyboard.Key, name, None)
    if special is not None:
        return special
    return keyboard.KeyCode.from_char(name)


def _to_wav(frames: list[bytes]) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"".join(frames))
    return buf.getvalue()


class Recorder:
    """Captures microphone audio only while the push-to-talk key is held."""

    def __init__(self):
        import sounddevice as sd

        self._sd = sd
        self._frames: list[bytes] = []
        self._stream = None

    def start(self) -> None:
        self._frames = []
        self._stream = self._sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            callback=lambda indata, *_: self._frames.append(bytes(indata)),
        )
        self._stream.start()

    def stop(self) -> bytes:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return _to_wav(self._frames)


def voice_loop(app) -> None:
    from pynput import keyboard

    config = app.agent.config
    name = config.get("assistant.name", "Juno")
    key = _resolve_key(config.get("voice.ptt_key", "ctrl_r"))
    speaker = Speaker(
        voice_id=config.get("voice.elevenlabs_voice_id"),
        model=config.get("voice.elevenlabs_model", "eleven_turbo_v2_5"),
    )
    recorder = Recorder()
    utterances: queue.Queue[bytes] = queue.Queue()
    holding = {"down": False}

    def on_press(k):
        if k == key and not holding["down"]:
            holding["down"] = True
            speaker.interrupt()  # let me cut it off
            recorder.start()
            print("\n[listening…]", flush=True)

    def on_release(k):
        if k == key and holding["down"]:
            holding["down"] = False
            utterances.put(recorder.stop())

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    print(
        f"{name} voice mode. Hold [{config.get('voice.ptt_key')}] to talk, "
        "release to send. Ctrl+C to quit. The text REPL still works via "
        "`python -m juno`."
    )

    try:
        while True:
            wav = utterances.get()
            print("[thinking…]", flush=True)
            try:
                heard = stt.transcribe(wav, model=config.get("voice.deepgram_model", "nova-2"))
            except stt.TranscriptionError as e:
                print(f"[{e}]")
                continue
            if not heard:
                print("[I didn't catch any speech in that.]")
                continue
            # Show what the ears thought you said, so you can tell whether a
            # wrong answer came from the ears or the brain.
            print(f'you (heard)> "{heard}"')

            splitter = SentenceSplitter()

            def on_text(chunk: str) -> None:
                print(chunk, end="", flush=True)
                for sentence in splitter.feed(chunk):
                    speaker.speak(sentence)

            print(f"{name.lower()}> ", end="", flush=True)
            try:
                app.agent.run_turn(heard, on_text=on_text)
                for sentence in splitter.flush():
                    speaker.speak(sentence)
                print()
            except ProviderError as e:
                print(f"\n[{e}]")
                speaker.speak("Sorry, I hit a problem reaching my brain. Try again?")
    except KeyboardInterrupt:
        print("\nbye.")
    finally:
        listener.stop()
        speaker.interrupt()
