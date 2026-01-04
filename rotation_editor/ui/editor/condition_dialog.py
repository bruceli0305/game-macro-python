from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from functools import partial

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPushButton,
    QStyle,
    QComboBox,
    QTreeWidget,
    QTreeWidgetItem,
    QInputDialog,
    QMenu,
    QTabWidget,
    QWidget,
)

from core.profiles import ProfileContext
from core.models.point import Point
from core.models.skill import Skill

from qtui.icons import load_icon
from qtui.notify import UiNotify
from rotation_editor.core.models import RotationPreset, Condition, GatewayNode, Track, Mode

log = logging.getLogger(__name__)


# ---------- 内部数据结构 ----------

@dataclass
class AtomCond:
    """
    原子条件：
    - kind: "pixel_point" | "pixel_skill" | "skill_cast_ge"
    - ref_id: point_id 或 skill_id
    - value:
        * pixel_*      : 容差 0..255
        * skill_cast_ge: 次数 N (>=1)
    - neg: 是否取反 (NOT)
    """
    kind: str
    ref_id: str
    value: int
    neg: bool = False


@dataclass
class CondGroup:
    """
    条件组合（Group）：
    - op: "and" / "or" （组内逻辑）
    - atoms: 该组内的原子条件列表

    顶层语义：所有组之间用 OR 组合，即：
        (组1) OR (组2) OR ...
    每个组内部则是：
        (a1 op a2 op a3 ...)
    """
    op: str
    atoms: List[AtomCond]


