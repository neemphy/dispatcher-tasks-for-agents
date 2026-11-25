"""Adapters on their own: the command each one builds and how it reads its agent's output (no agent is run, except the
fake claude for the limits probe)."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import adapters  # noqa: E402
from adapters.claude import ClaudeAdapter  # noqa: E402
from adapters.codex import CodexAdapter  # noqa: E402
from adapters.gemini import GeminiAdapter  # noqa: E402
from adapters.opencode import OpenCodeAdapter  # noqa: E402

FAKES = Path(__file__).resolve().parent / "fakes"


def ev(**kw):
    return json.dumps(kw)


class Claude(unittest.TestCase):
    def setUp(self):
        self.a = ClaudeAdapter({"name": "c", "model": "sonnet", "args": ["--permission-mode", "acceptEdits"]}, Path("/tmp"))

    def test_commands(self):
        argv, stdin = self.a.command({"session": "s-1"}, resume=False, text="brief")
        self.assertEqual(["claude", "-p", "--output-format", "stream-json", "--verbose", "--session-id", "s-1", "--model", "sonnet",
                          "--permission-mode", "acceptEdits"], argv)
        self.assertEqual("brief", stdin)
        argv, stdin = self.a.command({"session": "s-1"}, resume=True, text="more")
        self.assertIn("--resume", argv)
        self.assertNotIn("--session-id", argv)

    def test_done_with_windows_and_cost(self):
        t = time.time()
        out = "\n".join([ev(type="rate_limit_event", rate_limit_info={"unifiedWindows": {
            "five_hour": {"utilization": 0.4, "resetsAt": t + 100}, "seven_day": {"utilization": 0.1, "resetsAt": t + 900},
            "seven_day_opus": {"utilization": 0.3, "resetsAt": t + 900}}}),
            ev(type="result", is_error=False, result="all done", session_id="s-1", total_cost_usd=0.5)])
        o = self.a.parse(out, "", 0)
        self.assertEqual(("done", "all done", "s-1", 0.5), (o.status, o.report, o.session, o.cost_usd))
        self.assertEqual(40.0, o.windows["short"]["used"])
        self.assertEqual(30.0, o.windows["long"]["used"])           # the fullest weekly window

    def test_limit(self):
        o = self.a.parse(ev(type="rate_limit_event", rate_limit_info={"status": "rejected", "resetsAt": 123}), "", 1)
        self.assertEqual(("limit", 123), (o.status, o.resets_at))
        o = self.a.parse(ev(type="result", is_error=True, result="Claude usage limit reached"), "", 1)
        self.assertEqual("limit", o.status)

    def test_a_good_report_that_talks_about_limits_is_not_a_limit(self):
        o = self.a.parse(ev(type="result", is_error=False, result="fixed the rate limit handling in api.py"), "", 0)
        self.assertEqual("done", o.status)

    def test_no_result_is_an_error(self):
        o = self.a.parse("garbage", "Traceback: boom", 1)
        self.assertEqual(("error", "Traceback: boom"), (o.status, o.why))

    def test_the_probe_is_one_ordinary_tiny_request(self):
        log = Path(tempfile.mkdtemp()) / "log"
        a = ClaudeAdapter({"name": "c", "bin": [sys.executable, str(FAKES / "fake_claude.py")]}, Path("/tmp"))
        with mock.patch.dict(os.environ, {"FAKE_LOG": str(log), "FAKE_USED": "0.42"}):
            windows = a.limits()
        self.assertEqual(42.0, windows["short"]["used"])
        [call] = [json.loads(x) for x in log.read_text().splitlines()]
        self.assertEqual(["-p", "--model", "haiku", "--tools", "", "--no-session-persistence"], call["argv"][:6])
        self.assertNotIn("--session-id", call["argv"])
        shutil.rmtree(log.parent)


class Codex(unittest.TestCase):
    def setUp(self):
        self.a = CodexAdapter({"name": "x", "model": "gpt-x", "args": ["--sandbox", "workspace-write"]}, Path("/tmp"))

    def test_commands(self):
        argv, stdin = self.a.command({"session": ""}, resume=False, text="brief")
        self.assertEqual(["codex", "exec", "--json", "-m", "gpt-x", "--sandbox", "workspace-write", "-"], argv)
        self.assertEqual("brief", stdin)
        argv, stdin = self.a.command({"session": "th-1"}, resume=True, text="more")
        self.assertEqual(["codex", "exec", "--json", "-m", "gpt-x", "--sandbox", "workspace-write", "resume", "th-1", "more"], argv)
        self.assertIsNone(stdin)

    def test_parse(self):
        out = "\n".join([ev(type="thread.started", thread_id="th-1"),
                         ev(type="item.completed", item={"type": "agent_message", "text": "first"}),
                         ev(type="item.completed", item={"type": "command_execution", "text": "ls"}),
                         ev(type="item.completed", item={"type": "agent_message", "text": "final"}),
                         ev(type="turn.completed", usage={"input_tokens": 1})])
        o = self.a.parse(out, "", 0)
        self.assertEqual(("done", "final", "th-1"), (o.status, o.report, o.session))

    def test_failures(self):
        o = self.a.parse(ev(type="turn.failed", error={"message": "You've hit your usage limit"}), "", 1)
        self.assertEqual("limit", o.status)
        o = self.a.parse(ev(type="error", message="sandbox denied"), "", 1)
        self.assertEqual(("error", "sandbox denied"), (o.status, o.why))
        o = self.a.parse("", "not inside a trusted directory", 1)
        self.assertEqual("error", o.status)


class Gemini(unittest.TestCase):
    def setUp(self):
        self.a = GeminiAdapter({"name": "g", "args": ["--approval-mode", "auto_edit"]}, Path("/tmp"))

    def test_command_and_no_resume(self):
        argv, stdin = self.a.command({}, resume=False, text="brief")
        self.assertEqual(["gemini", "--output-format", "json", "--approval-mode", "auto_edit"], argv)
        self.assertEqual("brief", stdin)
        self.assertFalse(self.a.can_resume)

    def test_parse(self):
        self.assertEqual(("done", "ok"), (lambda o: (o.status, o.report))(self.a.parse(ev(response="ok", stats={}), "", 0)))
        o = self.a.parse(ev(error={"message": "Quota exceeded (429)"}), "", 1)
        self.assertEqual("limit", o.status)
        o = self.a.parse("", "", 53)
        self.assertEqual(("error", "turn limit exceeded"), (o.status, o.why))
        o = self.a.parse("Loaded cached credentials.\n" + ev(response="after a log line"), "", 0)
        self.assertEqual("after a log line", o.report)


class OpenCode(unittest.TestCase):
    def setUp(self):
        self.a = OpenCodeAdapter({"name": "oc", "model": "anthropic/claude-sonnet-5-5", "args": ["--auto"]}, Path("/tmp"))

    def test_command_and_no_resume(self):
        argv, stdin = self.a.command({}, resume=False, text="brief")
        self.assertEqual(["opencode", "run", "--model", "anthropic/claude-sonnet-5-5", "--auto", "brief"], argv)
        self.assertIsNone(stdin)
        self.assertFalse(self.a.can_resume)
        argv_res, stdin_res = self.a.command({"session": "ses_1"}, resume=True, text="more")
        self.assertEqual(["opencode", "run", "--model", "anthropic/claude-sonnet-5-5", "--auto", "more"], argv_res)
        self.assertIsNone(stdin_res)

    def test_parse(self):
        o = self.a.parse("all done\n", "", 0)
        self.assertEqual(("done", "all done"), (o.status, o.report))
        o = self.a.parse("", "Rate limit exceeded (429)", 1)
        self.assertEqual("limit", o.status)
        o = self.a.parse("", "provider failed\nbad request", 2)
        self.assertEqual(("error", "bad request"), (o.status, o.why))

    def test_a_good_report_that_talks_about_limits_is_not_a_limit(self):
        o = self.a.parse("fixed the rate limit handling in api.py", "", 0)
        self.assertEqual("done", o.status)


class Common(unittest.TestCase):
    def test_subscription_drops_api_keys_api_keeps_them(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k", "HOME": "/h"}):
            self.assertNotIn("GEMINI_API_KEY", GeminiAdapter({"name": "g"}, Path("/tmp")).env())
            self.assertEqual("k", GeminiAdapter({"name": "g", "auth": "api"}, Path("/tmp")).env()["GEMINI_API_KEY"])

    def test_an_unknown_agent_points_to_contributing(self):
        with self.assertRaises(SystemExit) as cm:
            adapters.get({"name": "x", "agent": "other"}, Path("/tmp"))
        self.assertIn("CONTRIBUTING.md", str(cm.exception))

    def test_the_template_is_a_valid_starting_point(self):
        from adapters import _template
        a = _template.MyAgentAdapter({"name": "m"}, Path("/tmp"))
        argv, stdin = a.command({"session": ""}, resume=False, text="brief")
        self.assertEqual("brief", stdin)
        self.assertEqual("done", a.parse("final text", "", 0).status)


class OneWorkerPerAgent(unittest.TestCase):
    def test_two_enabled_workers_of_one_agent_are_refused(self):
        from taskdispatch.home import Home, write_json
        tmp = Path(tempfile.mkdtemp())
        home = Home(tmp)
        write_json(home.config_path, {"workers": [{"name": "a", "agent": "claude"}, {"name": "b", "agent": "claude"}]})
        with self.assertRaises(SystemExit) as cm:
            home.workers()
        self.assertIn("one worker per agent", str(cm.exception))
        write_json(home.config_path, {"workers": [{"name": "a", "agent": "claude"},
                                                  {"name": "b", "agent": "claude", "enabled": False}]})
        self.assertEqual(["a"], [w["name"] for w in home.workers()])
        shutil.rmtree(tmp)


class Init(unittest.TestCase):
    def test_init_writes_a_config_without_secrets_and_never_overwrites(self):
        tmp = Path(tempfile.mkdtemp())
        bindir = tmp / "bin"
        bindir.mkdir()
        (bindir / "claude").write_text("#!/bin/sh\n")
        (bindir / "claude").chmod(0o755)
        from taskdispatch.cli import main
        from taskdispatch.home import Home
        home = Home(tmp / "home")
        with mock.patch.dict(os.environ, {"PATH": str(bindir), "ANTHROPIC_API_KEY": "secret-value"}), \
                mock.patch("sys.stdout"):
            self.assertEqual(0, main(["init"], home=home))
            first = home.config_path.read_text()
            self.assertEqual(0, main(["init"], home=home))
        cfg = json.loads(first)
        self.assertEqual({"claude": True, "codex": False, "gemini": False, "opencode": False},
                         {w["name"]: w["enabled"] for w in cfg["workers"]})
        self.assertEqual("reported", cfg["workers"][0]["windows"])
        self.assertNotIn("secret-value", first)
        self.assertEqual(first, home.config_path.read_text())
        shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
