"""Click engine: runs on its own thread so the UI and hotkeys stay responsive."""
from __future__ import annotations

import ctypes
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import pyautogui

from common import DEFAULT_DELAY_MS, MIN_DELAY_MS, LocalizedError, in_kill_corner

# pyautogui defaults would throttle fast clicking (0.1 s pause after every call)
# and its own fail-safe only raises an exception, so both are replaced by our
# own kill-switch below.
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False
pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0

JITTER_PX = 3                    # Human Mode: cursor offset of up to +-3 px
DELAY_JITTER_FRACTION = 0.15     # Human Mode: delay varies by +-15 % ...
DELAY_JITTER_MIN_MS = 2.0        # ... but never by less than +-2 ms
PREVIEW_HOP_SECONDS = 0.7        # Preview Route: time to glide between points
PREVIEW_DWELL_SECONDS = 0.35     # Preview Route: pause on every point
KILL_CHECK_INTERVAL = 0.02       # how often the corner is checked while waiting
GRAB_WINDOW_MASK = 0xFF          # look at the last 8 iterations ...
GRAB_THRESHOLD = 3               # ... and yield if the user moved the mouse in 3 of them
GRAB_STILL_SECONDS = 0.6         # resume after the mouse has been still this long


class EngineError(LocalizedError):
    """Raised when a run cannot be started (message is shown to the user)."""


@dataclass
class RunConfig:
    mode: str                                   # "single" | "multi" | "preview"
    interval_ms: int = DEFAULT_DELAY_MS         # single mode
    points: list[tuple[int, int, int]] = field(default_factory=list)  # (x, y, delay_ms)
    cycle_limit: int = 0                        # 0 = unlimited
    human_mode: bool = False


def _timer_resolution(enable: bool) -> None:
    """Ask Windows for a 1 ms timer so short delays are honoured."""
    try:
        winmm = ctypes.windll.winmm  # type: ignore[attr-defined]
        (winmm.timeBeginPeriod if enable else winmm.timeEndPeriod)(1)
    except Exception:
        pass


def _pos() -> tuple[int, int]:
    p = pyautogui.position()
    return int(p[0]), int(p[1])


def _humanize_delay(ms: float) -> float:
    amp = max(DELAY_JITTER_MIN_MS, ms * DELAY_JITTER_FRACTION)
    return max(float(MIN_DELAY_MS), ms + random.uniform(-amp, amp))


