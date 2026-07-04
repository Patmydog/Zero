"""Wire the layers together: one shared agent core, many ways in and out."""

from __future__ import annotations

from .agent import Agent
from .audit import AuditLog
from .builtin_tools import register_builtin_tools
from .config import Config
from .gate import background_gate
from .heartbeat import Heartbeat
from .memory import MemoryStore, register_memory_tools
from .notices import NoticeBoard
from .provider import make_provider
from .tools import ToolRegistry


class App:
    def __init__(self, config: Config):
        self.config = config
        data_dir = config.data_dir

        self.audit = AuditLog(
            data_dir,
            input_per_mtok=config.get("model.input_per_mtok", 0.0),
            output_per_mtok=config.get("model.output_per_mtok", 0.0),
        )
        self.notices = NoticeBoard(data_dir)
        self.memory = MemoryStore(data_dir)
        self.provider = make_provider(config)

        # The interactive agent: terminal confirmation gate.
        from .cli import confirm_on_terminal

        registry = ToolRegistry()
        self.tasks = register_builtin_tools(registry, data_dir)
        register_memory_tools(registry, self.memory)
        self.agent = Agent(
            self.provider,
            config,
            registry=registry,
            memory=self.memory,
            confirm=confirm_on_terminal,
            audit=self.audit,
        )

        # The heartbeat: same brain, fresh short conversation per check,
        # and a gate that defaults to "no + leave a note".
        def agent_factory(check_registry: ToolRegistry) -> Agent:
            register_builtin_tools(check_registry, data_dir)
            register_memory_tools(check_registry, self.memory)
            return Agent(
                self.provider,
                config,
                registry=check_registry,
                memory=self.memory,
                confirm=background_gate(self.notices, self.audit),
                audit=self.audit,
            )

        self.heartbeat = Heartbeat(config, agent_factory, self.notices, self.audit)

        # Urgent notices may interrupt; everything else waits in the inbox.
        self.notices.on_urgent = lambda n: print(
            f"\n🔔 {n['title']}: {n['body']}\n", flush=True
        )

    def start_background(self) -> None:
        self.heartbeat.start()

    def shutdown(self) -> None:
        self.heartbeat.stop()

    # ----------------------------------------------------- catch-up + slash

    def show_pending_notices(self) -> None:
        pending = self.notices.pending()
        if not pending:
            return
        print(f"\nWhile you were away — {len(pending)} notice(s):")
        for n in pending:
            mark = "❗" if n["urgent"] else "•"
            print(f"  {mark} [{n['id']}] {n['created']} {n['title']}: {n['body']}")
        print("Dismiss with /dismiss <id> or /dismiss all.\n")

    def slash_commands(self) -> dict:
        def notices_cmd(_):
            pending = self.notices.pending()
            if not pending:
                print("No pending notices.")
            for n in pending:
                print(f"  [{n['id']}] {n['created']} {n['title']}: {n['body']}")

        def dismiss_cmd(line: str):
            parts = line.split()
            if len(parts) < 2:
                print("Usage: /dismiss <id>|all")
            elif parts[1] == "all":
                print(f"Dismissed {self.notices.dismiss_all()} notice(s).")
            elif self.notices.dismiss(parts[1]):
                print("Dismissed.")
            else:
                print("No pending notice with that id.")

        def pause_cmd(_):
            self.heartbeat.pause()
            print("Proactive behavior paused (kill switch on). /resume to restart.")

        def resume_cmd(_):
            self.heartbeat.resume()
            print("Proactive behavior resumed.")

        def cost_cmd(_):
            print(self.audit.cost_summary())

        def memory_cmd(_):
            facts = self.memory.all_facts()
            if not facts:
                print("Nothing in long-term memory yet.")
            for f in facts:
                print(f"  [{f['id']}] {f['fact']}  (updated {f['updated']})")
            print(f"(edit by hand any time: {self.memory.path})")

        return {
            "/notices": notices_cmd,
            "/dismiss": dismiss_cmd,
            "/pause": pause_cmd,
            "/resume": resume_cmd,
            "/cost": cost_cmd,
            "/memory": memory_cmd,
        }


def build_app(config_path: str = "config.toml") -> App:
    app = App(Config.load(config_path))
    app.show_pending_notices()
    app.start_background()
    return app
