from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Optional

from core.profiles import ProfileContext


@dataclass
class ProfileSnapshot:
    base: dict
    skills: dict
    points: dict
    meta: dict


class ProfileUnitOfWork:
    """
    Phase-1 UoW (minimal but useful):
    - begin(): snapshot current ctx in-memory state
    - rollback(): restore from snapshot (in-memory only)
    - commit(): save_all to disk

    Notes:
    - This does NOT yet unify "dirty" across pages; pages still manage their own dirty flags.
    - Later we will move all mutations to services and drive dirty from UoW.
    """

    def __init__(self, ctx: ProfileContext) -> None:
        self._ctx: ProfileContext = ctx
        self._snap: Optional[ProfileSnapshot] = None

    @property
    def ctx(self) -> ProfileContext:
        return self._ctx

    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        self._snap = None

    def begin(self) -> None:
        self._snap = ProfileSnapshot(
            base=copy.deepcopy(self._ctx.base.to_dict()),
            skills=copy.deepcopy(self._ctx.skills.to_dict()),
            points=copy.deepcopy(self._ctx.points.to_dict()),
            meta=copy.deepcopy(self._ctx.meta.to_dict()),
        )

    def rollback(self) -> None:
        if self._snap is None:
            return
        # restore objects (keep repos/idgen references in ctx)
        self._ctx.base = self._ctx.base.__class__.from_dict(copy.deepcopy(self._snap.base))
        self._ctx.skills = self._ctx.skills.__class__.from_dict(copy.deepcopy(self._snap.skills))
        self._ctx.points = self._ctx.points.__class__.from_dict(copy.deepcopy(self._snap.points))
        self._ctx.meta = self._ctx.meta.__class__.from_dict(copy.deepcopy(self._snap.meta))

    def commit(self, *, backup: bool = True) -> None:
        self._ctx.save_all(backup=backup)
        # refresh snapshot after successful commit
        self.begin()