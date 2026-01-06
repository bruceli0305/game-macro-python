from __future__ import annotations

import uuid
import logging
from typing import Optional, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
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

from rotation_editor.core.models import RotationPreset, Track, SkillNode, GatewayNode, Condition
from rotation_editor.core.services.rotation_edit_service import RotationEditService
from rotation_editor.ui.editor.node_props_dialog import NodePropertiesDialog
from rotation_editor.ui.editor.condition_dialog import ConditionEditorDialog

from rotation_editor.ast import compile_expr_json

log = logging.getLogger(__name__)


class NodeListPanel(QWidget):
    def __init__(self, *, ctx: ProfileContext, edit_svc: RotationEditService, notify: UiNotify, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._edit_svc = edit_svc
        self._notify = notify
        self._preset: Optional[RotationPreset] = None
        self._mode_id: Optional[str] = None
        self._track_id: Optional[str] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        root.addWidget(QLabel("节点 (Nodes):", self))

        self._tree = QTreeWidget(self)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree.setSelectionBehavior(QTreeWidget.SelectRows)
        self._tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)

        self._tree.setHeaderLabels(["类型", "步骤", "标签", "技能ID", "动作", "目标", "条件"])
        for i, w in enumerate([60, 60, 140, 160, 90, 220, 220]):
            self._tree.setColumnWidth(i, w)

        root.addWidget(self._tree, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        style = self.style()

        self._btn_add_skill = QPushButton("新增技能节点", self)
        self._btn_add_skill.setIcon(load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon))
        self._btn_add_skill.clicked.connect(self._on_add_skill_node)
        btn_row.addWidget(self._btn_add_skill)

        self._btn_add_gw = QPushButton("新增网关节点", self)
        self._btn_add_gw.setIcon(load_icon("settings", style, QStyle.StandardPixmap.SP_DialogOpenButton))
        self._btn_add_gw.clicked.connect(self._on_add_gateway_node)
        btn_row.addWidget(self._btn_add_gw)

        btn_row.addSpacing(12)

        self._btn_up = QPushButton("上移", self)
        self._btn_up.setIcon(load_icon("up", style, QStyle.StandardPixmap.SP_ArrowUp))
        self._btn_up.clicked.connect(self._on_node_up)
        btn_row.addWidget(self._btn_up)

        self._btn_down = QPushButton("下移", self)
        self._btn_down.setIcon(load_icon("down", style, QStyle.StandardPixmap.SP_ArrowDown))
        self._btn_down.clicked.connect(self._on_node_down)
        btn_row.addWidget(self._btn_down)

        btn_row.addSpacing(12)

        self._btn_del = QPushButton("删除节点", self)
        self._btn_del.setIcon(load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon))
        self._btn_del.clicked.connect(self._on_delete_node)
        btn_row.addWidget(self._btn_del)

        self._btn_edit = QPushButton("编辑节点", self)
        self._btn_edit.setIcon(load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self._btn_edit.clicked.connect(self._on_edit_node)
        btn_row.addWidget(self._btn_edit)

        self._btn_cond = QPushButton("设置条件", self)
        self._btn_cond.setIcon(load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self._btn_cond.clicked.connect(self._on_set_condition)
        self._btn_cond.setEnabled(False)
        btn_row.addWidget(self._btn_cond)

        btn_row.addStretch(1)
        root.addLayout(btn_row)

    def set_context(self, ctx: ProfileContext, preset: Optional[RotationPreset]) -> None:
        self._ctx = ctx
        self._preset = preset
        self._rebuild_nodes()

    def set_target(self, mode_id: Optional[str], track_id: Optional[str]) -> None:
        self._mode_id = (mode_id or "").strip() or None
        self._track_id = (track_id or "").strip() or None
        self._rebuild_nodes()

    def _current_track(self) -> Optional[Track]:
        if self._preset is None:
            return None
        return self._edit_svc.get_track(self._preset, self._mode_id, self._track_id)

    def _gateway_condition_text(self, gw: GatewayNode) -> Tuple[str, bool, str]:
        p = self._preset
        if p is None:
            return "", True, ""
        ce = getattr(gw, "condition_expr", None)
        if isinstance(ce, dict) and ce:
            res = compile_expr_json(ce, ctx=self._ctx, path="$.condition_expr")
            if res.ok():
                return "内联条件", True, "内联条件（优先）"
            return "内联条件 [无效]", False, "内联条件编译失败"
        cid = (getattr(gw, "condition_id", None) or "").strip()
        if not cid:
            return "", True, ""
        cobj = next((c for c in (p.conditions or []) if (c.id or "").strip() == cid), None)
        if cobj is None:
            return f"(条件缺失:{cid[-6:]})", False, f"condition_id 不存在：{cid}"
        expr = getattr(cobj, "expr", None)
        if not isinstance(expr, dict) or not expr:
            return f"{cobj.name or '(未命名条件)'} [无效]", False, "Condition.expr 不是 AST JSON dict"
        res = compile_expr_json(expr, ctx=self._ctx, path="$.condition.expr")
        if res.ok():
            return cobj.name or "(未命名条件)", True, ""
        return f"{cobj.name or '(未命名条件)'} [无效]", False, "条件编译失败"

    def _rebuild_nodes(self) -> None:
        self._tree.clear()
        t = self._current_track()
        if t is None:
            self._btn_cond.setEnabled(False)
            return

        skills_by_id = {s.id: s for s in (getattr(self._ctx.skills, "skills", []) or []) if getattr(s, "id", "")}
        red = QBrush(QColor(255, 90, 90))

        for n in (t.nodes or []):
            warn = False
            msgs: List[str] = []

            step_txt = "0"
            try:
                step_txt = str(int(getattr(n, "step_index", 0) or 0))
            except Exception:
                pass

            typ = getattr(n, "kind", "") or "未知"
            label = getattr(n, "label", "") or ""
            skill_id = ""
            action = ""
            target_text = ""
            cond_text = ""

            if isinstance(n, SkillNode):
                typ = "技能"
                label = n.label or "Skill"
                sid = (n.skill_id or "").strip()
                if not sid:
                    warn = True
                    msgs.append("skill_id 为空")
                elif sid not in skills_by_id:
                    warn = True
                    msgs.append("skill_id 不存在")
                    skill_id = f"(技能缺失:{sid[-6:]})"
                else:
                    skill_id = sid

            elif isinstance(n, GatewayNode):
                typ = "网关"
                label = n.label or "Gateway"
                action = (n.action or "switch_mode").strip()

                # 目标描述：模式 / 轨道 / 节点 后 6 位
                tm = (getattr(n, "target_mode_id", "") or "").strip()
                tt = (getattr(n, "target_track_id", "") or "").strip()
                tn = (getattr(n, "target_node_id", "") or "").strip()
                parts: List[str] = []
                if tm:
                    parts.append(f"模式:{tm[-6:]}")
                if tt:
                    parts.append(f"轨道:{tt[-6:]}")
                if tn:
                    parts.append(f"节点:{tn[-6:]}")
                target_text = " / ".join(parts)

                ctext, okc, ctip = self._gateway_condition_text(n)
                cond_text = ctext
                if not okc:
                    warn = True
                    msgs.append(f"条件无效：{ctip}")

                act = (n.action or "").strip().lower()
                if act in ("jump_node", "jump_track") and not (getattr(n, "target_node_id", "") or "").strip():
                    warn = True
                    msgs.append("缺少 target_node_id")

            else:
                warn = True
                msgs.append("未知节点类型")

            item = QTreeWidgetItem([typ, step_txt, label, skill_id, action, target_text, cond_text])
            item.setData(0, Qt.UserRole, getattr(n, "id", ""))

            if warn:
                for col in range(0, 7):
                    item.setForeground(col, red)
                tip = "\n".join(msgs)
                for col in range(0, 7):
                    item.setToolTip(col, tip)

            self._tree.addTopLevelItem(item)

        self._btn_cond.setEnabled(False)

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
        for idx, n in enumerate(t.nodes or []):
            if (getattr(n, "id", "") or "") == nid:
                return idx
        return -1

    def _on_tree_selection_changed(self) -> None:
        idx = self._current_node_index()
        t = self._current_track()
        enable = False
        if t is not None and 0 <= idx < len(t.nodes):
            enable = isinstance(t.nodes[idx], GatewayNode)
        self._btn_cond.setEnabled(enable)

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        self._on_edit_node()

    def _on_add_skill_node(self) -> None:
        if self._preset is None:
            self._notify.error("当前没有选中的方案")
            return
        t = self._current_track()
        if t is None:
            self._notify.error("请先选择一个轨道")
            return
        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        if not skills:
            self._notify.error("当前没有技能")
            return

        items = [f"{s.name or '(未命名)'} [{(s.id or '')[-6:]}]" for s in skills]
        choice, ok = QInputDialog.getItem(self, "选择技能", "请选择要插入的技能：", items, 0, False)
        if not ok:
            return
        idx = items.index(choice) if choice in items else 0
        s = skills[idx]

        node = self._edit_svc.add_skill_node(
            preset=self._preset,
            mode_id=self._mode_id,
            track_id=self._track_id,
            skill_id=s.id or "",
            label=s.name or s.trigger.key or "Skill",
        )
        if node is None:
            self._notify.error("新增技能节点失败")
            return
        self._rebuild_nodes()

    def _on_add_gateway_node(self) -> None:
        if self._preset is None:
            self._notify.error("当前没有选中的方案")
            return
        t = self._current_track()
        if t is None:
            self._notify.error("请先选择一个轨道")
            return

        label, ok = QInputDialog.getText(self, "新建网关节点", "网关标签：", text="Gateway")
        if not ok:
            return

        gw = GatewayNode(
            id=uuid.uuid4().hex,
            kind="gateway",
            label=(label or "").strip() or "Gateway",
            condition_id=None,
            condition_expr=None,
            action="end",
            target_mode_id=None,
            target_track_id=None,
            target_node_id=None,
        )
        t.nodes.append(gw)
        self._edit_svc.mark_dirty()
        self._rebuild_nodes()

    def _on_edit_node(self) -> None:
        if self._preset is None:
            self._notify.error("当前没有选中的方案")
            return
        t = self._current_track()
        if t is None:
            self._notify.error("请先选择轨道")
            return
        idx = self._current_node_index()
        if idx < 0 or idx >= len(t.nodes):
            self._notify.error("请先选择节点")
            return
        n = t.nodes[idx]
        dlg = NodePropertiesDialog(
            ctx=self._ctx,
            preset=self._preset,
            node=n,
            mode_id=self._mode_id,
            track_id=self._track_id,
            notify=self._notify,
            parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            self._mark_dirty()
            self._rebuild_nodes()

    def _on_set_condition(self) -> None:
        if self._preset is None:
            self._notify.error("当前没有选中的方案")
            return
        t = self._current_track()
        if t is None:
            self._notify.error("请先选择轨道")
            return
        idx = self._current_node_index()
        if idx < 0 or idx >= len(t.nodes):
            self._notify.error("请先选择节点")
            return
        n = t.nodes[idx]
        if not isinstance(n, GatewayNode):
            self._notify.error("当前节点不是网关节点")
            return
        dlg = ConditionEditorDialog(ctx=self._ctx, preset=self._preset, gateway=n, notify=self._notify, mark_dirty=self._mark_dirty, parent=self)
        dlg.exec()
        self._rebuild_nodes()

    def _on_node_up(self) -> None:
        if self._preset is None:
            return
        idx = self._current_node_index()
        if idx <= 0:
            return
        if self._edit_svc.move_node_up(preset=self._preset, mode_id=self._mode_id, track_id=self._track_id, index=idx):
            self._rebuild_nodes()

    def _on_node_down(self) -> None:
        if self._preset is None:
            return
        idx = self._current_node_index()
        if idx < 0:
            return
        if self._edit_svc.move_node_down(preset=self._preset, mode_id=self._mode_id, track_id=self._track_id, index=idx):
            self._rebuild_nodes()

    def _on_delete_node(self) -> None:
        if self._preset is None:
            return
        t = self._current_track()
        if t is None:
            return
        idx = self._current_node_index()
        if idx < 0 or idx >= len(t.nodes):
            self._notify.error("请先选择要删除的节点")
            return
        n = t.nodes[idx]
        ok = QMessageBox.question(self, "删除节点", f"确认删除节点：{getattr(n,'label','') or getattr(n,'kind','')}？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ok != QMessageBox.Yes:
            return
        if self._edit_svc.delete_node(preset=self._preset, mode_id=self._mode_id, track_id=self._track_id, index=idx):
            self._rebuild_nodes()

    def _mark_dirty(self) -> None:
        try:
            self._edit_svc.mark_dirty()
        except Exception:
            log.exception("NodeListPanel._mark_dirty failed")

    def add_skill_node(self) -> None:
        """
        对外公开的“新增技能节点”接口：
        - 供 TimelineCanvas 右键菜单调用
        - 内部复用 _on_add_skill_node 的逻辑
        """
        self._on_add_skill_node()

    def add_gateway_node(self) -> None:
        """
        对外公开的“新增网关节点”接口：
        - 供 TimelineCanvas 右键菜单调用
        - 内部复用 _on_add_gateway_node 的逻辑
        """
        self._on_add_gateway_node()