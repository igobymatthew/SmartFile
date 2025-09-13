from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import typer
import yaml
from platformdirs import user_config_path
from rich import print
from rich.table import Table

from smart_file_organizer.rules import build_file_info, choose_destination, rules_from_config

app = typer.Typer(
    add_completion=False,
    help="""
Smart File Organizer (SFO)
Organize files by rules. Safe by default (dry-run, manifest-based undo).
""",
)


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
    ),
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


def _plan_moves(files: List[Path], cfg: Dict, dest: Path) -> List[Dict]:
    """
    Build a move/copy plan. Uses first-matching rule from config; if none matches,
    falls back to grouping by extension.
    """
    rules = rules_from_config(cfg)
    plan = []
    for f in files:
        fi = build_file_info(f)
        rule, target_template = choose_destination(fi, rules)
        if target_template is None:
            # Fallback: by extension
            subdir = fi.ext or "noext"
            target_dir = dest / subdir
        else:
            # Rendered template may contain trailing slash(s)
            target_dir = (dest / target_template).resolve()
        target = target_dir / f.name
        plan.append(
            {"src": str(f), "dst": str(target), "rule": rule.name if rule else "fallback_extension"}
        )
    return plan


def _print_plan(plan: List[Dict]):
    table = Table(title="Dry Run Plan")
    table.add_column("Source")
    table.add_column("Destination")
    table.add_column("Rule")
    for step in plan:
        table.add_row(step["src"], step["dst"], step.get("rule", ""))
    print(table)


@app.command("dry-run")
def dry_run(
    src: Path = typer.Option(..., exists=True, file_okay=False, help="Source folder"),
    dest: Path = typer.Option(..., help="Destination folder (will be created)"),
    config: Optional[Path] = typer.Option(None, help="Path to YAML config"),
    json_output: bool = typer.Option(False, "--json", help="Emit plan as JSON."),
    pretty: bool = typer.Option(False, "--pretty", help="Pretty-print JSON output."),
):
    """Show what would happen without changing any files."""
    cfg = load_config(config)
    files = _scan_files(src)
    plan = _plan_moves(files, cfg, dest)

    if json_output:
        # NOTE: use typer.echo to avoid rich formatting ruining JSON
        indent = 2 if pretty else None
        typer.echo(json.dumps(plan, indent=indent))
    else:
        _print_plan(plan)
        typer.secho(f"Planned moves: {len(plan)} (no changes made)", fg=typer.colors.BLUE)


def _get_unique_name(dest_path: Path) -> Path:
    if not dest_path.exists():
        return dest_path
    parent = dest_path.parent
    stem = dest_path.stem
    ext = dest_path.suffix
    i = 1
    while True:
        new_name = f"{stem}_({i}){ext}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        i += 1


@app.command()
def organize(
    src: Path = typer.Option(..., exists=True, file_okay=False, help="Source folder"),
    dest: Path = typer.Option(..., help="Destination folder (will be created)"),
    manifest: Path = typer.Option(Path("sfo-manifest.json"), help="Where to save undo manifest"),
    config: Optional[Path] = typer.Option(None, help="Path to YAML config"),
    on_collision: Optional[str] = typer.Option(
        None,
        "--on-collision",
        help="What to do in a file name collision (config: 'collision')",
        case_sensitive=False,
    ),
):
    """Apply the organization plan and save an undo manifest."""
    cfg = load_config(config)
    collision_mode = on_collision or cfg.get("collision", "rename")
    files = _scan_files(src)
    plan = _plan_moves(files, cfg, dest)
    records = []
    for step in plan:
        src_p = Path(step["src"])
        dst_p = Path(step["dst"])
        dst_p.parent.mkdir(parents=True, exist_ok=True)

        final_dst = dst_p
        if dst_p.exists():
            if collision_mode == "skip":
                typer.secho(f"Skipped (exists): {dst_p}", fg=typer.colors.YELLOW)
                continue
            elif collision_mode == "overwrite":
                typer.secho(f"Overwriting: {dst_p}", fg=typer.colors.YELLOW)
            elif collision_mode == "rename":
                final_dst = _get_unique_name(dst_p)
                typer.secho(f"Renaming {dst_p.name} -> {final_dst.name}", fg=typer.colors.BLUE)

        shutil.move(src_p, final_dst)
        records.append({"moved_from": str(src_p), "moved_to": str(final_dst)})
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
