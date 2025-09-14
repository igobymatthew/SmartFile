from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class FileInfo:
    path: Path
    name: str
    ext: str  # no leading dot
    mtime: datetime
    file_hash: Optional[str] = None


@dataclass
class Rule:
    name: str
    type: str  # 'extension' | 'regex' | 'mtime' | 'hash'
    pattern: Optional[str]
    when: Optional[str]
    target_template: str
    matcher: Callable[[FileInfo], bool]
    hash_prefix_len: int = 2  # Default value

    def render_target(self, fi: FileInfo) -> str:
        hash_prefix = ""
        if fi.file_hash:
            hash_prefix = fi.file_hash[: self.hash_prefix_len]

        tokens = {
            "name": fi.name,
            "ext": (fi.ext or "noext").lower(),  # 👈 safe lowercase
            "yyyy": f"{fi.mtime.year:04d}",
            "mm": f"{fi.mtime.month:02d}",
            "dd": f"{fi.mtime.day:02d}",
            "hash": fi.file_hash or "",
            "hash_prefix": hash_prefix,
        }
        return self.target_template.format(**tokens)


def _csv_to_set(csv: Optional[str]) -> set[str]:
    if not csv:
        return set()
    return {p.strip().lower() for p in csv.split(",") if p.strip()}


def make_extension_rule(
    name: str, pattern: str, target_template: str, when: Optional[str] = None
) -> Rule:
    allowed = _csv_to_set(pattern)

    def match(fi: FileInfo) -> bool:
        if when and not Path(fi.path.name).match(when):
            return False
        return fi.ext.lower() in allowed

    return Rule(
        name=name,
        type="extension",
        pattern=pattern,
        when=when,
        target_template=target_template,
        matcher=match,
    )


def make_regex_rule(
    name: str,
    pattern: str,
    target_template: str,
    when: Optional[str] = None,
    flags: int = re.IGNORECASE,
) -> Rule:
    rx = re.compile(pattern, flags)

    def match(fi: FileInfo) -> bool:
        if when and not Path(fi.path.name).match(when):
            return False
        return rx.search(fi.path.name) is not None

    return Rule(
        name=name,
        type="regex",
        pattern=pattern,
        when=when,
        target_template=target_template,
        matcher=match,
    )


def make_mtime_rule(name: str, target_template: str, when: Optional[str] = None) -> Rule:
    def match(fi: FileInfo) -> bool:
        if when and not Path(fi.path.name).match(when):
            return False
        # mtime always “matches”; this is a fallback or bucket-by-date rule
        return True

    return Rule(
        name=name,
        type="mtime",
        pattern=None,
        when=when,
        target_template=target_template,
        matcher=match,
    )


def make_hash_rule(
    name: str, target_template: str, when: Optional[str] = None, hash_prefix_len: int = 2
) -> Rule:
    def match(fi: FileInfo) -> bool:
        if when and not Path(fi.path.name).match(when):
            return False
        # Hash rule always matches if `when` is met.
        # The core logic is in how duplicates are handled, not in the matching itself.
        return True

    return Rule(
        name=name,
        type="hash",
        pattern=None,
        when=when,
        target_template=target_template,
        matcher=match,
        hash_prefix_len=hash_prefix_len,
    )


def build_file_info(p: Path, hash_cache: Dict[Path, str] = None) -> FileInfo:
    stat = p.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime)
    file_hash = None
    if hash_cache is not None:
        if p in hash_cache:
            file_hash = hash_cache[p]
        else:
            hasher = hashlib.sha256()
            with p.open("rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
            hash_cache[p] = file_hash

    return FileInfo(
        path=p,
        name=p.stem,
        ext=p.suffix.lstrip(".").lower(),  # 👈 force lowercase here
        mtime=mtime,
        file_hash=file_hash,
    )


def rules_from_config(cfg: Dict) -> List[Rule]:
    rules: List[Rule] = []
    for item in cfg.get("rules") or []:
        rtype = (item.get("type") or "").strip().lower()
        name = item.get("name") or f"rule_{len(rules) + 1}"
        pattern = item.get("pattern")
        when = item.get("when")
        target_template = item["target_template"]  # required
        if rtype == "extension":
            if not pattern:
                raise ValueError(f"Rule '{name}' type=extension requires 'pattern'")
            rules.append(make_extension_rule(name, pattern, target_template, when))
        elif rtype == "regex":
            if not pattern:
                raise ValueError(f"Rule '{name}' type=regex requires 'pattern'")
            rules.append(make_regex_rule(name, pattern, target_template, when))
        elif rtype == "mtime":
            rules.append(make_mtime_rule(name, target_template, when))
        elif rtype == "hash":
            hash_prefix_len = item.get("hash_prefix_len", 2)
            rules.append(make_hash_rule(name, target_template, when, hash_prefix_len))
        else:
            raise ValueError(f"Unsupported rule type: {rtype} (rule '{name}')")
    return rules


def choose_destination(fi: FileInfo, rules: List[Rule]) -> Tuple[Optional[Rule], Optional[str]]:
    for r in rules:
        if r.matcher(fi):
            return r, r.render_target(fi)
    return None, None
