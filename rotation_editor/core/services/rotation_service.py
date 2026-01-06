from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, List, Optional

from core.app.session import ProfileSession
from rotation_editor.core.models import RotationsFile, RotationPreset


@dataclass
class RotationService:
    """
    轨道方案（RotationPreset）业务服务：

    职责：
    - 面向 session.profile.rotations.presets 提供 CRUD（仅 preset 级别，Mode/Track/Node 由 RotationEditService 处理）
    - 通过 ProfileSession 标记/提交 "rotations" 脏状态
    - save_cmd / reload_cmd 负责与 profile.json 交互

    依赖：
    - ProfileSession: 提供 ctx（ProfileContext）与 dirty/commit/reload_parts 接口
    - notify_dirty: 通知 UI “脏状态可能变化”
    - notify_error: 通知 UI 错误信息 (msg, detail)
    """

    _session: ProfileSession
    _notify_dirty: Callable[[], None]
    _notify_error: Callable[[str, str], None]

    def __init__(
        self,
        *,
        session: ProfileSession,
        notify_dirty: Optional[Callable[[], None]] = None,
        notify_error: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._session = session
        self._notify_dirty = notify_dirty or (lambda: None)
        self._notify_error = notify_error or (lambda _m, _d="": None)

    # ---------- 基本属性 ----------

    @property
    def ctx(self):
        return self._session.ctx

    @property
    def rotations(self) -> RotationsFile:
        return self._session.profile.rotations

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
        entry_node_id: Optional[str] = None,
        max_exec_nodes: Optional[int] = None,
        max_run_seconds: Optional[int] = None,
    ) -> bool:
        """
        更新 preset 的基础字段：
        - name / description
        - entry_mode_id / entry_track_id（旧字段，现有 UI 使用）
        - entry_node_id（新字段：入口节点 node_id；新引擎强制要求）
        - 同步写入 preset.entry（新入口结构）
        - max_exec_nodes / max_run_seconds
        """
        p = self.find_preset(pid)
        if p is None:
            return False

        nm = (name or "").strip()
        desc = (description or "").rstrip("\n")
        em = (entry_mode_id or "").strip()
        et = (entry_track_id or "").strip()
        en = (entry_node_id or "").strip()

        changed = False
        if nm and nm != p.name:
            p.name = nm
            changed = True
        if desc != p.description:
            p.description = desc
            changed = True

        # ---- 旧字段 ----
        if em != (p.entry_mode_id or ""):
            p.entry_mode_id = em
            changed = True
        if et != (p.entry_track_id or ""):
            p.entry_track_id = et
            changed = True

        # ---- 新入口结构：同步写入 ----
        entry = getattr(p, "entry", None)
        if entry is None:
            try:
                from rotation_editor.core.models.entry import EntryPoint
                entry = EntryPoint()
                p.entry = entry  # type: ignore[attr-defined]
                changed = True
            except Exception:
                entry = None

        # 记录“轨道是否发生变化”，用于 node_id 合法性检查
        prev_scope = (getattr(entry, "scope", "global") if entry is not None else "global") if True else "global"
        prev_mode = (getattr(entry, "mode_id", "") if entry is not None else "")
        prev_track = (getattr(entry, "track_id", "") if entry is not None else "")
        prev_node = (getattr(entry, "node_id", "") if entry is not None else "")

        if entry is not None:
            if em:
                if entry.scope != "mode":
                    entry.scope = "mode"
                    changed = True
                if entry.mode_id != em:
                    entry.mode_id = em
                    changed = True
                if entry.track_id != et:
                    entry.track_id = et
                    changed = True
            else:
                if entry.scope != "global":
                    entry.scope = "global"
                    changed = True
                if entry.mode_id != "":
                    entry.mode_id = ""
                    changed = True
                if entry.track_id != et:
                    entry.track_id = et
                    changed = True

            # node_id：如果 UI 传了就写；没传就不写
            if en:
                if entry.node_id != en:
                    entry.node_id = en
                    changed = True

            # 如果 scope/mode/track 改了，且现有 node_id 不属于新轨道，则清空 node_id
            scope_now = (entry.scope or "global").strip().lower()
            mode_now = (entry.mode_id or "").strip()
            track_now = (entry.track_id or "").strip()
            node_now = (entry.node_id or "").strip()

            scope_changed = (scope_now != (prev_scope or "global").strip().lower())
            mode_changed = ((mode_now or "") != (prev_mode or ""))
            track_changed = ((track_now or "") != (prev_track or ""))

            if (scope_changed or mode_changed or track_changed) and node_now:
                # 检查 node 是否仍在该轨道
                tr = None
                if scope_now == "global":
                    tr = next((t for t in (p.global_tracks or []) if (t.id or "").strip() == track_now), None)
                else:
                    m = next((m for m in (p.modes or []) if (m.id or "").strip() == mode_now), None)
                    if m is not None:
                        tr = next((t for t in (m.tracks or []) if (t.id or "").strip() == track_now), None)

                ok_node = False
                if tr is not None:
                    for n in (tr.nodes or []):
                        if (getattr(n, "id", "") or "").strip() == node_now:
                            ok_node = True
                            break
                if not ok_node:
                    entry.node_id = ""
                    changed = True

        # ---- limits ----
        if max_exec_nodes is not None:
            val = int(max_exec_nodes)
            if val < 0:
                val = 0
            if val != (p.max_exec_nodes or 0):
                p.max_exec_nodes = val
                changed = True

        if max_run_seconds is not None:
            val = int(max_run_seconds)
            if val < 0:
                val = 0
            if val != (p.max_run_seconds or 0):
                p.max_run_seconds = val
                changed = True

        if changed:
            self._mark_dirty()
        return changed

    # ---------- dirty & save/reload ----------

    def _mark_dirty(self) -> None:
        try:
            self._session.mark_dirty("rotations")  # type: ignore[arg-type]
        except Exception:
            # ignore; 但仍然调用 notify_dirty，让 UI 自行查 session.dirty_parts()
            pass
        self._notify_dirty()

    def save_cmd(self, *, backup: Optional[bool] = None) -> bool:
        """
        保存 profile.json 中的 rotations；返回是否实际执行了保存。

        规则：
        - 若当前 session.dirty_parts() 不包含 "rotations" 则直接返回 False。
        - 若 backup 为 None，则取 profile.base.io.backup_on_save 作为默认。
        """
        parts = self._session.dirty_parts()
        if "rotations" not in parts:
            return False

        if backup is None:
            try:
                backup = bool(getattr(self.ctx.profile.base.io, "backup_on_save", True))
            except Exception:
                backup = True

        try:
            self._session.commit(
                parts={"rotations"},  # type: ignore[arg-type]
                backup=bool(backup),
                touch_meta=True,
            )
            self._notify_dirty()
            return True
        except Exception as e:
            self._notify_error("保存循环配置失败", str(e))
            return False

    def reload_cmd(self) -> None:
        """
        从 profile.json 重新加载 rotations 部分，放弃当前内存更改。
        """
        try:
            self._session.reload_parts({"rotations"})
            self._notify_dirty()
        except Exception as e:
            self._notify_error("重新加载循环配置失败", str(e))