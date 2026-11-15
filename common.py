"""Shared paths, dates and loaders."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
OUT = ROOT / "outputs"
WAT = timezone(timedelta(hours=1))  # Africa/Lagos, no daylight saving


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def company() -> dict:
    return load_yaml(CONFIG / "company.yaml")


TODAY = datetime.fromisoformat(load_yaml(CONFIG / "company.yaml")["today"])  # naive, Lagos time


def reps() -> dict:
    return {r["id"]: r for r in company()["reps"]}


def answer_key() -> list[dict]:
    with open(DATA / "answer_key.json") as f:
        return json.load(f)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False, default=str)
