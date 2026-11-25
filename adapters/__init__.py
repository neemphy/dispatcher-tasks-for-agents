"""Agent adapters. The scheduler finds one by the worker's ``"agent"`` name; adding an agent = one module here plus one line
in ``ADAPTERS`` (see CONTRIBUTING.md)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from adapters.base import Adapter
from adapters.claude import ClaudeAdapter
from adapters.codex import CodexAdapter
from adapters.gemini import GeminiAdapter
from adapters.opencode import OpenCodeAdapter

ADAPTERS = {"claude": ClaudeAdapter, "codex": CodexAdapter, "gemini": GeminiAdapter, "opencode": OpenCodeAdapter}


def get(worker: Dict[str, Any], runs: Path, spawn: Optional[Callable[[Path], None]] = None) -> Adapter:
    try:
        cls = ADAPTERS[worker.get("agent") or worker["name"]]
    except KeyError:
        raise SystemExit(f"worker {worker.get('name')!r}: no adapter for agent {worker.get('agent')!r} "
                         f"(known: {', '.join(sorted(ADAPTERS))}; see CONTRIBUTING.md)") from None
    return cls(worker, runs, spawn)
