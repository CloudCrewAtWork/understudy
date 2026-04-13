# Security

## Reporting a vulnerability

Open a private GitHub Security Advisory on this repo. Please do not file public issues for security problems. We aim to acknowledge within 72 hours.

## Threat model summary

See the **Threat Model & Limitations** section of the README for the full model. In brief: Understudy reads your screen and replays UI actions. Treat it like a piece of accessibility software with the same blast radius as a remote-control utility.

## Supply chain

- Dependencies pinned via `uv.lock` (committed alongside `pyproject.toml`).
- `pip-audit`, `bandit`, and `OSV-Scanner` run in CI on every PR.
- Dependabot configured in `.github/dependabot.yml`.
- Pre-commit `gitleaks` hook blocks committed secrets.
- GitHub Actions are pinned to commit SHAs.

## What we will not do

- Send screen frames, trajectories, or recipes to any service other than the configured Anthropic endpoint.
- Persist credentials. Replay (when implemented, week 1 day 3) will pause at login and ask the user to authenticate manually.
- Execute new binaries discovered at runtime.
- Silently fall back to plaintext storage when an encryption key is configured but the SQLCipher driver is unavailable.
