from typer.testing import CliRunner

from smart_file_organizer.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Smart File Organizer" in result.stdout
