# rotation_editor/ui/editor/condition_dialog.py
from __future__ import annotations

import uuid
import json
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QStyle,
    QComboBox,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QInputDialog,
)

from core.profiles import ProfileContext
from core.models.point import Point
from core.models.skill import Skill

from qtui.icons import load_icon
from qtui.notify import UiNotify
from rotation_editor.core.models import RotationPreset, Condition, GatewayNode, Track, Mode


# ---------- 内部：原子条件结构 ----------

@dataclass
class AtomCond:
    """
    UI 内部使用的原子条件结构：
    - kind: "pixel_point" | "pixel_skill"
    - ref_id: point_id 或 skill_id
    - tolerance: 容差 0..255
    - neg: 是否取反（NOT）
    """
    kind: str
    ref_id: str
    tolerance: int
    neg: bool = False


class ConditionEditorDialog(QDialog):
    """
    条件编辑对话框（针对某个 RotationPreset）：

    - 左侧：条件列表（Condition.name + 使用次数）
    - 右侧：当前条件的 basic + AST 构建器：
        * 名称
        * 顶层逻辑：全部满足 (AND) / 任一满足 (OR)
        * 原子条件列表（仅支持像素条件：点位 / 技能像素 + 取反 + 容差）

    数据结构：
    - Condition.kind="expr_tree_v1"
    - Condition.expr 为 AST：
        * 逻辑节点：
          - {"type": "logic_and", "children": [...]}
          - {"type": "logic_or",  "children": [...]}
          - {"type": "logic_not", "child": {...}}
        * 原子节点：
          - {"type": "pixel_point", "point_id": "...", "tolerance": 10}
          - {"type": "pixel_skill", "skill_id": "...", "tolerance": 5}
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        preset: RotationPreset,
        gateway: Optional[GatewayNode],
        notify: UiNotify,
        mark_dirty,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑条件")
        self.resize(620, 420)

        self._ctx = ctx
        self._preset = preset
        self._gateway = gateway
        self._notify = notify
        self._mark_dirty_cb = mark_dirty

        self._current_cond_id: Optional[str] = None
        self._building = False

        # 顶层逻辑："and" / "or"
        self._logic_op: str = "and"
        # 当前条件的原子条件列表
        self._atoms: List[AtomCond] = []
        # 条件使用次数：cond_id -> count
        self._usage_by_id: Dict[str, int] = {}

        self._build_ui()
        self._reload_from_preset()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # 顶部说明
        lbl_tip = QLabel(
            "说明：当前支持基于像素的条件组合：\n"
            "- 原子条件：点位颜色匹配 / 技能像素匹配（带容差）\n"
            "- 顶层逻辑：全部满足(AND) 或 任一满足(OR)\n"
            "- 每条原子条件可选择取反 (NOT)\n"
            "- 左侧列表会显示每个条件被网关节点引用的次数（未使用/使用 N 次）。",
            self,
        )
        lbl_tip.setWordWrap(True)
        layout.addWidget(lbl_tip)

        body_row = QHBoxLayout()
        body_row.setSpacing(8)
        layout.addLayout(body_row, 1)

        # 左侧：条件列表
        left_col = QVBoxLayout()
        left_col.setSpacing(4)

        lbl_list = QLabel("条件列表:", self)
        left_col.addWidget(lbl_list)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.currentItemChanged.connect(self._on_select)
        left_col.addWidget(self._list, 1)

        # 左侧按钮
        style = self.style()
        icon_add = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_del = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        left_btn_row = QHBoxLayout()
        self._btn_new = QPushButton("新建条件", self)
        self._btn_new.setIcon(icon_add)
        self._btn_new.clicked.connect(self._on_new)
        left_btn_row.addWidget(self._btn_new)

        self._btn_delete = QPushButton("删除条件", self)
        self._btn_delete.setIcon(icon_del)
        self._btn_delete.clicked.connect(self._on_delete)
        left_btn_row.addWidget(self._btn_delete)

        left_col.addLayout(left_btn_row)

        body_row.addLayout(left_col, 1)

        # 右侧：当前条件表单 + AST 构建器
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        # 名称
        row_name = QHBoxLayout()
        row_name.addWidget(QLabel("名称:", self))
        self._edit_name = QLineEdit(self)
        row_name.addWidget(self._edit_name, 1)
        right_col.addLayout(row_name)

        # 顶层逻辑
        row_logic = QHBoxLayout()
        row_logic.addWidget(QLabel("顶层逻辑:", self))
        self._cmb_logic = QComboBox(self)
        self._cmb_logic.addItem("全部满足 (AND)", userData="and")
        self._cmb_logic.addItem("任一满足 (OR)", userData="or")
        row_logic.addWidget(self._cmb_logic, 1)
        right_col.addLayout(row_logic)

        # 原子条件列表
        lbl_atoms = QLabel("原子条件列表:", self)
        right_col.addWidget(lbl_atoms)

        self._tree_atoms = QTreeWidget(self)
        self._tree_atoms.setRootIsDecorated(False)
        self._tree_atoms.setAlternatingRowColors(True)
        self._tree_atoms.setSelectionMode(QTreeWidget.SingleSelection)
        self._tree_atoms.setSelectionBehavior(QTreeWidget.SelectRows)
        self._tree_atoms.setHeaderLabels(["类型", "目标", "容差", "取反"])
        self._tree_atoms.setColumnWidth(0, 90)
        self._tree_atoms.setColumnWidth(1, 200)
        self._tree_atoms.setColumnWidth(2, 60)
        self._tree_atoms.setColumnWidth(3, 60)
        right_col.addWidget(self._tree_atoms, 1)

        # 原子条件按钮
        atoms_btn_row = QHBoxLayout()
        atoms_btn_row.setSpacing(6)

        icon_add_point = load_icon("point", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_add_skill = load_icon("skill", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_del_atom = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        self._btn_add_point = QPushButton("添加点位条件", self)
        self._btn_add_point.setIcon(icon_add_point)
        self._btn_add_point.clicked.connect(self._on_add_point_atom)
        atoms_btn_row.addWidget(self._btn_add_point)

        self._btn_add_skill = QPushButton("添加技能像素条件", self)
        self._btn_add_skill.setIcon(icon_add_skill)
        self._btn_add_skill.clicked.connect(self._on_add_skill_atom)
        atoms_btn_row.addWidget(self._btn_add_skill)

        self._btn_del_atom = QPushButton("删除选中条件", self)
        self._btn_del_atom.setIcon(icon_del_atom)
        self._btn_del_atom.clicked.connect(self._on_delete_atom)
        atoms_btn_row.addWidget(self._btn_del_atom)

        atoms_btn_row.addStretch(1)
        right_col.addLayout(atoms_btn_row)

        # 网关相关按钮
        gw_btn_row = QHBoxLayout()
        gw_btn_row.setSpacing(6)

        self._btn_apply = QPushButton("应用到当前网关节点", self)
        self._btn_apply.clicked.connect(self._on_apply)
        gw_btn_row.addWidget(self._btn_apply)

        self._btn_clear = QPushButton("清除当前网关条件", self)
        self._btn_clear.clicked.connect(self._on_clear_gateway)
        gw_btn_row.addWidget(self._btn_clear)

        gw_btn_row.addStretch(1)

        right_col.addLayout(gw_btn_row)

        # 关闭按钮
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        self._btn_close = QPushButton("关闭", self)
        self._btn_close.clicked.connect(self.close)
        close_row.addWidget(self._btn_close)
        right_col.addLayout(close_row)

        body_row.addLayout(right_col, 2)

        # 表单变更事件
        self._edit_name.textChanged.connect(self._on_form_changed)
        self._cmb_logic.currentIndexChanged.connect(self._on_form_changed)

        # 若当前没有 gateway，禁用应用/清除按钮
        if self._gateway is None:
            self._btn_apply.setEnabled(False)
            self._btn_clear.setEnabled(False)

    # ---------- 使用次数统计 ----------

    def _recompute_usage(self) -> None:
        """
        统计当前 preset 中每个条件被 GatewayNode 使用的次数。
        """
        usage: Dict[str, int] = {}
        for c in self._preset.conditions or []:
            if c.id:
                usage[c.id] = 0

        def scan_track(track: Track, mode_label: str) -> None:
            tname = track.name or "(未命名轨道)"
            for n in track.nodes or []:
                if isinstance(n, GatewayNode):
                    cid = (getattr(n, "condition_id", "") or "").strip()
                    if cid:
                        usage[cid] = usage.get(cid, 0) + 1

        # 全局轨道
        for t in self._preset.global_tracks or []:
            scan_track(t, "全局")

        # 模式轨道
        for m in self._preset.modes or []:
            mlabel = f"模式『{m.name or '(未命名模式)'}』"
            for t in m.tracks or []:
                scan_track(t, mlabel)

        self._usage_by_id = usage

    def _decorate_name(self, c: Condition) -> str:
        """
        在条件名后面附加“使用次数”信息：
        - 未使用：  名称  [未使用]
        - 使用 N 次：名称  (使用 N 次)
        """
        base = c.name or "(未命名)"
        cid = c.id or ""
        cnt = self._usage_by_id.get(cid, 0)
        if cnt <= 0:
            return f"{base}  [未使用]"
        return f"{base}  (使用 {cnt} 次)"

    # ---------- 载入/刷新 ----------

    def _reload_from_preset(self) -> None:
        prev = self._current_cond_id
        self._building = True
        try:
            # 每次重载前重新统计使用次数
            self._recompute_usage()

            self._list.clear()
            for c in self._preset.conditions:
                text = self._decorate_name(c)
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, c.id)
                # tooltip 显示使用次数
                cid = c.id or ""
                cnt = self._usage_by_id.get(cid, 0)
                if cnt <= 0:
                    tip = "未被任何网关节点引用"
                else:
                    tip = f"被网关节点引用 {cnt} 次"
                item.setToolTip(tip)
                self._list.addItem(item)
        finally:
            self._building = False

        # 尝试恢复选中
        if prev:
            for i in range(self._list.count()):
                item = self._list.item(i)
                cid = item.data(Qt.UserRole)
                if isinstance(cid, str) and cid == prev:
                    self._list.setCurrentItem(item)
                    return

        # 若 gateway 已指向某个条件，则选中
        if self._gateway is not None and self._gateway.condition_id:
            gid = self._gateway.condition_id
            for i in range(self._list.count()):
                item = self._list.item(i)
                cid = item.data(Qt.UserRole)
                if isinstance(cid, str) and cid == gid:
                    self._list.setCurrentItem(item)
                    return

        # 否则选中第一项（如果有）
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._current_cond_id = None
            self._clear_form()

    # ---------- 当前条件对象 ----------

    def _find_condition(self, cid: str) -> Optional[Condition]:
        cid = (cid or "").strip()
        if not cid:
            return None
        for c in self._preset.conditions:
            if c.id == cid:
                return c
        return None

    # ---------- 表单同步 ----------

    def _clear_form(self) -> None:
        self._building = True
        try:
            self._edit_name.clear()
            # 默认 AND
            for i in range(self._cmb_logic.count()):
                if self._cmb_logic.itemData(i) == "and":
                    self._cmb_logic.setCurrentIndex(i)
                    break
            self._logic_op = "and"
            self._atoms = []
            self._rebuild_atoms_view()
        finally:
            self._building = False

    def _load_into_form(self, cid: str) -> None:
        c = self._find_condition(cid)
        self._current_cond_id = cid if c is not None else None
        self._building = True
        try:
            if c is None:
                self._clear_form()
                return

            self._edit_name.setText(c.name or "")

            # 默认值
            self._logic_op = "and"
            self._atoms = []

            kind = (c.kind or "").strip().lower()
            expr = c.expr or {}

            # 仅在 kind == expr_tree_v1 且 expr 是 dict 时尝试解析 AST
            if kind == "expr_tree_v1" and isinstance(expr, dict):
                self._logic_op, self._atoms = self._parse_ast(expr)
            else:
                self._logic_op = "and"
                self._atoms = []

            # 设置逻辑下拉
            for i in range(self._cmb_logic.count()):
                if self._cmb_logic.itemData(i) == self._logic_op:
                    self._cmb_logic.setCurrentIndex(i)
                    break

            self._rebuild_atoms_view()

        finally:
            self._building = False

    def _on_select(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if self._building:
            return
        # 先把上一条表单写回
        if prev is not None:
            try:
                self._apply_form_to_current()
            except Exception:
                pass

        if curr is None:
            self._current_cond_id = None
            self._clear_form()
            return
        cid = curr.data(Qt.UserRole)
        if not isinstance(cid, str):
            self._current_cond_id = None
            self._clear_form()
            return

        self._load_into_form(cid)

    def _on_form_changed(self) -> None:
        if self._building:
            return
        self._apply_form_to_current()

    # ---------- AST <-> AtomCond ----------

    def _parse_ast(self, expr: Dict[str, Any]) -> tuple[str, List[AtomCond]]:
        """
        将 AST 表达式解析为 (logic_op, atoms)。
        """
        op = "and"
        atoms: List[AtomCond] = []

        t = (expr.get("type") or "").strip().lower()
        if t in ("logic_and", "logic_or"):
            op = "and" if t == "logic_and" else "or"
            children = expr.get("children", []) or []
        else:
            children = [expr]

        for ch in children:
            if not isinstance(ch, dict):
                continue
            neg = False
            t_child = (ch.get("type") or "").strip().lower()
            inner = ch

            if t_child == "logic_not":
                inner = ch.get("child") or {}
                if not isinstance(inner, dict):
                    continue
                neg = True
                t_child = (inner.get("type") or "").strip().lower()

            if t_child == "pixel_point":
                pid = (inner.get("point_id") or "").strip()
                tol = int(inner.get("tolerance", 0) or 0)
                tol = max(0, min(255, tol))
                if not pid:
                    continue
                atoms.append(AtomCond(kind="pixel_point", ref_id=pid, tolerance=tol, neg=neg))

            elif t_child == "pixel_skill":
                sid = (inner.get("skill_id") or "").strip()
                tol = int(inner.get("tolerance", 0) or 0)
                tol = max(0, min(255, tol))
                if not sid:
                    continue
                atoms.append(AtomCond(kind="pixel_skill", ref_id=sid, tolerance=tol, neg=neg))

            else:
                continue

        return op, atoms

    def _build_ast(self, op: str, atoms: List[AtomCond]) -> Dict[str, Any]:
        if not atoms:
            return {}

        children: List[Dict[str, Any]] = []
        for a in atoms:
            if a.kind == "pixel_point":
                base = {
                    "type": "pixel_point",
                    "point_id": a.ref_id,
                    "tolerance": max(0, min(255, int(a.tolerance))),
                }
            else:
                base = {
                    "type": "pixel_skill",
                    "skill_id": a.ref_id,
                    "tolerance": max(0, min(255, int(a.tolerance))),
                }

            if a.neg:
                node = {"type": "logic_not", "child": base}
            else:
                node = base
            children.append(node)

        if op == "or":
            return {"type": "logic_or", "children": children}
        return {"type": "logic_and", "children": children}

    # ---------- 原子条件列表视图 ----------

    def _rebuild_atoms_view(self) -> None:
        self._tree_atoms.blockSignals(True)
        try:
            self._tree_atoms.clear()
            for a in self._atoms:
                item = QTreeWidgetItem()
                if a.kind == "pixel_point":
                    typ = "点位颜色"
                    target = self._describe_point(a.ref_id)
                else:
                    typ = "技能像素"
                    target = self._describe_skill(a.ref_id)

                item.setText(0, typ)
                item.setText(1, target)
                item.setText(2, str(int(a.tolerance)))
                item.setText(3, "是" if a.neg else "否")

                item.setData(0, Qt.UserRole, a)
                self._tree_atoms.addTopLevelItem(item)
        finally:
            self._tree_atoms.blockSignals(False)

    def _describe_point(self, pid: str) -> str:
        pts: List[Point] = list(getattr(self._ctx.points, "points", []) or [])
        for p in pts:
            if p.id == pid:
                short = (p.id or "")[-6:]
                return f"{p.name or '(未命名)'} [{short}]"
        return f"(点位缺失: {pid[-6:] if pid else ''})"

    def _describe_skill(self, sid: str) -> str:
        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        for s in skills:
            if s.id == sid:
                short = (s.id or "")[-6:]
                return f"{s.name or '(未命名)'} [{short}]"
        return f"(技能缺失: {sid[-6:] if sid else ''})"

    # ---------- 原子条件增删 ----------

    def _on_add_point_atom(self) -> None:
        pts: List[Point] = list(getattr(self._ctx.points, "points", []) or [])
        if not pts:
            self._notify.error("当前 Profile 下没有点位，请先在“取色点位配置”页面添加。")
            return

        items = [f"{p.name or '(未命名)'} [{(p.id or '')[-6:]}]" for p in pts]
        choice, ok = QInputDialog.getItem(
            self,
            "选择点位",
            "请选择要匹配的点位：",
            items,
            0,
            False,
        )
        if not ok:
            return

        idx = items.index(choice) if choice in items else 0
        p = pts[idx]

        tol, ok_tol = QInputDialog.getInt(
            self,
            "设置容差",
            "容差(0-255)：",
            10,
            0,
            255,
            1,
        )
        if not ok_tol:
            return

        neg = QMessageBox.question(
            self,
            "是否取反",
            "是否对该条件取反？\n\n是：表示“当前颜色 不 等于该点位记录的颜色”",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

        self._atoms.append(AtomCond(kind="pixel_point", ref_id=p.id, tolerance=tol, neg=neg))
        self._rebuild_atoms_view()
        self._apply_form_to_current()

    def _on_add_skill_atom(self) -> None:
        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        if not skills:
            self._notify.error("当前 Profile 下没有技能，请先在“技能配置”页面添加。")
            return

        items = [f"{s.name or '(未命名)'} [{(s.id or '')[-6:]}]" for s in skills]
        choice, ok = QInputDialog.getItem(
            self,
            "选择技能",
            "请选择要匹配其像素的技能：",
            items,
            0,
            False,
        )
        if not ok:
            return

        idx = items.index(choice) if choice in items else 0
        s = skills[idx]

        tol, ok_tol = QInputDialog.getInt(
            self,
            "设置容差",
            "容差(0-255)：",
            5,
            0,
            255,
            1,
        )
        if not ok_tol:
            return

        neg = QMessageBox.question(
            self,
            "是否取反",
            "是否对该条件取反？\n\n是：表示“当前像素 不 等于技能记录的像素颜色”",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

        self._atoms.append(AtomCond(kind="pixel_skill", ref_id=s.id, tolerance=tol, neg=neg))
        self._rebuild_atoms_view()
        self._apply_form_to_current()

    def _on_delete_atom(self) -> None:
        item = self._tree_atoms.currentItem()
        if item is None:
            self._notify.error("请先选择要删除的原子条件")
            return
        idx = self._tree_atoms.indexOfTopLevelItem(item)
        if idx < 0 or idx >= len(self._atoms):
            return

        ok = QMessageBox.question(
            self,
            "删除原子条件",
            "确认删除选中的原子条件？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        del self._atoms[idx]
        self._rebuild_atoms_view()
        self._apply_form_to_current()

    # ---------- 写回 Condition ----------

    def _apply_form_to_current(self) -> None:
        if self._building:
            return
        cid = self._current_cond_id
        if not cid:
            return
        c = self._find_condition(cid)
        if c is None:
            return

        name = (self._edit_name.text() or "").strip()
        logic = self._cmb_logic.currentData()
        if logic not in ("and", "or"):
            logic = "and"

        changed = False

        if name and name != c.name:
            c.name = name
            changed = True

        if c.kind != "expr_tree_v1":
            c.kind = "expr_tree_v1"
            changed = True

        expr_new = self._build_ast(logic, self._atoms)
        if expr_new != (c.expr or {}):
            c.expr = expr_new
            changed = True

        if changed:
            self._mark_dirty()
            # 更新列表中显示的名称 + 使用次数
            for i in range(self._list.count()):
                item = self._list.item(i)
                cid2 = item.data(Qt.UserRole)
                if isinstance(cid2, str) and cid2 == cid:
                    item.setText(self._decorate_name(c))
                    break

    # ---------- 新建 / 删除 条件 ----------

    def _on_new(self) -> None:
        cid = uuid.uuid4().hex
        cond = Condition(
            id=cid,
            name="新条件",
            kind="expr_tree_v1",
            expr={},
        )
        self._preset.conditions.append(cond)
        self._mark_dirty()
        self._reload_from_preset()

        for i in range(self._list.count()):
            item = self._list.item(i)
            cid2 = item.data(Qt.UserRole)
            if isinstance(cid2, str) and cid2 == cid:
                self._list.setCurrentItem(item)
                break

    def _on_delete(self) -> None:
        cid = self._current_cond_id
        if not cid:
            self._notify.error("请先选择要删除的条件")
            return
        c = self._find_condition(cid)
        if c is None:
            self._notify.error("当前条件不存在")
            return

        ok = QMessageBox.question(
            self,
            "删除条件",
            f"确认删除条件：{c.name or '(未命名)'} ？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        before = len(self._preset.conditions)
        self._preset.conditions = [x for x in self._preset.conditions if x.id != cid]
        after = len(self._preset.conditions)
        if after != before:
            self._mark_dirty()
        self._current_cond_id = None
        self._reload_from_preset()

    # ---------- 应用到网关 ----------

    def _on_apply(self) -> None:
        if self._gateway is None:
            self._notify.error("当前没有网关节点上下文")
            return
        cid = self._current_cond_id
        if not cid:
            self._notify.error("请先在左侧列表选择一个条件")
            return
        self._gateway.condition_id = cid
        self._mark_dirty()
        self._notify.status_msg("已应用条件到网关节点", ttl_ms=1500)

        # 应用后，使用次数统计会变化，重新加载列表
        self._reload_from_preset()

    def _on_clear_gateway(self) -> None:
        if self._gateway is None:
            return
        if not self._gateway.condition_id:
            self._notify.status_msg("当前网关节点未绑定条件", ttl_ms=1500)
            return
        self._gateway.condition_id = None
        self._mark_dirty()
        self._notify.status_msg("已清除网关节点条件", ttl_ms=1500)

        # 清除后，使用次数统计会变化，重新加载列表
        self._reload_from_preset()

    # ---------- 辅助 ----------

    def _mark_dirty(self) -> None:
        try:
            self._mark_dirty_cb()
        except Exception:
            pass