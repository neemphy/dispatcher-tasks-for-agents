"""The scheduler end to end on fake agents (tests/fakes: small scripts that print what claude / codex / gemini print).

A tick decides; a start only prepares the run folder and records it (``spawn`` is replaced); ``complete()`` then runs the
recorded runs for real through ``dispatcher.py _run`` logic (taskdispatch.runner), which starts the fake agent program.
No real agent, network or credentials are used.
"""
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

from taskdispatch import runner  # noqa: E402
from taskdispatch.home import Home, write_json  # noqa: E402
from taskdispatch.scheduler import Scheduler  # noqa: E402

FAKES = Path(__file__).resolve().parent / "fakes"
H = 3600


def worker(name, agent=None, **more):
    agent = agent or name
    return {"name": name, "agent": agent, "enabled": True, "bin": [sys.executable, str(FAKES / f"fake_{agent}.py")],
            "auth": "subscription", "probe_minutes": 0, **more}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dispatcher-test-"))
        self.home = Home(self.tmp / "home")
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.log = self.tmp / "calls.jsonl"
        self.now = [time.time()]
        self.spawned = []
        self.env = mock.patch.dict(os.environ, {"FAKE_LOG": str(self.log), "FAKE_MODE": "done", "FAKE_USED": "0.30"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def config(self, *workers):
        write_json(self.home.config_path, {"workers": list(workers)})

    def sched(self):
        return Scheduler(self.home, spawn=self.spawned.append, clock=lambda: self.now[0])

    def add(self, iid, brief="do the thing", *, size="M", urgent=False, **kw):
        kw.setdefault("alone", True)
        kw.setdefault("cwd", str(self.work))
        return self.sched().add(iid, brief, size=size, urgent=urgent, **kw)

    def tick(self):
        self.lines = []
        return self.sched().tick(out=self.lines.append)

    def started(self):
        return [(e["task"], e.get("worker")) for e in self.home.events() if e["event"] in ("started", "continued", "moved")]

    def complete(self, mode="done"):
        with mock.patch.dict(os.environ, {"FAKE_MODE": mode}):
            for d in list(self.spawned):
                if not (d / "exit").exists():
                    runner.run(d)

    def reported(self, name, short, long, *, resets=2 * H):
        self.home.update_limits(name, windows={"short": {"used": short, "resets": self.now[0] + resets},
                                               "long": {"used": long, "resets": self.now[0] + 3 * 86400}}, at=self.now[0])

    def calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def waiting(self):
        return {x["id"]: x for x in self.home.state()["items"]}


class Urgency(Base):
    def test_urgency_is_required_and_the_message_says_ask(self):
        self.config(worker("claude", windows="reported"))
        with self.assertRaises(SystemExit) as cm:
            self.sched().add("a", "brief", size="M", urgent=None)
        self.assertIn("ask the user", str(cm.exception))
        self.assertEqual([], self.home.state()["items"])

    def test_cli_refuses_without_urgency(self):
        self.config(worker("claude"))
        from taskdispatch.cli import main
        err = []
        with mock.patch("sys.stderr") as fake_err:
            fake_err.write.side_effect = err.append
            rc = main(["queue", "add", "a", "--brief", "x", "--size", "S"], home=self.home)
        self.assertEqual(2, rc)
        self.assertIn("ask the user", "".join(err))


class Placement(Base):
    def setUp(self):
        super().setUp()
        self.config(worker("claude", windows="reported"), worker("codex", windows="reported"))

    def test_urgent_where_it_fits_most_weekly_headroom_of_two(self):
        self.reported("claude", 10, 60)
        self.reported("codex", 10, 20)
        self.add("u", urgent=True)
        self.tick()
        self.assertEqual([("u", "codex")], self.started())

    def test_urgent_goes_where_it_fits_now(self):
        self.reported("claude", 10, 60)
        self.reported("codex", 95, 5)
        self.add("u", urgent=True)
        self.tick()
        self.assertEqual([("u", "claude")], self.started())

    def test_urgent_that_fits_nowhere_waits_then_starts_where_the_reset_comes(self):
        self.reported("claude", 85, 30, resets=3 * H)
        self.reported("codex", 85, 30, resets=1 * H)
        self.add("u", urgent=True, size="L")
        self.tick()
        self.assertEqual([], self.started())
        self.now[0] += 1.5 * H
        self.tick()
        self.assertEqual([("u", "codex")], self.started())

    def test_normal_always_goes_to_the_most_weekly_headroom_even_if_another_has_room(self):
        self.reported("claude", 0, 60)
        self.reported("codex", 70, 20)
        self.add("n", size="S")
        self.tick()
        self.assertEqual([("n", "codex")], self.started())

    def test_normal_waits_for_that_workers_reset_and_is_not_moved(self):
        self.reported("claude", 0, 60)
        self.reported("codex", 95, 20, resets=2 * H)
        self.add("n")
        self.tick()
        self.assertEqual([], self.started())
        it = self.waiting()["n"]
        self.assertTrue(it["wait"].startswith("reset:codex"))
        self.assertIn("not moved to another worker", it["wait_why"])
        self.now[0] += 1 * H
        self.tick()                                          # still the same reason: no second event
        self.assertEqual(1, sum(1 for e in self.home.events() if e["event"] == "waiting"))
        self.now[0] += 1 * H + 60
        self.tick()
        self.assertEqual([("n", "codex")], self.started())

    def test_both_windows_full_waits_only_for_the_more_weekly_headroom(self):
        self.reported("claude", 95, 30, resets=4 * H)
        self.reported("codex", 95, 50, resets=1 * H)
        self.add("n")
        self.now[0] += 1 * H + 60                             # codex resets first, but claude has more of its week left
        self.tick()
        self.assertEqual([], self.started())
        self.now[0] += 3 * H
        self.tick()
        self.assertEqual([("n", "claude")], self.started())

    def test_needs_one_worker(self):
        self.reported("claude", 10, 90)
        self.reported("codex", 10, 5)
        self.add("n", needs="claude")
        self.tick()
        self.assertEqual([("n", "claude")], self.started())

    def test_the_reserve_is_kept(self):
        self.config(worker("claude", windows="reported", reserve_percent=20), worker("codex", windows="reported",
                                                                                    reserve_percent=5))
        self.reported("claude", 75, 10)                       # 100 - 75 - 20 = 5 < 10
        self.reported("codex", 85, 60)                        # 100 - 85 - 5 = 10 ≥ 10
        self.add("u", urgent=True, size="M")
        self.tick()
        self.assertEqual([("u", "codex")], self.started())

    def test_a_choice_sticks_within_a_margin(self):
        self.reported("claude", 95, 40)
        self.reported("codex", 95, 41)
        self.add("n")
        self.tick()
        self.assertEqual("claude", self.waiting()["n"]["target"])
        self.reported("claude", 95, 41.5)
        self.tick()
        self.assertEqual("claude", self.waiting()["n"]["target"])


class OneAtATime(Base):
    def test_one_task_per_worker_and_order_kept(self):
        self.config(worker("claude", windows="reported"))
        self.reported("claude", 0, 10)
        for i in range(3):
            self.add(f"n{i}", size="S")
        self.tick()
        self.assertEqual([("n0", "claude")], self.started())
        self.assertEqual({"n1": "busy:claude", "n2": "behind:claude"}, {k: v["wait"] for k, v in self.waiting().items()})
        self.tick()
        self.assertEqual(1, len(self.started()))
        self.complete()
        self.tick()
        self.assertEqual(["n0", "n1"], [t for t, _ in self.started()])

    def test_a_run_finished_without_the_runner_is_seen_by_tick(self):
        self.config(worker("claude", windows="reported"))
        self.add("a", urgent=True, size="S")
        self.tick()
        d = self.spawned[0]
        (d / "pid").write_text("999999999")                   # the run's process is gone without an exit code
        self.add("b", urgent=True, size="S")
        self.tick()
        self.assertEqual("error", self.home.state()["tasks"]["a"]["turns"][-1]["status"])
        self.assertEqual(["a", "b"], [t for t, _ in self.started()])


class Runs(Base):
    def test_a_run_uses_the_task_folder_the_brief_on_stdin_and_records_the_report(self):
        self.config(worker("claude", windows="reported"))
        self.add("a", "fix tests/test_x.py please", urgent=True, size="S")
        self.tick()
        self.complete()
        [call] = self.calls()
        self.assertEqual(self.work.resolve(), Path(call["cwd"]).resolve())  # macOS: /var is /private/var
        self.assertEqual("fix tests/test_x.py please", call["stdin"])
        self.assertIn("--session-id", call["argv"])
        info = self.sched().show("a")
        self.assertEqual(("done", "claude"), (info["state"], info["worker"]))
        self.assertIn("started: done", info["report"])
        cached = self.home.limits_cache()["claude"]["windows"]
        self.assertEqual(30.0, cached["short"]["used"])        # the run's own output updated the limits
        self.assertEqual(["added", "started", "finished"], [e["event"] for e in self.home.events()])

    def test_subscription_workers_do_not_get_api_keys_api_workers_do(self):
        self.config(worker("claude", windows="reported"), worker("codex", auth="api"))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x", "CODEX_API_KEY": "y"}):
            self.add("a", urgent=True, size="S", needs="claude")
            self.add("b", urgent=True, size="S", needs="codex")
            self.tick()
            self.complete()
        keys = {c["argv"][0] if c["argv"] else "": c["keys"] for c in self.calls()}
        by_agent = {("claude" if "-p" in c["argv"] else "codex"): c["keys"] for c in self.calls()}
        self.assertNotIn("ANTHROPIC_API_KEY", by_agent["claude"])
        self.assertIn("CODEX_API_KEY", by_agent["codex"])
        self.assertTrue(keys)

    def test_a_missing_folder_is_an_error_not_a_crash(self):
        self.config(worker("claude"))
        self.add("a", urgent=True, size="S", cwd=str(self.tmp / "nowhere"))
        self.tick()
        self.complete()
        info = self.sched().show("a")
        self.assertEqual("error", info["state"])


class Related(Base):
    def test_with_continues_the_same_session_after_the_current_run(self):
        self.config(worker("claude", windows="reported"))
        self.add("a", urgent=True, size="S")
        self.tick()
        self.add("b", "and update the docs", size="S", with_id="a")
        self.tick()
        self.assertEqual("after:a", self.waiting()["b"]["wait"])
        self.complete()
        self.tick()
        self.complete()
        first, second = self.calls()
        session = first["argv"][first["argv"].index("--session-id") + 1]
        self.assertEqual(session, second["argv"][second["argv"].index("--resume") + 1])
        self.assertEqual("and update the docs", second["stdin"])
        self.assertEqual("a", self.sched().show("b")["id"])      # «b» went into task «a»

    def test_codex_resume_uses_the_thread_id_from_its_output(self):
        self.config(worker("codex"))
        self.add("a", urgent=True, size="S")
        self.tick()
        self.complete()
        self.add("b", "more", size="S", with_id="a")
        self.tick()
        self.complete()
        second = self.calls()[-1]
        self.assertEqual(["exec", "--json", "resume", "thread-123", "more"], second["argv"])

    def test_an_agent_that_cannot_resume_gets_a_new_run_with_the_last_report(self):
        self.config(worker("gemini"))
        self.add("a", "write the parser", urgent=True, size="S")
        self.tick()
        self.complete()
        self.add("b", "now its docs", size="S", with_id="a")
        self.tick()
        self.complete()
        second = self.calls()[-1]["stdin"]
        self.assertIn("write the parser", second)                # the original brief
        self.assertIn("done: write the parser", second)          # the last report
        self.assertIn("now its docs", second)

    def test_opencode_runs_and_continues_with_a_new_run_and_last_report(self):
        self.config(worker("opencode"))
        self.add("a", "write the parser", urgent=True, size="S")
        self.tick()
        self.complete()
        self.add("b", "now its docs", size="S", with_id="a")
        self.tick()
        self.complete()
        first, second = self.calls()
        self.assertEqual(["run", "write the parser"], first["argv"])
        self.assertEqual("run", second["argv"][0])
        self.assertIn("write the parser", second["argv"][-1])
        self.assertIn("done: write the parser", second["argv"][-1])
        self.assertIn("now its docs", second["argv"][-1])

    def test_a_similar_brief_is_linked_and_logged(self):
        self.config(worker("claude"))
        self.add("a", "Refactor src/parser/lexer.py and src/parser/tokens.py, keep the tests green", urgent=True,
                 size="S", alone=False)
        self.tick()
        it, lines = self.add("b", "In src/parser/lexer.py and src/parser/tokens.py also refactor the tests", size="S",
                             alone=False)
        self.assertEqual("a", it["with"])
        self.assertIn("linked", lines[1])
        self.assertIn("shared files", self.home.events()[-1]["why"])

    def test_unrelated_is_not_linked(self):
        self.config(worker("claude"))
        self.add("a", "Translate the landing page to German", urgent=True, size="S", alone=False)
        it, _ = self.add("b", "Fix the database migration in db/migrate.sql", size="S", alone=False)
        self.assertEqual("", it["with"])


class AfterALimit(Base):
    def test_continues_the_same_session_after_the_reset(self):
        self.config(worker("claude", windows="reported"))
        self.add("t", urgent=True, size="S", needs="claude")
        self.tick()
        self.complete(mode="limit")
        st = self.home.state()
        self.assertEqual("limit", st["tasks"]["t"]["turns"][-1]["status"])
        self.assertEqual(["t-cont1"], [x["id"] for x in st["items"]])
        self.assertIn("continue-queued", [e["event"] for e in self.home.events()])
        self.tick()
        self.assertEqual(1, len(self.started()))                  # paused until the reset the agent named
        self.now[0] += H + 60
        self.reported("claude", 0, 25)
        self.tick()
        self.complete()
        last = self.calls()[-1]
        self.assertIn("--resume", last["argv"])
        self.assertIn("stopped at a usage limit", last["stdin"])
        self.assertEqual("done", self.home.state()["tasks"]["t"]["turns"][-1]["status"])

    def test_moves_to_another_free_worker_with_the_last_report(self):
        self.config(worker("claude", windows="reported"), worker("gemini"))
        self.reported("claude", 0, 10)
        self.add("t", "build the report page", urgent=True, size="S", needs="any")
        self.tick()
        self.assertEqual([("t", "claude")], self.started())
        self.complete(mode="limit")
        self.tick()
        self.assertEqual(("t-cont1", "gemini"), self.started()[-1])
        self.complete()
        moved = self.calls()[-1]["stdin"]
        self.assertIn("build the report page", moved)
        self.assertIn("You've hit your limit", moved)
        self.assertEqual("t", self.home.state()["tasks"]["t-on-gemini"]["continues"])

    def test_codex_and_gemini_limits_are_recognised(self):
        for agent in ("codex", "gemini", "opencode"):
            with self.subTest(agent=agent):
                self.setUp()
                self.config(worker(agent, pause_after_limit_minutes=30))
                self.add("t", urgent=True, size="S")
                self.tick()
                self.complete(mode="limit")
                st = self.home.state()
                self.assertEqual("limit", st["tasks"]["t"]["turns"][-1]["status"])
                paused = self.home.limits_cache()[agent]["paused_until"]
                self.assertAlmostEqual(time.time() + 1800, paused, delta=60)
                self.tearDown()
                self.env.start()


class Windows(Base):
    def test_configured_windows_are_counted_from_own_runs(self):
        self.config(worker("codex", windows=[{"name": "short", "hours": 5}, {"name": "week", "hours": 168}]))
        for i in range(4):
            self.add(f"x{i}", urgent=True, size="L")             # 25 % each; reserve 10 %
        for _ in range(4):
            self.tick()
            self.complete()
        started = [t for t, _ in self.started()]
        self.assertEqual(["x0", "x1", "x2"], started)            # 75 % used: the fourth waits for the window
        self.assertIn("short window", self.waiting()["x3"]["wait_why"])
        self.now[0] += 5 * H + 60
        self.tick()
        self.assertEqual("x3", self.started()[-1][0])

    def test_an_api_budget_in_dollars(self):
        self.config(worker("claude", auth="api", budget_usd={"amount": 1.0, "hours": 24}))
        for i in range(5):
            self.add(f"x{i}", urgent=True, size="S")
        for _ in range(5):
            self.tick()
            self.complete()
        # each fake run reports $0.25: after three runs 75 % of the budget is spent; with the 10 % reserve the next fits
        # only while 3 % ≤ 100 − used − 10
        self.assertEqual(4, len(self.started()))
        self.assertIn("short window", self.waiting()["x4"]["wait_why"])

    def test_unknown_limits_one_at_a_time_and_a_pause_after_a_limit(self):
        self.config(worker("gemini", pause_after_limit_minutes=60))
        self.add("a", urgent=True, size="XL")
        self.add("b", urgent=True, size="XL")
        self.tick()
        self.assertEqual([("a", "gemini")], self.started())       # unknown limits: XL fits, but one at a time
        self.complete(mode="limit")
        self.tick()
        self.assertEqual(1, len(self.started()))
        self.assertIn("paused after a usage limit", self.waiting()["b"]["wait_why"])

    def test_sizes_are_learned_from_reported_windows(self):
        self.config(worker("claude", windows="reported"))
        for i, used in enumerate(("0.10", "0.12", "0.14")):
            self.reported("claude", 0, 10)
            with mock.patch.dict(os.environ, {"FAKE_USED": used}):
                self.add(f"s{i}", urgent=True, size="S")
                self.tick()
                self.complete()
        learned = self.home.sizes()["S"]
        self.assertAlmostEqual(0.5 * 3 + 0.5 * 12, learned, delta=0.1)


class DryRun(Base):
    def test_dry_entries_are_shown_never_started(self):
        self.config(worker("claude"))
        self.add("hello-test", size="S", dry=True)
        self.tick()
        self.assertEqual([], self.started())
        self.assertIn("would start on claude", self.waiting()["hello-test"]["wait_why"])
        before = self.home.state_path.read_text()
        self.sched().tick(dry=True, out=lambda s: None)
        self.assertEqual(before, self.home.state_path.read_text())
        self.sched().remove("hello-test")
        self.assertEqual([], self.home.state()["items"])

    def test_tick_dry_run_changes_nothing(self):
        self.config(worker("claude"))
        self.add("a", urgent=True, size="S")
        self.add("b", urgent=True, size="S")
        before = self.home.state_path.read_text()
        out = []
        self.sched().tick(dry=True, out=out.append)
        self.assertEqual(before, self.home.state_path.read_text())
        self.assertEqual([], self.spawned)
        self.assertIn("a: would start on claude", out[0])
        self.assertIn("b: waits", out[1])


if __name__ == "__main__":
    unittest.main()
