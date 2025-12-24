from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationOutcome:
    data: Dict[str, Any]
    changed: bool
    from_version: int
    to_version: int
    notes: str = ""