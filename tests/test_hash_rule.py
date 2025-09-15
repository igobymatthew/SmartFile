import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from smart_file_organizer.cli import app

runner = CliRunner()


def test_hash_rule_with_duplicates(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    # Create dummy files, some with identical content
    (src_dir / "file1.txt").write_text("content1")
    (src_dir / "file2.txt").write_text("content2")
    (src_dir / "file3.txt").write_text("content1")  # Duplicate of file1.txt
    (src_dir / "image1.jpg").write_text("image_content")
    (src_dir / "image2.jpg").write_text("image_content") # Duplicate of image1.jpg

    config_data = {
        "rules": [
            {
                "name": "dedupe_by_hash",
                "type": "hash",
                "target_template": "unique_files/",
                "hash_prefix_len": 4,
            }
        ]
    }
    config_path = tmp_path / "config.yml"
    with config_path.open("w") as f:
        yaml.dump(config_data, f)

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
        catch_exceptions=False,
    )

    assert result.exit_code == 0

    # file1.txt and file3.txt have the same content, so one is unique, one is a duplicate.
    # image1.jpg and image2.jpg have the same content, so one is unique, one is a duplicate.
    # file2.txt is unique.
    assert len(list((dest_dir / "unique_files").iterdir())) == 3

    # Check that duplicates are moved to the correct directory
    # The exact hash is difficult to predict, but we can check the structure
    dupes_dir = dest_dir / "duplicates"
    assert dupes_dir.exists()
    assert len(list(dupes_dir.iterdir())) == 2 # two different hash prefixes

    # Clean up
    shutil.rmtree(src_dir)
    shutil.rmtree(dest_dir)
