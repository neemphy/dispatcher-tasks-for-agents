# Changelog

## v0.1.1 — 2026-11-26

### New
- **OpenCode adapter** (`adapters/opencode.py`): start a task with `opencode run`; related work continues in a new run
  with the last report, until OpenCode documents where its JSON output gives the session id. Thanks to
  @Rewaskc02-lang, our first contributor (#6).
- **Animated terminal demo** in the README's Commands section.

### Better
- **Task sizes learn more honestly.** The rest of a run that was cut off at a usage limit no longer teaches the table
  that a task is small, and learned sizes always stay in order (S ≤ M ≤ L ≤ XL). Found while running the dispatcher
  every day: a follow-up that was planned as "fits" filled a window to 99 %. See "Sizes" in the README.

## v0.1.0 — 2026-11-25

First public release: queue with urgency and sizes, runs after a usage window resets, one task at a time per agent,
related work in the same session, Claude Code / Codex CLI / Gemini CLI adapters.
