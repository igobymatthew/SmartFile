from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Iterable, Dict, List, Tuple, Callable


@dataclass
class FileInfo:
    path: Path
    name: str
    ext: str  # no leading dot
    mtime: datetime


@dataclass
class Rule:
    name: str
    type: str                     # 'extension' | 'regex' | 'mtime'
    pattern: Optional[str]
    when: Optional[str]
    target_template: str
    matcher: Callable[[FileInfo], bool]

    def render_target(self, fi: FileInfo) -> str:
        tokens = {
            "name": fi.name,
            "ext": (fi.ext or "noext").lower(),  # 👈 safe lowercase
            "yyyy": f"{fi.mtime.year:04d}",
            "mm": f"{fi.mtime.month:02d}",
            "dd": f"{fi.mtime.day:02d}",
        }
        return self.target_template.format(**tokens)



def _csv_to_set(csv: Optional[str]) -> set[str]:
    if not csv:
        return set()
    return {p.strip().lower() for p in csv.split(",") if p.strip()}


def make_extension_rule(name: str, pattern: str, target_template: str, when: Optional[str] = None) -> Rule:
    allowed = _csv_to_set(pattern)
    def match(fi: FileInfo) -> bool:
        if when and not Path(fi.path.name).match(when):
            return False
        return fi.ext.lower() in allowed
    return Rule(name=name, type="extension", pattern=pattern, when=when, target_template=target_template, matcher=match)


def make_regex_rule(name: str, pattern: str, target_template: str, when: Optional[str] = None, flags: int = re.IGNORECASE) -> Rule:
    rx = re.compile(pattern, flags)
    def match(fi: FileInfo) -> bool:
        if when and not Path(fi.path.name).match(when):
            return False
        return rx.search(fi.path.name) is not None
    return Rule(name=name, type="regex", pattern=pattern, when=when, target_template=target_template, matcher=match)


def make_mtime_rule(name: str, target_template: str, when: Optional[str] = None) -> Rule:
    def match(fi: FileInfo) -> bool:
        if when and not Path(fi.path.name).match(when):
            return False
        # mtime always “matches”; this is a fallback or bucket-by-date rule
        return True
    return Rule(name=name, type="mtime", pattern=None, when=when, target_template=target_template, matcher=match)


def build_file_info(p: Path) -> FileInfo:
    stat = p.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime)
    return FileInfo(
        path=p,
        name=p.stem,
        ext=p.suffix.lstrip(".").lower(),   # 👈 force lowercase here
        mtime=mtime,
    )


def rules_from_config(cfg: Dict) -> List[Rule]:
    rules: List[Rule] = []
    for item in (cfg.get("rules") or []):
        rtype = (item.get("type") or "").strip().lower()
        name = item.get("name") or f"rule_{len(rules)+1}"
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
        else:
            raise ValueError(f"Unsupported rule type: {rtype} (rule '{name}')")
    return rules


def choose_destination(fi: FileInfo, rules: List[Rule]) -> Tuple[Optional[Rule], Optional[str]]:
    for r in rules:
        if r.matcher(fi):
            return r, r.render_target(fi)
    return None, None
