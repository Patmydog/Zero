"""The text REPL — Juno's first and forever-primary interface.

Voice (Tier 3) wraps the same Agent; this loop stays alive as the
debugging surface and graceful fallback.
"""

from __future__ import annotations

import sys

from .agent import Agent
from .provider import ProviderError


def confirm_on_terminal(action: str) -> bool:
    """The interactive confirmation gate: state the action, wait for a yes."""
    print(f"\n⚠️  Juno wants to: {action}")
    answer = input("Allow this? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def repl(agent: Agent, extras=None) -> None:
    """extras: optional dict of slash-command handlers added by later tiers."""
    name = agent.config.get("assistant.name", "Juno")
    print(f"{name} is listening. Type your message, or /quit to exit.")
    extras = extras or {}

    while True:
        try:
            user_text = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return
        if not user_text:
            continue
        if user_text in ("/quit", "/exit"):
            print("bye.")
            return
        if user_text.startswith("/"):
            cmd = user_text.split()[0]
            if cmd in extras:
                extras[cmd](user_text)
            else:
                known = ", ".join(sorted(["/quit", *extras]))
                print(f"Unknown command. Available: {known}")
            continue

        print(f"{name.lower()}> ", end="", flush=True)
        try:
            agent.run_turn(user_text, on_text=lambda s: print(s, end="", flush=True))
            print()
        except ProviderError as e:
            print(f"\n[{e}]")
        except Exception as e:  # never die mid-conversation
            print(f"\n[Something went wrong on my side: {e}]", file=sys.stderr)
