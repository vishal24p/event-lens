"""Keyboard mapping tests (without a real terminal)."""
from __future__ import annotations

from unittest import mock

from src.controls.keyboard import _read_one


def test_read_one_maps_enter_to_accept():
    with mock.patch("src.controls.keyboard.msvcrt") as m:
        m.getwch.return_value = "\r"
        assert _read_one() == "accept"


def test_read_one_maps_esc_to_discard():
    with mock.patch("src.controls.keyboard.msvcrt") as m:
        m.getwch.return_value = "\x1b"
        assert _read_one() == "discard"


def test_read_one_maps_q_to_stop():
    with mock.patch("src.controls.keyboard.msvcrt") as m:
        m.getwch.return_value = "q"
        assert _read_one() == "stop"
        m.getwch.return_value = "Q"
        assert _read_one() == "stop"


def test_read_one_consumes_special_prefix_and_returns_none():
    with mock.patch("src.controls.keyboard.msvcrt") as m:
        m.getwch.side_effect = ["\x00", "H"]  # arrow key
        assert _read_one() is None
        assert m.getwch.call_count == 2


def test_read_one_ignores_other_chars():
    with mock.patch("src.controls.keyboard.msvcrt") as m:
        m.getwch.return_value = "x"
        assert _read_one() is None