class ClickEngine:
    def __init__(self, on_finish: Callable[[str], None]):
        # on_finish(reason) is called from the worker thread; reason is
        # "completed", "stopped" or "error: <message>".
        self._on_finish = on_finish
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.cycles = 0
        self.user_override = False   # True while paused because the user grabbed the mouse

    # ------------------------------------------------------------------ control
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, cfg: RunConfig) -> None:
        if self.running:
            raise EngineError("en_still_stopping")
        self._validate(cfg)
        x, y = _pos()
        if in_kill_corner(x, y):
            raise EngineError("en_corner")
        self._stop.clear()
        self.cycles = 0
        self.user_override = False
        self._thread = threading.Thread(target=self._run, args=(cfg,), name="clicker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _validate(cfg: RunConfig) -> None:
        if cfg.mode not in ("single", "multi", "preview"):
            raise ValueError(f"unknown mode: {cfg.mode}")
        if cfg.mode == "single":
            if cfg.interval_ms < MIN_DELAY_MS:
                raise ValueError("interval below minimum")
        elif not cfg.points:
            raise EngineError("no_points")

    # --------------------------------------------------------------- worker side
    def _run(self, cfg: RunConfig) -> None:
        reason = "stopped"
        _timer_resolution(True)
        try:
            if cfg.mode == "single":
                done = self._run_single(cfg)
            elif cfg.mode == "multi":
                done = self._run_multi(cfg)
            else:
                done = self._run_preview(cfg)
            reason = "completed" if done else "stopped"
        except Exception as exc:  # the worker must never die silently
            reason = f"error: {exc}"
        finally:
            _timer_resolution(False)
            try:
                self._on_finish(reason)
            except Exception:
                pass

    def _check_kill(self, pos: tuple[int, int] | None = None) -> None:
        x, y = pos if pos is not None else _pos()
        if in_kill_corner(x, y):
            os._exit(0)  # instant, unconditional force close

    def _wait(self, seconds: float) -> bool:
        """Sleep for `seconds`. Returns False if a stop was requested meanwhile."""
        deadline = time.perf_counter() + seconds
        next_kill_check = 0.0
        while True:
            if self._stop.is_set():
                return False
            now = time.perf_counter()
            if now >= next_kill_check:
                self._check_kill()
                next_kill_check = now + KILL_CHECK_INTERVAL
            remaining = deadline - now
            if remaining <= 0:
                return True
            if remaining > 0.002:
                time.sleep(min(remaining - 0.001, 0.01))
            else:
                time.sleep(0)  # short spin for the last ~2 ms

    # ------------------------------------------------------------------- modes
    def _run_single(self, cfg: RunConfig) -> bool:
        limit = cfg.cycle_limit
        while True:
            if self._stop.is_set():
                return False
            self._check_kill()
            pyautogui.click()  # left click at the current cursor position
            self.cycles += 1
            if limit and self.cycles >= limit:
                return True
            delay = _humanize_delay(cfg.interval_ms) if cfg.human_mode else cfg.interval_ms
            if not self._wait(delay / 1000.0):
                return False

    def _run_multi(self, cfg: RunConfig) -> bool:
        points = cfg.points
        limit = cfg.cycle_limit
        expected: tuple[int, int] | None = None  # where *we* left the cursor last
        recent = 0                               # bit history: 1 = user moved the cursor
        i = 0
        while True:
            if self._stop.is_set():
                return False
            px, py, delay = points[i]

            cur = _pos()
            self._check_kill(cur)
            if expected is not None:
                recent = ((recent << 1) | int(cur != expected)) & GRAB_WINDOW_MASK
                if bin(recent).count("1") >= GRAB_THRESHOLD:
                    # The user is physically moving the mouse while we keep
                    # teleporting it back. Stop fighting so the corner
                    # kill-switch (or F8) can be reached.
                    self.user_override = True
                    try:
                        if not self._yield_to_user():
                            return False
                    finally:
                        self.user_override = False
                    expected, recent = None, 0
                    continue

            tx, ty = px, py
            if cfg.human_mode:
                tx += random.randint(-JITTER_PX, JITTER_PX)
                ty += random.randint(-JITTER_PX, JITTER_PX)
            pyautogui.click(tx, ty)
            expected = _pos()

            if i == len(points) - 1:
                self.cycles += 1
                if limit and self.cycles >= limit:
                    return True
            wait_ms = _humanize_delay(delay) if cfg.human_mode else delay
            if not self._wait(wait_ms / 1000.0):
                return False
            i = (i + 1) % len(points)

    def _yield_to_user(self) -> bool:
        """Leave the cursor alone until it has been still for a while.
        Moving it into the top-left corner meanwhile force-closes the app."""
        last = _pos()
        still_since = time.perf_counter()
        while True:
            if self._stop.is_set():
                return False
            time.sleep(0.02)
            cur = _pos()
            self._check_kill(cur)
            now = time.perf_counter()
            if cur != last:
                last, still_since = cur, now
            elif now - still_since >= GRAB_STILL_SECONDS:
                return True

    def _run_preview(self, cfg: RunConfig) -> bool:
        """Dry run: visit every point slowly, without clicking."""
        for px, py, _delay in cfg.points:
            if not self._glide_to(px, py, PREVIEW_HOP_SECONDS):
                return False
            if not self._wait(PREVIEW_DWELL_SECONDS):
                return False
        return True

    def _glide_to(self, tx: int, ty: int, duration: float) -> bool:
        sx, sy = _pos()
        steps = max(1, int(duration / 0.01))
        last_set = (sx, sy)
        for n in range(1, steps + 1):
            if self._stop.is_set():
                return False
            cur = _pos()
            if cur != last_set:  # somebody else moved the cursor
                self._check_kill(cur)
                if abs(cur[0] - last_set[0]) + abs(cur[1] - last_set[1]) > 25:
                    return False  # user took over the mouse: end the preview
            t = n / steps
            t = t * t * (3 - 2 * t)  # smoothstep easing
            pyautogui.moveTo(round(sx + (tx - sx) * t), round(sy + (ty - sy) * t))
            last_set = _pos()
            time.sleep(0.01)
        return True
