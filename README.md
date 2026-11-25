# dispatcher-tasks-for-agents

**A small task queue for AI coding agents.** You tell your agent *what* needs doing; the dispatcher decides *when*
and *where* it runs — so long tasks don't die halfway through a usage window, nothing gets forgotten, and you stop
babysitting sessions.

Works with Claude Code, Codex CLI and Gemini CLI. Plain Python 3.9+, no dependencies, runs on your own machine.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/hero-dark.svg">
  <img alt="A person asks for a task; a small dispatcher robot keeps a queue of task cards with sizes and an urgent tag; one agent desk is working, one waits for its reset, one is free" src="docs/img/hero-light.svg">
</picture>

> Status: in development. Claude Code support is complete; Codex CLI and Gemini CLI adapters follow their official
> docs and are marked below as verified or not.

---

## Why

If you work with coding agents every day, you know these:

| Without a dispatcher | With it |
|---|---|
| A big task starts at 80 % of your usage window and gets cut off halfway — context and prompt cache are lost. | The task waits for the window to reset, then runs start to finish. |
| You queue three things at once, they compete, and none finishes. | One task at a time per agent. The next starts when the previous one is done. |
| "I'll do that later" — and later never comes. | Later is a queue entry. It runs on its own after the reset. |
| A follow-up starts a fresh session that has to re-read everything. | Related work continues **in the same session**, with its context. |
| One plan is drained by Tuesday while another sits idle. | Non-urgent work goes to the agent with the most weekly headroom. |
| You check every few minutes whether a run finished. | Each step writes an event; your agent reads the report and tells you. |

---

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/how-it-works-dark.svg">
  <img alt="Five steps: you say what to do, your agent writes a brief with size and urgency, the queue waits for the right moment, one agent runs it, you get the checked result" src="docs/img/how-it-works-light.svg">
</picture>

1. **You talk to your agent as usual.** When something should run later, in the background, or is too big for what
   is left of your window, the agent puts it in the queue: a short brief, a size (S/M/L/XL) and whether it is urgent.
2. **`tick` runs every few minutes** (launchd, systemd or cron). It looks at the queue and at each agent's limits.
3. **A task starts only when it fits** — and only if that agent isn't already busy with another queued task.
4. **When it finishes**, the run's report and an event land where your agent can read them. Your agent checks the
   result and tells you, errors first.

### Where does a task go?

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/placement-dark.svg">
  <img alt="Where a task goes: related work continues in the same session; urgent runs now; not sure means the agent asks you; normal work goes to the agent with the most weekly headroom and runs now if it fits, otherwise waits for that window to reset" src="docs/img/placement-light.svg">
</picture>

*Related* means it is part of work that is already running or queued.

- **Urgency is never guessed.** Broken-right-now is urgent; features, research and cleanup are not. If it's unclear,
  your agent asks you.
- **Non-urgent work always goes where the week is least used** — even if another agent happens to have room right
  now. Nobody gets drained first.
- **Waiting is a feature.** Over a week you use your plan anyway; a task that waits for a reset finishes in one piece
  instead of being cut off.

### One task at a time

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/one-at-a-time-dark.svg">
  <img alt="Three tasks stacked at once all hit the limit and are cut off; run one at a time with a wait for the reset, all three finish" src="docs/img/one-at-a-time-light.svg">
</picture>

Three tasks started together burn the window three times as fast and all stop mid-way. Run one after another and wait
for the reset when needed, and every one of them completes.

### Related work stays in one session

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/same-session-dark.svg">
  <img alt="Related work queued with --with continues in session 1 with context kept; without it a second session starts from zero and re-reads everything" src="docs/img/same-session-light.svg">
</picture>

---

## Examples

What you say to your agent — and what happens:

**"Refactor the payment module, not urgent."**
→ The agent sizes it L, queues it as normal. Your window is at 85 %, so it waits; at 14:00 the window resets and the
refactor runs in one go. You get the report when you're back.

**"The login page is down — fix it now."**
→ Urgent. It starts immediately on whichever agent has room.

**"Write tests for the parser, and after that update the docs for it."**
→ Two tasks; the docs one is queued `--with` the tests one, so it continues in the same session — the agent already
knows the parser.

**"Clean up old branches."**
→ The agent isn't sure how urgent that is and asks you: *"Urgent or can it wait for the next reset?"*

**You have Claude Code and Codex CLI.**
→ Non-urgent tasks go to whichever has used less of its week; urgent ones go wherever there is room now. Each agent
uses its own sign-in — the dispatcher only starts the CLI.

---

## Install

### The easy way — ask your agent

> Install dispatcher-tasks-for-agents from https://github.com/neemphy/dispatcher-tasks-for-agents following its
> `INSTALL_FOR_AGENTS.md`.

Your agent checks the prerequisites, clones the repo, runs the tests, asks which agents to use, adds the rules to its
memory (a Claude Code skill, or a block in `AGENTS.md` / `GEMINI.md`), does a dry run and — only if you say yes —
turns on the background tick. Every decision is yours; nothing runs in the background without your OK.

### By hand

```bash
git clone https://github.com/neemphy/dispatcher-tasks-for-agents.git
cd dispatcher-tasks-for-agents
python3 -m unittest discover -s tests
python3 dispatcher.py init
```

Then follow steps 2–6 of [`INSTALL_FOR_AGENTS.md`](INSTALL_FOR_AGENTS.md).

## Commands

