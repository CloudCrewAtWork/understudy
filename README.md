<!-- Demo GIF goes here once Day 5 ships -->

<h1 align="center">Understudy</h1>

<p align="center">
  <em>An understudy watches the play once, then performs it &mdash; with their own interpretation.</em>
</p>

<p align="center">
  Records a workflow once. Replays it with variations you can edit like code.
</p>

<p align="center">
  <a href="https://github.com/CloudCrewAtWork/understudy/actions"><img alt="ci" src="https://img.shields.io/github/actions/workflow/status/CloudCrewAtWork/understudy/ci.yml?branch=main&label=ci"></a>
  <img alt="python" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <img alt="license" src="https://img.shields.io/badge/license-Apache--2.0-green">
  <img alt="status" src="https://img.shields.io/badge/status-alpha-orange">
</p>

> **Status: v0.1 day-1 scaffold.** Browser capture and recipe induction work end-to-end. Replay engine and the editable memory-graph UI ship over the next two weeks &mdash; see [Status](#status).

---

## What it is

Understudy is a glass-box workflow agent. You demonstrate a workflow once. Understudy:

1. **Captures** every meaningful click, type, and navigation, anchored to stable ARIA references (not brittle CSS selectors).
2. **Induces** a parameterized natural-language *recipe* using Claude &mdash; identifying which parts of your demo are user-supplied parameters vs. structural constants.
3. **Replays** *(planned, week 1 day 3)* the recipe with new inputs by re-grounding each step against the current page state. No literal coordinate replay; the agent plans against intent.
4. Stores recipes in an **editable memory graph** *(planned, week 1 day 5)* &mdash; you can edit a step in plain English and re-run.

The thesis: post-Devin, the bottleneck for agent adoption is *trust*, not *capability*. Legibility beats autonomy. Understudy is a workflow agent you can read, edit, and audit at every step.

## How it differs from the alternatives

| | Cursor / Copilot | Devin / OpenInterpreter | Browser-use | **Understudy** |
|---|---|---|---|---|
| Surface | code editor | sandbox | headless browser | your real browser / Mac |
| Authoring | text prompts | text prompts | text prompts | demonstration |
| State | invisible | invisible | invisible | **inspectable graph** |
| Edit point | rerun prompt | rerun prompt | rerun prompt | **edit a single step in English** |
| Replay grounding | n/a | LLM each time | LLM each time | re-plan per step against ARIA anchor |

## Architecture

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   Capture        │ ─▶ │   Induction      │ ─▶ │   Replay         │
│ Playwright       │    │ Claude Sonnet 4.5│    │ re-ground &      │
│ + ARIA snapshot  │    │ → Recipe (JSON)  │    │ re-plan per step │
└──────────────────┘    └──────────────────┘    └──────────────────┘
        │                       │                       │
        └──────────┬────────────┴───────────────────────┘
                   ▼
             ┌──────────────────────────────────────┐
             │  Memory Graph  (editable JSON)       │
             │  SQLite (+ SQLCipher when installed) │
             └──────────────────────────────────────┘
```

## Status

| Component | State |
|---|---|
| Browser capture (Playwright) | ✅ v0.1 |
| Recipe induction (Claude) | ✅ v0.1 |
| Regex redaction + URL allowlist | ✅ v0.1 |
| HITL gate (CLI) | ✅ v0.1 (used in replay) |
| Encrypted local DB (SQLCipher) | ✅ when `brew install sqlcipher && uv sync --extra crypto`; otherwise plaintext SQLite (with a loud warning) |
| Replay engine | 🚧 week 1 day 3 |
| Memory-graph UI (React Flow) | 🚧 week 1 day 5 |
| Eval harness | ⚡ skeleton present, runner pending replay |
| macOS native capture | 🚧 week 2 |
| Prompt-injection classifier | 🚧 week 1 day 4 (delimiter isolation is in today) |

## Quickstart

```bash
git clone https://github.com/CloudCrewAtWork/understudy
cd understudy
just install                                 # uv sync + playwright chromium
cp .env.example .env                         # add ANTHROPIC_API_KEY
just record url=https://duckduckgo.com task=ddg_search
# do the workflow in the browser, then close the window
just induce trajectory=<id-from-output>
```

Verify your install:

```bash
uv run understudy doctor
```

## Threat model & limitations

> **Threat model version:** v0.1, last reviewed 2026-04-13.

Understudy is accessibility software with the same blast radius as a remote-control utility. Treat it accordingly.

### Assets at risk

Screen content, ARIA trees, OCR'd text, prompts sent to Claude, the local memory-graph DB.

### Trust boundaries

Local process ↔ Anthropic API ↔ disk ↔ user.

### Adversaries considered

| Adversary | Mitigation in v0.1 |
|---|---|
| Malicious page content (prompt injection) | Trajectory text wrapped in `<trajectory_untrusted>` XML tag inside the induction prompt; system prompt explicitly forbids treating its contents as instructions. A classifier-based defence (`protectai/deberta-v3-prompt-injection`) is planned for week 1 day 4. |
| Page JavaScript forging trajectory events | Page→host binding is gated by a per-session 256-bit nonce held in a closure of the init script; without the nonce, calls to the binding are dropped. |
| Shoulder-surfer / screen recorder | Capture suppresses values from `input[type=password]`, `autocomplete=current-password|new-password|one-time-code|cc-number|cc-csc|cc-exp`, and any element with `data-sensitive`. Re-checked at flush time so "show password" toggles do not leak buffered keystrokes. |
| Stolen laptop | DB encrypted with SQLCipher when installed; key in macOS Keychain. Without the SQLCipher driver Understudy refuses to start with a configured key (no silent fallback). |
| Compromised dependency | `pip-audit`, `bandit`, `OSV-Scanner`, Dependabot in CI; deps pinned in `uv.lock`. |
| API-side logging | No screen frames or trajectories sent to anything other than the configured Anthropic endpoint. |
| Accidental capture of secrets | Default deny-list of password managers, banks, OAuth providers, payment processors, and cloud consoles. URL parser hardened against userinfo, IDNA, and IP-literal bypasses. Regex redaction on every captured value. |

### Explicit non-goals / residual risk in v0.1

- **Screenshots, when enabled (`UNDERSTUDY_SCREENSHOTS=1`), are written unencrypted to disk.** Default is OFF. We intend to either store them as encrypted BLOBs inside the SQLCipher DB or skip them entirely; until then, leaving screenshots on is a known gap.
- Cannot defend against kernel-level malware or the root user.
- Cannot defend against an Anthropic-side breach (the model provider sees redacted prompts).
- Regex redaction is best-effort; false-negatives on novel credential formats are possible. We accept over-redaction.
- macOS `rm` is not secure on APFS. Use `understudy wipe` which removes the whole data dir and rotates the Keychain entry.
- Replay-time HITL and credential handling are not yet exercised because the replay engine ships day 3.

### Data lifecycle

Capture → redact → encrypt at rest (when SQLCipher available) → 7-day TTL (configurable) → secure delete via `understudy wipe`.

### Telemetry

None. The CLI does not phone home.

### Kill switch

```bash
understudy wipe --yes
```

Removes the data directory and the Keychain entry. Irreversible.

## Eval

```bash
just eval
```

Eval harness compares replay outcomes against `evals/cases/*.yaml`. The README results table will land once the replay engine ships:

| Workflow | Variant | Pass | Steps | Cost |
|---|---|---|---|---|

## Development

```bash
just install        # deps
just lint           # ruff
just types          # basedpyright
just test           # pytest
just audit          # pip-audit + bandit
just ci             # all of the above
```

## License

Apache-2.0 &copy; Sai Anurag. The patent grant matters because Understudy reaches into OS APIs.
