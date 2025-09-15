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


def test_organize_collision_handling(tmp_path: Path):
    # 1. Setup: one source file, one conflicting destination file
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src_file = src_dir / "test.txt"
    src_file.write_text("source")

    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest_file_orig = dest_dir / "txt" / "test.txt"
    dest_file_orig.parent.mkdir()
    dest_file_orig.write_text("destination")

    config_path = tmp_path / "config.yml"
    config_data = {"version": 1, "rules": []}  # Use fallback extension rule
    with config_path.open("w") as f:
        yaml.dump(config_data, f)

    # 2. Test 'skip'
    result_skip = runner.invoke(
        app,
        [
            "organize",
            "--src",
            str(src_dir),
            "--dest",
            str(dest_dir),
            "--config",
            str(config_path),
            "--on-collision",
            "skip",
        ],
    )
    assert result_skip.exit_code == 0
    assert "Skipped" in result_skip.stdout
    assert src_file.exists()  # Not moved
    assert dest_file_orig.read_text() == "destination"  # Unchanged

    # 3. Test 'overwrite'
    src_file.write_text("source_for_overwrite")  # Re-create src
    result_overwrite = runner.invoke(
        app,
        [
            "organize",
            "--src",
            str(src_dir),
            "--dest",
            str(dest_dir),
            "--config",
            str(config_path),
            "--on-collision",
            "overwrite",
        ],
    )
    assert result_overwrite.exit_code == 0
    assert "Overwriting" in result_overwrite.stdout
    assert not src_file.exists()  # Moved
    assert dest_file_orig.read_text() == "source_for_overwrite"  # Changed

    # 4. Test 'rename'
    src_file.write_text("source_for_rename")  # Re-create src
    dest_file_orig.write_text("destination")  # Re-create dst
    result_rename = runner.invoke(
        app,
        [
            "organize",
            "--src",
            str(src_dir),
            "--dest",
            str(dest_dir),
            "--config",
            str(config_path),
            "--on-collision",
            "rename",
        ],
    )
    assert result_rename.exit_code == 0
    assert "Renaming" in result_rename.stdout
    assert not src_file.exists()
    renamed_file = dest_dir / "txt" / "test_(1).txt"
    assert renamed_file.exists()
    assert renamed_file.read_text() == "source_for_rename"


def test_organize_trash_on_failure(tmp_path: Path):
    # 1. Setup: one source file, read-only destination
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src_file = src_dir / "test.txt"
    src_file.write_text("test content")

    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()

    # Make destination read-only to cause a failure
    (dest_dir / "txt").mkdir()
    (dest_dir / "txt").chmod(0o555)

    config_path = tmp_path / "config.yml"
    config_data = {"version": 1, "rules": []}  # Use fallback
    with config_path.open("w") as f:
        yaml.dump(config_data, f)

    manifest_path = tmp_path / "manifest.json"

    # 2. Run command
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
            "--trash",
            str(trash_dir),
            "--manifest",
            str(manifest_path),
        ],
        catch_exceptions=False,
    )

    # 3. Assertions
    assert result.exit_code == 0
    assert "Error moving" in result.stdout
    assert "File saved in trash" in result.stdout

    # File should be in trash, not in src
    assert not src_file.exists()
    trashed_file = trash_dir / "test.txt"
    assert trashed_file.exists()
    assert trashed_file.read_text() == "test content"

    # Manifest should record the failure
    manifest_data = json.loads(manifest_path.read_text())
    assert len(manifest_data) == 1
    record = manifest_data[0]
    assert record["moved_from"] == str(src_file)
    assert "trashed_at" in record
    assert Path(record["trashed_at"]) == trashed_file

    # Make dest writable again so cleanup can succeed
    (dest_dir / "txt").chmod(0o755)


def test_dry_run_with_ignore_globs(tmp_path: Path):
    # 1. Setup temp dirs and files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    # Files that should be processed
    (src_dir / "my-image.jpg").touch()
    (src_dir / "document.pdf").touch()

    # Files that should be ignored
    git_dir = src_dir / ".git"
    git_dir.mkdir()
    (git_dir / "config").touch()

    node_modules_dir = src_dir / "node_modules"
    node_modules_dir.mkdir()
    (node_modules_dir / "dependency.js").touch()

    (src_dir / ".DS_Store").touch()
    (src_dir / "error.log").touch()
    sub_dir = src_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / ".DS_Store").touch()

    # 2. Setup config with ignore rules
    config_path = tmp_path / "config.yml"
    config_data = {
        "version": 1,
        "ignore": ["**/.git/**", "**/node_modules/**", "**/.DS_Store", "**/*.log"],
        "rules": [],  # Use fallback rules
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

    src_paths = {item["src"] for item in data}
    assert str(src_dir / "my-image.jpg") in src_paths
    assert str(src_dir / "document.pdf") in src_paths

    assert str(git_dir / "config") not in src_paths
    assert str(node_modules_dir / "dependency.js") not in src_paths
    assert str(src_dir / ".DS_Store") not in src_paths
    assert str(sub_dir / ".DS_Store") not in src_paths
    assert str(src_dir / "error.log") not in src_paths


def test_organize_with_logging(tmp_path: Path):
    # 1. Setup
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "image.jpg").touch()
    (src_dir / "doc.txt").touch()

    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    log_file = tmp_path / "events.log"

    config_path = tmp_path / "config.yml"
    config_data = {
        "version": 1,
        "rules": [
            {
                "name": "images",
                "type": "extension",
                "pattern": "jpg",
                "target_template": "pictures/",
            }
        ],
    }
    with config_path.open("w") as f:
        yaml.dump(config_data, f)

    # 2. Run organize with logging
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
            "--log-file",
            str(log_file),
        ],
    )

    # 3. Assertions
    assert result.exit_code == 0
    assert log_file.exists()

    # Verify log content
    log_lines = log_file.read_text().strip().split("\n")
    assert len(log_lines) == 2

    logs = [json.loads(line) for line in log_lines]

    # Check image log entry
    image_log = next((log for log in logs if "image.jpg" in log["src"]), None)
    assert image_log is not None
    assert image_log["action"] == "move"
    assert "pictures" in image_log["dst"]
    assert image_log["rule"] == "images"
    assert "ts" in image_log
    assert "level" in image_log

    # Check document log entry
    doc_log = next((log for log in logs if "doc.txt" in log["src"]), None)
    assert doc_log is not None
    assert doc_log["action"] == "move"
    assert "txt" in doc_log["dst"]  # Fallback rule
    assert doc_log["rule"] == "fallback_extension"
