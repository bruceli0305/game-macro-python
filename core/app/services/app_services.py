# File: core/app/services/app_services.py
from __future__ import annotations

from typing import Callable, Iterable, Optional, Set

from core.app.session import ProfileSession, Part
from core.profiles import ProfileContext

from core.app.services.base_settings_service import BaseSettingsService
from core.app.services.skills_service import SkillsService
from core.app.services.points_service import PointsService


class AppServices:
    """
    整个应用当前 Profile 的服务入口：

    - 持有 ProfileSession（工作单元 + 脏标记）
    - 封装 BaseSettingsService / SkillsService / PointsService
    - 提供 “保存脏部分 / 回滚 / 通知脏状态” 等便捷方法
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        notify_error: Optional[Callable[[str, str], None]] = None,  # (msg, detail)
    ) -> None:
        # 统一的工作单元
        self.session = ProfileSession(ctx)

        self._notify_error = notify_error or (lambda _m, _d="": None)

        self.base = BaseSettingsService(
            session=self.session,
            notify_dirty=self.notify_dirty,
        )

        self.skills = SkillsService(
            session=self.session,
            notify_dirty=self.notify_dirty,
            notify_error=self._notify_error,
        )
        self.points = PointsService(
            session=self.session,
            notify_dirty=self.notify_dirty,
            notify_error=self._notify_error,
        )

        self._repair_ids_and_persist()
        self.notify_dirty()

    # ---------- 当前上下文 ----------

    @property
    def ctx(self) -> ProfileContext:
        return self.session.ctx

    def set_context(self, ctx: ProfileContext) -> None:
        """
        切换到另一个 ProfileContext（profile 切换时调用）。
        """
        self.session.set_context(ctx)
        self._repair_ids_and_persist()
        self.notify_dirty()

    # ---------- dirty facade ----------

    def dirty_parts(self) -> Set[Part]:
        try:
            return set(self.session.dirty_parts())
        except Exception:
            return set()

    def is_dirty(self) -> bool:
        try:
            return bool(self.session.is_dirty())
        except Exception:
            return False

    # ---------- commit/rollback ----------

    def commit_parts_cmd(
        self,
        *,
        parts: Iterable[str],
        backup: Optional[bool] = None,
        touch_meta: bool = True,
    ) -> bool:
        """
        显式提交指定的部分（base/skills/points/meta/rotations）。
        """
        valid = {"base", "skills", "points", "meta", "rotations"}
        target: Set[Part] = set()

        for p in parts:
            ps = (str(p) if p is not None else "").strip()
            if not ps:
                continue
            if ps not in valid:
                raise ValueError(f"Unknown part: {ps!r}")
            target.add(ps)  # type: ignore[arg-type]

        if not target:
            return False

        if backup is None:
            try:
                backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
            except Exception:
                backup = True

        self.session.commit(
            parts=set(target),
            backup=bool(backup),
            touch_meta=bool(touch_meta),
        )
        self.notify_dirty()
        return True

    def save_dirty_cmd(self, *, backup: Optional[bool] = None, touch_meta: bool = True) -> bool:
        """
        保存当前所有脏部分（若无脏数据返回 False）。
        """
        parts = self.dirty_parts()
        if not parts:
            return False

        if backup is None:
            try:
                backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
            except Exception:
                backup = True

        self.session.commit(
            parts=set(parts),
            backup=bool(backup),
            touch_meta=bool(touch_meta),
        )
        self.notify_dirty()
        return True

    def rollback_cmd(self) -> None:
        """
        回滚所有部分到最近一次 snapshot（不触碰磁盘）。
        """
        self.session.rollback()
        self.notify_dirty()

    # ---------- dirty broadcast ----------

    def notify_dirty(self) -> None:
        """
        主动触发一次当前脏状态的广播（供 UI 初始同步等场景使用）。
        """
        try:
            self.session.emit_dirty()
        except Exception:
            pass

    # ---------- repair ----------

    def _repair_ids_and_persist(self) -> None:
        """
        启动时/切换 profile 时，对 skills / points 的 id 进行一次性修复：

        - 若缺 id 或重复 id，会重新分配新的 snowflake id
        - 修复后尝试立即持久化（不触发 meta 更新时间）
        """
        ctx = self.ctx
        p = self.session.profile
        changed_parts: Set[str] = set()

        # 修复 Skill.id
        seen: Set[str] = set()
        for s in p.skills.skills:
            if (not s.id) or (s.id in seen):
                s.id = ctx.idgen.next_id()
                changed_parts.add("skills")
            seen.add(s.id)

        # 修复 Point.id
        seen_p: Set[str] = set()
        for pt in p.points.points:
            if (not pt.id) or (pt.id in seen_p):
                pt.id = ctx.idgen.next_id()
                changed_parts.add("points")
            seen_p.add(pt.id)

        if not changed_parts:
            return

        try:
            backup = bool(getattr(p.base.io, "backup_on_save", True))
        except Exception:
            backup = True

        try:
            self.session.commit(
                parts=set(changed_parts),  # type: ignore[arg-type]
                backup=backup,
                touch_meta=False,
            )
            for part in changed_parts:
                try:
                    self.session.clear_dirty(part)  # type: ignore[arg-type]
                except Exception:
                    pass
        except Exception as e:
            for part in changed_parts:
                try:
                    self.session.mark_dirty(part)  # type: ignore[arg-type]
                except Exception:
                    pass
            # 不再走 EventBus，直接交给 UI 的 notify_error
            self._notify_error("数据修复保存失败", str(e))