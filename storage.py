"""Remembers the 5 most recently used .acp files (stored in %APPDATA%\\AutoClicker)."""
from __future__ import annotations

import json
import os
from pathlib import Path

MAX_RECENT = 5


def _config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "AutoClicker" / "config.json"


def _read() -> dict:
    try:
        with open(_config_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    path = _config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass  # history is a convenience; never crash because of it


def load_recent() -> list[str]:
    raw = _read().get("recent", [])
    result: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item not in result and os.path.isfile(item):
                result.append(item)
    return result[:MAX_RECENT]


def add_recent(path: str) -> list[str]:
    path = os.path.abspath(path)
    key = os.path.normcase(path)
    items = [path] + [p for p in load_recent() if os.path.normcase(p) != key]
    items = items[:MAX_RECENT]
    data = _read()
    data["recent"] = items
    _write(data)
    return items


def load_language() -> str:
    code = _read().get("language", "en")
    return code if isinstance(code, str) else "en"


def save_language(code: str) -> None:
    data = _read()
    data["language"] = code
    _write(data)
