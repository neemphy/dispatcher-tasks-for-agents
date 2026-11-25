"""OpenCode CLI (`opencode`) — start; "continue" is a new run with the last report. NOT VERIFIED LIVE: built from the
official docs (OpenCode CLI Intro and CLI Commands: https://opencode.ai/docs/cli and
https://opencode.ai/docs/cli/commands); please report what you see on a real run.

* start: ``opencode run [--model MODEL] [args…] <prompt>`` — sends a message and prints the reply without opening the
  interactive interface (the docs show the prompt as a positional argument, not stdin)
* report: stdout text; on a non-zero exit code, stderr (or stdout) is checked for usage/rate-limit keywords (the exact
  wording is not documented)
* resume: the CLI documents ``opencode run --session <id>`` and ``--format json`` (newline-delimited JSON), but the
  official docs do not document the JSON event schema or which field exposes the session id from ``run`` output, and
  ``--continue`` only targets the last session globally; so ``can_resume = False`` and the dispatcher continues with a
  new run carrying the original brief and the last report
* limits: not reported by the CLI — configure the worker's windows yourself, or leave them unknown.

Approvals, permissions, and isolation for unattended runs are yours to choose — put the flags in the worker's
``args`` (for example ``["--auto"]`` or ``["--standalone"]``). Sign-in: your own (``opencode auth login``, or provider
API keys in your environment with ``"auth": "api"``).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from adapters.base import DONE, ERROR, LIMIT, LIMIT_WORDS, Outcome, ProcessAdapter


class OpenCodeAdapter(ProcessAdapter):
    name = "opencode"
    binary = "opencode"
    can_resume = False
    KEY_VARS = (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
    )

    def command(self, task: Dict[str, Any], *, resume: bool, text: str) -> Tuple[List[str], Optional[str]]:
        argv = self.bin() + ["run"]
        if self.worker.get("model"):
            argv += ["--model", str(self.worker["model"])]
        argv += self.extra()
        return argv + [text], None

    def parse(self, out: str, err: str, code: int) -> Outcome:
        o = Outcome(DONE, code, out.strip())
        if code != 0:
            problem = err.strip() or out.strip()
            o.status = LIMIT if LIMIT_WORDS.search(problem) else ERROR
            o.why = (problem.splitlines()[-1:] or [f"exit code {code}"])[0][:300]
        return o
