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
from .db import session
from .induction import induce_recipe, load_trajectory
from .replay import Replayer, load_recipe
from .replay.params import ParamError, validate_params
from .replay.ui import build_confirm_fn, render_summary, run_with_live_ui

app = typer.Typer(
    name="understudy",
    help="Record a workflow once. Replay it with variations you can edit like code.",
    no_args_is_help=True,
    add_completion=False,
)
recipes_app = typer.Typer(help="Inspect and edit recipes.", no_args_is_help=True)
app.add_typer(recipes_app, name="recipes")

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


@app.command()
def replay(
    recipe_id: Annotated[str, typer.Argument(help="Recipe id (see `understudy recipes list`)")],
    param: Annotated[
        list[str] | None,
        typer.Option("--param", "-p", help="key=value, repeatable"),
    ] = None,
    headed: Annotated[bool, typer.Option("--headed/--headless")] = True,
    slow_mo: Annotated[int, typer.Option("--slow-mo", min=0, max=2000)] = 250,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Ground only, no actions")] = False,
) -> None:
    """Replay a recipe with new parameter values."""
    os.umask(0o077)
    get_settings()
    try:
        recipe = load_recipe(recipe_id)
    except FileNotFoundError:
        console.print(f"[red]recipe not found:[/red] {recipe_id}")
        raise typer.Exit(2) from None

    raw_params = _parse_params(param or [])
    try:
        params = validate_params(recipe, raw_params)
    except ParamError as e:
        console.print(f"[red]param error:[/red] {e}")
        raise typer.Exit(2) from None

    replayer = Replayer(
        recipe,
        params,
        headed=headed,
        slow_mo_ms=slow_mo,
        confirm=build_confirm_fn(console),
        dry_run=dry_run,
    )
    run_with_live_ui(console, replayer, recipe.steps)
    render_summary(console, replayer.result)
    if replayer.result.status in {"error", "aborted"}:
        raise typer.Exit(1)


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


@recipes_app.command("list")
def recipes_list(
    task: Annotated[str | None, typer.Option("--task", help="Filter by task_name")] = None,
) -> None:
    """List recipes in the DB."""
    with session() as conn:
        if task:
            rows = conn.execute(
                "SELECT id, task_name, created_at FROM recipes "
                "WHERE task_name = ? ORDER BY created_at DESC",
                (task,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, task_name, created_at FROM recipes ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
    if not rows:
        console.print("[yellow]no recipes yet — run `understudy induce`[/yellow]")
        return
    table = Table(title="Recipes")
    table.add_column("id")
    table.add_column("task")
    table.add_column("created")
    for row in rows:
        table.add_row(row[0], row[1], row[2])
    console.print(table)


@recipes_app.command("show")
def recipes_show(
    recipe_id: str,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show the full recipe JSON."""
    recipe = load_recipe(recipe_id)
    if as_json:
        console.print_json(recipe.model_dump_json())
        return
    console.print(f"[bold]{recipe.task_name}[/bold]  [dim]{recipe.id}[/dim]")
    console.print(f"  description: {recipe.description}")
    for p in recipe.params:
        console.print(
            f"  [cyan]param[/cyan] {p.name}: {p.type} "
            f"{'(required)' if p.required else '(optional)'} — {p.description}"
        )
    for step in recipe.steps:
        mark = "⚠" if step.requires_confirmation else " "
        console.print(f"  {mark} {step.idx:>2}  {step.action.value:<8} {step.intent}")


@recipes_app.command("edit")
def recipes_edit(
    recipe_id: str,
    editor: Annotated[str | None, typer.Option("--editor", help="$EDITOR override")] = None,
) -> None:
    """Open the recipe JSON in $EDITOR, validate on save."""
    import subprocess
    import tempfile

    os.umask(0o077)
    recipe = load_recipe(recipe_id)
    with tempfile.NamedTemporaryFile(
        suffix=".json", mode="w", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(recipe.model_dump_json(indent=2))
        path = Path(tf.name)

    ed_raw = editor or os.environ.get("EDITOR", "vi")
    ed_bin = shutil.which(ed_raw)
    if ed_bin is None:
        console.print(f"[red]editor not found on PATH:[/red] {ed_raw}")
        raise typer.Exit(1)
    try:
        subprocess.run([ed_bin, str(path)], check=True)  # noqa: S603
    except subprocess.CalledProcessError as e:
        console.print(f"[red]editor exited with {e.returncode}[/red]")
        raise typer.Exit(1) from e

    from .types import Recipe

    try:
        updated = Recipe.model_validate_json(path.read_text())
    except Exception as e:
        console.print(f"[red]invalid recipe JSON:[/red] {e}")
        raise typer.Exit(1) from e

    if updated.id != recipe.id:
        console.print("[red]refusing to change recipe id[/red]")
        raise typer.Exit(1)

    # Edited recipes must still pass safety invariants. Without this, a user
    # could edit a recipe to add a nav to a denied domain and have it run.
    from .replay import RecipeInvariantError, validate_recipe_invariants

    try:
        validate_recipe_invariants(updated)
    except RecipeInvariantError as e:
        console.print(f"[red]edited recipe violates invariants:[/red] {e}")
        raise typer.Exit(1) from e

    with session() as conn:
        conn.execute(
            "UPDATE recipes SET recipe_json = ?, edited_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE id = ?",
            (updated.model_dump_json(), updated.id),
        )
    console.print(f"[green]✓ saved[/green] recipe {updated.id}")


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


def _parse_params(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for kv in pairs:
        if "=" not in kv:
            raise typer.BadParameter(f"--param expects key=value, got: {kv!r}")
        k, v = kv.split("=", 1)
        k = k.strip()
        if not k:
            raise typer.BadParameter(f"--param has empty key: {kv!r}")
        out[k] = v
    return out


def _find_chromium() -> Path | None:
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
