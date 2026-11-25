"""The scheduler: queue, urgency, sizes, placement, one task at a time per worker, related work in the same session,
continuing after a usage limit, events. It knows no agent — it talks to workers only through adapters (adapters/base.py).

Placement rules:
* **Urgent** — now, on a free worker where the task fits; between several, the one with the most long-window headroom.
* **Normal** — always to the worker with the most long-window headroom (the least used week), even if another one has
  room right now, so no worker is drained before the others. If its short window can't fit the task, the task waits for
  that reset — it is not pushed to another worker. A choice sticks until another worker is ahead by more than a margin.
* **One task at a time per worker.** Normal tasks for the same worker keep their order.
* **Related work** (``--with`` or a similar brief) continues the same session on the same worker after its current run.
* **A run stopped by a limit** is queued again: after the reset it continues the same session on the same worker; if that
  worker is still blocked and the task may run anywhere, another free worker gets a new run with "continue" + the last report.
Workers whose limits are unknown are compared by what this dispatcher started on them in the last 7 days.
"""
from __future__ import annotations

import contextlib
import fcntl
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import adapters
from adapters.base import LIMIT, RUNNING, Outcome
from taskdispatch import similar
from taskdispatch import windows as win
from taskdispatch.home import SIZES, Home, iso, write_json

CONTINUE_TEXT = ("The previous run of this task stopped at a usage limit. Continue the task from where it stopped; "
                 "finish with the usual final report.")
WEEK_HYST = 2.0                 # % of a long window
RECENT_HYST = 10.0              # % of a short window (one M task)


def continue_brief(task: Dict[str, Any], report: str, text: str = "") -> str:
    """A new run that has to pick up someone else's (or its own lost) session: the original brief and the last report."""
    return (f"# Continuing task {task['id']}\n\nAn earlier run of this task stopped before it was done (it cannot be resumed "
            f"here). Check what is already done (files, branches, the report below), then continue.\n\n"
            f"## Original brief\n\n{task.get('brief') or task.get('title') or task['id']}\n\n"
            f"## Last report\n\n{report or '(no report)'}\n" + (f"\n## Now\n\n{text}\n" if text else ""))


