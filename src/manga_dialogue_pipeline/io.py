"""Small file and environment helpers with no framework dependency."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from .schema import CharacterRoster

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def load_env(path: Path = Path(".env")) -> None:
    """Load KEY=VALUE lines without overriding exported environment variables."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def collect_images(path: Path) -> list[Path]:
    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"image path not found: {path}")
    images = sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES
    )
    if not images:
        raise FileNotFoundError(f"no supported images found under: {path}")
    return images


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_roster(path: Path | None) -> CharacterRoster:
    if path is None:
        return CharacterRoster()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return CharacterRoster.model_validate(payload)


def relative_or_absolute(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
