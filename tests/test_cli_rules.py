from pathlib import Path

import pytest
from typer.testing import CliRunner

from smart_file_organizer.cli import app

runner = CliRunner()

@pytest.fixture
def valid_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "valid_config.yml"
    config_path.write_text(r"""
version: 1
rules:
  - name: images
    type: extension
    pattern: "jpg,png"
    target_template: "images/{ext}"
  - name: docs
    type: regex
    pattern: ".*\\.docx"
    target_template: "docs/"
""")
    return config_path

@pytest.fixture
def invalid_config_bad_key(tmp_path: Path) -> Path:
    config_path = tmp_path / "invalid_config_bad_key.yml"
    config_path.write_text("""
version: 1
rules:
  - name: images
    type: extension
    patern: "jpg,png" # misspelled key
    target_template: "images/{ext}"
""")
    return config_path

@pytest.fixture
def invalid_config_missing_pattern(tmp_path: Path) -> Path:
    config_path = tmp_path / "invalid_config_missing_pattern.yml"
    config_path.write_text("""
version: 1
rules:
  - name: images
    type: extension
    target_template: "images/{ext}"
""")
    return config_path

def test_validate_valid_config(valid_config: Path):
    result = runner.invoke(app, ["rules", "validate", "--config", str(valid_config)])
    assert result.exit_code == 0
    assert "✅ Config is valid." in result.stdout

def test_validate_invalid_config_bad_key(invalid_config_bad_key: Path):
    result = runner.invoke(app, ["rules", "validate", "--config", str(invalid_config_bad_key)])
    assert result.exit_code == 1
    assert "❌ Invalid config: Rule 'images' (type: extension) has unexpected keys: patern" in result.stdout

def test_validate_invalid_config_missing_pattern(invalid_config_missing_pattern: Path):
    result = runner.invoke(app, ["rules", "validate", "--config", str(invalid_config_missing_pattern)])
    assert result.exit_code == 1
    assert "❌ Invalid config: Rule 'images' (type=extension) requires 'pattern'" in result.stdout

@pytest.fixture
def file_to_explain(tmp_path: Path) -> Path:
    file_path = tmp_path / "test_image.jpg"
    file_path.touch()
    return file_path

def test_explain_rule(valid_config: Path, file_to_explain: Path):
    result = runner.invoke(app, ["rules", "explain", "--config", str(valid_config), "--file", str(file_to_explain)])
    assert result.exit_code == 0
    assert "Matched rule: 'images'" in result.stdout
    assert "Destination: 'images/jpg'" in result.stdout

def test_explain_rule_no_match(valid_config: Path, tmp_path: Path):
    file_path = tmp_path / "unmatched.txt"
    file_path.touch()
    result = runner.invoke(app, ["rules", "explain", "--config", str(valid_config), "--file", str(file_path)])
    assert result.exit_code == 0
    assert "No matching rule found" in result.stdout
