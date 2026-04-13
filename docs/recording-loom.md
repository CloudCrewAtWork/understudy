# Recording the Understudy Loom

This is the runbook for producing the 60-second launch video. Shoot once; edit zero.

## Setup (once)

1. Install the dev branch and Chromium:
   ```bash
   git clone https://github.com/CloudCrewAtWork/understudy
   cd understudy
   just install
   cp .env.example .env   # put your ANTHROPIC_API_KEY here
   ```
2. Open **Kap** (`brew install --cask kap`) and set:
   - Frame rate: 30 fps
   - Resolution: 1280 × 800 (match Understudy's default viewport)
   - Export: MP4 first (lossless), then GIF via `gifski` if the README GIF needs to stay < 5MB
3. Create a **fresh macOS user account** ("demo") OR a clean Chrome profile. You do NOT want real bookmarks, autofill, or extensions in the shot.
4. Use a **72-pt font** in iTerm2 (or whichever terminal). The CLI log text must be legible at phone-screen scale.
5. Pre-stage two terminal tabs:
   - **Tab A**: `~/projects/understudy` ready with `cp .env.example .env` already done and key filled in.
   - **Tab B**: Chromium window, already at 1280 × 800.

## Storyboard (60 seconds)

| t | scene | action | narration / on-screen text |
|---|---|---|---|
| 0–4s | title card | static PNG: "Understudy — record once, replay with variations" | — |
| 4–14s | **record** | Tab A: `just record url=https://duckduckgo.com task=ddg_search`; in the opened Chromium, click the search box, type `claude agents`, press Enter, close the window | caption: "demonstrate once" |
| 14–20s | **induce** | Tab A: `just induce trajectory=<id>` → recipe JSON prints with params | caption: "Claude induces a recipe" |
| 20–28s | **recipes show** | Tab A: `understudy recipes show <id>` renders the step list with parameter pills | caption: "steps you can read" |
| 28–52s | **replay** | Tab A: `understudy replay <id> --param query="anthropic mcp"` — the Chromium window in Tab B executes each step visibly; intent ticker on left, aria-target on right | caption: "different input, same workflow" |
| 52–58s | post-run | rich summary panel: OK  ddg_search  6/6 steps  $0.000 | — |
| 58–60s | CTA card | "built solo — looking for AI-agent roles in SF — dodsaianu@gmail.com" | — |

## Post-production

1. Export Kap MP4 at 1080p.
2. Trim dead air at head/tail in **QuickTime** (free) — target exactly 60s.
3. Upload the MP4 unlisted to **YouTube** — that becomes the canonical link.
4. Generate a GIF for the README:
   ```bash
   ffmpeg -i demo.mp4 -vf "fps=15,scale=960:-2:flags=lanczos,palettegen" palette.png
   ffmpeg -i demo.mp4 -i palette.png -lavfi "fps=15,scale=960:-2:flags=lanczos [x]; [x][1:v] paletteuse" \
     -y docs/assets/replay-demo.gif
   # or use gifski for better quality:
   # gifski --fps 15 --width 960 -o docs/assets/replay-demo.gif demo.mp4
   ```
5. Commit the GIF, update the `<img>` src at the top of the README.

## Don'ts

- Don't record with real Google/Gmail/bank domains visible in tabs — the deny-list allowlist will abort, and it looks bad even if it didn't.
- Don't pause in the middle. Re-shoot. Pauses are obvious; perfect take exists.
- Don't over-narrate. The caption track does the work.
- Don't show `$ANTHROPIC_API_KEY` in any frame. Double-check Kap's recording area excludes `.env`.
- Don't use a dark-theme terminal with a light-theme browser or vice-versa — pick one and commit.

## Before you post

- [ ] 60s ± 2s runtime
- [ ] Under 5 MB GIF, or link to YouTube MP4
- [ ] README GIF loads above the fold on a 13" laptop
- [ ] `.env` never on screen
- [ ] Real success terminal output (no edits)
