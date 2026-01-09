from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, List, Dict, Any

from core.app.session import ProfileSession
from core.models.common import clamp_int
from core.models.skill import Skill, ColorRGB, PixelSpec, SampleConfig, AmmoStagePixel


@dataclass(frozen=True)
class SkillFormPatch:
    # 基本信息
    name: str
    enabled: bool
    trigger_key: str
    readbar_ms: int

    # 像素检测配置（主像素）
    monitor: str
    vx: int
    vy: int

    r: int
    g: int
    b: int

    tolerance: int
    sample_mode: str
    sample_radius: int

    # 备注
    note: str

    # ---- 通用游戏字段 ----
    game_id: int = 0
    game_desc: str = ""
    icon_url: str = ""
    cooldown_ms: int = 0
    radius: int = 0

    # ---- rotation & ammo 字段 ----
    # 在 rotation 中一次轮到该技能希望打几发（逻辑层语义，默认 1）
    shots_per_cycle: int = 1

    # 弹药阶段像素数据：
    # 每个 dict 结构约定至少包含：
    #   { "charges_left": int,
    #     "monitor": str,
    #     "vx": int, "vy": int,
    #     "r": int, "g": int, "b": int,
    #     "tolerance": int,
    #     "sample_mode": str, "sample_radius": int }
    ammo_stages: List[Dict[str, Any]] = field(default_factory=list)


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

    @property
    def ctx(self):
        return self._session.ctx

    @property
    def profile(self):
        return self._session.profile

    def find(self, sid: str) -> Optional[Skill]:
        for s in self.profile.skills.skills:
            if s.id == sid:
                return s
        return None

    def mark_dirty(self) -> None:
        self._session.mark_dirty("skills")

    def _apply_patch_to_skill(self, s: Skill, patch: SkillFormPatch) -> None:
        # 基本信息
        s.name = (patch.name or "").strip()
        s.enabled = bool(patch.enabled)

        # 触发键 / 读条
        s.trigger.type = "key"
        s.trigger.key = (patch.trigger_key or "").strip()
        s.cast.readbar_ms = clamp_int(int(patch.readbar_ms), 0, 10**9)

        # 像素配置（主像素）
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

        # 备注
        s.note = patch.note or ""

        # ---- 通用游戏字段 ----
        try:
            s.game_id = int(patch.game_id or 0)
        except Exception:
            s.game_id = 0

        s.game_desc = (patch.game_desc or "").strip()
        s.icon_url = (patch.icon_url or "").strip()

        try:
            cd = int(patch.cooldown_ms or 0)
        except Exception:
            cd = 0
        s.cooldown_ms = clamp_int(cd, 0, 10**9)

        try:
            rad = int(patch.radius or 0)
        except Exception:
            rad = 0
        s.radius = clamp_int(rad, 0, 10**9)

        # ---- rotation & ammo 字段 ----

        # 技能次数（至少 1 次）
        try:
            s.shots_per_cycle = clamp_int(int(getattr(patch, "shots_per_cycle", 1)), 1, 10**3)
        except Exception:
            s.shots_per_cycle = 1

        # 弹药阶段像素列表
        stages_list: List[AmmoStagePixel] = []
        for item in (patch.ammo_stages or []):
            if not isinstance(item, dict):
                continue
            try:
                ch = int(item.get("charges_left", 0) or 0)
                mon2 = (item.get("monitor", "primary") or "primary").strip() or "primary"
                vx2 = clamp_int(int(item.get("vx", 0) or 0), -10**9, 10**9)
                vy2 = clamp_int(int(item.get("vy", 0) or 0), -10**9, 10**9)
                r2 = clamp_int(int(item.get("r", 0) or 0), 0, 255)
                g2 = clamp_int(int(item.get("g", 0) or 0), 0, 255)
                b2 = clamp_int(int(item.get("b", 0) or 0), 0, 255)
                tol2 = clamp_int(int(item.get("tolerance", 0) or 0), 0, 255)
                mode2 = (item.get("sample_mode", "single") or "single").strip() or "single"
                rad2 = clamp_int(int(item.get("sample_radius", 0) or 0), 0, 50)
            except Exception:
                continue

            if ch <= 0:
                continue

            pix = PixelSpec(
                monitor=mon2,
                vx=vx2,
                vy=vy2,
                color=ColorRGB(r=r2, g=g2, b=b2),
                tolerance=tol2,
                sample=SampleConfig(mode=mode2, radius=rad2),
            )
            stages_list.append(
                AmmoStagePixel(
                    charges_left=ch,
                    pixel=pix,
                )
            )

        # 按 charges_left 从大到小排序（例如 3,2,1,...）
        stages_list.sort(key=lambda st: int(getattr(st, "charges_left", 0) or 0), reverse=True)
        s.ammo_stages = stages_list

    def apply_form_patch(self, sid: str, patch: SkillFormPatch, *, auto_save: bool) -> tuple[bool, bool]:
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
        self._session.commit(parts={"skills"}, backup=backup, touch_meta=True)
        self._notify_dirty()

    def reload_cmd(self) -> None:
        """
        从 profile.json 重新加载 skills 部分。
        """
        try:
            self._session.reload_parts({"skills"})
        except Exception:
            pass
        self._notify_dirty()