# rotation_editor/ui/editor/node_panel.py
from __future__ import annotations

import uuid
import logging
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
from rotation_editor.core.services.rotation_edit_service import RotationEditService
from rotation_editor.ui.editor.node_props_dialog import NodePropertiesDialog
from rotation_editor.ui.editor.condition_dialog import ConditionEditorDialog

log = logging.getLogger(__name__)


class NodeListPanel(QWidget):
    """
    节点编辑面板（逻辑组件，当前不直接显示到 UI）：

    职责：
    - 绑定 ProfileContext & 当前 RotationPreset
    - 绑定“目标轨道”（mode_id + track_id）
    - 使用 RotationEditService 对当前轨道的节点进行：
        * 列表展示（QTreeWidget）
        * 新增技能节点 / 网关节点
        * 编辑节点属性（NodePropertiesDialog）
        * 设置条件（ConditionEditorDialog）
        * 上移 / 下移 / 删除节点

    注意：
    - 本面板不加入 layout，而是由 RotationEditorPage 调用其方法作为逻辑助手。
    - 若未来需要重新展示“列表编辑”UI，只需将本 widget 加入到某个 layout 即可。
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        edit_svc: RotationEditService,
        notify: UiNotify,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._edit_svc = edit_svc
        self._notify = notify

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

        # 节点列表
        self._tree = QTreeWidget(self)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.setSelectionBehavior(QTreeWidget.SelectRows)
        self._tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)

        # 增加“步骤(step_index)”这一列
        headers = ["类型", "步骤", "标签", "技能ID", "动作", "目标模式", "条件"]
        self._tree.setHeaderLabels(headers)
        for i, w in enumerate([60, 60, 120, 140, 80, 120, 140]):
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
        """
        绑定新的 ProfileContext 和 RotationPreset。
        """
        self._ctx = ctx
        self._preset = preset
        self._rebuild_nodes()

    def set_target(self, mode_id: Optional[str], track_id: Optional[str]) -> None:
        """
        绑定当前编辑的“目标轨道”：
        - mode_id 非空 => 模式轨道
        - mode_id 为空 且 track_id 非空 => 全局轨道
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
        """
        优先通过服务查找 Track，保持逻辑入口一致。
        """
        p = self._preset
        if p is None:
            return None
        return self._edit_svc.get_track(p, self._mode_id, self._track_id)

    # ---------- 重建节点列表 ----------

    def _rebuild_nodes(self) -> None:
        """
        根据当前 preset/mode_id/track_id 重建节点列表，并做编辑期告警：
        - SkillNode.skill_id 缺失/不存在：标红 + 提示
        - GatewayNode.condition_id 缺失/无效：标红 + 提示
        - Condition.kind 非 groups 或引用缺：标红
        """
        self._tree.clear()
        t = self._current_track()
        if t is None:
            self._btn_cond.setEnabled(False)
            return

        p = self._preset

        # 索引
        skills_by_id = {s.id: s for s in (getattr(self._ctx.skills, "skills", []) or []) if getattr(s, "id", "")}
        modes_by_id = {m.id: m.name for m in (p.modes if p else [])}
        cond_by_id = {c.id: c for c in (p.conditions if p else [])}

        # 额外：判断 condition 是否“有效”
        def cond_is_valid(c) -> tuple[bool, str]:
            if c is None:
                return False, "条件不存在"
            if (c.kind or "").strip().lower() != "groups":
                return False, f"条件 kind 非 groups：{c.kind}"
            expr = c.expr or {}
            if not isinstance(expr, dict):
                return False, "条件 expr 非 dict"
            groups = expr.get("groups", [])
            if not isinstance(groups, list):
                return False, "条件 groups 非 list"
            # 引用检查（只做简单缺 ref）
            points_by_id = {pp.id: pp for pp in (getattr(self._ctx.points, "points", []) or []) if getattr(pp, "id", "")}
            for g in groups:
                if not isinstance(g, dict):
                    return False, "group 非 dict"
                atoms = g.get("atoms", [])
                if not isinstance(atoms, list):
                    return False, "atoms 非 list"
                for a in atoms:
                    if not isinstance(a, dict):
                        return False, "atom 非 dict"
                    t = (a.get("type") or "").strip().lower()
                    if t == "pixel_point":
                        pid = (a.get("point_id") or "").strip()
                        if not pid or pid not in points_by_id:
                            return False, "引用了不存在的点位"
                    if t in ("pixel_skill", "skill_cast_ge"):
                        sid = (a.get("skill_id") or "").strip()
                        if not sid or sid not in skills_by_id:
                            return False, "引用了不存在的技能"
            return True, ""

        for n in t.nodes:
            warn = False
            warn_msgs: list[str] = []

            cond_text = ""
            if isinstance(n, SkillNode):
                typ = "技能"
                label = n.label or "Skill"
                sid = (n.skill_id or "").strip()
                if not sid:
                    skill_id = "(未设置)"
                    warn = True
                    warn_msgs.append("skill_id 为空")
                elif sid not in skills_by_id:
                    skill_id = f"(技能缺失:{sid[-6:]})"
                    warn = True
                    warn_msgs.append(f"skill_id 不存在：{sid}")
                else:
                    skill_id = sid
                action = ""
                target_mode = ""
            elif isinstance(n, GatewayNode):
                typ = "网关"
                label = n.label or "Gateway"
                skill_id = ""
                action = (n.action or "").strip()
                target_mode = modes_by_id.get(n.target_mode_id or "", "") if n.target_mode_id else ""

                cid = getattr(n, "condition_id", None)
                if cid:
                    cobj = cond_by_id.get(cid)
                    ok, reason = cond_is_valid(cobj)
                    if cobj is None:
                        cond_text = f"(条件缺失: {cid[-6:]})"
                        warn = True
                        warn_msgs.append(f"condition_id 不存在：{cid}")
                    elif not ok:
                        cname = getattr(cobj, "name", "") or "(未命名条件)"
                        cond_text = f"{cname} [无效]"
                        warn = True
                        warn_msgs.append(f"条件无效：{reason}")
                    else:
                        cname = getattr(cobj, "name", "") or "(未命名条件)"
                        cond_text = cname
                else:
                    cond_text = ""
            else:
                typ = getattr(n, "kind", "") or "未知"
                label = getattr(n, "label", "") or ""
                skill_id = ""
                action = ""
                target_mode = ""

            # step
            try:
                step_txt = str(int(getattr(n, "step_index", 0) or 0))
            except Exception:
                step_txt = "0"

            item = QTreeWidgetItem([typ, step_txt, label, skill_id, action, target_mode, cond_text])
            item.setData(0, Qt.UserRole, getattr(n, "id", ""))

            if warn:
                # 整行标红 + tooltip
                for col in range(0, 7):
                    item.setForeground(col, QBrush(QColor(255, 90, 90)))
                item.setToolTip(0, "\n".join(warn_msgs))
                item.setToolTip(3, "\n".join(warn_msgs))
                item.setToolTip(6, "\n".join(warn_msgs))

            self._tree.addTopLevelItem(item)

        self._btn_cond.setEnabled(False)

    def _current_node_index(self) -> int:
        """
        返回当前选中节点在 Track.nodes 列表中的索引，若无选中或找不到则返回 -1。
        """
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

    # ---------- 列表联动 ----------

    def _on_tree_selection_changed(self) -> None:
        """
        当树形列表选中项变化时：
        - 根据是否为 GatewayNode 启用/禁用“设置条件”按钮。
        """
        idx = self._current_node_index()
        t = self._current_track()
        enable_cond = False
        if t is not None and 0 <= idx < len(t.nodes):
            n = t.nodes[idx]
            if isinstance(n, GatewayNode):
                enable_cond = True
        self._btn_cond.setEnabled(enable_cond)

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """
        双击节点时打开属性编辑。
        """
        self._on_edit_node()

    # ---------- 按钮行为：新增/编辑/条件/移动/删除 ----------

    def _on_add_skill_node(self) -> None:
        p = self._preset
        if p is None:
            self._notify.error("当前没有选中的方案")
            return

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

        node = self._edit_svc.add_skill_node(
            preset=p,
            mode_id=self._mode_id,
            track_id=self._track_id,
            skill_id=s.id or "",
            label=label,
            override_cast_ms=None,
            comment="",
        )
        if node is None:
            self._notify.error("新增技能节点失败：轨道不存在")
            return

        self._rebuild_nodes()

    def _on_add_gateway_node(self) -> None:
        """
        在当前轨道末尾新增一个网关节点。

        旧版本在此处会强制要求选择“目标模式”，以便立即配置 switch_mode。
        为了让操作更轻量，这里改为：

        - 仅询问网关标签；
        - 新建时 action="end"，不指定目标模式/轨道/节点；
        - 用户后续可以通过“编辑节点”对话框调整为 switch_mode/jump_track/jump_node。

        这样就不会在“新增网关节点”时就必须选目标。
        """
        p = self._preset
        if p is None:
            self._notify.error("当前没有选中的方案")
            return

        t = self._current_track()
        if t is None:
            self._notify.error("请先选择一个轨道")
            return

        label, ok = QInputDialog.getText(self, "新建网关节点", "网关标签：", text="Gateway")
        if not ok:
            return
        label = (label or "").strip() or "Gateway"

        # 直接创建一个 action="end" 的 GatewayNode（无目标），后续由用户编辑
        from rotation_editor.core.models import GatewayNode  # 避免循环导入

        nid = self._edit_svc._new_id()  # 使用服务内部的 ID 生成（已存在）

        gw = GatewayNode(
            id=nid,
            kind="gateway",
            label=label,
            condition_id=None,
            action="end",
            target_mode_id=None,
            target_track_id=None,
            target_node_index=None,
        )
        t.nodes.append(gw)
        self._edit_svc.mark_dirty()

        self._rebuild_nodes()

    def _on_edit_node(self) -> None:
        """
        打开当前选中节点的属性编辑对话框。
        """
        p = self._preset
        if p is None:
            self._notify.error("当前没有选中的方案")
            return

        t = self._current_track()
        if t is None:
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
            mode_id=self._mode_id,
            track_id=self._track_id,
            notify=self._notify,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            # NodePropertiesDialog 直接修改了节点对象；这里只需标记脏并重建列表
            self._mark_dirty()
            self._rebuild_nodes()
            if 0 <= idx < self._tree.topLevelItemCount():
                self._tree.setCurrentItem(self._tree.topLevelItem(idx))   
       
    def _on_set_condition(self) -> None:
        """
        为当前选中的网关节点设置/编辑条件。
        """
        p = self._preset
        if p is None:
            self._notify.error("当前没有选中的方案")
            return

        t = self._current_track()
        if t is None:
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
            ctx=self._ctx,
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
        p = self._preset
        if p is None:
            return
        idx = self._current_node_index()
        if idx <= 0:
            return
        moved = self._edit_svc.move_node_up(
            preset=p,
            mode_id=self._mode_id,
            track_id=self._track_id,
            index=idx,
        )
        if not moved:
            return
        self._rebuild_nodes()
        self._tree.setCurrentItem(self._tree.topLevelItem(idx - 1))

    def _on_node_down(self) -> None:
        p = self._preset
        if p is None:
            return
        idx = self._current_node_index()
        if idx < 0:
            return
        moved = self._edit_svc.move_node_down(
            preset=p,
            mode_id=self._mode_id,
            track_id=self._track_id,
            index=idx,
        )
        if not moved:
            return
        self._rebuild_nodes()
        self._tree.setCurrentItem(self._tree.topLevelItem(idx + 1))

    def _on_delete_node(self) -> None:
        p = self._preset
        if p is None:
            return
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
            f"确认删除节点：{n.label or getattr(n, 'kind', '')} ？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return
        deleted = self._edit_svc.delete_node(
            preset=p,
            mode_id=self._mode_id,
            track_id=self._track_id,
            index=idx,
        )
        if not deleted:
            return
        self._rebuild_nodes()

    # ---------- 对外便捷方法：供主编辑器调用 ----------

    def select_node_index(self, index: int) -> None:
        """
        供外部调用：根据索引选中当前轨道上的某个节点。
        """
        if index < 0 or index >= self._tree.topLevelItemCount():
            return
        item = self._tree.topLevelItem(index)
        if item is not None:
            self._tree.setCurrentItem(item)

    def add_skill_node(self) -> None:
        """在当前轨道末尾新增一个技能节点。"""
        self._on_add_skill_node()

    def add_gateway_node(self) -> None:
        """在当前轨道末尾新增一个网关节点。"""
        self._on_add_gateway_node()

    def edit_current_node(self) -> None:
        """打开当前选中节点的属性编辑对话框。"""
        self._on_edit_node()

    def set_condition_for_current(self) -> None:
        """为当前选中节点（若为 GatewayNode）设置/编辑条件。"""
        self._on_set_condition()

    def delete_current_node(self) -> None:
        """删除当前选中节点。"""
        self._on_delete_node()

    # ---------- 脏标记 ----------

    def _mark_dirty(self) -> None:
        """
        供 ConditionEditorDialog / NodePropertiesDialog 调用。
        实际委托给 RotationEditService.mark_dirty()。
        """
        try:
            self._edit_svc.mark_dirty()
        except Exception:
            log.exception("NodeListPanel._mark_dirty: edit_svc.mark_dirty failed")