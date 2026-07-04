"""
Надёжное чтение клавиш из терминала.
"""

from collections import deque
from dataclasses import dataclass
import os
import select
import sys
import termios
import time
import tty
from typing import TextIO


@dataclass(frozen=True)
class KeyEvent:
    name: str
    char: str = ""
    sequence: str = ""


class KeyboardReader:
    """
    Читает терминальные escape-последовательности как цельные события.
    """

    READ_SIZE = 64
    SEQUENCE_TIMEOUT = 0.05

    def __init__(self, input_stream: TextIO | None = None) -> None:
        self.input_stream = input_stream or sys.stdin
        self.fd = self.input_stream.fileno()
        self.settings: list[int | bytes] | None = None
        self.buffer: deque[int] = deque()

    def __enter__(self) -> "KeyboardReader":
        if self.input_stream.isatty():
            self.settings = termios.tcgetattr(self.input_stream)
            tty.setcbreak(self.input_stream)
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self.settings is not None and self.input_stream.isatty():
            termios.tcsetattr(self.input_stream, termios.TCSADRAIN, self.settings)
            self.settings = None

    def read(self, timeout: float) -> KeyEvent | None:
        if not self.input_stream.isatty():
            time.sleep(timeout)
            return None

        if not self.buffer:
            readable, _, _ = select.select([self.input_stream], [], [], timeout)
            if not readable:
                return None
            self._read_available()

        if not self.buffer:
            return None

        return self._parse_event()

    def _read_available(self) -> None:
        self.buffer.extend(os.read(self.fd, self.READ_SIZE))
        while select.select([self.input_stream], [], [], self.SEQUENCE_TIMEOUT)[0]:
            self.buffer.extend(os.read(self.fd, self.READ_SIZE))

    def _parse_event(self) -> KeyEvent | None:
        byte = self.buffer.popleft()
        if byte == 0x1B:
            return self._parse_escape_sequence()
        if byte == 0x09:
            return KeyEvent("TAB", sequence="\t")
        if byte in {0x0A, 0x0D}:
            return KeyEvent("ENTER", sequence=chr(byte))

        char = chr(byte)
        if char.isalpha():
            return KeyEvent(char.upper(), char=char, sequence=char)
        return KeyEvent(char, char=char, sequence=char)

    def _parse_escape_sequence(self) -> KeyEvent:
        self._fill_sequence_tail()
        if not self.buffer:
            return KeyEvent("ESC", sequence="\x1b")

        prefix = self.buffer.popleft()
        if prefix == ord("["):
            return self._parse_csi_sequence()
        if prefix == ord("O"):
            return self._parse_ss3_sequence()

        sequence = "\x1b" + chr(prefix)
        return KeyEvent("ESC", sequence=sequence)

    def _parse_csi_sequence(self) -> KeyEvent:
        payload: list[int] = []
        while True:
            self._fill_sequence_tail()
            if not self.buffer:
                sequence = "\x1b[" + bytes(payload).decode(errors="ignore")
                return KeyEvent("ESC", sequence=sequence)

            byte = self.buffer.popleft()
            payload.append(byte)
            if 0x40 <= byte <= 0x7E:
                break

        text = bytes(payload).decode(errors="ignore")
        mapping = {
            "A": "UP",
            "B": "DOWN",
            "C": "RIGHT",
            "D": "LEFT",
            "24~": "F12",
        }
        if text.startswith("24") and text.endswith("~"):
            return KeyEvent("F12", sequence="\x1b[" + text)
        return KeyEvent(mapping.get(text, "ESC"), sequence="\x1b[" + text)

    def _parse_ss3_sequence(self) -> KeyEvent:
        self._fill_sequence_tail()
        if not self.buffer:
            return KeyEvent("ESC", sequence="\x1bO")

        byte = self.buffer.popleft()
        char = chr(byte)
        mapping = {
            "A": "UP",
            "B": "DOWN",
            "C": "RIGHT",
            "D": "LEFT",
        }
        return KeyEvent(mapping.get(char, "ESC"), sequence="\x1bO" + char)

    def _fill_sequence_tail(self) -> None:
        if self.buffer:
            return
        readable, _, _ = select.select(
            [self.input_stream],
            [],
            [],
            self.SEQUENCE_TIMEOUT,
        )
        if readable:
            self.buffer.extend(os.read(self.fd, self.READ_SIZE))
