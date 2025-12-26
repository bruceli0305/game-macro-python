# File: core/store/app_store.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Set

from core.models.base import BaseFile
from core.models.meta import ProfileMeta
from core.models.point import PointsFile
from core.models.skill import SkillsFile
from core.profiles import ProfileContext

Part = Literal["base", "skills", "points", "meta"]


@dataclass(frozen=True)
class Snapshot:
    base: Dict[str, Any]
    skills: Dict[str, Any]
    points: Dict[str, Any]
    meta: Dict[str, Any]


class AppStore:
    """
    Central state holder for the current profile.

    Responsibilities:
    - hold current ProfileContext
    - track dirty parts
    - maintain a committed snapshot for rollback
    - commit selected parts to disk in stable order
    """

    def __init__(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        self._dirty: Set[Part] = set()
        self._snap = self._take_snapshot()

    @property
    def ctx(self) -> ProfileContext:
        return self._ctx

    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        self._dirty.clear()
        self._snap = self._take_snapshot()

    # ---------- dirty ----------
    def dirty_parts(self) -> Set[Part]:
        return set(self._dirty)

    def is_dirty(self) -> bool:
        return bool(self._dirty)

    def mark_dirty(self, part: Part) -> None:
        self._dirty.add(part)

    def clear_dirty(self, part: Part) -> None:
        self._dirty.discard(part)

    def clear_all_dirty(self) -> None:
        self._dirty.clear()

    # ---------- snapshot ----------
    def refresh_snapshot(self, *, parts: Optional[Set[Part]] = None) -> None:
        """
        Refresh snapshot for selected parts (or all if None).
        Does NOT change dirty flags.
        """
        ctx = self._ctx
        old = self._snap
        target = set(parts) if parts is not None else {"base", "skills", "points", "meta"}

        base = ctx.base.to_dict() if "base" in target else old.base
        skills = ctx.skills.to_dict() if "skills" in target else old.skills
        points = ctx.points.to_dict() if "points" in target else old.points
        meta = ctx.meta.to_dict() if "meta" in target else old.meta

        self._snap = Snapshot(base=base, skills=skills, points=points, meta=meta)

    def rollback(self) -> None:
        """
        Roll back in-memory objects to last committed snapshot (best-effort).
        Does NOT touch disk.
        """
        ctx = self._ctx
        snap = self._snap

        try:
            ctx.base = BaseFile.from_dict(snap.base)
        except Exception:
            pass
        try:
            ctx.skills = SkillsFile.from_dict(snap.skills)
        except Exception:
            pass
        try:
            ctx.points = PointsFile.from_dict(snap.points)
        except Exception:
            pass
        try:
            ctx.meta = ProfileMeta.from_dict(snap.meta)
        except Exception:
            pass

        self._dirty.clear()

    def commit(
        self,
        *,
        parts: Optional[Set[Part]] = None,
        backup: Optional[bool] = None,
        touch_meta: bool = True,
    ) -> None:
        """
        Commit changes to disk.

        - If parts is None: commit all currently dirty parts.
        - touch_meta=True: also save meta.json (updated_at advances).
        - touch_meta=False: do not save meta.json.
        """
        target: Set[Part] = set(self._dirty) if parts is None else set(parts)
        if not target:
            return

        ctx = self._ctx

        if backup is None:
            try:
                backup = bool(ctx.base.io.backup_on_save)
            except Exception:
                backup = True

        # stable order
        if "base" in target:
            ctx.base_repo.save(ctx.base, backup=bool(backup))
            self._dirty.discard("base")

        if "skills" in target:
            ctx.skills_repo.save(ctx.skills, backup=bool(backup))
            self._dirty.discard("skills")

        if "points" in target:
            ctx.points_repo.save(ctx.points, backup=bool(backup))
            self._dirty.discard("points")

        if touch_meta:
            ctx.meta_repo.save(ctx.meta, backup=bool(backup))
            self._dirty.discard("meta")

        # snapshot becomes the new committed state
        self._snap = self._take_snapshot()

    def _take_snapshot(self) -> Snapshot:
        ctx = self._ctx
        return Snapshot(
            base=ctx.base.to_dict(),
            skills=ctx.skills.to_dict(),
            points=ctx.points.to_dict(),
            meta=ctx.meta.to_dict(),
        )