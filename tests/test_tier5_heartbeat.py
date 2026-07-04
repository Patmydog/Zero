"""Tier 5: the heartbeat is quiet by default, holds notices for later,
survives restarts without refiring, skips overlapping runs, respects
quiet hours, and stops on the kill switch."""

from datetime import datetime, timedelta

from conftest import FakeProvider, text_reply, tool_reply

from juno.agent import Agent
from juno.heartbeat import Heartbeat, in_quiet_hours, parse_hhmm
from juno.notices import NoticeBoard


def make_heartbeat(config, notices, script_per_check):
    """script_per_check: list of TurnResults handed to each check's agent."""

    def agent_factory(registry):
        return Agent(FakeProvider(list(script_per_check)), config, registry=registry)

    return Heartbeat(config, agent_factory, notices)


NOON = datetime(2026, 7, 4, 12, 0)


def prime(hb, when=NOON):
    """First tick only schedules; nothing fires on boot."""
    assert hb.tick(now=when) == []


def test_check_fires_when_due_and_posts_notice(config):
    notices = NoticeBoard(config.data_dir)
    hb = make_heartbeat(
        config,
        notices,
        [tool_reply("surface_notice", {"title": "Heads up", "body": "milk is due"}), text_reply("OK")],
    )
    prime(hb)
    ran = hb.tick(now=NOON + timedelta(minutes=6))
    assert ran == ["demo_check"]
    pending = notices.pending()
    assert len(pending) == 1
    assert pending[0]["title"] == "Heads up"


def test_quiet_check_produces_nothing(config):
    notices = NoticeBoard(config.data_dir)
    hb = make_heartbeat(config, notices, [text_reply("OK")])
    prime(hb)
    hb.tick(now=NOON + timedelta(minutes=6))
    assert notices.pending() == []  # quiet by default


def test_schedule_survives_restart(config):
    notices = NoticeBoard(config.data_dir)
    hb1 = make_heartbeat(config, notices, [text_reply("OK")])
    prime(hb1)
    # "Restart": a new heartbeat over the same data dir, one minute later.
    hb2 = make_heartbeat(config, notices, [text_reply("OK")])
    assert hb2.tick(now=NOON + timedelta(minutes=1)) == []  # not due yet — no boot refire
    assert hb2.tick(now=NOON + timedelta(minutes=6)) == ["demo_check"]


def test_overlapping_run_is_skipped(config):
    notices = NoticeBoard(config.data_dir)
    hb = make_heartbeat(config, notices, [text_reply("OK")])
    prime(hb)
    hb._running.add("demo_check")  # simulate a still-running slow check
    assert hb.tick(now=NOON + timedelta(minutes=6)) == []


def test_kill_switch_pauses_everything(config):
    notices = NoticeBoard(config.data_dir)
    hb = make_heartbeat(config, notices, [text_reply("OK")])
    prime(hb)
    hb.pause()
    assert hb.paused
    assert hb.tick(now=NOON + timedelta(minutes=10)) == []
    hb.resume()
    assert hb.tick(now=NOON + timedelta(minutes=10)) == ["demo_check"]


def test_quiet_hours_hold_non_urgent(config):
    notices = NoticeBoard(config.data_dir)
    hb = make_heartbeat(
        config,
        notices,
        [tool_reply("surface_notice", {"title": "fyi", "body": "later is fine"}), text_reply("OK")],
    )
    interruptions = []
    notices.on_urgent = interruptions.append
    night = datetime(2026, 7, 4, 23, 30)  # inside 22:00–08:00
    prime(hb, when=night)
    hb.tick(now=night + timedelta(minutes=6))
    assert notices.pending()  # held for catch-up…
    assert interruptions == []  # …but no interruption at night


def test_urgent_notice_interrupts_daytime(config):
    notices = NoticeBoard(config.data_dir)
    hb = make_heartbeat(
        config,
        notices,
        [
            tool_reply("surface_notice", {"title": "smoke", "body": "now", "urgent": True}),
            text_reply("OK"),
        ],
    )
    interruptions = []
    notices.on_urgent = interruptions.append
    prime(hb)
    hb.tick(now=NOON + timedelta(minutes=6))
    assert len(interruptions) == 1


def test_notice_dismissal(config):
    notices = NoticeBoard(config.data_dir)
    notices.post("a", "b")
    nid = notices.pending()[0]["id"]
    assert notices.dismiss(nid) is True
    assert notices.pending() == []
    assert notices.dismiss(nid) is False  # already gone


def test_quiet_hours_math():
    start, end = parse_hhmm("22:00"), parse_hhmm("08:00")
    assert in_quiet_hours(parse_hhmm("23:30"), start, end)
    assert in_quiet_hours(parse_hhmm("03:00"), start, end)
    assert not in_quiet_hours(parse_hhmm("12:00"), start, end)
