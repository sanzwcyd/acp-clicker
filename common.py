"""Constants and small helpers shared by every module (no GUI / OS imports here)."""

APP_NAME = "Auto Clicker"
PROFILE_EXT = ".acp"

MIN_DELAY_MS = 1
MAX_DELAY_MS = 3_600_000  # 1 hour
DEFAULT_DELAY_MS = 100
MAX_POINTS = 200
MAX_CYCLES = 1_000_000

# Emergency kill-switch: cursor inside this top-left square of the primary
# screen => the app force-closes.
CORNER_KILL_PX = 2
# Recorded / imported points must stay clear of the kill zone
# (Human Mode can add +-3 px of jitter).
CORNER_RESERVED_PX = 12


class LocalizedError(Exception):
    """An error whose message is looked up in the current UI language when displayed."""

    def __init__(self, key: str, **params):
        super().__init__(key)
        self.key = key
        self.params = params

    def __str__(self) -> str:
        from i18n import t  # imported lazily: i18n has no dependency on this module

        return t(self.key, **self.params)


class InputError(LocalizedError, ValueError):
    """Invalid text typed into a number field."""


def in_kill_corner(x: int, y: int) -> bool:
    return 0 <= x <= CORNER_KILL_PX and 0 <= y <= CORNER_KILL_PX


def in_reserved_corner(x: int, y: int) -> bool:
    return 0 <= x <= CORNER_RESERVED_PX and 0 <= y <= CORNER_RESERVED_PX


def _is_plain_number(text: str) -> bool:
    # str.isdigit() also accepts characters such as "²" or Arabic-Indic digits,
    # so ASCII is checked explicitly.
    return text.isascii() and text.isdigit()


def parse_ms(text: str, label: str = "Delay") -> int:
    """Parse a millisecond value typed by the user. Raises InputError (a ValueError)."""
    text = (text or "").strip()
    if not text:
        raise InputError("e_empty", label=label)
    if not _is_plain_number(text):
        raise InputError("e_whole", label=label)
    value = int(text)
    if value < MIN_DELAY_MS:
        raise InputError("e_min", label=label, min=MIN_DELAY_MS)
    if value > MAX_DELAY_MS:
        raise InputError("e_max", label=label, max=MAX_DELAY_MS)
    return value


def parse_cycles(text: str) -> int:
    """Cycle limit: blank or 0 means unlimited."""
    text = (text or "").strip()
    if not text:
        return 0
    if not _is_plain_number(text):
        raise InputError("e_cycles_whole")
    value = int(text)
    if value > MAX_CYCLES:
        raise InputError("e_cycles_max", max=MAX_CYCLES)
    return value
