from __future__ import annotations

import uuid
from typing import Callable, List, Optional

from core.app.session import ProfileSession
from rotation_editor.core.models import (
    RotationsFile,
    RotationPreset,
    Track,
    Mode,
    Node,
    SkillNode,
    GatewayNode,
)


class RotationEditService:
    """
    轨道/节点/模式编辑服务（不负责 preset CRUD，只负责在内存中修改结构 + 标记脏）：

    职责：
    - 在指定 RotationPreset 范围内：
        * 模式操作：新增 / 重命名 / 删除 Mode
        * 轨道操作：在指定模式或全局下新增 Track
        * 在指定 (mode_id, track_id) 轨道下：
            - 查找轨道
            - 列出节点
            - 新增技能节点 / 网关节点
            - 上移 / 下移 / 删除节点
            - 按 node_ids 顺序重排节点
            - 在轨道之间移动节点（跨轨道拖拽）
    - 通过 ProfileSession 标记 "rotations" 为脏
    - 不负责磁盘 I/O（保存/重载由 RotationService 完成）
    """

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

    # ---------- 内部：工具 ----------

    def _new_id(self) -> str:
        return uuid.uuid4().hex

    # ---------- 脏标记 ----------

    def mark_dirty(self) -> None:
        """
        对外公开的“标记 rotations 脏”方法：
        - 供 UI 或对话框在直接修改对象后手动调用。
        """
        try:
            self._session.mark_dirty("rotations")  # type: ignore[arg-type]
        except Exception:
            pass
        self._notify_dirty()

    def _mark_dirty(self) -> None:
        self.mark_dirty()

    # ---------- 内部：模式/轨道查找 ----------

    def _find_mode(self, preset: RotationPreset, mode_id: str) -> Optional[Mode]:
        mid = (mode_id or "").strip()
        if not mid:
            return None
        for m in preset.modes:
            if m.id == mid:
                return m
        return None

    def get_track(
        self,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
    ) -> Optional[Track]:
        """
        根据 (preset, mode_id, track_id) 查找轨道：

        - mode_id 非空 => 在对应 Mode.tracks 下查找
        - mode_id 为空 => 在 preset.global_tracks 下查找
        """
        tid = (track_id or "").strip()
        if not tid:
            return None

        mid = (mode_id or "").strip()
        if mid:
            mode = self._find_mode(preset, mid)
            if mode is None:
                return None
            for t in mode.tracks:
                if t.id == tid:
                    return t
            return None

        # 全局轨道
        for t in preset.global_tracks:
            if t.id == tid:
                return t
        return None

    def list_nodes(
        self,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
    ) -> List[Node]:
        """
        返回指定轨道的节点列表（直接返回 Track.nodes 引用，不复制）。
        """
        t = self.get_track(preset, mode_id, track_id)
        if t is None:
            return []
        return t.nodes

    def get_node(
        self,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
        index: int,
    ) -> Optional[Node]:
        """
        根据索引获取节点（index 基于 Track.nodes）。
        """
        t = self.get_track(preset, mode_id, track_id)
        if t is None:
            return None
        if index < 0 or index >= len(t.nodes):
            return None
        return t.nodes[index]

    # ---------- 模式操作 ----------

    def create_mode(self, preset: RotationPreset, name: str) -> Mode:
        """
        在给定 preset 下新增一个 Mode，并标记 rotations 脏。
        """
        nm = (name or "").strip() or "新模式"
        mid = self._new_id()
        m = Mode(id=mid, name=nm, tracks=[])
        preset.modes.append(m)
        self._mark_dirty()
        return m

    def rename_mode(self, preset: RotationPreset, mode_id: str, new_name: str) -> bool:
        """
        重命名指定 mode_id 的模式。
        """
        m = self._find_mode(preset, mode_id)
        if m is None:
            return False
        nm = (new_name or "").strip()
        if not nm or nm == m.name:
            return False
        m.name = nm
        self._mark_dirty()
        return True

    def delete_mode(self, preset: RotationPreset, mode_id: str) -> bool:
        """
        删除指定 mode_id 的模式及其下所有轨道/节点。

        新行为：
        - 只操作 preset.modes 和 preset.entry（EntryPoint）；
        - 若入口 entry.scope=mode 且 entry.mode_id 指向被删模式，则重置入口为 global，
          并清空 track_id / node_id。
        """
        mid = (mode_id or "").strip()
        if not mid:
            return False

        before = len(preset.modes)
        preset.modes = [m for m in preset.modes if (m.id or "") != mid]
        after = len(preset.modes)
        if after == before:
            return False

        entry = getattr(preset, "entry", None)
        if entry is not None:
            scope = (getattr(entry, "scope", "global") or "global").strip().lower()
            em = (getattr(entry, "mode_id", "") or "").strip()
            if scope == "mode" and em == mid:
                entry.scope = "global"
                entry.mode_id = ""
                entry.track_id = ""
                entry.node_id = ""

        self._mark_dirty()
        return True

    # ---------- 轨道操作 ----------

    def create_track(
        self,
        preset: RotationPreset,
        mode_id: Optional[str],
        name: str,
    ) -> Optional[Track]:
        """
        在给定 preset 下创建一个轨道：

        - mode_id 非空 => 在对应 Mode.tracks 下追加新轨道
        - mode_id 为空 => 在 preset.global_tracks 下追加新轨道
        """
        nm = (name or "").strip() or "新轨道"
        tid = self._new_id()
        track = Track(id=tid, name=nm, nodes=[])

        mid = (mode_id or "").strip()
        if mid:
            mode = self._find_mode(preset, mid)
            if mode is None:
                return None
            mode.tracks.append(track)
        else:
            preset.global_tracks.append(track)

        self._mark_dirty()
        return track

    # ---------- 节点操作：新增 ----------

    def add_skill_node(
        self,
        *,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
        skill_id: str,
        label: str,
        override_cast_ms: Optional[int] = None,
        comment: str = "",
    ) -> Optional[SkillNode]:
        """
        在指定轨道末尾新增一个 SkillNode。
        UI 负责选择 skill_id 和 label，本方法只做结构修改和标记脏。
        """
        t = self.get_track(preset, mode_id, track_id)
        if t is None:
            return None

        sid = (skill_id or "").strip()
        nid = self._new_id()

        node = SkillNode(
            id=nid,
            kind="skill",
            label=label or "Skill",
            skill_id=sid,
            override_cast_ms=override_cast_ms,
            comment=comment or "",
        )
        t.nodes.append(node)
        self._mark_dirty()
        return node

    def add_gateway_node(
        self,
        *,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
        label: str,
        target_mode_id: str,
    ) -> Optional[GatewayNode]:
        """
        在指定轨道末尾新增一个 GatewayNode。

        - target_mode_id 有效：action="switch_mode"，仅写 target_mode_id
        - target_mode_id 为空：action="end"
        - 不写 target_node_index（已移除）
        """
        t = self.get_track(preset, mode_id, track_id)
        if t is None:
            return None

        nid = self._new_id()
        nm = (label or "").strip() or "Gateway"
        tm = (target_mode_id or "").strip()

        if tm:
            gw = GatewayNode(
                id=nid,
                kind="gateway",
                label=nm,
                condition_id=None,
                condition_expr=None,
                action="switch_mode",
                target_mode_id=tm,
                target_track_id=None,
                target_node_id=None,
            )
        else:
            gw = GatewayNode(
                id=nid,
                kind="gateway",
                label=nm,
                condition_id=None,
                condition_expr=None,
                action="end",
                target_mode_id=None,
                target_track_id=None,
                target_node_id=None,
            )

        t.nodes.append(gw)
        self._mark_dirty()
        return gw

    # ---------- 节点操作：移动 / 删除 ----------

    def move_node_up(
        self,
        *,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
        index: int,
    ) -> bool:
        """
        将 index 位置的节点上移一位。
        """
        t = self.get_track(preset, mode_id, track_id)
        if t is None:
            return False
        if index <= 0 or index >= len(t.nodes):
            return False
        t.nodes[index - 1], t.nodes[index] = t.nodes[index], t.nodes[index - 1]
        self._mark_dirty()
        return True

    def move_node_down(
        self,
        *,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
        index: int,
    ) -> bool:
        """
        将 index 位置的节点下移一位。
        """
        t = self.get_track(preset, mode_id, track_id)
        if t is None:
            return False
        if index < 0 or index >= len(t.nodes) - 1:
            return False
        t.nodes[index + 1], t.nodes[index] = t.nodes[index], t.nodes[index + 1]
        self._mark_dirty()
        return True

    def delete_node(
        self,
        *,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
        index: int,
    ) -> bool:
        """
        删除 index 位置的节点。
        """
        t = self.get_track(preset, mode_id, track_id)
        if t is None:
            return False
        if index < 0 or index >= len(t.nodes):
            return False
        del t.nodes[index]
        self._mark_dirty()
        return True

    # ---------- 节点重排：按节点 ID 顺序重建 ----------

    def reorder_nodes_by_ids(
        self,
        *,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
        node_ids: List[str],
    ) -> bool:
        """
        根据 node_ids 的顺序重建 Track.nodes：
        - node_ids 中出现的 ID 将按给定顺序排列；
        - Track.nodes 中存在但 node_ids 未包含的节点，会按原顺序追加到末尾。
        """
        t = self.get_track(preset, mode_id, track_id)
        if t is None:
            return False
        if not node_ids:
            return False

        id2node = {getattr(n, "id", ""): n for n in t.nodes}
        new_nodes: List[Node] = []
        seen: set[str] = set()

        for nid in node_ids:
            nid_s = (nid or "").strip()
            if not nid_s:
                continue
            n = id2node.get(nid_s)
            if n is not None and nid_s not in seen:
                new_nodes.append(n)
                seen.add(nid_s)

        for n in t.nodes:
            nid = getattr(n, "id", "")
            if nid and nid not in seen:
                new_nodes.append(n)
                seen.add(nid)

        if not new_nodes or new_nodes == t.nodes:
            return False

        t.nodes = new_nodes
        self._mark_dirty()
        return True

    # ---------- 节点跨轨道移动 ----------

    def move_node_between_tracks(
        self,
        *,
        preset: RotationPreset,
        src_mode_id: Optional[str],
        src_track_id: Optional[str],
        dst_mode_id: Optional[str],
        dst_track_id: Optional[str],
        node_id: str,
        dst_index: int,
    ) -> bool:
        """
        将指定 node_id 的节点从 (src_mode_id, src_track_id) 移动到
        (dst_mode_id, dst_track_id) 的 dst_index 位置。

        规则：
        - 如果 src/dst 轨道不存在，返回 False；
        - 如果源轨道中找不到该节点，返回 False；
        - dst_index 会被裁剪到 [0, len(dst_track.nodes)]。
        """
        src_t = self.get_track(preset, src_mode_id, src_track_id)
        dst_t = self.get_track(preset, dst_mode_id, dst_track_id)
        if src_t is None or dst_t is None:
            return False

        nid = (node_id or "").strip()
        if not nid:
            return False

        node: Optional[Node] = None
        for i, n in enumerate(src_t.nodes):
            if getattr(n, "id", "") == nid:
                node = n
                del src_t.nodes[i]
                break
        if node is None:
            return False

        if dst_index < 0:
            dst_index = 0
        if dst_index > len(dst_t.nodes):
            dst_index = len(dst_t.nodes)

        dst_t.nodes.insert(dst_index, node)
        self._mark_dirty()
        return True
    # ---------- 设置节点的步骤(step_index) ----------

    def set_node_step(
        self,
        *,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
        node_id: str,
        step_index: int,
        order_in_step: Optional[int] = None,
    ) -> bool:
        """
        设置指定节点的 step_index（以及可选的 order_in_step）：

        约束（新版）：
        - 同一轨道的同一个 step_index 上，最多只允许 1 个节点。
          若尝试将某节点移动到一个已有节点的 step_index，则本次操作被拒绝。

        返回：
        - 若找到节点且值有变化，则返回 True 并标记 rotations 脏；
        - 否则返回 False。
        """
        t = self.get_track(preset, mode_id, track_id)
        if t is None:
            return False

        nid = (node_id or "").strip()
        if not nid:
            return False

        # 归一化 step_index
        try:
            s_new = int(step_index)
        except Exception:
            s_new = 0
        if s_new < 0:
            s_new = 0

        # 可选：order_in_step
        if order_in_step is None:
            o_new: Optional[int] = None
        else:
            try:
                o_new = int(order_in_step)
            except Exception:
                o_new = 0
            if o_new < 0:
                o_new = 0

        target_node = None
        for n in t.nodes:
            if getattr(n, "id", "") == nid:
                target_node = n
                break

        if target_node is None:
            return False

        # 同一轨道同一 step 上是否已存在其他节点（不包括自己）
        count_in_step = 0
        for n in t.nodes:
            if getattr(n, "id", "") == nid:
                continue
            try:
                s_val = int(getattr(n, "step_index", 0) or 0)
            except Exception:
                s_val = 0
            if s_val < 0:
                s_val = 0
            if s_val == s_new:
                count_in_step += 1

        # 若目标 step 上已经有 1 个节点，则拒绝本次移动（不改变任何东西）
        current_s = int(getattr(target_node, "step_index", 0) or 0)
        if current_s != s_new and count_in_step >= 1:
            return False

        changed = False

        # 写入 step_index
        if current_s != s_new:
            try:
                setattr(target_node, "step_index", s_new)
                changed = True
            except Exception:
                pass

        # 写入 order_in_step
        if o_new is not None:
            try:
                o_old = int(getattr(target_node, "order_in_step", 0) or 0)
            except Exception:
                o_old = 0
            if o_old != o_new:
                try:
                    setattr(target_node, "order_in_step", o_new)
                    changed = True
                except Exception:
                    pass

        if changed:
            self._mark_dirty()
        return changed

    def delete_track(
        self,
        *,
        preset: RotationPreset,
        mode_id: Optional[str],
        track_id: Optional[str],
    ) -> bool:
        """
        删除指定轨道：

        - mode_id 非空 => 从对应 Mode.tracks 中删除 track_id；
        - mode_id 为空 => 从 preset.global_tracks 中删除 track_id。
        删除成功时：
        - 若 preset.entry 指向该轨道，则清空 entry.track_id / entry.node_id。
        """
        tid = (track_id or "").strip()
        if not tid:
            return False

        mid = (mode_id or "").strip()
        deleted = False

        if mid:
            mode = self._find_mode(preset, mid)
            if mode is None:
                return False
            before = len(mode.tracks)
            mode.tracks = [t for t in mode.tracks if (t.id or "") != tid]
            deleted = len(mode.tracks) != before
        else:
            before = len(preset.global_tracks)
            preset.global_tracks = [t for t in preset.global_tracks if (t.id or "") != tid]
            deleted = len(preset.global_tracks) != before

        if not deleted:
            return False

        # 处理入口轨道引用（仅操作新的 entry 结构）
        entry = getattr(preset, "entry", None)
        if entry is not None:
            scope = (getattr(entry, "scope", "global") or "global").strip().lower()
            em = (getattr(entry, "mode_id", "") or "").strip()
            et = (getattr(entry, "track_id", "") or "").strip()

            if mid:
                # 模式轨道：scope=mode && mode_id/track_id 匹配时清空 track/node
                if scope == "mode" and em == mid and et == tid:
                    entry.track_id = ""
                    entry.node_id = ""
            else:
                # 全局轨道：scope=global && track_id 匹配时清空 track/node
                if scope == "global" and et == tid:
                    entry.track_id = ""
                    entry.node_id = ""

        self._mark_dirty()
        return True