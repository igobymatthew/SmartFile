from __future__ import annotations

import concurrent.futures
import fnmatch
import json
import shutil
from datetime import datetime, timezone
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

rules_app = typer.Typer(name="rules", help="Manage and inspect rules.")
app.add_typer(rules_app)


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


def _scan_files(src: Path, ignore_globs: List[str]) -> List[Path]:
    """Scan for files, filtering out ignored ones."""
    all_files = [p for p in src.rglob("*") if p.is_file()]
    if not ignore_globs:
        return all_files

    kept_files = []
    for p in all_files:
        # Match globs against the full path to allow for patterns like
        # '**/node_modules/**' to work correctly.
        is_ignored = any(fnmatch.fnmatch(p, glob) for glob in ignore_globs)
        if not is_ignored:
            kept_files.append(p)
    return kept_files


def _build_file_infos_parallel(
    files: List[Path], hash_cache: Dict[Path, str], max_workers: int
) -> List[Dict]:
    """Build FileInfo objects in parallel to speed up hashing."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(build_file_info, f, hash_cache): f for f in files
        }
        results = []
        for future in concurrent.futures.as_completed(future_to_file):
            results.append(future.result())
        return results


def _plan_moves(
    files: List[Path], cfg: Dict, dest: Path, max_workers_hashing: int
) -> List[Dict]:
    """
    Build a move/copy plan. Uses first-matching rule from config; if none matches,
    falls back to grouping by extension.
    """
    rules = rules_from_config(cfg)
    plan = []
    hash_cache: Dict[Path, str] = {}
    seen_hashes: Dict[str, Path] = {}

    # Determine if any hash rules are active
    has_hash_rule = any(r.type == "hash" for r in rules)

    # Efficiently build FileInfo objects, with hashing if needed
    if has_hash_rule:
        file_infos = _build_file_infos_parallel(
            files, hash_cache, max_workers=max_workers_hashing
        )
    else:
        file_infos = [build_file_info(f) for f in files]

    for fi in file_infos:
        rule, target_template = choose_destination(fi, rules)

        if rule and rule.type == "hash":
            if fi.file_hash in seen_hashes:
                # This is a duplicate
                prefix = fi.file_hash[: rule.hash_prefix_len]
                target_dir = dest / "duplicates" / prefix
                rule_name = f"{rule.name} (duplicate)"
            else:
                # First time seeing this hash
                seen_hashes[fi.file_hash] = fi.path
                target_dir = (dest / target_template).resolve()
                rule_name = rule.name
        elif target_template is None:
            # Fallback: by extension
            subdir = fi.ext or "noext"
            target_dir = dest / subdir
            rule_name = "fallback_extension"
        else:
            # Rendered template may contain trailing slash(s)
            target_dir = (dest / target_template).resolve()
            rule_name = rule.name if rule else "fallback_no_rule"

        target = target_dir / fi.path.name
        plan.append({"src": str(fi.path), "dst": str(target), "rule": rule_name})
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
    max_workers_hashing: int = typer.Option(
        4, help="Max parallel workers for hashing."
    ),
):
    """Show what would happen without changing any files."""
    cfg = load_config(config)
    ignore_globs = cfg.get("ignore", [])
    files = _scan_files(src, ignore_globs)
    plan = _plan_moves(files, cfg, dest, max_workers_hashing)

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


def _log_action(
    log_file: Path,
    action: str,
    src: Path,
    dst: Path,
    rule: str,
    level: str = "info",
):
    """Emit a JSONL log entry."""
    if not log_file:
        return
    log_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "action": action,
        "src": str(src),
        "dst": str(dst),
        "rule": rule,
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")


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
    trash: Optional[Path] = typer.Option(
        None,
        "--trash",
        help="Stage files in this directory before final move.",
    ),
    max_workers_hashing: int = typer.Option(
        4, help="Max parallel workers for hashing."
    ),
    log_file: Optional[Path] = typer.Option(
        None, "--log-file", help="Emit JSONL logs to this file."
    ),
):
    """Apply the organization plan and save an undo manifest."""
    cfg = load_config(config)
    collision_mode = on_collision or cfg.get("collision", "rename")
    ignore_globs = cfg.get("ignore", [])
    files = _scan_files(src, ignore_globs)
    plan = _plan_moves(files, cfg, dest, max_workers_hashing)
    if trash:
        trash.mkdir(parents=True, exist_ok=True)
    records = []
    for step in plan:
        src_p = Path(step["src"])
        dst_p = Path(step["dst"])
        rule_name = step.get("rule", "unknown")
        dst_p.parent.mkdir(parents=True, exist_ok=True)

        final_dst = dst_p
        if dst_p.exists():
            if collision_mode == "skip":
                typer.secho(f"Skipped (exists): {dst_p}", fg=typer.colors.YELLOW)
                _log_action(log_file, "skip", src_p, dst_p, rule_name)
                continue
            elif collision_mode == "overwrite":
                typer.secho(f"Overwriting: {dst_p}", fg=typer.colors.YELLOW)
                _log_action(log_file, "overwrite", src_p, dst_p, rule_name)
            elif collision_mode == "rename":
                final_dst = _get_unique_name(dst_p)
                typer.secho(f"Renaming {dst_p.name} -> {final_dst.name}", fg=typer.colors.BLUE)
                _log_action(log_file, "rename", src_p, final_dst, rule_name)
        if trash:
            try:
                staged_path = trash / src_p.name
                shutil.move(src_p, staged_path)
                shutil.move(staged_path, final_dst)
                records.append({"moved_from": str(src_p), "moved_to": str(final_dst)})
                _log_action(log_file, "move", src_p, final_dst, rule_name)
            except Exception as e:
                typer.secho(f"Error moving {src_p}: {e}. File saved in trash.", fg=typer.colors.RED)
                records.append({"moved_from": str(src_p), "trashed_at": str(staged_path)})
                _log_action(log_file, "trash_error", src_p, staged_path, rule_name, level="error")
        else:
            shutil.move(src_p, final_dst)
            records.append({"moved_from": str(src_p), "moved_to": str(final_dst)})
            _log_action(log_file, "move", src_p, final_dst, rule_name)
    manifest.write_text(json.dumps(records, indent=2), encoding="utf-8")
    typer.secho(f"Done. Manifest written to {manifest}", fg=typer.colors.GREEN)


@rules_app.command("validate")
def validate_rules(
    config: Path = typer.Option(
        ..., "--config", "-c", exists=True, help="Path to YAML config to validate."
    ),
):
    """Validate the rules in a configuration file."""
    try:
        cfg = load_config(config)
        rules_from_config(cfg)
        typer.secho("✅ Config is valid.", fg=typer.colors.GREEN)
    except (ValueError, KeyError) as e:
        typer.secho(f"❌ Invalid config: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@rules_app.command("explain")
def explain_rule(
    config: Path = typer.Option(..., "--config", "-c", exists=True, help="Path to YAML config."),
    file: Path = typer.Option(..., "--file", "-f", exists=True, dir_okay=False, help="File to test against rules."),
):
    """Show which rule matches a file and what the destination would be."""
    cfg = load_config(config)
    try:
        rules = rules_from_config(cfg)
        # Check if hashing is needed
        has_hash_rule = any(r.type == "hash" for r in rules)
        hash_cache = {} if has_hash_rule else None

        file_info = build_file_info(file, hash_cache=hash_cache)
        rule, target_path = choose_destination(file_info, rules)

        if rule:
            print(f"File: '{file}'")
            print(f" [bold green]✔[/bold green] Matched rule: '[bold]{rule.name}[/bold]' (type: {rule.type})")
            print(f"   Destination: '{target_path}'")
        else:
            print(f"File: '{file}'")
            print(" [bold yellow]✖[/bold yellow] No matching rule found.")

    except (ValueError, KeyError) as e:
        typer.secho(f"❌ Invalid config: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


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
