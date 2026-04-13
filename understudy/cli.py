"""`understudy` CLI."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from .capture import BrowserRecorder
from .config import get_settings
from .induction import induce_recipe, load_trajectory

app = typer.Typer(
    name="understudy",
    help="Record a workflow once. Replay it with variations you can edit like code.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
log = logging.getLogger(__name__)


@app.command()
def record(
    url: Annotated[str, typer.Option("--url", "-u", help="Start URL")],
    task: Annotated[str, typer.Option("--task", "-t", help="Short task name")],
    headed: Annotated[bool, typer.Option(help="Show the browser window")] = True,
) -> None:
    """Record a browser workflow. Close the window when done."""
    os.umask(0o077)
    get_settings()
    rec = BrowserRecorder(task_name=task, start_url=url, headed=headed)
    traj = asyncio.run(rec.run())
    console.print(f"[green]✓ recorded[/green] {len(traj.steps)} steps → {rec.trajectory_path}")
    console.print(f"  trajectory id: [cyan]{traj.id}[/cyan]")


@app.command()
def induce(
    trajectory_id_or_path: Annotated[str, typer.Argument(help="Trajectory id or .jsonl path")],
) -> None:
    """Run recipe induction on a recorded trajectory."""
    s = get_settings()
    path = _resolve_traj_path(s.trajectories_dir(), trajectory_id_or_path)
    traj = load_trajectory(path)
    recipe = induce_recipe(traj)
    console.print(f"[green]✓ recipe[/green] id={recipe.id} steps={len(recipe.steps)}")
    console.print(f"  description: {recipe.description}")
    if recipe.params:
        table = Table(title="Parameters")
        table.add_column("name")
        table.add_column("type")
        table.add_column("required")
        table.add_column("description")
        for p in recipe.params:
            table.add_row(p.name, p.type, str(p.required), p.description)
        console.print(table)


@app.command(name="list")
def list_cmd() -> None:
    """List recorded trajectories."""
    s = get_settings()
    rows = sorted(s.trajectories_dir().glob("*.jsonl"))
    if not rows:
        console.print("[yellow]no trajectories yet — run `understudy record`[/yellow]")
        return
    table = Table(title="Trajectories")
    table.add_column("id")
    table.add_column("steps")
    table.add_column("path")
    for p in rows:
        with p.open() as fh:
            steps = sum(1 for _ in fh)
        table.add_row(p.stem, str(steps), str(p))
    console.print(table)


@app.command()
def show(trajectory_id: str) -> None:
    """Print a trajectory's steps as JSON."""
    s = get_settings()
    path = _resolve_traj_path(s.trajectories_dir(), trajectory_id)
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        console.print_json(line)


@app.command()
def doctor() -> None:
    """Verify the install: deps, paths, API key reachable."""
    s = get_settings()
    ok = True

    def check(label: str, cond: bool, hint: str = "") -> None:
        nonlocal ok
        mark = "[green]✓[/green]" if cond else "[red]✗[/red]"
        suffix = f"  [dim]({hint})[/dim]" if hint and not cond else ""
        console.print(f"{mark} {label}{suffix}")
        if not cond:
            ok = False

    check("data dir exists", s.expanded_data_dir().is_dir(), str(s.expanded_data_dir()))
    check(
        "anthropic api key set",
        bool(s.anthropic_api_key.get_secret_value()),
        "set ANTHROPIC_API_KEY in .env",
    )
    try:
        import playwright  # noqa: F401

        check("playwright importable", True)
    except ImportError:
        check("playwright importable", False, "uv sync --all-extras")
    chromium_path = _find_chromium()
    check("chromium installed", chromium_path is not None, "uv run playwright install chromium")
    raise typer.Exit(0 if ok else 1)


@app.command()
def wipe(
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
) -> None:
    """Destroy all local data: trajectories, replays, the DB. Irreversible."""
    s = get_settings()
    target = s.expanded_data_dir()
    console.print(f"[red]about to delete[/red] {target}")
    if not yes and not Confirm.ask("Are you sure?", default=False):
        console.print("aborted")
        raise typer.Exit(1)
    if target.exists():
        shutil.rmtree(target)
    try:
        import keyring

        keyring.delete_password("understudy", "db_key")
    except Exception as e:
        log.debug("keychain entry not present or removable: %s", e)
    console.print("[green]✓ wiped[/green]")


def _find_chromium() -> Path | None:
    # Playwright stores browsers under a known cache dir.
    candidates: list[Path] = []
    home = Path.home()
    candidates.append(home / "Library/Caches/ms-playwright")
    candidates.append(home / ".cache/ms-playwright")
    env_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_root:
        candidates.append(Path(env_root))
    for root in candidates:
        if root.exists():
            for child in root.glob("chromium-*"):
                return child
    return None


def _resolve_traj_path(dir_: Path, ident: str) -> Path:
    p = Path(ident)
    if p.exists():
        return p
    p2 = dir_ / f"{ident}.jsonl"
    if p2.exists():
        return p2
    raise typer.BadParameter(f"trajectory not found: {ident}")


def main() -> None:
    sys.exit(app())


if __name__ == "__main__":
    main()
