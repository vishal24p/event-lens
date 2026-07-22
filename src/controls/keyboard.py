"""Keyboard listener using msvcrt.

Runs in its own thread, posts discrete action names onto a callback.
ENTER -> "accept"
ESC   -> "discard"
Q/q   -> "stop"
Other keys are ignored. Special-key prefixes (e.g. arrow keys) are consumed
without triggering an action.
"""
from __future__ import annotations

import sys
import threading
from typing import Callable, Optional

try:
    import msvcrt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - non-Windows fallback
    msvcrt = None  # type: ignore[assignment]


Action = str  # "accept" | "discard" | "stop"


def _read_one() -> Optional[str]:
    """Read one logical key from the console. Return None on EOF/empty.

    Returns the logical key name we care about, or None to ignore.
    """
    if msvcrt is None:
        return None
    ch = msvcrt.getwch()
    if ch == "" or ch is None:
        return None
    if ch in ("\r", "\n"):
        return "accept"
    if ch == "\x1b":
        return "discard"
    if ch in ("q", "Q"):
        return "stop"
    # Special-key prefix on Windows is typically \x00 or \xe0 followed by a code.
    if ch in ("\x00", "\xe0"):
        try:
            _ = msvcrt.getwch()  # consume the second byte
        except Exception:
            pass
        return None
    return None


class KeyboardListener:
    """Spawn a thread that fires `on_action` for ENTER/ESC/Q."""

    def __init__(self, on_action: Callable[[Action], None]) -> None:
        self._on_action = on_action
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if msvcrt is None:
            print(
                "[keyboard] msvcrt unavailable; keyboard controls disabled.",
                file=sys.stderr,
                flush=True,
            )
            return
        self._thread = threading.Thread(
            target=self._loop, name="keyboard-listener", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # Cannot interrupt a blocking msvcrt.getwch reliably; daemon thread dies on exit.

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                key = _read_one()
            except Exception:  # pragma: no cover - defensive
                return
            if key is None:
                continue
            try:
                self._on_action(key)
            except Exception as e:  # pragma: no cover
                print(f"[keyboard] action handler error: {e}", flush=True)
