# Juno

A voice-first personal AI assistant, built tier by tier. The what and why
live in [AGENT.md](AGENT.md) — that file is the spec; this one is how to
run it.

## Quick start (text mode — the foundation)

```sh
pip install -r requirements.txt
cp .env.example .env        # fill in ANTHROPIC_API_KEY
set -a; source .env; set +a
python -m juno
```

Talk to it. Slash commands: `/notices`, `/dismiss <id>|all`, `/pause`
(kill switch for all proactive behavior), `/resume`, `/cost`, `/memory`,
`/quit`.

## Voice mode (push-to-talk)

```sh
pip install -r requirements-voice.txt   # sounddevice, numpy, pynput
# also set DEEPGRAM_API_KEY and ELEVENLABS_API_KEY in .env
python -m juno --voice
```

Hold the push-to-talk key (default: right Ctrl, set in `config.toml`),
speak, release. Juno prints the transcript of what it *heard* next to its
reply so you can tell whether a wrong answer came from the ears or the
brain. Press the key again mid-reply to cut it off and speak.

macOS note: the terminal needs Microphone + Accessibility (for the key
listener) permissions. Linux note: `sounddevice` needs PortAudio
(`apt install libportaudio2`).

## Layout

| Piece | File |
|---|---|
| Brain (one shared agent loop) | `juno/agent.py` |
| Model seam (swap providers here) | `juno/provider.py` |
| Tool registry + built-in tools | `juno/tools.py`, `juno/builtin_tools.py` |
| Long-term memory (plain JSON, hand-editable) | `juno/memory.py` → `data/memory.json` |
| Heartbeat + notice inbox | `juno/heartbeat.py`, `juno/notices.py` |
| Confirmation gate + audit trail | `juno/gate.py`, `juno/audit.py` → `data/audit.jsonl` |
| Voice adapters (ears/mouth/PTT) | `juno/voice/` |
| All tunables | `config.toml` |

Everything Juno learns or does lands under `data/` (git-ignored,
human-readable JSON). Open it, fix it, delete it — it's yours.

## Tests

```sh
python -m pytest tests/
```

The suite drives every tier against a scripted fake model provider, so it
runs offline with no keys. Each `tests/test_tierN_*.py` file encodes that
tier's verification checklist from the build plan.

## Verifying with real ears and voice

The automated suite can't hold a key and speak. Once keys are in `.env`:

1. **Tier 1–2:** `python -m juno`, ask "what's on my list for today?" and
   watch it call `list_tasks`. Ask something that needs the web.
2. **Tier 3:** `python -m juno --voice`, hold the key, ask the same
   question, release — spoken answer, transcript printed. Interrupt it
   mid-sentence by pressing the key again.
3. **Tier 4:** tell it your name, quit, restart — it should know you.
   Then edit `data/memory.json` by hand and confirm it respects the edit.
4. **Tier 5:** add a reminder due one minute from now, wait for the
   `due_reminders` check (runs every 5 min by default; tighten
   `every_minutes` in `config.toml` to test faster). Close Juno, let it
   fire, reopen — the notice is waiting for you.
5. **Tier 6:** ask it to send a message — it must state exactly what it
   will send and wait for your `y`. `/pause` stops all proactive
   behavior while conversation keeps working.
