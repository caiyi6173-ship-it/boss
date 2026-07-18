#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import candidates from resources/chinese_synonym.txt into domain_glossary.json.

Usage:
  python tools/import_chinese_synonyms.py
  python tools/import_chinese_synonyms.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config

MAX_GROUP_SIZE = 12
MAX_NEW_ALIASES = 10
MAX_ALIAS_LEN = 6

BLACKLIST = {
    "妄想", "希图", "贪图", "企图", "估计", "估量", "推算", "盘算",
    "意料", "料想", "预想", "预料", "预计", "广告", "鼓动", "声张",
    "张扬", "案牍", "壅闭", "流动", "运动", "举止", "条记", "前期",
    "野鸡", "非法", "地下", "私自", "黑", "伪", "暗",
    "揭橥", "揭晓", "传布", "流传", "劝导", "疏导", "疏浚", "疏通",
    "质料", "原料", "片断",
}


def load_groups(path: Path) -> list[list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"missing synonym file: {path}")
    groups: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.split("\t") if p.strip()]
        if len(parts) == 1:
            parts = [p for p in parts[0].split() if p]
        if len(parts) >= 2:
            groups.append(parts)
    return groups


def build_index(groups: list[list[str]]) -> dict[str, list[list[str]]]:
    idx: dict[str, list[list[str]]] = {}
    for g in groups:
        if len(g) > MAX_GROUP_SIZE:
            continue
        for w in g:
            idx.setdefault(w, []).append(g)
    return idx


def collect_candidates(seeds: set[str], index: dict[str, list[list[str]]]) -> list[str]:
    found: list[str] = []
    seen = set(seeds)
    for seed in list(seeds):
        for group in index.get(seed, []):
            for w in group:
                if w in seen or w in BLACKLIST:
                    continue
                if not (1 <= len(w) <= MAX_ALIAS_LEN):
                    continue
                if "," in w or "，" in w or " " in w:
                    continue
                seen.add(w)
                found.append(w)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Import general Chinese synonyms into domain glossary")
    parser.add_argument("--write", action="store_true", help="write aliases back to domain_glossary.json")
    parser.add_argument("--synonym-file", type=Path, default=config.CHINESE_SYNONYM_TXT)
    parser.add_argument("--glossary", type=Path, default=config.DOMAIN_GLOSSARY_JSON)
    args = parser.parse_args()

    groups = load_groups(args.synonym_file)
    index = build_index(groups)
    data = json.loads(args.glossary.read_text(encoding="utf-8"))
    terms = data.get("terms") or []

    print(f"synonym file: {args.synonym_file} ({len(groups)} groups)")
    print(f"glossary: {args.glossary} ({len(terms)} terms)")
    print("-" * 60)

    changed = 0
    for item in terms:
        canonical = str(item.get("canonical") or "").strip()
        if not canonical:
            continue
        aliases = [str(a).strip() for a in (item.get("aliases") or []) if str(a).strip()]
        seeds = {canonical, *aliases}
        candidates = collect_candidates(seeds, index)[:MAX_NEW_ALIASES]
        new_ones = [c for c in candidates if c not in seeds]
        if new_ones:
            changed += 1
            print(f"[{item.get('category', '')}] {canonical}")
            print(f"  current: {aliases}")
            print(f"  add: {new_ones}")
            if args.write:
                item["aliases"] = aliases + new_ones
        else:
            print(f"[{item.get('category', '')}] {canonical}  (no useful general synonym)")

    if args.write:
        data["source"] = {
            "general_synonym": str(args.synonym_file.name),
            "note": "aliases include manual business terms + general synonym import; edit freely",
        }
        args.glossary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("-" * 60)
        print(f"written: {args.glossary} (updated {changed} terms)")
    else:
        print("-" * 60)
        print(f"preview done: {changed} terms expandable. use --write to save.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
