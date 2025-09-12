from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional, List, Dict

import typer
from rich import print
from rich.table import Table
from platformdirs import user_config_path
import yaml

app = typer.Typer(add_completion=False, help="""
Smart File Organizer (SFO)
Organize files by rules. Safe by default (dry-run, manifest-based undo).
""")


DEFAULT_CONFIG_NAME = "config.yml"
DEFAULT_APP_DIRNAME = "sfo"


def default_config_path() -> Path:
    cfg_dir = user_config_path(DEFAULT_APP_DIRNAME, ensure_exists=True)
    return cfg_dir / DEFAULT_CONFIG_NAME


def load_config(path: Optional[Path]) -> dict:
    p = path or default_config_path()
    if not p.exists():
        typer.secho(f"Config not found: {p}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


@app.command()
def init(
    path: Optional[Path] = typer.Option(
        None, "--path", "-p", help="Optional path to write the default config to."
    )
):
    """Write a default YAML config to the OS config directory (or a given path)."""
    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        typer.confirm(f"{target} exists. Overwrite?", abort=True)
    example = (Path(__file__).parent / "config.example.yml").read_text(encoding="utf-8")
    target.write_text(example, encoding="utf-8")
    typer.secho(f"Default config written to: {target}", fg=typer.colors.GREEN)


def _scan_files(src: Path) -> List[Path]:
    return [p for p in src.rglob("*") if p.is_file()]


def _plan_moves(files: List[Path], rules: Dict, dest: Path) -> List[Dict]:
    # Minimal placeholder logic: group by extension into dest / ext / filename
    plan = []
    for f in files:
        ext = f.suffix.lower().lstrip(".") or "noext"
        target_dir = dest / ext
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f.name
        plan.append({"src": str(f), "dst": str(target)})
    return plan


def _print_plan(plan: List[Dict]):
    table = Table(title="Dry Run Plan")
    table.add_column("Source")
    table.add_column("Destination")
    for step in plan:
        table.add_row(step["src"], step["dst"])
    print(table)


@app.command("dry-run")
def dry_run(
    src: Path = typer.Option(..., exists=True, file_okay=False, help="Source folder"),
    dest: Path = typer.Option(..., help="Destination folder (will be created)"),
    config: Optional[Path] = typer.Option(None, help="Path to YAML config"),
):
    """Show what would happen without changing any files."""
    _ = load_config(config)  # not yet used; placeholder for rules engine
    files = _scan_files(src)
    plan = _plan_moves(files, {}, dest)
    _print_plan(plan)
    typer.secho(f"Planned moves: {len(plan)} (no changes made)", fg=typer.colors.BLUE)


@app.command()
def organize(
    src: Path = typer.Option(..., exists=True, file_okay=False, help="Source folder"),
    dest: Path = typer.Option(..., help="Destination folder (will be created)"),
    manifest: Path = typer.Option(Path("sfo-manifest.json"), help="Where to save undo manifest"),
    config: Optional[Path] = typer.Option(None, help="Path to YAML config"),
):
    """Apply the organization plan and save an undo manifest."""
    _ = load_config(config)  # placeholder; rules TBD
    files = _scan_files(src)
    plan = _plan_moves(files, {}, dest)
    records = []
    for step in plan:
        src_p = Path(step["src"])
        dst_p = Path(step["dst"])
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src_p, dst_p)
        records.append({"moved_from": str(src_p), "moved_to": str(dst_p)})
    manifest.write_text(json.dumps(records, indent=2), encoding="utf-8")
    typer.secho(f"Done. Manifest written to {manifest}", fg=typer.colors.GREEN)


@app.command()
def undo(
    manifest: Path = typer.Option(..., exists=True, help="Path to a manifest from 'organize'"),
):
    """Undo moves recorded in a manifest (best-effort)."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for rec in reversed(data):
        src = Path(rec["moved_to"])
        dst = Path(rec["moved_from"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.move(src, dst)
            typer.echo(f"Restored: {dst}")
        else:
            typer.echo(f"Skip missing: {src}")
    typer.secho("Undo complete.", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    app()