What it looks like in a terminal:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/demo-dark.svg">
  <img alt="Terminal demo: a person asks an agent to refactor the payment module; the agent queues it with queue add, queue list shows it waiting for the window reset at 14:00, tick starts it, and queue show reports done with 0 errors and tests passed" src="docs/img/demo-light.svg">
</picture>

```bash
python3 dispatcher.py queue add <id> --brief-file brief.md --size M --normal   # or --urgent
python3 dispatcher.py queue add <id2> --brief-file next.md --size S --normal --with <id>   # related work
python3 dispatcher.py queue list        # what runs, what waits and why
python3 dispatcher.py queue show <id>   # status and last report
python3 dispatcher.py limits            # what each agent has left (when the agent reports it)
python3 dispatcher.py tick --dry-run    # what the next step would do
```

`--brief "text"` works instead of `--brief-file`; `--needs <worker>` pins a task to one agent; `--cwd` is the folder the
agent works in (default: where you run the command); `--dry-run` records a test entry that `tick` only describes.

Sizes are rough shares of a usage window: **S** ≈ 3 %, **M** ≈ 10 %, **L** ≈ 25 %, **XL** ≈ 50 %. When the agent
reports its usage (Claude Code does), the dispatcher learns real sizes from finished tasks.

## Configuration

`python3 dispatcher.py init` writes `config.json` in the dispatcher home (`~/.config/dispatcher-tasks`, or
`$DISPATCHER_HOME`) with one worker per agent CLI found on your machine. It holds no secrets:

```json
{"workers": [
  {"name": "claude", "agent": "claude", "enabled": true, "auth": "subscription", "windows": "reported", "probe_minutes": 10},
  {"name": "codex", "agent": "codex", "enabled": true, "auth": "api", "args": ["--sandbox", "workspace-write"],
   "windows": [{"name": "short", "hours": 5}, {"name": "week", "hours": 168}]},
  {"name": "gemini", "agent": "gemini", "enabled": false}
]}
```

- `auth`: `subscription` — the agent's own sign-in (API-key variables are removed from the run's environment, so a stray
  key does not bill an API account); `api` — an API key you set in your own environment; the agent reads it, the
  dispatcher never does. For unattended work, API keys are the recommended path; `"budget_usd": {"amount": 5,
  "hours": 24}` then limits spending (for agents that report cost).
- `windows`: `"reported"` — the agent says how much is used; a list of windows (`hours`) — counted from the dispatcher's
  own runs; left out — unknown: one task at a time, and a pause after a limit is hit (`pause_after_limit_minutes`).
- `model`, `args` — added to the agent's command. Approvals and sandbox for unattended runs are your choice and go into
  `args`; the dispatcher does not loosen them for you.
- One worker per agent — the dispatcher schedules your work, it does not spread it over several accounts.

## Limits: what is read and what it costs

- **Claude Code** prints its usage windows (`rate_limit_event`) in its normal JSON output; every finished run updates
  them at no extra cost. When a task is waiting and the numbers are older than `probe_minutes` (default 10), the
  dispatcher makes one *probe*: an ordinary `claude -p` request to Haiku with no tools and no saved session, answering
  one word — it counts against your plan like any tiny request. `"probe_minutes": 0` turns the probe off.
- **Codex CLI and Gemini CLI** do not report usage in their output, so there is no probe: you describe your plan's
  windows in the config, or leave them unknown.
- After any run stops at a usage limit, that worker pauses until the reset the agent named (or for
  `pause_after_limit_minutes`), and the task continues after it.

## Supported agents

| Agent | Start | Continue same session | Limits | Verified live |
|---|---|---|---|---|
| Claude Code | ✅ | ✅ `--resume` | ✅ read from the CLI's output | ✅ start, resume, limits |
| Codex CLI | ✅ `codex exec --json` | ✅ `codex exec resume` (per its docs) | configured by you | not yet — built from its docs |
| Gemini CLI | ✅ `gemini --output-format json` | a new run with the last report¹ | configured by you | not yet — built from its docs |
| OpenCode | ✅ `opencode run` | a new run with the last report² | configured by you | not yet — built from its docs |
| Other agents | — | — | — | [contributions welcome](CONTRIBUTING.md) |

¹ Gemini CLI has `--resume`, but its documented JSON output does not include the session id, so the adapter does not
guess it. A contribution that reads it is welcome.

² OpenCode documents `opencode run --session <id>` and `--format json`, but its official docs do not specify the JSON
event schema for extracting the session id, so `can_resume` stays `False`. A contribution that reads it is welcome.

### Other agents — contributions welcome

The scheduler knows no agent; each agent is one small adapter in `adapters/`: start, continue, status, report, and
(optionally) limits. Copy `adapters/_template.py` and see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## What it does not do

- It does **not** bypass usage limits. It waits for them.
- It does **not** switch, pool or share accounts.
- It does **not** read, store or pass on passwords, tokens or API keys. Each worker is an agent CLI you are already
  signed in to, or an API key you set in your own environment.
- It does **not** modify any agent's binary.

## Terms

This is a scheduler for **one person's own work** on their own machine. You are responsible for complying with the
terms of each agent you configure. For unattended runs, providers generally
recommend API keys over consumer subscriptions. Read, for example, Anthropic's
[Consumer Terms](https://www.anthropic.com/legal/consumer-terms), [Usage Policy](https://www.anthropic.com/legal/aup)
and [Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance), and the equivalent pages
for any other agent you configure.

This project is not affiliated with or endorsed by Anthropic, OpenAI or Google. "Claude Code", "Codex" and "Gemini"
are used only to describe compatibility.

## License

MIT — see [LICENSE](LICENSE).
