# Hero Demo: GitHub Repo Triage

A sharp, recordable end-to-end demonstration of what Understudy does. Produces
the 60–90s screencast that goes at the top of the README / HN post.

## The workflow

**Pain:** "I'm evaluating 20 GitHub repos before picking a dependency — who has
momentum, who's abandoned, who has a real release cadence?"

**Workflow (6 steps, ~15s per repo):**

1. Navigate to `https://github.com/{repo}`.
2. Read the repo description.
3. Read the star count.
4. Read the primary language.
5. Click **Releases** → read the latest tag + publish date.
6. Back → click the **Issues** tab → read the open-issue count from the
   tab badge (not issue bodies — we don't touch user-generated content,
   which keeps the prompt-injection surface near zero).
7. Back → click **Pull requests** → read the open-PR count.

**Input:** a CSV of repos.
**Output:** a rectangular CSV with one row per repo and columns
`repo, description, stars, language, latest_release, release_date, open_issues, open_prs`.

## The hero moment (the thing that sells the thesis)

Record step 5 deliberately wrong: "read the version number from the sidebar."
That works on repos with a "Releases" card in the right rail. On a repo with no
releases, the card is missing, and replay fails on that step.

In the UI, click the failing step card. The Editor opens. Rewrite the intent in
plain English:

> *"Read the latest release tag, or "none" if the repo has no releases."*

Hit **resynth**. The cinder shimmer flashes (the new Commit E polish). ~1s
later the acid-lime diff appears: `aria_name` regenerated, `success_check`
updated to include the null branch. Accept. Re-run the batch. Row that was
previously empty is now populated with `"none"`.

**That's the whole pitch: an agent whose plan you can read and rewrite in
English when it's wrong.**

## One-time setup

You need to record the real trajectory once — the shipped
`evals/fixtures/repo_triage_recipe.json` is hand-seeded for CI tests against
local HTML fixtures and uses a `{url}` param. For the video, you want a recipe
induced from a real recording on `github.com` that takes `repo` (e.g.
`anthropics/claude-code`) as its param:

```bash
# One repo that HAS a Releases card — click through all 7 steps.
uv run understudy record \
  --url https://github.com/anthropics/claude-code \
  --task repo_triage_live

# (close the browser when you finish the workflow)
uv run understudy induce <trajectory-id>
```

After induction, check the recipe in the UI (`understudy ui`), clean up any
step where Claude's intent drifted, and save.

## The batch

Create `repos.csv`:

```csv
repo
anthropics/claude-code
openai/openai-python
langchain-ai/langchain
microsoft/vscode
rust-lang/rust
```

Run:

```bash
uv run understudy replay <recipe-id> --csv repos.csv
```

That writes `repos-results-<hex>.csv` in the same directory.

## 60-second shot list

For the screencast (Cmd+Shift+5 on macOS, record a selected portion):

| Time | On screen | Caption |
|---|---|---|
| 0–10s | Full UI, slow zoom onto the DAG of step cards. Params pill pulses once. | *"Demonstrate once. Understudy records it."* |
| 10–20s | Click the "read latest release" card. Editor slides in. Zoom to 125% on Intent textarea. | *"Read the recipe. Edit it in English."* |
| 20–30s | Retype the intent to include the "or 'none' if no releases" clause. | — |
| 30–40s | Hit **resynth**. Hold on the lime diff flash — slow from 200ms to 1.2s for the GIF. Zoom on the ARIA-name and success-check lines. | *"Claude re-synthesises. You approve."* |
| 40–50s | Accept. Crossfade bottom third to terminal. `uv run understudy replay <id> --csv repos.csv`. Node pulses down the DAG as each step runs. | *"Run the batch."* |
| 50–60s | Pan to `repos-results.csv` opening in the editor. Cursor highlights the previously-broken row now reading `none`. Freeze-frame, logo. | *"Five repos triaged in 87 seconds. Every step auditable."* |

## Why this workflow specifically

All the candidates the v0.3 panel considered (arXiv triage, HN digest,
Stack Overflow harvester, DDG company pager) ranked. GitHub won on:

- **Visual storytelling** — a CSV row filling with numbers reads instantly on
  video. Text-heavy search results do not.
- **Real pain** — every recruiter reviewing an AI-agents candidate works at a
  company that ships on GitHub. They recognize "vet repos before depending on
  them" in 5 seconds.
- **Prompt-injection surface** — by scoping extraction to the server-rendered
  metadata only (stars, language, license, release tags, tab badge counts)
  and avoiding READMEs / issue bodies / gists, attacker-controlled text
  never enters a Claude prompt.
- **DOM stability** — the fields we extract use `itemprop` / role="status"
  anchors that GitHub has held stable across redesigns.

The wrong-on-purpose "read the version number from the sidebar" step is what
makes the demo legible as a *thesis*, not just a scraping tool.
