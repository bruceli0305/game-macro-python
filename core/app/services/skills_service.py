# File: core/app/services/skills_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from core.app.session import ProfileSession
from core.models.common import clamp_int
from core.models.skill import Skill, ColorRGB


@dataclass(frozen=True)
class SkillFormPatch:
    name: str
    enabled: bool
    trigger_key: str
    readbar_ms: int

    monitor: str
    vx: int
    vy: int

    r: int
    g: int
    b: int

    tolerance: int
    sample_mode: str
    sample_radius: int

    note: str


class SkillsService:
    """
    技能配置编辑服务：

    - 不依赖 EventBus
    - 通过 ProfileSession 管理脏状态与提交
    - autosave 失败通过 notify_error 回调（由 UI 注入）
    """

    def __init__(
        self,
        *,
        session: ProfileSession,
        notify_dirty: Optional[Callable[[], None]] = None,
        notify_error: Optional[Callable[[str, str], None]] = None,  # (msg, detail)
    ) -> None:
        self._session = session
        self._notify_dirty = notify_dirty or (lambda: None)
        self._notify_error = notify_error or (lambda _m, _d="": None)

    # ---------- 便捷属性 ----------

    @property
    def ctx(self):
        return self._session.ctx

    @property
    def profile(self):
        return self._session.profile

    # ---------- 基本查询 ----------

    def find(self, sid: str) -> Optional[Skill]:
        for s in self.profile.skills.skills:
            if s.id == sid:
                return s
        return None

    def mark_dirty(self) -> None:
        self._session.mark_dirty("skills")

    # ---------- 应用表单 patch ----------

    def _apply_patch_to_skill(self, s: Skill, patch: SkillFormPatch) -> None:
        s.name = (patch.name or "").strip()
        s.enabled = bool(patch.enabled)

        s.trigger.type = "key"
        s.trigger.key = (patch.trigger_key or "").strip()
        s.cast.readbar_ms = clamp_int(int(patch.readbar_ms), 0, 10**9)

        s.pixel.monitor = (patch.monitor or "primary").strip() or "primary"
        s.pixel.vx = clamp_int(int(patch.vx), -10**9, 10**9)
        s.pixel.vy = clamp_int(int(patch.vy), -10**9, 10**9)

        r = clamp_int(int(patch.r), 0, 255)
        g = clamp_int(int(patch.g), 0, 255)
        b = clamp_int(int(patch.b), 0, 255)
        s.pixel.color = ColorRGB(r=r, g=g, b=b)

        s.pixel.tolerance = clamp_int(int(patch.tolerance), 0, 255)
        s.pixel.sample.mode = (patch.sample_mode or "single").strip() or "single"
        s.pixel.sample.radius = clamp_int(int(patch.sample_radius), 0, 50)

        s.note = patch.note or ""

    def apply_form_patch(self, sid: str, patch: SkillFormPatch, *, auto_save: bool) -> tuple[bool, bool]:
        """
        应用表单 patch 到指定技能：
        返回 (applied, saved)：
        - applied: 是否实际有变更
        - saved  : 若 auto_save=True，是否自动保存成功
        """
        s = self.find(sid)
        if s is None:
            return (False, False)

        before = s.to_dict()
        tmp = Skill.from_dict(before)
        self._apply_patch_to_skill(tmp, patch)
        after = tmp.to_dict()

        if after == before:
            return (False, False)

        self._apply_patch_to_skill(s, patch)
        self.mark_dirty()
        self._notify_dirty()

        saved = False
        if auto_save:
            saved = self._maybe_autosave()
            self._notify_dirty()

        return (True, bool(saved))

    def apply_pick_cmd(
        self,
        sid: str,
        *,
        vx: int,
        vy: int,
        monitor: str,
        r: int,
        g: int,
        b: int,
    ) -> tuple[bool, bool]:
        """
        用于取色确认事件：
        - 仅更新 pixel 位置信息和颜色，不动读条时间等。
        返回 (applied, saved)。
        """
        s = self.find(sid)
        if s is None:
            return (False, False)

        s.pixel.vx = int(vx)
        s.pixel.vy = int(vy)
        if monitor:
            s.pixel.monitor = str(monitor)
        s.pixel.color = ColorRGB(r=int(r), g=int(g), b=int(b))

        self.mark_dirty()
        self._notify_dirty()

        saved = self._maybe_autosave()
        self._notify_dirty()
        return (True, bool(saved))

    # ---------- non-cmd helpers ----------

    def create_skill(self, *, name: str = "新技能") -> Skill:
        sid = self.ctx.idgen.next_id()
        s = Skill(id=sid, name=name, enabled=True)
        s.pixel.monitor = "primary"
        s.pixel.vx = 0
        s.pixel.vy = 0
        self.profile.skills.skills.append(s)
        self.mark_dirty()
        return s

    def clone_skill(self, src_id: str) -> Optional[Skill]:
        src = self.find(src_id)
        if src is None:
            return None
        new_id = self.ctx.idgen.next_id()
        clone = Skill.from_dict(src.to_dict())
        clone.id = new_id
        clone.name = f"{src.name} (副本)"
        self.profile.skills.skills.append(clone)
        self.mark_dirty()
        return clone

    def delete_skill(self, sid: str) -> bool:
        before = len(self.profile.skills.skills)
        self.profile.skills.skills = [x for x in self.profile.skills.skills if x.id != sid]
        after = len(self.profile.skills.skills)
        if after != before:
            self.mark_dirty()
            return True
        return False

    # ---------- autosave ----------

    def _maybe_autosave(self) -> bool:
        """
        若开启 auto_save，则只保存 skills 部分（不更新 meta）。
        """
        try:
            auto = bool(getattr(self.profile.base.io, "auto_save", False))
        except Exception:
            auto = False
        if not auto:
            return False

        try:
            backup = bool(getattr(self.profile.base.io, "backup_on_save", True))
        except Exception:
            backup = True

        try:
            self._session.commit(parts={"skills"}, backup=backup, touch_meta=False)
            return True
        except Exception as e:
            self._notify_error("自动保存失败", str(e))
            return False

    # ---------- cmd API ----------

    def create_cmd(self, *, name: str = "新技能") -> Skill:
        s = self.create_skill(name=name)
        self._notify_dirty()
        _ = self._maybe_autosave()
        self._notify_dirty()
        return s

    def clone_cmd(self, src_id: str) -> Optional[Skill]:
        clone = self.clone_skill(src_id)
        if clone is None:
            return None
        self._notify_dirty()
        _ = self._maybe_autosave()
        self._notify_dirty()
        return clone

    def delete_cmd(self, sid: str) -> bool:
        ok = self.delete_skill(sid)
        if not ok:
            return False
        self._notify_dirty()
        _ = self._maybe_autosave()
        self._notify_dirty()
        return True

    def save_cmd(self, *, backup: Optional[bool] = None) -> None:
        """
        显式保存 skills 部分（更新 meta）。
        """
        self._session.commit(parts={"skills"}, backup=backup, touch_meta=True)
        self._notify_dirty()

    def reload_cmd(self) -> None:
        """
        从磁盘重新加载 skills.json / Profile.skills：
        - 仍使用旧的 SkillsRepo.load_or_create
        - 清除 skills 脏标记，刷新 snapshot
        """
        self.profile.skills = self.ctx.skills_repo.load_or_create()  # type: ignore[attr-defined]
        try:
            self._session.clear_dirty("skills")
        except Exception:
            pass
        try:
            self._session.refresh_snapshot(parts={"skills"})
        except Exception:
            pass
        self._notify_dirty()