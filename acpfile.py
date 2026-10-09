"""Reading and writing .acp (Auto Clicker Profile) files.

An .acp file is JSON with a small envelope:

    {"magic": "ACP", "version": 1, "checksum": "<sha256 of data>", "data": {...}}

The checksum is not security - it only lets us reject files that were damaged
or hand-edited into something the app does not understand.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from common import (
    LocalizedError,
    MAX_CYCLES,
    MAX_DELAY_MS,
    MAX_POINTS,
    MIN_DELAY_MS,
    PROFILE_EXT,
    in_reserved_corner,
)

MAGIC = "ACP"
VERSION = 1
MAX_FILE_BYTES = 256 * 1024
COORD_LIMIT = 100_000


class ProfileError(LocalizedError):
    """A profile cannot be used; str(error) is a friendly message in the UI language."""


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _checksum(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_data(data) -> tuple[list[tuple[int, int, int]], dict]:
    if not isinstance(data, dict):
        raise ProfileError("p_damaged")

    raw_points = data.get("points")
    if not isinstance(raw_points, list) or not raw_points:
        raise ProfileError("p_nopoints")
    if len(raw_points) > MAX_POINTS:
        raise ProfileError("p_toomany", max=MAX_POINTS)

    points: list[tuple[int, int, int]] = []
    for number, item in enumerate(raw_points, start=1):
        if not isinstance(item, dict):
            raise ProfileError("p_point_bad", n=number)
        x, y, delay = item.get("x"), item.get("y"), item.get("delay")
        if not (_is_int(x) and _is_int(y) and _is_int(delay)):
            raise ProfileError("p_point_bad", n=number)
        if abs(x) > COORD_LIMIT or abs(y) > COORD_LIMIT:
            raise ProfileError("p_point_bad", n=number)
        if in_reserved_corner(x, y):
            raise ProfileError("p_point_corner", n=number)
        if not MIN_DELAY_MS <= delay <= MAX_DELAY_MS:
            raise ProfileError("p_point_bad", n=number)
        points.append((x, y, delay))

    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        raise ProfileError("p_settings")
    human = settings.get("human_mode", False)
    cycles = settings.get("cycle_limit", 0)
    if not isinstance(human, bool):
        raise ProfileError("p_settings")
    if not _is_int(cycles) or not 0 <= cycles <= MAX_CYCLES:
        raise ProfileError("p_settings")

    return points, {"human_mode": human, "cycle_limit": cycles}


def save_profile(path, points, human_mode: bool = False, cycle_limit: int = 0) -> str:
    """Write a profile and return the final path (the .acp extension is enforced)."""
    path = str(path)
    if not path.lower().endswith(PROFILE_EXT):
        path += PROFILE_EXT

    data = {
        "points": [{"x": int(x), "y": int(y), "delay": int(d)} for x, y, d in points],
        "settings": {"human_mode": bool(human_mode), "cycle_limit": int(cycle_limit)},
    }
    _validate_data(data)  # never write a file we could not load again
    doc = {"magic": MAGIC, "version": VERSION, "checksum": _checksum(data), "data": data}

    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, indent=2)
        os.replace(tmp, path)  # atomic: no half-written profile on a crash
    except OSError as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ProfileError("p_write", err=exc.strerror or str(exc)) from exc
    return path


def load_profile(path) -> tuple[list[tuple[int, int, int]], dict]:
    """Return (points, settings). Raises ProfileError for anything unusable."""
    file = Path(path)
    if file.suffix.lower() != PROFILE_EXT:
        raise ProfileError("p_ext", ext=PROFILE_EXT)

    try:
        size = file.stat().st_size
    except OSError:
        raise ProfileError("p_unreadable") from None
    if size > MAX_FILE_BYTES:
        raise ProfileError("p_toolarge")

    try:
        doc = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        raise ProfileError("p_damaged") from None

    if not isinstance(doc, dict) or doc.get("magic") != MAGIC:
        raise ProfileError("p_damaged")
    version = doc.get("version")
    if not _is_int(version) or version < 1:
        raise ProfileError("p_damaged")
    if version > VERSION:
        raise ProfileError("p_newer")

    data = doc.get("data")
    if not isinstance(data, dict) or doc.get("checksum") != _checksum(data):
        raise ProfileError("p_modified")

    return _validate_data(data)
