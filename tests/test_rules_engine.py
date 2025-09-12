import os
import time
from pathlib import Path

from smart_file_organizer.rules import build_file_info, choose_destination, rules_from_config

CFG = {
    "rules": [
        {
            "name": "imgs",
            "type": "extension",
            "pattern": "jpg,jpeg,png",
            "target_template": "images/{ext}/{yyyy}/{mm}/",
        },
        {
            "name": "logs",
            "type": "regex",
            "pattern": r".*\.log$",
            "target_template": "logs/{yyyy}/{mm}/{dd}/",
        },
        {"name": "mtime_fallback", "type": "mtime", "target_template": "{yyyy}/{mm}/"},
    ]
}


def _touch_with_mtime(p: Path, ts: float):
    p.write_text("x")
    os.utime(p, (ts, ts))


def test_extension_rule(tmp_path):
    f = tmp_path / "photo.JPG"
    _touch_with_mtime(f, time.time())
    rules = rules_from_config(CFG)
    fi = build_file_info(f)
    rule, target = choose_destination(fi, rules)
    assert rule is not None and rule.name == "imgs"
    assert "images/jpg/" in target.replace("\\", "/")


def test_regex_rule(tmp_path):
    f = tmp_path / "server.log"
    _touch_with_mtime(f, time.time())
    rules = rules_from_config(CFG)
    fi = build_file_info(f)
    rule, target = choose_destination(fi, rules)
    assert rule is not None and rule.name == "logs"
    assert "logs/" in target.replace("\\", "/")


def test_mtime_fallback(tmp_path):
    f = tmp_path / "notes.txt"
    _touch_with_mtime(f, time.time())
    rules = rules_from_config(CFG)
    fi = build_file_info(f)
    rule, target = choose_destination(fi, rules)
    assert rule is not None and rule.name == "mtime_fallback"
    # yyyy/mm should exist in target
    parts = target.replace("\\", "/").split("/")
    assert len(parts) >= 2 and len(parts[-3]) == 4 and len(parts[-2]) == 2
