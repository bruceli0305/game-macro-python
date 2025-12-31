# rotation_editor/ui/editor/node_panel.py
from __future__ import annotations

import uuid
from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QInputDialog,
    QMessageBox,
    QStyle,
)

from core.profiles import ProfileContext
from core.models.skill import Skill

from qtui.notify import UiNotify
from qtui.icons import load_icon
from rotation_editor.core.models import RotationPreset, Mode, Track, SkillNode, GatewayNode


class NodeListPanel(QWidget):
    """
    右侧“节点”子面板：

    - set_context(ctx, preset)：绑定 ProfileContext & 当前 preset（供技能列表和模式名称用）
    - set_target(mode_id, track_id)：指定当前编辑的 Mode/Track
    - 内部管理节点增删改：
        - 新增技能节点：从 ctx.skills 中选择 Skill
        - 新增网关节点：选择目标 Mode（action="switch_mode"）
        - 上移 / 下移 / 删除
    - 所有修改直接作用于 dataclass，外部通过 mark_dirty 回调标记 rotations 脏
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        notify: UiNotify,
        mark_dirty,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._notify = notify
        self._mark_dirty_cb = mark_dirty

        self._preset: Optional[RotationPreset] = None
        self._mode_id: Optional[str] = None
        self._track_id: Optional[str] = None

        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        lbl_nodes = QLabel("节点 (Nodes):", self)
        root.addWidget(lbl_nodes)

        self._tree = QTreeWidget(self)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.setSelectionBehavior(QTreeWidget.SelectRows)

        headers = ["类型", "标签", "技能ID", "动作", "目标模式"]
        self._tree.setHeaderLabels(headers)
        for i, w in enumerate([60, 120, 140, 80, 120]):
            self._tree.setColumnWidth(i, w)

        root.addWidget(self._tree, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        style = self.style()
        icon_add_skill = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_add_gw = load_icon("settings", style, QStyle.StandardPixmap.SP_DialogOpenButton)
        icon_up = load_icon("up", style, QStyle.StandardPixmap.SP_ArrowUp)
        icon_down = load_icon("down", style, QStyle.StandardPixmap.SP_ArrowDown)
        icon_del_node = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        self._btn_add_skill = QPushButton("新增技能节点", self)
        self._btn_add_skill.setIcon(icon_add_skill)
        self._btn_add_skill.clicked.connect(self._on_add_skill_node)
        btn_row.addWidget(self._btn_add_skill)

        self._btn_add_gw = QPushButton("新增网关节点", self)
        self._btn_add_gw.setIcon(icon_add_gw)
        self._btn_add_gw.clicked.connect(self._on_add_gateway_node)
        btn_row.addWidget(self._btn_add_gw)

        btn_row.addSpacing(12)

        self._btn_up = QPushButton("上移", self)
        self._btn_up.setIcon(icon_up)
        self._btn_up.clicked.connect(self._on_node_up)
        btn_row.addWidget(self._btn_up)

        self._btn_down = QPushButton("下移", self)
        self._btn_down.setIcon(icon_down)
        self._btn_down.clicked.connect(self._on_node_down)
        btn_row.addWidget(self._btn_down)

        btn_row.addSpacing(12)

        self._btn_del = QPushButton("删除节点", self)
        self._btn_del.setIcon(icon_del_node)
        self._btn_del.clicked.connect(self._on_delete_node)
        btn_row.addWidget(self._btn_del)

        btn_row.addStretch(1)
        root.addLayout(btn_row)

    # ---------- 外部 API ----------

    def set_context(self, ctx: ProfileContext, preset: Optional[RotationPreset]) -> None:
        self._ctx = ctx
        self._preset = preset
        self._rebuild_nodes()

    def set_target(self, mode_id: Optional[str], track_id: Optional[str]) -> None:
        self._mode_id = (mode_id or "").strip() or None
        self._track_id = (track_id or "").strip() or None
        self._rebuild_nodes()

    # ---------- 内部：获取当前对象 ----------

    def _current_mode(self) -> Optional[Mode]:
        p = self._preset
        mid = self._mode_id
        if p is None or not mid:
            return None
        for m in p.modes:
            if m.id == mid:
                return m
        return None

    def _current_track(self) -> Optional[Track]:
        m = self._current_mode()
        tid = self._track_id
        if m is None or not tid:
            return None
        for t in m.tracks:
            if t.id == tid:
                return t
        return None

    # ---------- 重建节点列表 ----------

    def _rebuild_nodes(self) -> None:
        self._tree.clear()
        t = self._current_track()
        if t is None:
            return
        p = self._preset
        modes_by_id = {m.id: m.name for m in (p.modes if p else [])}

        for n in t.nodes:
            if isinstance(n, SkillNode):
                typ = "技能"
                label = n.label or "Skill"
                skill_id = n.skill_id or ""
                action = ""
                target_mode = ""
            elif isinstance(n, GatewayNode):
                typ = "网关"
                label = n.label or "Gateway"
                skill_id = ""
                action = n.action or ""
                target_mode = modes_by_id.get(n.target_mode_id or "", "") if n.target_mode_id else ""
            else:
                typ = n.kind or "未知"
                label = n.label or ""
                skill_id = ""
                action = ""
                target_mode = ""

            item = QTreeWidgetItem([typ, label, skill_id, action, target_mode])
            item.setData(0, Qt.UserRole, n.id)
            self._tree.addTopLevelItem(item)

    def _current_node_index(self) -> int:
        t = self._current_track()
        if t is None:
            return -1
        item = self._tree.currentItem()
        if item is None:
            return -1
        nid = item.data(0, Qt.UserRole)
        if not isinstance(nid, str):
            return -1
        for idx, n in enumerate(t.nodes):
            if n.id == nid:
                return idx
        return -1

    # ---------- 按钮行为：新增/移动/删除 ----------

    def _on_add_skill_node(self) -> None:
        t = self._current_track()
        if t is None:
            self._notify.error("请先选择一个轨道")
            return

        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        if not skills:
            self._notify.error("当前 Profile 下还没有技能，请先在“技能配置”页面添加技能")
            return

        items = [f"{s.name or '(未命名)'} [{(s.id or '')[-6:]}]" for s in skills]
        choice, ok = QInputDialog.getItem(
            self,
            "选择技能",
            "请选择要插入的技能：",
            items,
            0,
            False,
        )
        if not ok:
            return

        idx = items.index(choice) if choice in items else 0
        s = skills[idx]
        label = s.name or s.trigger.key or "Skill"
        nid = uuid.uuid4().hex
        node = SkillNode(
            id=nid,
            kind="skill",
            label=label,
            skill_id=s.id or "",
            override_cast_ms=None,
            comment="",
        )
        t.nodes.append(node)
        self._mark_dirty()
        self._rebuild_nodes()

    def _on_add_gateway_node(self) -> None:
        t = self._current_track()
        p = self._preset
        if t is None or p is None:
            self._notify.error("请先选择一个轨道")
            return

        label, ok = QInputDialog.getText(self, "新建网关节点", "网关标签：", text="Gateway")
        if not ok:
            return
        label = (label or "").strip() or "Gateway"

        modes = p.modes or []
        if not modes:
            self._notify.error("当前方案下还没有模式，请先新建模式")
            return

        names = [m.name or "(未命名)" for m in modes]
        choice, ok = QInputDialog.getItem(
            self,
            "选择目标模式",
            "当执行到该网关节点时，切换到哪个模式：",
            names,
            0,
            False,
        )
        if not ok:
            return
        idx = names.index(choice) if choice in names else 0
        target_mode = modes[idx]

        nid = uuid.uuid4().hex
        gw = GatewayNode(
            id=nid,
            kind="gateway",
            label=label,
            condition_id=None,
            action="switch_mode",
            target_mode_id=target_mode.id or "",
            target_track_id=None,
            target_node_index=None,
        )
        t.nodes.append(gw)
        self._mark_dirty()
        self._rebuild_nodes()

    def _on_node_up(self) -> None:
        t = self._current_track()
        if t is None:
            return
        idx = self._current_node_index()
        if idx <= 0:
            return
        t.nodes[idx - 1], t.nodes[idx] = t.nodes[idx], t.nodes[idx - 1]
        self._mark_dirty()
        self._rebuild_nodes()
        self._tree.setCurrentItem(self._tree.topLevelItem(idx - 1))

    def _on_node_down(self) -> None:
        t = self._current_track()
        if t is None:
            return
        idx = self._current_node_index()
        if idx < 0 or idx >= len(t.nodes) - 1:
            return
        t.nodes[idx + 1], t.nodes[idx] = t.nodes[idx], t.nodes[idx + 1]
        self._mark_dirty()
        self._rebuild_nodes()
        self._tree.setCurrentItem(self._tree.topLevelItem(idx + 1))

    def _on_delete_node(self) -> None:
        t = self._current_track()
        if t is None:
            return
        idx = self._current_node_index()
        if idx < 0 or idx >= len(t.nodes):
            self._notify.error("请先选择要删除的节点")
            return
        n = t.nodes[idx]
        ok = QMessageBox.question(
            self,
            "删除节点",
            f"确认删除节点：{n.label or n.kind} ？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return
        del t.nodes[idx]
        self._mark_dirty()
        self._rebuild_nodes()

    # ---------- 脏标记 ----------

    def _mark_dirty(self) -> None:
        try:
            self._mark_dirty_cb()
        except Exception:
            pass