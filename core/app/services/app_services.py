# File: core/app/services/app_services.py
from __future__ import annotations

from typing import Callable, Iterable, Optional, Set

from core.store.app_store import AppStore, Part
from core.profiles import ProfileContext

from core.app.services.base_settings_service import BaseSettingsService
from core.app.services.skills_service import SkillsService
from core.app.services.points_service import PointsService


class AppServices:
    def __init__(
        self,
        *,
        ctx: ProfileContext,
        notify_error: Optional[Callable[[str, str], None]] = None,  # (msg, detail)
    ) -> None:
        self.store = AppStore(ctx)
        self._notify_error = notify_error or (lambda _m, _d="": None)

        self.base = BaseSettingsService(store=self.store, notify_dirty=self.notify_dirty)

        self.skills = SkillsService(
            store=self.store,
            notify_dirty=self.notify_dirty,
            notify_error=self._notify_error,
        )
        self.points = PointsService(
            store=self.store,
            notify_dirty=self.notify_dirty,
            notify_error=self._notify_error,
        )

        self._repair_ids_and_persist()
        self.notify_dirty()

    @property
    def ctx(self) -> ProfileContext:
        return self.store.ctx

    def set_context(self, ctx: ProfileContext) -> None:
        self.store.set_context(ctx)
        self._repair_ids_and_persist()
        self.notify_dirty()

    # ---------- dirty facade ----------
    def dirty_parts(self) -> Set[Part]:
        try:
            return set(self.store.dirty_parts())
        except Exception:
            return set()

    def is_dirty(self) -> bool:
        try:
            return bool(self.store.is_dirty())
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

        self.store.commit(parts=set(target), backup=bool(backup), touch_meta=bool(touch_meta))
        self.notify_dirty()
        return True

    def save_dirty_cmd(self, *, backup: Optional[bool] = None, touch_meta: bool = True) -> bool:
        parts = self.dirty_parts()
        if not parts:
            return False

        if backup is None:
            try:
                backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
            except Exception:
                backup = True

        self.store.commit(parts=set(parts), backup=bool(backup), touch_meta=bool(touch_meta))
        self.notify_dirty()
        return True

    def rollback_cmd(self) -> None:
        self.store.rollback()
        self.notify_dirty()

    # ---------- dirty broadcast ----------
    def notify_dirty(self) -> None:
        """
        主动触发一次当前脏状态的广播（供 UI 初始同步等场景使用）。
        """
        try:
            self.store.emit_dirty()
        except Exception:
            pass

    # ---------- repair ----------
    def _repair_ids_and_persist(self) -> None:
        ctx = self.ctx
        changed_parts: Set[str] = set()

        seen: Set[str] = set()
        for s in ctx.skills.skills:
            if (not s.id) or (s.id in seen):
                s.id = ctx.idgen.next_id()
                changed_parts.add("skills")
            seen.add(s.id)

        seen_p: Set[str] = set()
        for p in ctx.points.points:
            if (not p.id) or (p.id in seen_p):
                p.id = ctx.idgen.next_id()
                changed_parts.add("points")
            seen_p.add(p.id)

        if not changed_parts:
            return

        try:
            backup = bool(getattr(ctx.base.io, "backup_on_save", True))
        except Exception:
            backup = True

        try:
            self.store.commit(parts=set(changed_parts), backup=backup, touch_meta=False)  # type: ignore[arg-type]
            for part in changed_parts:
                try:
                    self.store.clear_dirty(part)  # type: ignore[arg-type]
                except Exception:
                    pass
        except Exception as e:
            for part in changed_parts:
                try:
                    self.store.mark_dirty(part)  # type: ignore[arg-type]
                except Exception:
                    pass
            # 不再走 EventBus.ERROR
            self._notify_error("数据修复保存失败", str(e))