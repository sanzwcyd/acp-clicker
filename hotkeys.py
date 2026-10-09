"""Global hotkeys that keep working while another program has the focus."""
from __future__ import annotations

from typing import Callable

from pynput import keyboard


class HotkeyListener:
    def __init__(self, bindings: dict):
        # bindings: {keyboard.Key.f8: callback, ...}. Callbacks run on pynput's
        # hook thread, so they must be quick (the app just pushes to a queue).
        self._bindings: dict = dict(bindings)
        self._down: set = set()
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        callback: Callable[[], None] | None = self._bindings.get(key)
        if callback is None or key in self._down:  # ignore OS key-repeat while held
            return
        self._down.add(key)
        try:
            callback()
        except Exception:
            pass  # an exception would stop pynput's listener

    def _on_release(self, key) -> None:
        self._down.discard(key)