class ConditionEditorDialog(QDialog):
    """
    条件编辑对话框（Tab 分组版，每个 Tab 内有独立条件列表）：

    - 左侧：Condition 列表（名称 + 使用次数）
    - 右侧：
        * 条件名称
        * 当前组合逻辑（AND / OR）
        * Tab 区：每个 Tab 是一个组合（Group），标签如“组合1[AND]”，带关闭 X
            - Tab 内有自己的 QTreeWidget 显示该组合的原子条件
            - Tab 内右键 / 按钮都只影响当前组合
    表达式语义：
        (Group1) OR (Group2) OR ...
        Group 内的逻辑为 AND/OR。
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
        self.resize(840, 520)

        self._ctx = ctx
        self._preset = preset
        self._gateway = gateway
        self._notify = notify
        self._mark_dirty_cb = mark_dirty

        self._current_cond_id: Optional[str] = None
        self._building = False

        # 逻辑分组
        self._groups: List[CondGroup] = []
        # 每个组对应一个 QTreeWidget（和 _groups 同索引）
        self._group_trees: List[QTreeWidget] = []

        # 条件使用次数：cond_id -> count
        self._usage_by_id: Dict[str, int] = {}

        self._build_ui()
        self._reload_from_preset()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        lbl_tip = QLabel(
            "说明：支持将原子条件分组并使用 OR 组合：\n"
            "  - 组内逻辑：全部满足(AND) 或 任一满足(OR)\n"
            "  - 组之间：固定使用 OR 组合 (组1) OR (组2) OR ...\n"
            "示例：(A AND B) OR C 可配置为：\n"
            "  - 组合1: AND [A, B]\n"
            "  - 组合2: AND [C]",
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

        # 右侧：当前条件编辑
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        # 条件名称
        row_name = QHBoxLayout()
        row_name.addWidget(QLabel("名称:", self))
        self._edit_name = QLineEdit(self)
        row_name.addWidget(self._edit_name, 1)
        right_col.addLayout(row_name)

        # 当前组合逻辑（针对当前 Tab）
        row_group_logic = QHBoxLayout()
        row_group_logic.addWidget(QLabel("当前组合逻辑:", self))
        self._cmb_group_logic = QComboBox(self)
        self._cmb_group_logic.addItem("全部满足 (AND)", userData="and")
        self._cmb_group_logic.addItem("任一满足 (OR)", userData="or")
        row_group_logic.addWidget(self._cmb_group_logic, 1)
        right_col.addLayout(row_group_logic)

        # Tabs：每个组合一个 Tab
        self._tabs = QTabWidget(self)
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        right_col.addWidget(self._tabs, 1)

        # 原子条件按钮行
        icon_add_point = load_icon("point", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_add_skill = load_icon("skill", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_add_skill_cast = load_icon("skill", style, QStyle.StandardPixmap.SP_FileDialogListView)
        icon_del_atom = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        atoms_btn_row = QHBoxLayout()
        atoms_btn_row.setSpacing(6)

        self._btn_add_group = QPushButton("新增组合", self)
        self._btn_add_group.setIcon(icon_add)
        self._btn_add_group.clicked.connect(self._on_add_group)
        atoms_btn_row.addWidget(self._btn_add_group)

        atoms_btn_row.addSpacing(12)

        self._btn_add_point = QPushButton("添加点位条件", self)
        self._btn_add_point.setIcon(icon_add_point)
        self._btn_add_point.clicked.connect(self._on_add_point_atom)
        atoms_btn_row.addWidget(self._btn_add_point)

        self._btn_add_skill = QPushButton("添加技能像素条件", self)
        self._btn_add_skill.setIcon(icon_add_skill)
        self._btn_add_skill.clicked.connect(self._on_add_skill_atom)
        atoms_btn_row.addWidget(self._btn_add_skill)

        self._btn_add_skill_cast = QPushButton("添加技能次数条件", self)
        self._btn_add_skill_cast.setIcon(icon_add_skill_cast)
        self._btn_add_skill_cast.clicked.connect(self._on_add_skill_cast_atom)
        atoms_btn_row.addWidget(self._btn_add_skill_cast)

        self._btn_del_atom = QPushButton("删除条件", self)
        self._btn_del_atom.setIcon(icon_del_atom)
        self._btn_del_atom.clicked.connect(self._on_delete_atom)
        atoms_btn_row.addWidget(self._btn_del_atom)

        atoms_btn_row.addStretch(1)
        right_col.addLayout(atoms_btn_row)

        # 底部：保存 / 清除 / 关闭
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)

        self._btn_apply = QPushButton("保存", self)
        self._btn_apply.clicked.connect(self._on_apply)
        bottom_row.addWidget(self._btn_apply)

        self._btn_clear = QPushButton("清除", self)
        self._btn_clear.clicked.connect(self._on_clear_gateway)
        bottom_row.addWidget(self._btn_clear)

        self._btn_close = QPushButton("关闭", self)
        self._btn_close.clicked.connect(self.close)
        bottom_row.addWidget(self._btn_close)

        right_col.addLayout(bottom_row)

        body_row.addLayout(right_col, 2)

        # 事件
        self._edit_name.textChanged.connect(self._on_form_changed)
        self._cmb_group_logic.currentIndexChanged.connect(self._on_group_logic_changed)

        # 若当前没有 gateway，禁用“保存”和“清除”
        if self._gateway is None:
            self._btn_apply.setEnabled(False)
            self._btn_clear.setEnabled(False)

    # ---------- 使用次数 / 条件列表 ----------

    def _recompute_usage(self) -> None:
        usage: Dict[str, int] = {}
        for c in self._preset.conditions or []:
            if c.id:
                usage[c.id] = 0

        def scan_track(track: Track, mode_label: str) -> None:
            for n in track.nodes or []:
                if isinstance(n, GatewayNode):
                    cid = (getattr(n, "condition_id", "") or "").strip()
                    if cid:
                        usage[cid] = usage.get(cid, 0) + 1

        for t in self._preset.global_tracks or []:
            scan_track(t, "全局")

        for m in self._preset.modes or []:
            for t in m.tracks or []:
                scan_track(t, f"模式『{m.name or '(未命名模式)'}』")

        self._usage_by_id = usage

    def _decorate_name(self, c: Condition) -> str:
        base = c.name or "(未命名)"
        cid = c.id or ""
        cnt = self._usage_by_id.get(cid, 0)
        if cnt <= 0:
            return f"{base}  [未使用]"
        return f"{base}  (使用 {cnt} 次)"

    def _reload_from_preset(self) -> None:
        prev = self._current_cond_id
        self._building = True
        try:
            self._recompute_usage()
            self._list.clear()
            for c in self._preset.conditions:
                text = self._decorate_name(c)
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, c.id)
                cid = c.id or ""
                cnt = self._usage_by_id.get(cid, 0)
                tip = "未被任何网关节点引用" if cnt <= 0 else f"被网关节点引用 {cnt} 次"
                item.setToolTip(tip)
                self._list.addItem(item)
        finally:
            self._building = False

        if prev:
            for i in range(self._list.count()):
                item = self._list.item(i)
                cid = item.data(Qt.UserRole)
                if isinstance(cid, str) and cid == prev:
                    self._list.setCurrentItem(item)
                    return

        if self._gateway is not None and self._gateway.condition_id:
            gid = self._gateway.condition_id
            for i in range(self._list.count()):
                item = self._list.item(i)
                cid = item.data(Qt.UserRole)
                if isinstance(cid, str) and cid == gid:
                    self._list.setCurrentItem(item)
                    return

        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._current_cond_id = None
            self._clear_form()

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
            self._groups = []
            self._group_trees = []
            self._tabs.clear()
            self._cmb_group_logic.setEnabled(False)
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

            expr = c.expr or {}
            if (c.kind or "").strip().lower() == "expr_tree_v1" and isinstance(expr, dict):
                groups = self._parse_groups_from_expr(expr)
            else:
                groups = []

            self._groups = groups or []
            self._rebuild_tabs(select_index=0 if self._groups else -1)
        finally:
            self._building = False

    def _on_select(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if self._building:
            return

        if prev is not None:
            try:
                self._apply_form_to_current()
            except Exception:
                log.exception("ConditionEditorDialog._on_select: apply_form_to_current failed")

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

    # ---------- Tabs & 组合逻辑 ----------

    def _tab_title_for_group(self, idx: int) -> str:
        g = self._groups[idx]
        op = (g.op or "and").strip().lower()
        if op not in ("and", "or"):
            op = "and"
            g.op = op
        op_txt = "AND" if op == "and" else "OR"
        return f"组合 {idx + 1} [{op_txt}]"

    def _create_tree_for_group(self, gi: int) -> QTreeWidget:
        tree = QTreeWidget(self._tabs)
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        tree.setSelectionBehavior(QTreeWidget.SelectRows)
        tree.setHeaderLabels(["类型", "目标", "数值/容差", "取反"])
        tree.setColumnWidth(0, 120)
        tree.setColumnWidth(1, 280)
        tree.setColumnWidth(2, 90)
        tree.setColumnWidth(3, 60)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.customContextMenuRequested.connect(partial(self._on_atoms_context_menu, gi))
        return tree

    def _rebuild_tabs(self, select_index: int = -1) -> None:
        """
        根据 self._groups 重建所有 Tab 和各自的 tree。
        """
        self._tabs.blockSignals(True)
        try:
            self._tabs.clear()
            self._group_trees = []
            for gi, g in enumerate(self._groups):
                page = QWidget(self._tabs)
                v = QVBoxLayout(page)
                v.setContentsMargins(2, 2, 2, 2)
                v.setSpacing(2)

                tree = self._create_tree_for_group(gi)
                self._group_trees.append(tree)
                v.addWidget(tree)

                self._tabs.addTab(page, self._tab_title_for_group(gi))

                # 填充当前组的 atoms
                for a in g.atoms:
                    item = QTreeWidgetItem()
                    k = (a.kind or "").strip().lower()
                    if k == "pixel_point":
                        typ = "点位颜色"
                        target = self._describe_point(a.ref_id)
                    elif k == "pixel_skill":
                        typ = "技能像素"
                        target = self._describe_skill(a.ref_id)
                    elif k == "skill_cast_ge":
                        typ = "技能施放次数≥"
                        target = self._describe_skill(a.ref_id)
                    else:
                        typ = a.kind or "未知"
                        target = a.ref_id
                    item.setText(0, typ)
                    item.setText(1, target)
                    item.setText(2, str(int(a.value)))
                    item.setText(3, "是" if a.neg else "否")
                    tree.addTopLevelItem(item)
        finally:
            self._tabs.blockSignals(False)

        if self._groups:
            if 0 <= select_index < len(self._groups):
                self._tabs.setCurrentIndex(select_index)
            elif self._tabs.currentIndex() < 0:
                self._tabs.setCurrentIndex(0)
        else:
            self._tabs.setCurrentIndex(-1)

        self._sync_group_logic_to_ui()

    def _current_group_index(self) -> int:
        return self._tabs.currentIndex()

    def _current_tree(self) -> Optional[QTreeWidget]:
        gi = self._current_group_index()
        if gi < 0 or gi >= len(self._group_trees):
            return None
        return self._group_trees[gi]

    def _on_tab_changed(self, index: int) -> None:
        if self._building:
            return
        self._sync_group_logic_to_ui()

    def _on_tab_close_requested(self, index: int) -> None:
        if index < 0 or index >= len(self._groups):
            return
        ok = QMessageBox.question(
            self,
            "删除组合",
            f"确认删除组合 {index + 1} 及其下所有条件？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return
        del self._groups[index]
        # 重建 tabs
        new_sel = index - 1
        if new_sel < 0 and self._groups:
            new_sel = 0
        self._rebuild_tabs(select_index=new_sel)
        self._apply_form_to_current()

    def _sync_group_logic_to_ui(self) -> None:
        gi = self._current_group_index()
        if gi < 0 or gi >= len(self._groups):
            self._cmb_group_logic.setEnabled(False)
            return

        g = self._groups[gi]
        op = (g.op or "and").strip().lower()
        if op not in ("and", "or"):
            op = "and"
        g.op = op

        self._cmb_group_logic.blockSignals(True)
        try:
            for i in range(self._cmb_group_logic.count()):
                if self._cmb_group_logic.itemData(i) == op:
                    self._cmb_group_logic.setCurrentIndex(i)
                    break
        finally:
            self._cmb_group_logic.blockSignals(False)

        self._cmb_group_logic.setEnabled(True)

    def _on_group_logic_changed(self) -> None:
        if self._building:
            return
        gi = self._current_group_index()
        if gi < 0 or gi >= len(self._groups):
            return
        data = self._cmb_group_logic.currentData()
        op = (data or "and").strip().lower()
        if op not in ("and", "or"):
            op = "and"
        self._groups[gi].op = op
        self._rebuild_tabs(select_index=gi)
        self._apply_form_to_current()

    # ---------- 新增 / 删除 组合 & 条件 ----------

    def _ensure_group_for_add_atom(self) -> int:
        gi = self._current_group_index()
        if 0 <= gi < len(self._groups):
            return gi
        # 没有组时自动新建一个
        self._groups.append(CondGroup(op="and", atoms=[]))
        self._rebuild_tabs(select_index=0)
        return 0

    def _on_add_group(self) -> None:
        gi = len(self._groups)
        self._groups.append(CondGroup(op="and", atoms=[]))
        self._rebuild_tabs(select_index=gi)
        self._apply_form_to_current()

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

        gi = self._ensure_group_for_add_atom()
        self._groups[gi].atoms.append(AtomCond(kind="pixel_point", ref_id=p.id, value=tol, neg=neg))
        self._rebuild_tabs(select_index=gi)
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

        gi = self._ensure_group_for_add_atom()
        self._groups[gi].atoms.append(AtomCond(kind="pixel_skill", ref_id=s.id, value=tol, neg=neg))
        self._rebuild_tabs(select_index=gi)
        self._apply_form_to_current()

    def _on_add_skill_cast_atom(self) -> None:
        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        if not skills:
            self._notify.error("当前 Profile 下没有技能，请先在“技能配置”页面添加。")
            return

        items = [f"{s.name or '(未命名)'} [{(s.id or '')[-6:]}]" for s in skills]
        choice, ok = QInputDialog.getItem(
            self,
            "选择技能",
            "请选择要检查施放次数的技能：",
            items,
            0,
            False,
        )
        if not ok:
            return

        idx = items.index(choice) if choice in items else 0
        s = skills[idx]

        cnt, ok_cnt = QInputDialog.getInt(
            self,
            "设置次数",
            "施放次数 (>=1)：",
            1,
            1,
            10**6,
            1,
        )
        if not ok_cnt:
            return

        neg = QMessageBox.question(
            self,
            "是否取反",
            "是否对该条件取反？\n\n"
            "否：表示“该技能施放次数 ≥ N”\n"
            "是：表示“该技能施放次数 < N”",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

        gi = self._ensure_group_for_add_atom()
        self._groups[gi].atoms.append(AtomCond(kind="skill_cast_ge", ref_id=s.id, value=cnt, neg=neg))
        self._rebuild_tabs(select_index=gi)
        self._apply_form_to_current()

    def _on_delete_atom(self) -> None:
        gi = self._current_group_index()
        if gi < 0 or gi >= len(self._groups):
            self._notify.error("请先选择组合（上方 Tab）")
            return
        tree = self._current_tree()
        if tree is None:
            self._notify.error("当前组合没有条件列表")
            return
        item = tree.currentItem()
        if item is None:
            self._notify.error("请先选择要删除的条件")
            return
        ai = tree.indexOfTopLevelItem(item)
        if ai < 0 or ai >= len(self._groups[gi].atoms):
            self._notify.error("无法识别当前选中的条件")
            return

        ok = QMessageBox.question(
            self,
            "删除条件",
            "确认删除选中的原子条件？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        del self._groups[gi].atoms[ai]
        self._rebuild_tabs(select_index=gi)
        self._apply_form_to_current()

    def _on_atoms_context_menu(self, gi: int, pos: QPoint) -> None:
        if gi < 0 or gi >= len(self._group_trees):
            return
        tree = self._group_trees[gi]
        item = tree.itemAt(pos)
        if item is None:
            return
        tree.setCurrentItem(item)

        menu = QMenu(self)
        act_del = menu.addAction("删除此条件")
        gpos = tree.viewport().mapToGlobal(pos)
        action = menu.exec(gpos)
        if action is None:
            return
        if action == act_del:
            # 当前 Tab 有可能不是 gi，但删除逻辑只依赖 _groups[gi]
            self._tabs.setCurrentIndex(gi)
            self._on_delete_atom()

    # ---------- AST <-> 分组 ----------

    def _parse_groups_from_expr(self, expr: Dict[str, Any]) -> List[CondGroup]:
        if not isinstance(expr, dict):
            return []

        t = (expr.get("type") or "").strip().lower()
        groups: List[CondGroup] = []

        if t == "logic_or":
            for ch in expr.get("children", []) or []:
                if not isinstance(ch, dict):
                    continue
                ct = (ch.get("type") or "").strip().lower()
                if ct in ("logic_and", "logic_or"):
                    atoms = self._parse_atoms_flat(ch)
                    if atoms:
                        op = "and" if ct == "logic_and" else "or"
                        groups.append(CondGroup(op=op, atoms=atoms))
                else:
                    atoms = self._parse_atoms_flat(ch)
                    if atoms:
                        groups.append(CondGroup(op="and", atoms=atoms))
            if groups:
                return groups

        atoms = self._parse_atoms_flat(expr)
        if not atoms:
            return []
        return [CondGroup(op="and", atoms=atoms)]

    def _parse_atoms_flat(self, expr: Dict[str, Any]) -> List[AtomCond]:
        atoms: List[AtomCond] = []

        def visit(node: Any, neg: bool = False) -> None:
            if not isinstance(node, dict):
                return
            t = (node.get("type") or "").strip().lower()
            if t in ("logic_and", "logic_or"):
                for ch in node.get("children", []) or []:
                    visit(ch, neg)
                return
            if t == "logic_not":
                ch = node.get("child")
                if isinstance(ch, dict):
                    visit(ch, not neg)
                return
            if t == "pixel_point":
                pid = (node.get("point_id") or "").strip()
                tol = int(node.get("tolerance", 0) or 0)
                tol = max(0, min(255, tol))
                if pid:
                    atoms.append(AtomCond(kind="pixel_point", ref_id=pid, value=tol, neg=neg))
                return
            if t == "pixel_skill":
                sid = (node.get("skill_id") or "").strip()
                tol = int(node.get("tolerance", 0) or 0)
                tol = max(0, min(255, tol))
                if sid:
                    atoms.append(AtomCond(kind="pixel_skill", ref_id=sid, value=tol, neg=neg))
                return
            if t == "skill_cast_ge":
                sid = (node.get("skill_id") or "").strip()
                cnt = int(node.get("count", 0) or 0)
                if sid and cnt > 0:
                    atoms.append(AtomCond(kind="skill_cast_ge", ref_id=sid, value=cnt, neg=neg))
                return

        visit(expr, False)
        return atoms

    def _build_atom_node(self, a: AtomCond) -> Dict[str, Any]:
        k = (a.kind or "").strip().lower()
        if k == "pixel_point":
            base = {
                "type": "pixel_point",
                "point_id": a.ref_id,
                "tolerance": max(0, min(255, int(a.value))),
            }
        elif k == "pixel_skill":
            base = {
                "type": "pixel_skill",
                "skill_id": a.ref_id,
                "tolerance": max(0, min(255, int(a.value))),
            }
        elif k == "skill_cast_ge":
            cnt = int(a.value)
            if cnt <= 0:
                cnt = 1
            base = {
                "type": "skill_cast_ge",
                "skill_id": a.ref_id,
                "count": cnt,
            }
        else:
            base = {"type": "unknown"}

        if a.neg:
            return {"type": "logic_not", "child": base}
        return base

    def _build_group_node(self, g: CondGroup) -> Dict[str, Any]:
        atoms_nodes = [self._build_atom_node(a) for a in g.atoms]
        atoms_nodes = [n for n in atoms_nodes if isinstance(n, dict) and n.get("type")]
        if not atoms_nodes:
            return {}
        if len(atoms_nodes) == 1:
            return atoms_nodes[0]
        op = (g.op or "and").strip().lower()
        if op == "or":
            return {"type": "logic_or", "children": atoms_nodes}
        return {"type": "logic_and", "children": atoms_nodes}

    def _build_expr_from_groups(self, groups: List[CondGroup]) -> Dict[str, Any]:
        gs = [g for g in groups if g.atoms]
        if not gs:
            return {}
        if len(gs) == 1:
            node = self._build_group_node(gs[0])
            return node or {}
        children: List[Dict[str, Any]] = []
        for g in gs:
            n = self._build_group_node(g)
            if n:
                children.append(n)
        if not children:
            return {}
        return {"type": "logic_or", "children": children}

    # ---------- 描述工具 ----------

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

        changed = False

        if name and name != c.name:
            c.name = name
            changed = True

        if c.kind != "expr_tree_v1":
            c.kind = "expr_tree_v1"
            changed = True

        expr_new = self._build_expr_from_groups(self._groups)
        if expr_new != (c.expr or {}):
            c.expr = expr_new
            changed = True

        if changed:
            self._mark_dirty()
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
        self._notify.status_msg("已保存到当前网关节点", ttl_ms=1500)
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
        self._reload_from_preset()

    # ---------- 辅助 ----------

    def _mark_dirty(self) -> None:
        try:
            self._mark_dirty_cb()
        except Exception:
            log.exception("ConditionEditorDialog._mark_dirty: mark_dirty_cb failed")