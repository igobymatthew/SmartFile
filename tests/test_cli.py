import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from smart_file_organizer.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Smart File Organizer" in result.stdout


def test_dry_run_json_output(tmp_path: Path):
    # 1. Setup temp dirs and files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    (src_dir / "test.jpg").touch()
    (src_dir / "another.txt").touch()

    # 2. Setup config
    config_path = tmp_path / "config.yml"
    config_data = {
        "version": 1,
        "rules": [
            {
                "name": "images",
                "type": "extension",
                "pattern": "jpg,jpeg,png",
                "target_template": "images/",
            }
        ],
    }
    with config_path.open("w") as f:
        yaml.dump(config_data, f)

    # 3. Run command
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

    # 4. Assertions
    assert result.exit_code == 0
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        assert False, f"Output is not valid JSON: {result.stdout}"

    assert isinstance(data, list)
    assert len(data) == 2

    # Find the entry for 'test.jpg'
    jpg_move = next((item for item in data if "test.jpg" in item["src"]), None)
    assert jpg_move is not None
    assert jpg_move["rule"] == "images"
    expected_dst = dest_dir / "images" / "test.jpg"
    assert Path(jpg_move["dst"]) == expected_dst

    # Find the entry for 'another.txt' (fallback)
    txt_move = next((item for item in data if "another.txt" in item["src"]), None)
    assert txt_move is not None
    assert txt_move["rule"] == "fallback_extension"
    expected_dst = dest_dir / "txt" / "another.txt"
    assert Path(txt_move["dst"]) == expected_dst
