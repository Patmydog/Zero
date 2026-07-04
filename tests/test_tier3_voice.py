"""Tier 3: the voice plumbing that can be tested without a microphone —
sentence chunking for streamed speech, and the STT seam's error path."""

import pytest

from juno.voice.sentences import SentenceSplitter
from juno.voice import stt


def test_sentences_stream_out_as_they_complete():
    s = SentenceSplitter()
    out = []
    for chunk in ["The weather today is sunn", "y and warm. Tomorrow looks ", "rainy. Bring a coat"]:
        out.extend(s.feed(chunk))
    out.extend(s.flush())
    assert out == ["The weather today is sunny and warm.", "Tomorrow looks rainy.", "Bring a coat"]


def test_short_openers_ride_with_next_sentence():
    s = SentenceSplitter()
    out = s.feed("Hi! It's a lovely day outside today. ")
    assert out == ["Hi! It's a lovely day outside today."]


def test_flush_returns_trailing_fragment():
    s = SentenceSplitter()
    assert s.feed("no boundary here") == []
    assert s.flush() == ["no boundary here"]


def test_stt_requires_key(monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    with pytest.raises(stt.TranscriptionError):
        stt.transcribe(b"RIFF....")
