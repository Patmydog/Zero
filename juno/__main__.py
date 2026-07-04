"""Entry point: `python -m juno` (text) or `python -m juno --voice`."""

from __future__ import annotations

import argparse

from .app import build_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="juno")
    parser.add_argument("--voice", action="store_true", help="push-to-talk voice mode")
    parser.add_argument("--config", default="config.toml", help="path to config file")
    args = parser.parse_args()

    app = build_app(args.config)
    try:
        if args.voice:
            from .voice.ptt import voice_loop

            voice_loop(app)
        else:
            from .cli import repl

            repl(app.agent, extras=app.slash_commands())
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
