# This file is forked from https://github.com/ai-powered-dev/swe-agent/blob/main/docs/examples/sfo/smart_file_organizer/utils.py
from __future__ import annotations

import sys
from pathlib import Path

# Windows-specific path handling
WIN_RESERVED_NAMES = (
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
)


def is_windows_reserved_name(name: str) -> bool:
    """Check if a filename is a reserved name on Windows."""
    if not sys.platform == "win32":
        return False
    # CON.txt is fine, but CON is not.
    stem = name.split(".")[0].upper()
    return stem in WIN_RESERVED_NAMES


def sanitize_filename(name: str) -> str:
    """
    Sanitize a filename by replacing reserved names and characters.
    - Appends an underscore to Windows-reserved names.
    - Replaces characters that are invalid on Windows or problematic in URLs.
    """
    # Replace invalid URL/Windows characters with an underscore
    # Symbols: < > : " / \ | ? *
    # Also remove control characters (0-31)
    # Ref: https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file
    sanitized = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name)

    # Handle reserved names on Windows
    if is_windows_reserved_name(sanitized):
        stem, dot, ext = sanitized.rpartition(".")
        return f"{stem}_{dot}{ext}"
    return sanitized


def win_long_path(path: Path | str) -> str:
    """
    Return a Windows long-path-safe version of a path.
    - On non-Windows platforms, returns the original path unchanged.
    - On Windows, converts to an absolute path and prepends `\\?\`.
    """
    if not sys.platform == "win32":
        return str(path)

    p = Path(path).resolve()
    # Path is already UNC? Nothing to do.
    # (see https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation#unc)
    if str(p).startswith("\\\\"):
        return str(p)

    # Prepend the long-path prefix
    return f"\\\\?\\{p}"
