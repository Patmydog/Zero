"""The confirmation gate.

The gate is a callable `confirm(action_description) -> bool` that sits
between the model choosing a consequential tool and the tool running —
the agent core enforces it identically for typed, spoken, and heartbeat-
initiated actions. Approval is per-action and never generalizes.
"""

from __future__ import annotations


def background_gate(notices, audit=None):
    """The gate for heartbeat-initiated actions: never block forever
    waiting on a human. The safe default is "no, and leave a note"."""

    def confirm(action: str) -> bool:
        notices.post(
            "Action skipped — needed your OK",
            f"A background task wanted to: {action}. It was NOT performed "
            "because you weren't there to confirm. Ask me again if you "
            "want it done.",
            urgent=False,
        )
        if audit:
            audit.write("confirmation", source="background", action=action, approved=False)
        return False

    return confirm
