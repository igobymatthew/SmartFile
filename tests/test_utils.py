# This file is forked from https://github.com/ai-powered-dev/swe-agent/blob/main/docs/examples/sfo/tests/test_utils.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from smart_file_organizer.utils import (
    is_windows_reserved_name,
    sanitize_filename,
    win_long_path,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
def test_win_long_path_on_windows():
    p = Path("C:\\Users\\test").resolve()
    assert win_long_path(p) == f"\\\\?\\{p}"


@pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows test")
def test_win_long_path_on_non_windows():
    p = Path("/home/user/test")
    assert win_long_path(p) == str(p)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("file.txt", "file.txt"),
        ("file<>.txt", "file__.txt"),
        ('file:"/\\|?*.txt', "file_______.txt"),
        ("file\x00.txt", "file_.txt"),
    ],
)
def test_sanitize_filename_chars(name, expected):
    assert sanitize_filename(name) == expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
@pytest.mark.parametrize(
    "name, expected",
    [
        ("CON", True),
        ("con", True),
        ("con.txt", True),
        ("prn.jpg", True),
        ("aux", True),
        ("nul", True),
        ("COM1", True),
        ("LPT1", True),
        ("ACON", False),
        ("content", False),
    ],
)
def test_is_windows_reserved_name(name, expected):
    assert is_windows_reserved_name(name) is expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
def test_sanitize_filename_reserved():
    assert sanitize_filename("con.txt") == "con_.txt"
    assert sanitize_filename("PRN") == "PRN_"
