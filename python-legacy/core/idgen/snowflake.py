from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Final


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class SnowflakeLayout:
    """
    A classic Snowflake-style layout:
      - timestamp: 41 bits (ms since custom epoch)
      - worker_id: 10 bits
      - sequence:  12 bits
    Total: 63 bits (fits in signed int64 positive range).
    """
    timestamp_bits: int = 41
    worker_bits: int = 10
    sequence_bits: int = 12

    @property
    def max_worker_id(self) -> int:
        return (1 << self.worker_bits) - 1

    @property
    def max_sequence(self) -> int:
        return (1 << self.sequence_bits) - 1

    @property
    def worker_shift(self) -> int:
        return self.sequence_bits

    @property
    def timestamp_shift(self) -> int:
        return self.worker_bits + self.sequence_bits


class SnowflakeGenerator:
    """
    Thread-safe Snowflake ID generator.

    Notes:
    - Returns IDs as *string* to avoid precision issues in external JSON tooling.
    - If system clock moves backwards, we clamp to last timestamp (monotonic within process).
    """

    _layout: Final[SnowflakeLayout] = SnowflakeLayout()

    def __init__(self, *, worker_id: int, epoch_ms: int = 1704067200000) -> None:
        """
        epoch_ms default: 2024-01-01T00:00:00Z in milliseconds.
        """
        if worker_id < 0 or worker_id > self._layout.max_worker_id:
            raise ValueError(f"worker_id must be in [0, {self._layout.max_worker_id}]")

        self._worker_id = worker_id
        self._epoch_ms = epoch_ms

        self._lock = threading.Lock()
        self._last_ts = -1
        self._sequence = 0

    @property
    def worker_id(self) -> int:
        return self._worker_id

    @property
    def epoch_ms(self) -> int:
        return self._epoch_ms

    def next_id(self) -> str:
        with self._lock:
            ts = _now_ms()

            # clamp if clock moved backwards
            if ts < self._last_ts:
                ts = self._last_ts

            if ts == self._last_ts:
                self._sequence = (self._sequence + 1) & self._layout.max_sequence
                if self._sequence == 0:
                    ts = self._wait_next_ms(self._last_ts)
            else:
                self._sequence = 0

            self._last_ts = ts

            elapsed = ts - self._epoch_ms
            if elapsed < 0:
                # epoch set in the future; treat as 0 to avoid negative IDs
                elapsed = 0

            value = (
                (elapsed << self._layout.timestamp_shift)
                | (self._worker_id << self._layout.worker_shift)
                | self._sequence
            )
            return str(value)

    def _wait_next_ms(self, last_ts: int) -> int:
        ts = _now_ms()
        while ts <= last_ts:
            # short sleep to reduce CPU spin; still precise enough for ms boundaries
            time.sleep(0.0001)
            ts = _now_ms()
        return ts