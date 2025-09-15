import os
import time
from pathlib import Path
from datetime import datetime
import piexif

from smart_file_organizer.rules import build_file_info, choose_destination, rules_from_config

from PIL import Image

# Helper function to create a test image with specific EXIF data
def create_test_image_with_exif(tmp_path, filename, dt):
    p = tmp_path / filename
    img = Image.new('RGB', (1, 1))
    exif_dict = {"Exif": {piexif.ExifIFD.DateTimeOriginal: dt.strftime("%Y:%m:%d %H:%M:%S").encode()}}
    exif_bytes = piexif.dump(exif_dict)
    img.save(p, "jpeg", exif=exif_bytes)
    return p

# Helper function to create a test image without EXIF data
def create_test_image_without_exif(tmp_path, filename, mtime_ts):
    p = tmp_path / filename
    img = Image.new('RGB', (1, 1))
    img.save(p, "jpeg")
    os.utime(p, (mtime_ts, mtime_ts))
    return p

CFG_EXIF = {
    "rules": [
        {
            "name": "exif_rule",
            "type": "exif_date",
            "when": "*.jpg",
            "target_template": "images/{yyyy}/{mm}/",
        },
    ]
}

def test_exif_date_rule_with_exif(tmp_path):
    exif_date = datetime(2023, 1, 15)
    f = create_test_image_with_exif(tmp_path, "photo_with_exif.jpg", exif_date)

    rules = rules_from_config(CFG_EXIF)
    fi = build_file_info(f)
    rule, target = choose_destination(fi, rules)

    assert rule is not None and rule.name == "exif_rule"
    assert "images/2023/01/" in target.replace("\\", "/")

def test_exif_date_rule_without_exif_fallback(tmp_path):
    mtime_ts = time.mktime(datetime(2022, 5, 20).timetuple())
    f = create_test_image_without_exif(tmp_path, "photo_without_exif.jpg", mtime_ts)

    rules = rules_from_config(CFG_EXIF)
    fi = build_file_info(f)
    rule, target = choose_destination(fi, rules)

    assert rule is not None and rule.name == "exif_rule"
    assert "images/2022/05/" in target.replace("\\", "/")

def test_exif_rule_for_non_image(tmp_path):
    mtime_ts = time.mktime(datetime(2021, 11, 11).timetuple())
    f = tmp_path / "document.txt"
    f.write_text("some text")
    os.utime(f, (mtime_ts, mtime_ts))

    # Using a config that would apply to all files if not for the 'when' clause
    cfg = { "rules": [ { "name": "exif_fallback", "type": "exif_date", "target_template": "files/{yyyy}/{mm}/" } ] }
    rules = rules_from_config(cfg)
    fi = build_file_info(f)
    rule, target = choose_destination(fi, rules)

    assert rule is not None
    assert "files/2021/11/" in target.replace("\\", "/")
