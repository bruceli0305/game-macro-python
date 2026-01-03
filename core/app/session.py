# core/app/session.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Literal, Optional, Set

import logging

from core.models.base import BaseFile
from core.models.meta import ProfileMeta
from core.models.point import PointsFile
from core.models.skill import SkillsFile
from core.profiles import ProfileContext
from rotation_editor.core.models import RotationsFile
from rotation_editor.core.storage import save_rotations

log = logging.getLogger(__name__)

Part = Literal["base", "skills", "points", "meta", "rotations"]


@dataclass(frozen=True)
class Snapshot:
    """
    用于 rollback 的内存快照（按部分拆开）。
    """
    base: Dict[str, Any]
    skills: Dict[str, Any]
    points: Dict[str, Any]
    meta: Dict[str, Any]
    rotations: Dict[str, Any]


class ProfileSession:
    """
    Profile 工作单元 + 脏标记：

    - 持有 ProfileContext（其中包含 Profile 聚合和旧的 repo）
    - 维护 dirty_parts / snapshot
    - commit() 仍按旧逻辑分别调用 BaseRepo/SkillsRepo/PointsRepo/MetaRepo/save_rotations
      ——后续会统一改为 ProfileRepository + 单一 profile.json。
    - subscribe_dirty(fn)：供 UI 订阅脏状态变更。
    """

    def __init__(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        self._dirty: Set[Part] = set()
        self._snap = self._take_snapshot()
        self._listeners: list[Callable[[Set[Part]], None]] = []

    # ---------- 基本属性 ----------

    @property
    def ctx(self) -> ProfileContext:
        return self._ctx

    @property
    def profile(self):
        return self._ctx.profile

    # ---------- 上下文切换 ----------

    def set_context(self, ctx: ProfileContext) -> None:
        """
        切换到另一个 ProfileContext（例如切换 profile）。
        """
        self._ctx = ctx
        self._dirty.clear()
        self._snap = self._take_snapshot()
        self._emit_dirty()

    # ---------- 订阅脏状态 ----------

    def subscribe_dirty(self, fn: Callable[[Set[Part]], None]) -> Callable[[], None]:
        self._listeners.append(fn)

        def _unsub() -> None:
            try:
                self._listeners.remove(fn)
            except ValueError:
                pass

        return _unsub

    def _emit_dirty(self) -> None:
        parts = set(self._dirty)
        for fn in list(self._listeners):
            try:
                fn(parts)
            except Exception:
                log.exception("dirty listener failed")

    def emit_dirty(self) -> None:
        """
        主动向所有订阅者广播当前脏状态（不改变任何状态）。
        """
        self._emit_dirty()

    # ---------- dirty 管理 ----------

    def dirty_parts(self) -> Set[Part]:
        return set(self._dirty)

    def is_dirty(self) -> bool:
        return bool(self._dirty)

    def mark_dirty(self, part: Part) -> None:
        before = set(self._dirty)
        self._dirty.add(part)
        if self._dirty != before:
            self._emit_dirty()

    def clear_dirty(self, part: Part) -> None:
        before = set(self._dirty)
        self._dirty.discard(part)
        if self._dirty != before:
            self._emit_dirty()

    def clear_all_dirty(self) -> None:
        if self._dirty:
            self._dirty.clear()
            self._emit_dirty()

    # ---------- snapshot ----------

    def _take_snapshot(self) -> Snapshot:
        p = self.profile
        return Snapshot(
            base=p.base.to_dict(),
            skills=p.skills.to_dict(),
            points=p.points.to_dict(),
            meta=p.meta.to_dict(),
            rotations=p.rotations.to_dict(),
        )

    def refresh_snapshot(self, *, parts: Optional[Set[Part]] = None) -> None:
        """
        刷新部分 snapshot（或全部），不改变 dirty 标记。
        """
        p = self.profile
        old = self._snap
        target = set(parts) if parts is not None else {"base", "skills", "points", "meta", "rotations"}

        base = p.base.to_dict() if "base" in target else old.base
        skills = p.skills.to_dict() if "skills" in target else old.skills
        points = p.points.to_dict() if "points" in target else old.points
        meta = p.meta.to_dict() if "meta" in target else old.meta
        rotations = p.rotations.to_dict() if "rotations" in target else old.rotations

        self._snap = Snapshot(
            base=base,
            skills=skills,
            points=points,
            meta=meta,
            rotations=rotations,
        )

    # ---------- rollback ----------

    def rollback(self) -> None:
        """
        回滚到最近一次 snapshot（仅内存，不触碰磁盘）。
        """
        ctx = self._ctx
        p = self.profile
        s = self._snap

        try:
            p.base = BaseFile.from_dict(s.base)
        except Exception:
            log.exception("rollback base failed")
        try:
            p.skills = SkillsFile.from_dict(s.skills)
        except Exception:
            log.exception("rollback skills failed")
        try:
            p.points = PointsFile.from_dict(s.points)
        except Exception:
            log.exception("rollback points failed")
        try:
            p.meta = ProfileMeta.from_dict(s.meta)
        except Exception:
            log.exception("rollback meta failed")
        try:
            p.rotations = RotationsFile.from_dict(s.rotations)
        except Exception:
            log.exception("rollback rotations failed")

        self._dirty.clear()
        self._emit_dirty()

    # ---------- commit ----------

    def commit(
        self,
        *,
        parts: Optional[Set[Part]] = None,
        backup: Optional[bool] = None,
        touch_meta: bool = True,
    ) -> None:
        """
        提交变更到磁盘。

        当前阶段（兼容旧结构）：
        - 分别触发：
          * base_repo.save  -> base.json
          * skills_repo.save -> skills.json
          * points_repo.save -> points.json
          * save_rotations   -> rotation.json
          * meta_repo.save   -> meta.json (若 touch_meta=True)
        - 后续会统一改写为 ProfileRepository.save(profile.json)。
        """
        target: Set[Part] = set(self._dirty) if parts is None else set(parts)
        if not target:
            return

        ctx = self._ctx
        p = self.profile

        if backup is None:
            try:
                backup = bool(p.base.io.backup_on_save)
            except Exception:
                backup = True

        # 仍依赖旧的 repo 字段；稍后会整体替换为 ProfileRepository
        if "base" in target:
            ctx.base_repo.save(p.base, backup=bool(backup))  # type: ignore[attr-defined]
            self._dirty.discard("base")

        if "skills" in target:
            ctx.skills_repo.save(p.skills, backup=bool(backup))  # type: ignore[attr-defined]
            self._dirty.discard("skills")

        if "points" in target:
            ctx.points_repo.save(p.points, backup=bool(backup))  # type: ignore[attr-defined]
            self._dirty.discard("points")

        if "rotations" in target:
            save_rotations(ctx.profile_dir, p.rotations, backup=bool(backup))
            self._dirty.discard("rotations")

        if touch_meta:
            ctx.meta_repo.save(p.meta, backup=bool(backup))  # type: ignore[attr-defined]
            self._dirty.discard("meta")

        self._snap = self._take_snapshot()
        self._emit_dirty()