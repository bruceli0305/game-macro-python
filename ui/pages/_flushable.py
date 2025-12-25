from __future__ import annotations

from typing import Protocol


class FlushablePage(Protocol):
    def flush_to_model(self) -> None: ...