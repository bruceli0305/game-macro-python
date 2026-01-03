from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, List, Optional

from core.store.app_store import AppStore
from rotation_editor.core.models import RotationsFile, RotationPreset
from rotation_editor.core.storage import load_or_create_rotations


@dataclass
class RotationService:
    """
    轨道方案（RotationPreset）业务服务：

    职责：
    - 面向 ctx.rotations.presets 提供 CRUD（仅 preset 级别，Mode/Track/Node 由 UI 或后续服务处理）
    - 通过 AppStore 标记/提交 "rotations" 脏状态
    - save_cmd / reload_cmd 负责与磁盘交互

    依赖：
    - AppStore: 提供 ctx（ProfileContext）与 dirty/commit 接口
    - notify_dirty: 通知 UI “脏状态可能变化”
    - notify_error: 通知 UI 错误信息 (msg, detail)
    """

    _store: AppStore
    _notify_dirty: Callable[[], None]
    _notify_error: Callable[[str, str], None]

    def __init__(
        self,
        *,
        store: AppStore,
        notify_dirty: Optional[Callable[[], None]] = None,
        notify_error: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._store = store
        self._notify_dirty = notify_dirty or (lambda: None)
        self._notify_error = notify_error or (lambda _m, _d="": None)

    # ---------- 基本属性 ----------

    @property
    def ctx(self):
        return self._store.ctx

    @property
    def rotations(self) -> RotationsFile:
        return self.ctx.rotations

    # ---------- ID 生成 ----------

    def _new_id(self) -> str:
        # 使用 uuid4 生成本地唯一 ID，避免依赖外部 idgen
        return uuid.uuid4().hex

    # ---------- CRUD: presets ----------

    def list_presets(self) -> List[RotationPreset]:
        return list(self.rotations.presets or [])

    def find_preset(self, pid: str) -> Optional[RotationPreset]:
        pid = (pid or "").strip()
        if not pid:
            return None
        for p in self.rotations.presets:
            if p.id == pid:
                return p
        return None

    def create_preset(self, name: str) -> RotationPreset:
        nm = (name or "").strip() or "新方案"
        pid = self._new_id()
        preset = RotationPreset(id=pid, name=nm, description="")
        self.rotations.presets.append(preset)
        self._mark_dirty()
        return preset

    def clone_preset(self, src_id: str, new_name: str) -> Optional[RotationPreset]:
        src = self.find_preset(src_id)
        if src is None:
            return None

        nm = (new_name or "").strip() or f"{src.name} (副本)"
        pid = self._new_id()
        # 深拷贝：走 to_dict / from_dict，避免共享内部列表引用
        data = src.to_dict()
        clone = RotationPreset.from_dict(data)
        clone.id = pid
        clone.name = nm

        self.rotations.presets.append(clone)
        self._mark_dirty()
        return clone

    def rename_preset(self, pid: str, new_name: str) -> bool:
        p = self.find_preset(pid)
        if p is None:
            return False
        nm = (new_name or "").strip()
        if not nm or nm == p.name:
            return False
        p.name = nm
        self._mark_dirty()
        return True

    def delete_preset(self, pid: str) -> bool:
        pid = (pid or "").strip()
        if not pid:
            return False
        before = len(self.rotations.presets)
        self.rotations.presets = [p for p in self.rotations.presets if p.id != pid]
        after = len(self.rotations.presets)
        if after != before:
            self._mark_dirty()
            return True
        return False

    def update_preset_basic(
        self,
        pid: str,
        *,
        name: str,
        description: str,
        entry_mode_id: Optional[str] = None,
        entry_track_id: Optional[str] = None,
    ) -> bool:
        """
        更新 preset 的基础字段：
        - name / description
        - entry_mode_id / entry_track_id

        若有变更则标记 rotations 脏。
        """
        p = self.find_preset(pid)
        if p is None:
            return False

        nm = (name or "").strip()
        desc = (description or "").rstrip("\n")
        em = (entry_mode_id or "").strip()
        et = (entry_track_id or "").strip()

        changed = False
        if nm and nm != p.name:
            p.name = nm
            changed = True
        if desc != p.description:
            p.description = desc
            changed = True
        if em != (p.entry_mode_id or ""):
            p.entry_mode_id = em
            changed = True
        if et != (p.entry_track_id or ""):
            p.entry_track_id = et
            changed = True

        if changed:
            self._mark_dirty()
        return changed

    # ---------- dirty & save/reload ----------

    def _mark_dirty(self) -> None:
        try:
            self._store.mark_dirty("rotations")  # type: ignore[arg-type]
        except Exception:
            # ignore; 但仍然调用 notify_dirty，让 UI 自行查 store.dirty_parts()
            pass
        self._notify_dirty()

    def save_cmd(self, *, backup: Optional[bool] = None) -> bool:
        """
        保存 rotations.json；返回是否实际执行了保存。

        规则：
        - 若当前 store.dirty_parts() 不包含 "rotations" 则直接返回 False。
        - 若 backup 为 None，则取 ctx.base.io.backup_on_save 作为默认。
        """
        parts = self._store.dirty_parts()
        if "rotations" not in parts:
            return False

        if backup is None:
            try:
                backup = bool(getattr(self.ctx.base.io, "backup_on_save", True))
            except Exception:
                backup = True

        try:
            self._store.commit(parts={"rotations"}, backup=bool(backup), touch_meta=True)  # type: ignore[arg-type]
            self._notify_dirty()
            return True
        except Exception as e:
            self._notify_error("保存循环配置失败", str(e))
            return False

    def reload_cmd(self) -> None:
        """
        从磁盘重新加载 rotations.json，放弃当前内存更改。
        """
        try:
            new_rot = load_or_create_rotations(self.ctx.profile_dir)
            self.ctx.rotations = new_rot
            try:
                self._store.clear_dirty("rotations")  # type: ignore[arg-type]
            except Exception:
                pass
            try:
                self._store.refresh_snapshot(parts={"rotations"})  # type: ignore[arg-type]
            except Exception:
                pass
            self._notify_dirty()
        except Exception as e:
            self._notify_error("重新加载循环配置失败", str(e))