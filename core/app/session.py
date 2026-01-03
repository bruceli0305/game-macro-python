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
from core.io.json_store import now_iso_utc

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

    - 持有 ProfileContext（其中包含 Profile 聚合和 ProfileRepository）
    - 维护 dirty_parts / snapshot
    - commit() 统一写入 profile.json
    - reload_parts() 按需从 profile.json 局部刷新
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

    @property
    def repo(self):
        return self._ctx.repo

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

    # ---------- reload parts ----------

    def reload_parts(self, parts: Set[Part]) -> None:
        """
        从 profile.json 重新加载指定部分（base/skills/points/meta/rotations）：
        - 其它部分保持不变
        - 被 reload 的部分从 dirty 集合中移除
        """
        fresh = self.repo.load_or_create(self.ctx.profile_name, self.ctx.idgen)
        p = self.profile

        if "base" in parts:
            p.base = fresh.base
            self._dirty.discard("base")
        if "skills" in parts:
            p.skills = fresh.skills
            self._dirty.discard("skills")
        if "points" in parts:
            p.points = fresh.points
            self._dirty.discard("points")
        if "rotations" in parts:
            p.rotations = fresh.rotations
            self._dirty.discard("rotations")
        if "meta" in parts:
            p.meta = fresh.meta
            self._dirty.discard("meta")

        self._snap = self._take_snapshot()
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

        现在统一写入 profile.json：
        - parts 仍用于控制 dirty 标记（以及 UI 显示），但 IO 层始终写整个 Profile。
        - touch_meta=True 时会更新 meta.updated_at（meta.created_at 为空时一并填充）。
        """
        target: Set[Part] = set(self._dirty) if parts is None else set(parts)
        if not target:
            return

        p = self.profile

        if backup is None:
            try:
                backup = bool(p.base.io.backup_on_save)
            except Exception:
                backup = True

        # 更新 meta.updated_at（仅在 touch_meta=True 时）
        if touch_meta:
            now = now_iso_utc()
            if not p.meta.created_at:
                p.meta.created_at = now
            p.meta.updated_at = now

        # 一次性写整个 Profile
        self.repo.save(self.ctx.profile_name, p, backup=bool(backup))

        # 清理对应 dirty 标记（其它未提交部分仍保留）
        for part in target:
            self._dirty.discard(part)

        self._snap = self._take_snapshot()
        self._emit_dirty()