class Scheduler:
    def __init__(self, home: Optional[Home] = None, *, spawn: Optional[Callable[[Path], None]] = None,
                 clock: Callable[[], float] = time.time):
        self.home = home or Home()
        self.spawn = spawn
        self.clock = clock

    # ------------------------------------------------------------------ workers
    def workers(self) -> List[Dict[str, Any]]:
        return self.home.workers()

    def worker(self, name: str) -> Optional[Dict[str, Any]]:
        return next((w for w in self.home.config()["workers"] if w["name"] == name), None)

    def adapter(self, worker: Dict[str, Any]):
        return adapters.get(worker, self.home.path / "runs", self.spawn)

    def candidates(self, needs: str) -> List[Dict[str, Any]]:
        return [w for w in self.workers() if needs in ("any", "", None) or w["name"] == needs]

    def views(self, st: Dict[str, Any], names: Optional[List[str]] = None) -> Dict[str, win.View]:
        at = self.clock()
        cache = self.home.limits_cache()
        out = {}
        for w in self.workers():
            if names is not None and w["name"] not in names:
                continue
            turns = [{"at": t["at_ts"], "size": t.get("size", 0.0), "cost_usd": t.get("cost_usd")}
                     for task in st["tasks"].values() if task.get("worker") == w["name"] for t in task.get("turns") or []]
            ad = self.adapter(w)
            out[w["name"]] = win.view(w, turns=turns, cache=cache.get(w["name"]) or {}, reported_names=ad.reported_windows,
                                      at=at)
        return out

    # ------------------------------------------------------------------ finishing a run (from the runner, or seen by tick)
    def finish(self, st: Dict[str, Any], task_id: str, n: int, outcome: Outcome) -> bool:
        """Record the end of a run in the state (st is held under the lock by the caller). False — already recorded."""
        task = st["tasks"].get(task_id)
        if not task:
            return False
        turn = next((t for t in task["turns"] if t["n"] == n), None)
        if turn is None or turn.get("status") not in (None, RUNNING):
            return False
        at = self.clock()
        turn.update(status=outcome.status, exit=outcome.exit_code, finished=iso(at), why=outcome.why,
                    report_tail=(outcome.report or "")[-2000:])
        if outcome.cost_usd is not None:
            turn["cost_usd"] = outcome.cost_usd
        if outcome.session and not task.get("session"):
            task["session"] = outcome.session
        worker = self.worker(task["worker"]) or {"name": task["worker"]}
        if outcome.windows:
            self.home.update_limits(task["worker"], windows=outcome.windows, at=at)
            self.calibrate(turn, outcome)
        if outcome.status == LIMIT:
            pause = outcome.resets_at if outcome.resets_at > at else \
                at + 60 * float(worker.get("pause_after_limit_minutes", win.DEFAULT_PAUSE_MINUTES))
            self.home.update_limits(task["worker"], paused_until=pause)
            cid = f"{task_id}-cont{n}"
            if not any(x["id"] == cid for x in st["items"]):
                st["items"].append({"id": cid, "kind": "continue", "task": task_id, "title": f"{task.get('title', task_id)} "
                                    "(continued)", "size": task.get("size_name", "M"), "needs": task.get("needs", "any"),
                                    "urgent": bool(task.get("urgent")), "added": iso(at), "report": (outcome.report or "")[-4000:]})
                self.home.event("continue-queued", cid, f"run {n} of {task_id} on {task['worker']} stopped at a usage limit; "
                                f"it continues after {win.clock(pause, at)}", worker=task["worker"])
        self.home.event("finished", task_id, outcome.why or outcome.status, worker=task["worker"], run=n,
                        status=outcome.status, exit=outcome.exit_code)
        return True

    def calibrate(self, turn: Dict[str, Any], outcome: Outcome) -> None:
        """Learn real sizes: how much of the short window a run of this size really used (when the agent reports it)."""
        from taskdispatch.home import read_json
        before, after = turn.get("before_short"), (outcome.windows.get("short") or {}).get("used")
        if before is None or after is None or after < before or not turn.get("size_name"):
            return                                       # the window reset in between — not a measurement
        if turn.get("remaining"):
            return                                       # only the rest of a cut-off run: it would teach a size too small
        data = read_json(self.home.sizes_path, {})
        samples = data.setdefault("_samples", {}).setdefault(turn["size_name"], [])
        samples.append(round(after - before, 1))
        del samples[:-20]
        if len(samples) >= 3:
            median = sorted(samples)[len(samples) // 2]
            data[turn["size_name"]] = round(0.5 * self.home.sizes()[turn["size_name"]] + 0.5 * median, 1)
        # sizes stay in order (S ≤ M ≤ L ≤ XL): a few noisy samples must not make a bigger size look cheaper
        cur = {**SIZES, **{k: v for k, v in data.items() if k in SIZES}}
        names = list(SIZES)
        for lo, hi in zip(names, names[1:]):
            if cur[hi] < cur[lo]:
                cur[hi] = data[hi] = cur[lo]
        write_json(self.home.sizes_path, data)

    # ------------------------------------------------------------------ who is busy
    def scan(self, st: Dict[str, Any]) -> Tuple[Dict[str, str], set]:
        busy, running = {}, set()
        for tid, task in st["tasks"].items():
            turns = task.get("turns") or []
            if not turns or turns[-1].get("status") not in (None, RUNNING):
                continue
            worker = self.worker(task["worker"])
            if worker is None:
                continue
            outcome = self.adapter(worker).status(turns[-1]["run"])
            if outcome.status == RUNNING:
                busy.setdefault(task["worker"], tid)
                running.add(tid)
            else:
                self.finish(st, tid, turns[-1]["n"], outcome)
        return busy, running

    # ------------------------------------------------------------------ the queue
    def add(self, item_id: str, brief: str, *, size: str, urgent: Optional[bool], needs: str = "any", with_id: str = "",
            alone: bool = False, title: str = "", cwd: str = "", dry: bool = False) -> Tuple[Dict[str, Any], List[str]]:
        if urgent is None:
            raise SystemExit("urgency is required: --urgent or --normal. If it is unclear whether the task is urgent, "
                             "ask the user — do not guess.")
        if size not in self.home.sizes():
            raise SystemExit(f"size must be one of {', '.join(self.home.sizes())}")
        if needs not in ("any", "") and self.worker(needs) is None:
            raise SystemExit(f"--needs {needs}: no such worker (workers: {', '.join(w['name'] for w in self.workers())})")
        if not brief.strip():
            raise SystemExit("the brief is empty")
        lines = []
        with self.home.changing() as st:
            if item_id in st["tasks"] or item_id in st["moved"] or any(x["id"] == item_id for x in st["items"]):
                raise SystemExit(f"{item_id} exists already — for related work use a new id with --with {item_id}")
            it = {"id": item_id, "kind": "new", "brief": brief, "title": title or item_id, "size": size, "needs": needs or "any",
                  "urgent": bool(urgent), "cwd": str(Path(cwd or ".").expanduser().resolve()), "with": "", "alone": alone,
                  "dry": dry, "added": iso(self.clock())}
            if with_id:
                if not (with_id in st["tasks"] or with_id in st["moved"] or any(x["id"] == with_id for x in st["items"])):
                    raise SystemExit(f"--with {with_id}: no such task in the queue or among started tasks")
                it["with"], it["linked"] = with_id, "explicit (--with)"
                lines.append(f"part of {with_id}: it continues the same session after that run")
            elif not alone:
                rel, why = similar.find_related(brief, self._related_candidates(st))
                if rel:
                    it["with"], it["linked"] = rel, f"hint: {why}"
                    lines.append(f"looks like part of {rel} ({why}) — linked; if not: queue rm {item_id} and add again with --alone")
            st["items"].append(it)
        self.home.event("added", item_id, ("urgent" if urgent else "normal") + f", {size}, worker: {needs or 'any'}"
                        + (", dry run (never started)" if dry else "")
                        + (f", part of {it['with']} — {it['linked']}" if it["with"] else ""))
        lines.insert(0, f"queued: {item_id} ({'urgent' if urgent else 'normal'}, {size}, {needs or 'any'})"
                     + (" — dry run: shown by tick --dry-run, never started" if dry else " — the next tick places it"))
        return it, lines

    def _related_candidates(self, st: Dict[str, Any], running: Optional[set] = None):
        for tid, task in st["tasks"].items():
            last = (task.get("turns") or [{}])[-1]
            if (running is None and last.get("status") in (None, RUNNING)) or (running is not None and tid in running):
                yield tid, task.get("brief") or ""
        if running is None:
            for x in st["items"]:
                if x.get("kind") == "new":
                    yield x["id"], x.get("brief") or ""

    def remove(self, item_id: str) -> None:
        with self.home.changing() as st:
            left = [x for x in st["items"] if x["id"] != item_id]
            if len(left) == len(st["items"]):
                raise SystemExit(f"{item_id}: not waiting in the queue" + (" (it has started; it cannot be removed)"
                                                                          if item_id in st["tasks"] else ""))
            st["items"] = left
        self.home.event("removed", item_id, "removed from the queue by hand")

    # ------------------------------------------------------------------ placement
    def resolve(self, ref: str, st: Dict[str, Any]) -> Optional[str]:
        """The started task whose session related work continues: a task id; None — still waiting; '' — no such task."""
        seen = set()
        while ref and ref not in seen:
            seen.add(ref)
            if ref in st["tasks"]:
                return ref
            if ref in st["moved"]:
                return st["moved"][ref]
            it = next((x for x in st["items"] if x["id"] == ref), None)
            if it is None:
                return ""
            if it.get("with"):
                ref = it["with"]
                continue
            return None
        return ""

    @staticmethod
    def pick(cands: List[win.View], prefer: str = "") -> Optional[win.View]:
        """The worker with the most long-window headroom; if some have unknown limits, the one this dispatcher used least
        in the last 7 days. ``prefer`` (the earlier choice) sticks until another one is ahead by a margin."""
        if not cands:
            return None
        keep = next((v for v in cands if v.worker == prefer), None)
        if all(v.load is not None for v in cands):
            least = min(v.load for v in cands)
            best = min((v for v in cands if v.load - least < 1.0), key=lambda v: (v.short.used if v.short else 0.0))
            return keep if keep is not None and keep.load <= best.load + WEEK_HYST else best
        best = min(cands, key=lambda v: v.recent)
        return keep if keep is not None and keep.recent <= best.recent + RECENT_HYST else best

    def decide(self, it: Dict[str, Any], st: Dict[str, Any], views: Dict[str, win.View], busy: Dict[str, str],
               running: set, held: Dict[str, str]) -> Dict[str, Any]:
        at = self.clock()
        size = self.home.sizes()[it["size"]]

        def free(name: str) -> Tuple[bool, str]:
            if name in busy:
                return False, f"{name} is running {busy[name]} — one task at a time"
            return True, ""

        def fit(name: str) -> Tuple[bool, str]:
            w = self.worker(name)
            if w is None or name not in views:
                return False, f"{name}: not a configured worker"
            return win.fits(views[name], size, w, at)

        def wait(key: str, why: str) -> Dict[str, Any]:
            return {"act": "wait", "key": key, "why": why}

        def go(name: str, mode: str, why: str, task: str = "") -> Dict[str, Any]:
            return {"act": "start", "worker": name, "mode": mode, "why": why, "task": task}

        # 1) a run that stopped at a limit
        if it.get("kind") == "continue":
            task = st["tasks"].get(it["task"]) or {}
            name = task.get("worker", "")
            ok, why = fit(name)
            if ok:
                ok_free, why_busy = free(name)
                return go(name, "follow", f"{name} can take it again — continuing the same task", it["task"]) if ok_free \
                    else wait("busy:" + name, why_busy)
            if it.get("needs") == "any":
                for v in sorted(views.values(), key=lambda v: v.worker):
                    if v.worker != name and fit(v.worker)[0] and free(v.worker)[0]:
                        return go(v.worker, "move", f"{why}; {v.worker} has room — a new run there with the last report",
                                  it["task"])
            return wait("reset:" + name, f"{why} — then it continues the same task there")
        # 2) related work — the same session after the current run
        if it.get("with"):
            root = self.resolve(it["with"], st)
            if root is None:
                return wait("with:" + it["with"], f"part of {it['with']}: waits until that one starts")
            if root:
                name = st["tasks"][root]["worker"]
                if root in running:
                    return wait("after:" + root, f"part of {root}: continues its session on {name} after the current run")
                ok, why = free(name)
                if not ok:
                    return wait("busy:" + name, why)
                ok, why = fit(name)
                return go(name, "follow", f"part of {root}: continues its session on {name}", root) if ok \
                    else wait("reset:" + name, f"part of {root}: {why}")
            it["with"] = ""                                    # the related task is gone — a normal task
        names = [w["name"] for w in self.candidates(it.get("needs", "any"))]
        if not names:
            return wait("noworker", f"no enabled worker for --needs {it.get('needs')}")
        cand = [views[n] for n in names if n in views]
        # 3) urgent — now, where it fits; between several, the most long-window headroom
        if it.get("urgent"):
            fitting = [v for v in cand if fit(v.worker)[0]]
            best = self.pick([v for v in fitting if free(v.worker)[0]])
            if best:
                return go(best.worker, "new", "urgent: fits now on " + best.worker +
                          (" (the most weekly headroom of the free ones)" if len(fitting) > 1 else ""))
            if fitting:
                return wait("busy", "; ".join(free(v.worker)[1] for v in fitting))
            return wait("reset", "urgent, but it fits nowhere now: " + "; ".join(fit(v.worker)[1] for v in cand)
                        + " — it starts where room comes first")
        # 4) normal — always the most long-window headroom; wait for that worker's reset
        roomy = [v for v in cand if not v.long or size * v.long_scale <= 100 - v.long.used -
                 float((self.worker(v.worker) or {}).get("reserve_long_percent", win.DEFAULT_RESERVE_LONG))]
        target = self.pick(roomy, it.get("target", ""))
        if target is None:
            return wait("week", "the long window of every worker is too full for it — waits for a weekly reset")
        name = target.worker
        it["target"] = name
        first = held.get(name)
        if first and first != it["id"]:
            return wait("behind:" + name, f"normal → {name} (most weekly headroom); {first} waits for it first")
        ok, why = free(name)
        if not ok:
            held.setdefault(name, it["id"])
            return wait("busy:" + name, f"normal → {name} (most weekly headroom); {why}")
        ok, why = fit(name)
        if ok:
            return go(name, "new", f"normal → {name}: the most weekly headroom" + self._loads(cand) + "; fits now")
        held.setdefault(name, it["id"])
        return wait("reset:" + name, f"normal → {name}: the most weekly headroom{self._loads(cand)}; {why} — waits for that, "
                                     "not moved to another worker")

    @staticmethod
    def _loads(cand: List[win.View]) -> str:
        if len(cand) < 2:
            return ""
        parts = [f"{v.worker} {v.load:.0f} %" if v.load is not None else f"{v.worker} ?" for v in cand]
        return " (" + ", ".join(parts) + ")"

    # ------------------------------------------------------------------ starting
    def execute(self, it: Dict[str, Any], d: Dict[str, Any], st: Dict[str, Any], views: Dict[str, win.View]) -> Tuple[str, int]:
        at = self.clock()
        worker = self.worker(d["worker"])
        ad = self.adapter(worker)
        size = self.home.sizes()[it["size"]]
        before = views[d["worker"]].short.used if views.get(d["worker"]) and views[d["worker"]].short else None
        turn = {"at": iso(at), "at_ts": at, "size": size, "size_name": it["size"], "status": None, "before_short": before}
        if it.get("kind") == "continue" or d["mode"] == "move":
            turn["remaining"] = True        # the rest of a run cut off at a limit: its usage is not what a full task costs
        if d["mode"] in ("new", "move"):
            tid = it["id"] if d["mode"] == "new" else self._unique(f"{d['task']}-on-{d['worker']}", st)
            brief = continue_brief(st["tasks"][d["task"]], it.get("report", "")) if d["mode"] == "move" else it["brief"]
            task = {"id": tid, "worker": d["worker"], "agent": ad.name, "session": ad.new_session(), "title": it.get("title") or tid,
                    "size_name": it["size"], "urgent": bool(it.get("urgent")), "needs": it.get("needs", "any"),
                    "cwd": it.get("cwd") or str(Path.cwd()), "brief": brief[:20000], "turns": [],
                    **({"continues": d["task"]} if d["mode"] == "move" else {})}
            turn["n"] = 1
            turn["run"] = ad.start({**task, "n": 1})
            task["turns"].append(turn)
            st["tasks"][tid] = task
        else:                                                   # follow: the same task, its next run
            tid = d["task"]
            task = st["tasks"][tid]
            n = len(task["turns"]) + 1
            text = CONTINUE_TEXT if it.get("kind") == "continue" else it["brief"]
            turn["n"] = n
            if ad.can_resume and task.get("session"):
                turn["run"] = ad.resume(task["turns"][-1]["run"], text, {**task, "n": n})
            else:                                               # the agent cannot resume: a new run with the last report
                last = (task["turns"][-1] or {}).get("report_tail", "")
                task["session"] = ad.new_session()
                turn["run"] = ad.start({**task, "n": n, "brief": continue_brief(task, last, "" if it.get("kind") == "continue"
                                                                                   else it["brief"])})
                turn["new_session"] = True
            task["turns"].append(turn)
            if it.get("kind") != "continue":
                st["moved"][it["id"]] = tid
        return tid, turn["n"]

    @staticmethod
    def _unique(base: str, st: Dict[str, Any]) -> str:
        tid, k = base, 1
        while tid in st["tasks"]:
            k += 1
            tid = f"{base}-{k}"
        return tid

    # ------------------------------------------------------------------ tick
    @staticmethod
    def order(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Urgent first; then continuations after a limit, then related work, then new tasks; oldest first."""
        return sorted(items, key=lambda x: (not x.get("urgent"), 0 if x.get("kind") == "continue" else 1 if x.get("with") else 2,
                                            x.get("added", "")))

    def refresh_limits(self, st: Dict[str, Any], *, force: bool = False) -> None:
        """Ask workers whose agent reports limits, when the cached numbers are older than probe_minutes (default 10)."""
        cache = self.home.limits_cache()
        at = self.clock()
        for w in self.workers():
            if w.get("windows") != "reported":
                continue
            minutes = float(w.get("probe_minutes", 10))
            got = cache.get(w["name"]) or {}
            if minutes <= 0 or (not force and at - float(got.get("at") or 0) < minutes * 60):
                continue
            windows = self.adapter(w).limits()
            if windows:
                self.home.update_limits(w["name"], windows=windows, at=at)
            else:
                self.home.update_limits(w["name"], probe_failed=iso(at))

    def tick(self, *, dry: bool = False, out: Callable[[str], Any] = print) -> List[Dict[str, Any]]:
        self.home.path.mkdir(parents=True, exist_ok=True)
        acts: List[Dict[str, Any]] = []
        with open(self.home.path / "tick.lock", "a") as guard:
            try:
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                out("another tick is running — skipped")
                return acts
            with self.home.changing() as st:
                busy, running = self.scan(st)
                if st["items"] and not dry:
                    self.refresh_limits(st)
                views = self.views(st)
                held: Dict[str, str] = {}
                for it in self.order(list(st["items"])):
                    if it.get("kind") == "new" and not it.get("with") and not it.get("alone"):   # related to what started since?
                        rel, why = similar.find_related(it["brief"], self._related_candidates(st, running))
                        if rel and rel != it["id"]:
                            it["with"], it["linked"] = rel, f"hint: {why}"
                            if not dry:
                                acts.append(self.home.event("linked", it["id"], f"part of {rel} ({why}) — same session"))
                    d = self.decide(it, st, views, busy, running, held)
                    if d["act"] == "start" and (dry or it.get("dry")):     # shown, never started
                        out(f"{it['id']}: would start on {d['worker']} ({d['mode']}) — {d['why']}")
                        if dry:
                            busy[d["worker"]] = it["id"]                    # as if it had started: one at a time
                        else:
                            it["wait"], it["wait_why"] = "dry", f"dry run — would start on {d['worker']}: {d['why']}"
                        continue
                    if d["act"] == "wait":
                        if dry or it.get("dry"):
                            out(f"{it['id']}: waits — {d['why']}")
                        if not dry:
                            if it.get("wait") != d["key"]:                 # an event only when the reason changes
                                acts.append(self.home.event("waiting", it["id"], d["why"]))
                            it["wait"], it["wait_why"] = d["key"], d["why"]
                        continue
                    try:
                        tid, n = self.execute(it, d, st, views)
                    except (SystemExit, Exception) as exc:      # noqa: BLE001 — one failure does not stop the queue
                        msg = f"{type(exc).__name__}: {exc}"[:300]
                        if it.get("wait") != "error:" + msg:
                            acts.append(self.home.event("error", it["id"], f"could not start on {d['worker']}: {msg}"))
                        it["wait"], it["wait_why"] = "error:" + msg, msg
                        continue
                    st["items"] = [x for x in st["items"] if x["id"] != it["id"]]
                    busy[d["worker"]] = tid
                    running.add(tid)
                    kind = {"new": "started", "follow": "continued", "move": "moved"}[d["mode"]]
                    acts.append(self.home.event(kind, it["id"], d["why"], worker=d["worker"], into=tid, run=n))
        for a in acts:
            out(f"{a['event']} {a['task']}" + (f" → {a['worker']}" if a.get("worker") else "") + f": {a['why']}")
        return acts

    # ------------------------------------------------------------------ reading
    def listing(self) -> List[str]:
        st = self.home.state()
        rows = []
        for tid, task in st["tasks"].items():
            last = (task.get("turns") or [{}])[-1]
            if last.get("status") in (None, RUNNING):
                rows.append(f"running  {tid:28s} {task['worker']:10s} run {last.get('n')} since {last.get('at')}")
        for it in self.order(st["items"]):
            kind = "continue" if it.get("kind") == "continue" else ("urgent" if it.get("urgent") else "normal")
            rows.append(f"waiting  {it['id']:28s} {kind:8s} {it['size']:2s} {it.get('needs', 'any'):8s} "
                        + (f"(with {it['with']}) " if it.get("with") else "") + ("[dry run] " if it.get("dry") else "")
                        + (it.get("wait_why") or "not looked at by tick yet"))
        done = [(tid, t) for tid, t in st["tasks"].items() if (t.get("turns") or [{}])[-1].get("status") not in (None, RUNNING)]
        for tid, task in done[-5:]:
            last = task["turns"][-1]
            rows.append(f"finished {tid:28s} {task['worker']:10s} {last.get('status')} {last.get('finished')}"
                        + (f" — {last.get('why')}" if last.get("why") else ""))
        return rows or ["the queue is empty"]

    def show(self, ref: str) -> Dict[str, Any]:
        st = self.home.state()
        it = next((x for x in st["items"] if x["id"] == ref), None)
        if it:
            return {"state": "waiting", **{k: v for k, v in it.items() if k != "brief"}, "brief": it["brief"][:3000]}
        tid = st["moved"].get(ref, ref)
        task = st["tasks"].get(tid)
        if not task:
            return {"state": "unknown", "id": ref}
        last = task["turns"][-1]
        worker = self.worker(task["worker"])
        report = ""
        if worker is not None:
            with contextlib.suppress(Exception):
                report = self.adapter(worker).report(last["run"])
        return {"state": last.get("status") or RUNNING, "id": tid, "worker": task["worker"], "session": task.get("session"),
                "runs": [{k: t.get(k) for k in ("n", "at", "status", "exit", "finished", "why")} for t in task["turns"]],
                "report": report or last.get("report_tail", ""), **({"continues": task["continues"]} if task.get("continues") else {}),
                **({"part_of": tid} if ref != tid else {})}
