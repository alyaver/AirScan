from __future__ import annotations

from collections import deque
from time import sleep

from app.serial.reader import SerialLineReader


class FakeReadableConnection:
    def __init__(self, chunks: list[bytes | Exception]) -> None:
        self._chunks = deque(chunks)
        self.is_open = True

    def read_until(self, _: bytes) -> bytes:
        if self._chunks:
            next_chunk = self._chunks.popleft()
            if isinstance(next_chunk, Exception):
                raise next_chunk
            return next_chunk
        return b""


def wait_for(predicate: object) -> None:
    for _ in range(50):
        if callable(predicate) and predicate():
            return
        sleep(0.01)
    raise AssertionError("Timed out waiting for reader activity.")


def test_reader_forwards_complete_utf8_lines_and_accepts_crlf() -> None:
    received: list[str] = []
    reader = SerialLineReader(
        FakeReadableConnection([b'{"first":', b'1}\r\n{"second":2}\n']),
        received.append,
        lambda _: None,
    )

    reader.start()
    wait_for(lambda: len(received) == 2)
    reader.stop()

    assert received == ['{"first":1}', '{"second":2}']
    assert reader.statistics().received_lines == 2


def test_reader_ignores_invalid_utf8_and_continues_to_the_next_line() -> None:
    received: list[str] = []
    reader = SerialLineReader(
        FakeReadableConnection([b"\xff\n", b'{"valid":true}\n']),
        received.append,
        lambda _: None,
    )

    reader.start()
    wait_for(lambda: received == ['{"valid":true}'])
    reader.stop()

    assert reader.statistics().decode_errors == 1


def test_reader_continues_when_the_line_handler_rejects_a_line() -> None:
    received: list[str] = []

    def handler(line: str) -> None:
        if line == "bad":
            raise ValueError("fixture parser failure")
        received.append(line)

    reader = SerialLineReader(
        FakeReadableConnection([b"bad\n", b"good\n"]),
        handler,
        lambda _: None,
    )

    reader.start()
    wait_for(lambda: received == ["good"])
    reader.stop()

    assert reader.statistics().handler_errors == 1
    assert reader.statistics().received_lines == 1


def test_reader_reports_a_disconnect_and_stops_cleanly() -> None:
    errors: list[Exception] = []
    reader = SerialLineReader(
        FakeReadableConnection([OSError("device disconnected")]),
        lambda _: None,
        errors.append,
    )

    reader.start()
    wait_for(lambda: bool(errors))
    wait_for(lambda: not reader.statistics().running)

    assert str(errors[0]) == "device disconnected"
    assert reader.statistics().read_errors == 1


def test_reader_stops_when_requested_during_repeated_timeouts() -> None:
    reader = SerialLineReader(
        FakeReadableConnection([]),
        lambda _: None,
        lambda _: None,
    )

    reader.start()
    wait_for(lambda: reader.statistics().running)
    reader.stop()

    assert reader.statistics().running is False