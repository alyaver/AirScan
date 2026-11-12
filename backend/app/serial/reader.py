"""Background line reader for AirScan's newline-delimited serial protocol."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock, Thread, current_thread
from time import sleep
from typing import Any, Callable


@dataclass(frozen=True)
class SerialReaderStatistics:
    """Non-fatal diagnostics collected while reading one serial connection."""

    running: bool
    received_lines: int
    decode_errors: int
    handler_errors: int
    read_errors: int


class SerialLineReader:
    """Read complete UTF-8 lines without allowing one bad line to stop reading."""

    def __init__(
        self,
        connection: Any,
        line_handler: Callable[[str], None],
        error_handler: Callable[[Exception], None],
    ) -> None:
        self._connection = connection
        self._line_handler = line_handler
        self._error_handler = error_handler
        self._stop_requested = Event()
        self._lock = Lock()
        self._buffer = bytearray()
        self._thread: Thread | None = None
        self._running = False
        self._received_lines = 0
        self._decode_errors = 0
        self._handler_errors = 0
        self._read_errors = 0

    def start(self) -> None:
        """Start the one reader thread for this already-open serial connection."""

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._stop_requested.clear()
            self._running = True
            self._thread = Thread(
                target=self._run,
                name="airscan-serial-reader",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Request shutdown and wait briefly unless called by the reader itself."""

        self._stop_requested.set()
        with self._lock:
            thread = self._thread

        if thread is not None and thread is not current_thread():
            thread.join(timeout=2)

    def statistics(self) -> SerialReaderStatistics:
        """Return a consistent snapshot of reader health counters."""

        with self._lock:
            return SerialReaderStatistics(
                running=self._running,
                received_lines=self._received_lines,
                decode_errors=self._decode_errors,
                handler_errors=self._handler_errors,
                read_errors=self._read_errors,
            )

    def _run(self) -> None:
        try:
            while not self._stop_requested.is_set():
                try:
                    chunk = self._connection.read_until(b"\n")
                except Exception as error:  # Serial drivers use platform-specific errors.
                    self._record_read_error()
                    self._error_handler(error)
                    break

                if not chunk:
                    # pyserial normally waits for its configured timeout. This small pause
                    # also keeps mocked immediate timeouts from becoming a busy loop.
                    sleep(0.01)
                    continue

                self._buffer.extend(chunk)
                self._dispatch_complete_lines()
        finally:
            with self._lock:
                self._running = False

    def _dispatch_complete_lines(self) -> None:
        while True:
            try:
                newline_index = self._buffer.index(ord("\n"))
            except ValueError:
                return

            raw_line = bytes(self._buffer[:newline_index])
            del self._buffer[: newline_index + 1]
            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]
            if not raw_line:
                continue

            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError:
                with self._lock:
                    self._decode_errors += 1
                continue

            try:
                self._line_handler(line)
            except Exception:
                with self._lock:
                    self._handler_errors += 1
                continue

            with self._lock:
                self._received_lines += 1

    def _record_read_error(self) -> None:
        with self._lock:
            self._read_errors += 1