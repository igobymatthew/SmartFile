# Smart File Organizer (SFO)

A safe, test-driven CLI to organize files into well-structured folders using declarative rules.
Features include **dry-run**, **manifest-based undo**, cross-platform paths, and rich logs.

## Quickstart
```bash
# create and activate a venv (recommended)
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate

# install in editable mode
pip install -e .

# see commands
sfo --help

# initialize default config
sfo init

# simulate changes without touching files
sfo dry-run --src ~/Downloads --config ~/.config/sfo/config.yml

# apply organization
sfo organize --src ~/Downloads --config ~/.config/sfo/config.yml

# undo last run using manifest file produced by 'organize'
sfo undo --manifest ./sfo-manifest.json
```

## Commands
- `init` – write a default config to the OS-appropriate config dir.
- `dry-run` – print a plan of moves/copies without changing the filesystem.
- `organize` – execute the plan and produce an undo manifest.
  - `--on-collision`: What to do if a destination file already exists (`rename` (default), `overwrite`, `skip`).
  - `--trash PATH`: Stage files in this directory before final move. On failure, the file remains in the trash and is recorded in the manifest.
- `undo` – revert changes recorded in a manifest file.

## Architecture

```mermaid
flowchart LR
    P[Planner] --> E[Executor]
    E --> M[Manifest]
```

The planner analyzes your files and configuration to create a plan. The executor performs the moves and copies, while the manifest records actions so they can be undone later.

## Configuration (YAML)
See `config.example.yml` for a complete schema with comments.

## Development
- Tests: `pytest`
- Lint/format: `ruff check .`
- CI: GitHub Actions runs tests on push/PR.
