# This file is forked from https://github.com/ai-powered-dev/swe-agent/blob/main/docs/examples/sfo/tests/test_windows_edge_cases.py
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from smart_file_organizer.cli import app

runner = CliRunner()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
def test_organize_with_reserved_name(tmp_path: Path):
    # 1. Setup
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "con.txt").touch()  # A reserved name on Windows

    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    config_path = tmp_path / "config.yml"
    config_data = {"version": 1, "rules": []}  # Use fallback
    with config_path.open("w") as f:
        yaml.dump(config_data, f)

    # 2. Run organize
    result = runner.invoke(
        app,
        [
            "organize",
            "--src",
            str(src_dir),
            "--dest",
            str(dest_dir),
            "--config",
            str(config_path),
        ],
    )

    # 3. Assertions
    assert result.exit_code == 0
    assert not (src_dir / "con.txt").exists()

    # The file should be moved and sanitized
    sanitized_file = dest_dir / "txt" / "con_.txt"
    assert sanitized_file.exists()


def test_organize_handles_permission_error(tmp_path: Path):
    # 1. Setup
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "locked_file.txt").touch()

    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    config_path = tmp_path / "config.yml"
    config_data = {"version": 1, "rules": []}
    with config_path.open("w") as f:
        yaml.dump(config_data, f)

    manifest_path = tmp_path / "manifest.json"

    # 2. Mock shutil.move to raise PermissionError
    with patch("shutil.move", side_effect=PermissionError("File is locked")):
        result = runner.invoke(
            app,
            [
                "organize",
                "--src",
                str(src_dir),
                "--dest",
                str(dest_dir),
                "--config",
                str(config_path),
                "--manifest",
                str(manifest_path),
            ],
        )

    # 3. Assertions
    assert result.exit_code == 0
    assert "Permission error" in result.stdout

    # File should still be in source
    assert (src_dir / "locked_file.txt").exists()

    # Manifest should record the error
    manifest_data = json.loads(manifest_path.read_text())
    assert len(manifest_data) == 1
    record = manifest_data[0]
    assert "error" in record
    assert "File is locked" in record["error"]


def test_paths_are_posix_in_json_output(tmp_path: Path):
    # 1. Setup
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "test.txt").touch()

    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    config_path = tmp_path / "config.yml"
    config_data = {"version": 1, "rules": []}
    with config_path.open("w") as f:
        yaml.dump(config_data, f)

    # 2. Run dry-run with --json
    result = runner.invoke(
        app,
        [
            "dry-run",
            "--src",
            str(src_dir),
            "--dest",
            str(dest_dir),
            "--config",
            str(config_path),
            "--json",
        ],
    )

    # 3. Assertions
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 1
    record = data[0]

    # All paths must use forward slashes, regardless of OS
    assert "/" in record["src"]
    assert "/" in record["dst"]
    if sys.platform == "win32":
        assert "\\" not in record["src"]
        assert "\\" not in record["dst"]
