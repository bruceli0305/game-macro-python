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
    QDialog,
)

from core.profiles import ProfileContext
from core.models.skill import Skill

from qtui.notify import UiNotify
from qtui.icons import load_icon

from rotation_editor.core.models import (
    RotationPreset,
    Mode,
    Track,
    SkillNode,
    GatewayNode,
)
from rotation_editor.ui.editor.timeline_view import TrackTimelineView
from rotation_editor.ui.editor.node_props_dialog import NodePropertiesDialog
from rotation_editor.ui.editor.condition_dialog import ConditionEditorDialog


class NodeListPanel(QWidget):
    """
    右侧“节点”子面板（带简易时间轴）：

    - set_context(ctx, preset): 绑定 ProfileContext & 当前 RotationPreset
    - set_target(mode_id, track_id):
        * 若 mode_id 非空 => 编辑该 Mode 下的指定轨道
        * 若 mode_id 为空 且 track_id 非空 => 编辑 preset.global_tracks 中的指定轨道

    提供功能：
    - 新增技能节点：从 ctx.skills 中选 Skill 绑定到 SkillNode
    - 新增网关节点：选择目标 Mode（GatewayNode.action="switch_mode"）
    - 编辑节点：NodePropertiesDialog（支持 SkillNode / GatewayNode 的详细属性）
    - 设置条件：ConditionEditorDialog（只对 GatewayNode 可用，将 condition_id 绑定到网关）
    - 上移 / 下移 / 删除节点
    - 时间轴视图：按节点顺序绘制盒子，宽度与大致时长成比例
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

        # 时间轴视图
        self._timeline = TrackTimelineView(self)
        root.addWidget(self._timeline)
        self._timeline.nodeClicked.connect(self._on_timeline_clicked)

        # 节点列表
        self._tree = QTreeWidget(self)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.setSelectionBehavior(QTreeWidget.SelectRows)
        self._tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)

        headers = ["类型", "标签", "技能ID", "动作", "目标模式"]
        self._tree.setHeaderLabels(headers)
        for i, w in enumerate([60, 120, 140, 80, 120]):
            self._tree.setColumnWidth(i, w)

        root.addWidget(self._tree, 1)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        style = self.style()
        icon_add_skill = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_add_gw = load_icon("settings", style, QStyle.StandardPixmap.SP_DialogOpenButton)
        icon_up = load_icon("up", style, QStyle.StandardPixmap.SP_ArrowUp)
        icon_down = load_icon("down", style, QStyle.StandardPixmap.SP_ArrowDown)
        icon_del_node = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)
        icon_edit = load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogDetailedView)

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

        self._btn_edit = QPushButton("编辑节点", self)
        self._btn_edit.setIcon(icon_edit)
        self._btn_edit.clicked.connect(self._on_edit_node)
        btn_row.addWidget(self._btn_edit)

        self._btn_cond = QPushButton("设置条件", self)
        self._btn_cond.setIcon(icon_edit)
        self._btn_cond.clicked.connect(self._on_set_condition)
        self._btn_cond.setEnabled(False)
        btn_row.addWidget(self._btn_cond)

        btn_row.addStretch(1)
        root.addLayout(btn_row)

    # ---------- 外部 API ----------

    def set_context(self, ctx: ProfileContext, preset: Optional[RotationPreset]) -> None:
        self._ctx = ctx
        self._preset = preset
        self._rebuild_nodes()

    def set_target(self, mode_id: Optional[str], track_id: Optional[str]) -> None:
        """
        mode_id 非空 => 模式轨道
        mode_id 为空 => 全局轨道
        """
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
        p = self._preset
        tid = self._track_id
        if p is None or not tid:
            return None

        # 有 mode_id 时，视为模式轨道
        if self._mode_id:
            m = self._current_mode()
            if m is None:
                return None
            for t in m.tracks:
                if t.id == tid:
                    return t
            return None

        # 无 mode_id，则优先按全局轨道查找
        for t in p.global_tracks:
            if t.id == tid:
                return t
        return None

    # ---------- 重建节点列表 & 时间轴 ----------

    def _rebuild_nodes(self) -> None:
        self._tree.clear()
        t = self._current_track()
        nodes: List[SkillNode | GatewayNode] = []
        durations: List[int] = []

        if t is not None:
            nodes = list(t.nodes)
            p = self._preset
            modes_by_id = {m.id: m.name for m in (p.modes if p else [])}

            # 为计算时长，构建 Skill 映射
            skills_by_id: dict[str, Skill] = {}
            try:
                for s in getattr(self._ctx.skills, "skills", []) or []:
                    if s.id:
                        skills_by_id[s.id] = s
            except Exception:
                pass

            for n in t.nodes:
                # 列表显示
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
                    typ = getattr(n, "kind", "") or "未知"
                    label = getattr(n, "label", "") or ""
                    skill_id = ""
                    action = ""
                    target_mode = ""

                item = QTreeWidgetItem([typ, label, skill_id, action, target_mode])
                item.setData(0, Qt.UserRole, getattr(n, "id", ""))
                self._tree.addTopLevelItem(item)

                # 计算时长（毫秒）用于时间轴宽度
                d = 1000  # 默认 1 秒
                try:
                    if isinstance(n, SkillNode):
                        if n.override_cast_ms is not None and n.override_cast_ms > 0:
                            d = int(n.override_cast_ms)
                        else:
                            s = skills_by_id.get(n.skill_id or "", None)
                            if s is not None and getattr(s.cast, "readbar_ms", 0) > 0:
                                d = int(s.cast.readbar_ms)
                    elif isinstance(n, GatewayNode):
                        d = 500  # 网关节点统一给个较短长度
                    else:
                        d = 800
                except Exception:
                    d = 1000
                durations.append(d)

        # 更新时间轴视图
        if nodes:
            from rotation_editor.ui.editor.timeline_view import TrackTimelineView  # type: ignore  # 避免循环
            self._timeline.set_nodes_with_durations(nodes, durations)
        else:
            self._timeline.set_nodes([])

        self._timeline.set_current_index(-1)

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
            if getattr(n, "id", "") == nid:
                return idx
        return -1

    # ---------- 列表与时间轴联动 ----------

    def _on_tree_selection_changed(self) -> None:
        """
        当树形列表选中项变化时：
        - 更新时间轴高亮；
        - 根据是否为 GatewayNode 启用/禁用“设置条件”按钮。
        """
        idx = self._current_node_index()
        self._timeline.set_current_index(idx)

        t = self._current_track()
        enable_cond = False
        if t is not None and 0 <= idx < len(t.nodes):
            n = t.nodes[idx]
            if isinstance(n, GatewayNode):
                enable_cond = True
        self._btn_cond.setEnabled(enable_cond)

    def _on_timeline_clicked(self, index: int) -> None:
        """
        当点击时间轴上的盒子时，选中树形列表对应节点。
        """
        if index < 0:
            return
        item = self._tree.topLevelItem(index)
        if item is not None:
            self._tree.setCurrentItem(item)

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """
        双击节点时打开属性编辑。
        """
        self._on_edit_node()

    # ---------- 按钮行为：新增/编辑/条件/移动/删除 ----------

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

    def _on_edit_node(self) -> None:
        """
        打开当前选中节点的属性编辑对话框。
        """
        t = self._current_track()
        p = self._preset
        if t is None or p is None:
            self._notify.error("请先选择一个轨道")
            return

        idx = self._current_node_index()
        if idx < 0 or idx >= len(t.nodes):
            self._notify.error("请先选择要编辑的节点")
            return

        n = t.nodes[idx]
        dlg = NodePropertiesDialog(
            ctx=self._ctx,
            preset=p,
            node=n,
            notify=self._notify,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            self._mark_dirty()
            self._rebuild_nodes()
            if 0 <= idx < self._tree.topLevelItemCount():
                self._tree.setCurrentItem(self._tree.topLevelItem(idx))

    def _on_set_condition(self) -> None:
        """
        为当前选中的网关节点设置/编辑条件。
        """
        t = self._current_track()
        p = self._preset
        if t is None or p is None:
            self._notify.error("请先选择一个轨道")
            return

        idx = self._current_node_index()
        if idx < 0 or idx >= len(t.nodes):
            self._notify.error("请先选择一个节点")
            return

        n = t.nodes[idx]
        if not isinstance(n, GatewayNode):
            self._notify.error("当前节点不是网关节点，无法设置条件")
            return

        dlg = ConditionEditorDialog(
            preset=p,
            gateway=n,
            notify=self._notify,
            mark_dirty=self._mark_dirty,
            parent=self,
        )
        dlg.exec()

        # 条件可能已改变，刷新列表并保留当前选中
        self._rebuild_nodes()
        if 0 <= idx < self._tree.topLevelItemCount():
            self._tree.setCurrentItem(self._tree.topLevelItem(idx))

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
    def select_node_index(self, index: int) -> None:
        """
        供外部调用：根据索引选中当前轨道上的某个节点。
        """
        if index < 0 or index >= self._tree.topLevelItemCount():
            return
        item = self._tree.topLevelItem(index)
        if item is not None:
            self._tree.setCurrentItem(item)