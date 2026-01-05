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
    QMessageBox,
)

from core.profiles import ProfileContext
from core.models.point import Point
from core.models.skill import Skill

from qtui.icons import load_icon
from qtui.notify import UiNotify
from rotation_editor.core.models import RotationPreset, Condition, GatewayNode, Track, Mode

log = logging.getLogger(__name__)

# -----------------------------
# 数据模型（结构化，不走 AST 编辑）
# -----------------------------

@dataclass
class Atom:
    id: str
    kind: str                 # "pixel_point" | "pixel_skill" | "skill_cast_ge"
    ref_id: str               # point_id 或 skill_id
    value: int                # tolerance 或 count
    neg: bool = False


@dataclass
class Group:
    id: str
    op: str                   # "and" | "or"
    atoms: List[Atom]


# -----------------------------
# ConditionEditorDialog
# -----------------------------

class ConditionEditorDialog(QDialog):
    """
    条件编辑对话框（稳定 ID 版，修复删除/新增 bug）：

    - Condition.kind 固定使用 "groups"
    - Condition.expr 结构：
        {
          "groups": [
            {
              "id": "...",
              "op": "and"|"or",
              "atoms": [
                {"id":"...","type":"pixel_point","point_id":"...","tolerance":10,"neg":false},
                {"id":"...","type":"pixel_skill","skill_id":"...","tolerance":5,"neg":true},
                {"id":"...","type":"skill_cast_ge","skill_id":"...","count":3,"neg":false}
              ]
            }
          ]
        }

    语义：
    - 组与组之间固定 OR： (G1) OR (G2) OR ...
    - 组内按 g.op 组合 atoms
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
        self.resize(860, 540)

        self._ctx = ctx
        self._preset = preset
        self._gateway = gateway
        self._notify = notify
        self._mark_dirty_cb = mark_dirty

        self._current_cond_id: Optional[str] = None
        self._building: bool = False

        # groups 为编辑时内存结构
        self._groups: List[Group] = []

        # cond_id -> usage_count
        self._usage_by_id: Dict[str, int] = {}

        self._build_ui()
        self._reload_condition_list()

    # -----------------------------
    # UI
    # -----------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        lbl_tip = QLabel(
            "表达式语义：组与组之间固定使用 OR。\n"
            "每个组内可选 AND/OR。\n"
            "示例：(A AND B) OR C\n"
            "  - 组合1: AND [A, B]\n"
            "  - 组合2: AND [C]\n",
            self,
        )
        lbl_tip.setWordWrap(True)
        layout.addWidget(lbl_tip)

        body = QHBoxLayout()
        body.setSpacing(10)
        layout.addLayout(body, 1)

        # 左侧：条件列表
        left = QVBoxLayout()
        left.setSpacing(6)
        body.addLayout(left, 1)

        left.addWidget(QLabel("条件列表:", self))

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.currentItemChanged.connect(self._on_select)
        left.addWidget(self._list, 1)

        style = self.style()
        icon_add = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_del = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        row_left_btn = QHBoxLayout()
        self._btn_new = QPushButton("新建条件", self)
        self._btn_new.setIcon(icon_add)
        self._btn_new.clicked.connect(self._on_new_condition)
        row_left_btn.addWidget(self._btn_new)

        self._btn_delete = QPushButton("删除条件", self)
        self._btn_delete.setIcon(icon_del)
        self._btn_delete.clicked.connect(self._on_delete_condition)
        row_left_btn.addWidget(self._btn_delete)

        row_left_btn.addStretch(1)
        left.addLayout(row_left_btn)

        # 右侧：编辑区
        right = QVBoxLayout()
        right.setSpacing(6)
        body.addLayout(right, 2)

        # 条件名称
        row_name = QHBoxLayout()
        row_name.addWidget(QLabel("名称:", self))
        self._edit_name = QLineEdit(self)
        self._edit_name.textChanged.connect(self._on_form_changed)
        row_name.addWidget(self._edit_name, 1)
        right.addLayout(row_name)

        # 组内逻辑（针对当前 Tab）
        row_logic = QHBoxLayout()
        row_logic.addWidget(QLabel("当前组合逻辑:", self))
        self._cmb_group_logic = QComboBox(self)
        self._cmb_group_logic.addItem("全部满足 (AND)", userData="and")
        self._cmb_group_logic.addItem("任一满足 (OR)", userData="or")
        self._cmb_group_logic.currentIndexChanged.connect(self._on_group_logic_changed)
        row_logic.addWidget(self._cmb_group_logic, 1)
        right.addLayout(row_logic)

        # Tabs：每个组一个 tab
        self._tabs = QTabWidget(self)
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        right.addWidget(self._tabs, 1)

        # 原子条件按钮行
        icon_add_point = load_icon("point", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_add_skill = load_icon("skill", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_add_cast = load_icon("skill", style, QStyle.StandardPixmap.SP_FileDialogListView)
        icon_del_atom = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        row_atoms_btn = QHBoxLayout()
        row_atoms_btn.setSpacing(6)

        self._btn_add_group = QPushButton("新增组合", self)
        self._btn_add_group.setIcon(icon_add)
        self._btn_add_group.clicked.connect(self._on_add_group)
        row_atoms_btn.addWidget(self._btn_add_group)

        row_atoms_btn.addSpacing(12)

        self._btn_add_point = QPushButton("添加点位条件", self)
        self._btn_add_point.setIcon(icon_add_point)
        self._btn_add_point.clicked.connect(self._on_add_point_atom)
        row_atoms_btn.addWidget(self._btn_add_point)

        self._btn_add_skill = QPushButton("添加技能像素条件", self)
        self._btn_add_skill.setIcon(icon_add_skill)
        self._btn_add_skill.clicked.connect(self._on_add_skill_atom)
        row_atoms_btn.addWidget(self._btn_add_skill)

        self._btn_add_cast = QPushButton("添加技能次数条件", self)
        self._btn_add_cast.setIcon(icon_add_cast)
        self._btn_add_cast.clicked.connect(self._on_add_skill_cast_atom)
        row_atoms_btn.addWidget(self._btn_add_cast)

        self._btn_del_atom = QPushButton("删除原子条件", self)
        self._btn_del_atom.setIcon(icon_del_atom)
        self._btn_del_atom.clicked.connect(self._on_delete_atom)
        row_atoms_btn.addWidget(self._btn_del_atom)

        row_atoms_btn.addStretch(1)
        right.addLayout(row_atoms_btn)

        # 底部：保存到网关 / 清除网关 / 关闭
        row_bottom = QHBoxLayout()
        row_bottom.addStretch(1)

        self._btn_apply_gateway = QPushButton("保存到当前网关", self)
        self._btn_apply_gateway.clicked.connect(self._on_apply_to_gateway)
        row_bottom.addWidget(self._btn_apply_gateway)

        self._btn_clear_gateway = QPushButton("清除网关绑定", self)
        self._btn_clear_gateway.clicked.connect(self._on_clear_gateway)
        row_bottom.addWidget(self._btn_clear_gateway)

        self._btn_close = QPushButton("关闭", self)
        self._btn_close.clicked.connect(self.close)
        row_bottom.addWidget(self._btn_close)

        right.addLayout(row_bottom)

        # 若无 gateway，上面两个按钮不可用
        if self._gateway is None:
            self._btn_apply_gateway.setEnabled(False)
            self._btn_clear_gateway.setEnabled(False)

    # -----------------------------
    # 条件列表 & 使用次数
    # -----------------------------

    def _recompute_usage(self) -> None:
        usage: Dict[str, int] = {c.id: 0 for c in (self._preset.conditions or []) if c.id}

        def scan_track(track: Track) -> None:
            for n in track.nodes or []:
                if isinstance(n, GatewayNode):
                    cid = (getattr(n, "condition_id", "") or "").strip()
                    if cid:
                        usage[cid] = usage.get(cid, 0) + 1

        for t in self._preset.global_tracks or []:
            scan_track(t)

        for m in self._preset.modes or []:
            for t in m.tracks or []:
                scan_track(t)

        self._usage_by_id = usage

    def _decorate_name(self, c: Condition) -> str:
        base = c.name or "(未命名)"
        cnt = self._usage_by_id.get(c.id or "", 0)
        if cnt <= 0:
            return f"{base}  [未使用]"
        return f"{base}  (使用 {cnt} 次)"

    def _reload_condition_list(self) -> None:
        prev = self._current_cond_id

        self._building = True
        try:
            self._recompute_usage()
            self._list.clear()
            for c in self._preset.conditions or []:
                item = QListWidgetItem(self._decorate_name(c))
                item.setData(Qt.UserRole, c.id)
                cnt = self._usage_by_id.get(c.id or "", 0)
                item.setToolTip("未被任何网关引用" if cnt <= 0 else f"被网关引用 {cnt} 次")
                self._list.addItem(item)
        finally:
            self._building = False

        # 恢复选择优先级：
        # 1) 上一次选择
        if prev:
            if self._select_condition_in_list(prev):
                return

        # 2) 若当前有 gateway 且已绑定
        if self._gateway is not None and self._gateway.condition_id:
            if self._select_condition_in_list(self._gateway.condition_id):
                return

        # 3) 默认选第一个
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._current_cond_id = None
            self._clear_form()

    def _select_condition_in_list(self, cid: str) -> bool:
        cid = (cid or "").strip()
        if not cid:
            return False
        for i in range(self._list.count()):
            it = self._list.item(i)
            val = it.data(Qt.UserRole)
            if isinstance(val, str) and val == cid:
                self._list.setCurrentItem(it)
                return True
        return False

    def _find_condition(self, cid: str) -> Optional[Condition]:
        cid = (cid or "").strip()
        if not cid:
            return None
        for c in self._preset.conditions or []:
            if c.id == cid:
                return c
        return None

    # -----------------------------
    # 表单加载/保存
    # -----------------------------

    def _clear_form(self) -> None:
        self._building = True
        try:
            self._edit_name.clear()
            self._groups = []
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

            # 只认 kind="groups"
            if (c.kind or "").strip().lower() == "groups" and isinstance(c.expr, dict):
                self._groups = self._parse_groups(c.expr)
            else:
                self._groups = []

            self._rebuild_tabs(select_group_id=self._groups[0].id if self._groups else None)
        finally:
            self._building = False

        self._sync_group_logic_to_ui()

    def _apply_form_to_current(self) -> None:
        if self._building:
            return
        cid = self._current_cond_id
        if not cid:
            return
        c = self._find_condition(cid)
        if c is None:
            return

        changed = False

        name = (self._edit_name.text() or "").strip()
        if name and name != (c.name or ""):
            c.name = name
            changed = True

        if (c.kind or "").strip().lower() != "groups":
            c.kind = "groups"
            changed = True

        expr_new = self._build_expr(self._groups)
        if expr_new != (c.expr or {}):
            c.expr = expr_new
            changed = True

        if changed:
            self._mark_dirty()

            # 更新列表显示名称/usage
            self._recompute_usage()
            for i in range(self._list.count()):
                it = self._list.item(i)
                val = it.data(Qt.UserRole)
                if isinstance(val, str) and val == cid:
                    it.setText(self._decorate_name(c))
                    break

    # -----------------------------
    # Tabs / Group UI
    # -----------------------------

    def _tab_title(self, g: Group, idx: int) -> str:
        op = (g.op or "and").strip().lower()
        if op not in ("and", "or"):
            op = "and"
        return f"组合 {idx + 1} [{'AND' if op == 'and' else 'OR'}]"

    def _group_id_for_tab(self, tab_index: int) -> Optional[str]:
        w = self._tabs.widget(tab_index)
        if w is None:
            return None
        gid = w.property("group_id")
        return gid if isinstance(gid, str) and gid else None

    def _current_group_id(self) -> Optional[str]:
        idx = self._tabs.currentIndex()
        if idx < 0:
            return None
        return self._group_id_for_tab(idx)

    def _find_group(self, gid: str) -> Optional[Group]:
        gid = (gid or "").strip()
        if not gid:
            return None
        for g in self._groups:
            if g.id == gid:
                return g
        return None

    def _rebuild_tabs(self, *, select_group_id: Optional[str]) -> None:
        self._tabs.blockSignals(True)
        try:
            self._tabs.clear()

            for i, g in enumerate(self._groups):
                page = QWidget(self._tabs)
                page.setProperty("group_id", g.id)
                v = QVBoxLayout(page)
                v.setContentsMargins(2, 2, 2, 2)
                v.setSpacing(2)

                tree = QTreeWidget(page)
                tree.setRootIsDecorated(False)
                tree.setAlternatingRowColors(True)
                tree.setSelectionMode(QTreeWidget.SingleSelection)
                tree.setSelectionBehavior(QTreeWidget.SelectRows)
                tree.setHeaderLabels(["类型", "目标", "数值/容差", "取反"])
                tree.setColumnWidth(0, 120)
                tree.setColumnWidth(1, 320)
                tree.setColumnWidth(2, 90)
                tree.setColumnWidth(3, 60)
                tree.setContextMenuPolicy(Qt.CustomContextMenu)
                tree.customContextMenuRequested.connect(partial(self._on_atoms_context_menu, g.id, tree))

                v.addWidget(tree)

                # 填充 atoms：每个 item 绑定 atom_id
                for a in g.atoms:
                    it = QTreeWidgetItem()
                    it.setData(0, Qt.UserRole, a.id)

                    k = (a.kind or "").strip().lower()
                    if k == "pixel_point":
                        it.setText(0, "点位颜色")
                        it.setText(1, self._describe_point(a.ref_id))
                        it.setText(2, str(int(a.value)))
                        it.setText(3, "是" if a.neg else "否")
                    elif k == "pixel_skill":
                        it.setText(0, "技能像素")
                        it.setText(1, self._describe_skill(a.ref_id))
                        it.setText(2, str(int(a.value)))
                        it.setText(3, "是" if a.neg else "否")
                    elif k == "skill_cast_ge":
                        it.setText(0, "技能施放次数≥")
                        it.setText(1, self._describe_skill(a.ref_id))
                        it.setText(2, str(int(a.value)))
                        it.setText(3, "是" if a.neg else "否")
                    else:
                        it.setText(0, a.kind or "未知")
                        it.setText(1, a.ref_id or "")
                        it.setText(2, str(int(a.value)))
                        it.setText(3, "是" if a.neg else "否")

                    tree.addTopLevelItem(it)

                tab_idx = self._tabs.addTab(page, self._tab_title(g, i))

                if select_group_id and g.id == select_group_id:
                    self._tabs.setCurrentIndex(tab_idx)

            if self._tabs.count() > 0 and self._tabs.currentIndex() < 0:
                self._tabs.setCurrentIndex(0)

        finally:
            self._tabs.blockSignals(False)

        self._sync_group_logic_to_ui()

    def _sync_group_logic_to_ui(self) -> None:
        gid = self._current_group_id()
        g = self._find_group(gid or "")
        if g is None:
            self._cmb_group_logic.setEnabled(False)
            return

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

    # -----------------------------
    # 事件：选择/编辑
    # -----------------------------

    def _on_select(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if self._building:
            return

        if prev is not None:
            try:
                self._apply_form_to_current()
            except Exception:
                log.exception("apply_form_to_current failed")

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

    def _on_tab_changed(self, index: int) -> None:
        if self._building:
            return
        self._sync_group_logic_to_ui()

    def _on_group_logic_changed(self) -> None:
        if self._building:
            return
        gid = self._current_group_id()
        g = self._find_group(gid or "")
        if g is None:
            return

        data = self._cmb_group_logic.currentData()
        op = (data or "and").strip().lower()
        if op not in ("and", "or"):
            op = "and"

        if op != g.op:
            g.op = op
            self._rebuild_tabs(select_group_id=g.id)
            self._apply_form_to_current()

    def _on_tab_close_requested(self, index: int) -> None:
        gid = self._group_id_for_tab(index)
        if not gid:
            return

        ok = QMessageBox.question(
            self,
            "删除组合",
            "确认删除当前组合及其下所有原子条件？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        self._groups = [g for g in self._groups if g.id != gid]
        sel = self._groups[0].id if self._groups else None
        self._rebuild_tabs(select_group_id=sel)
        self._apply_form_to_current()

    # -----------------------------
    # 新建/删除 条件（左侧）
    # -----------------------------

    def _on_new_condition(self) -> None:
        cid = uuid.uuid4().hex
        cond = Condition(
            id=cid,
            name="新条件",
            kind="groups",
            expr={"groups": []},
        )
        self._preset.conditions.append(cond)
        self._mark_dirty()
        self._reload_condition_list()
        self._select_condition_in_list(cid)

    def _on_delete_condition(self) -> None:
        cid = self._current_cond_id
        if not cid:
            self._notify.error("请先选择要删除的条件")
            return

        c = self._find_condition(cid)
        if c is None:
            self._notify.error("当前条件不存在")
            return

        used = int(self._usage_by_id.get(cid, 0))
        msg = f"确认删除条件：{c.name or '(未命名)'} ？"
        if used > 0:
            msg += f"\n\n注意：该条件当前被网关引用 {used} 次。\n删除时将自动清除所有引用。"

        ok = QMessageBox.question(
            self,
            "删除条件",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        # 1) 删除条件
        before = len(self._preset.conditions)
        self._preset.conditions = [x for x in self._preset.conditions if x.id != cid]
        after = len(self._preset.conditions)

        # 2) 清除所有 gateway 引用（避免 dangling）
        if used > 0:
            self._clear_condition_references(cid)

        if after != before or used > 0:
            self._mark_dirty()

        self._current_cond_id = None
        self._reload_condition_list()

    def _clear_condition_references(self, cond_id: str) -> None:
        cond_id = (cond_id or "").strip()
        if not cond_id:
            return

        def scan_track(track: Track) -> None:
            for n in track.nodes or []:
                if isinstance(n, GatewayNode) and (getattr(n, "condition_id", None) == cond_id):
                    n.condition_id = None

        for t in self._preset.global_tracks or []:
            scan_track(t)
        for m in self._preset.modes or []:
            for t in m.tracks or []:
                scan_track(t)

        # 如果当前 gateway 正好绑定此条件，也清掉
        if self._gateway is not None and self._gateway.condition_id == cond_id:
            self._gateway.condition_id = None

    # -----------------------------
    # 组/原子条件 操作
    # -----------------------------

    def _ensure_current_group(self) -> Group:
        gid = self._current_group_id()
        g = self._find_group(gid or "")
        if g is not None:
            return g

        # 没有 group：自动建一个
        g = Group(id=uuid.uuid4().hex, op="and", atoms=[])
        self._groups.append(g)
        self._rebuild_tabs(select_group_id=g.id)
        return g

    def _on_add_group(self) -> None:
        g = Group(id=uuid.uuid4().hex, op="and", atoms=[])
        self._groups.append(g)
        self._rebuild_tabs(select_group_id=g.id)
        self._apply_form_to_current()

    def _on_add_point_atom(self) -> None:
        pts: List[Point] = list(getattr(self._ctx.points, "points", []) or [])
        if not pts:
            self._notify.error("当前 Profile 下没有点位，请先在“取色点位配置”页面添加。")
            return

        items = [f"{p.name or '(未命名)'} [{(p.id or '')[-6:]}]" for p in pts]
        choice, ok = QInputDialog.getItem(self, "选择点位", "请选择要匹配的点位：", items, 0, False)
        if not ok:
            return

        try:
            idx = items.index(choice)
        except Exception:
            idx = 0
        p = pts[idx]

        tol, ok_tol = QInputDialog.getInt(self, "设置容差", "容差(0-255)：", 10, 0, 255, 1)
        if not ok_tol:
            return

        neg = QMessageBox.question(
            self,
            "是否取反",
            "是否对该条件取反？\n\n是：表示“当前颜色 不 等于该点位记录的颜色”",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

        g = self._ensure_current_group()
        g.atoms.append(Atom(id=uuid.uuid4().hex, kind="pixel_point", ref_id=p.id, value=int(tol), neg=bool(neg)))
        self._rebuild_tabs(select_group_id=g.id)
        self._apply_form_to_current()

    def _on_add_skill_atom(self) -> None:
        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        if not skills:
            self._notify.error("当前 Profile 下没有技能，请先在“技能配置”页面添加。")
            return

        items = [f"{s.name or '(未命名)'} [{(s.id or '')[-6:]}]" for s in skills]
        choice, ok = QInputDialog.getItem(self, "选择技能", "请选择要匹配其像素的技能：", items, 0, False)
        if not ok:
            return

        try:
            idx = items.index(choice)
        except Exception:
            idx = 0
        s = skills[idx]

        tol, ok_tol = QInputDialog.getInt(self, "设置容差", "容差(0-255)：", 5, 0, 255, 1)
        if not ok_tol:
            return

        neg = QMessageBox.question(
            self,
            "是否取反",
            "是否对该条件取反？\n\n是：表示“当前像素 不 等于技能记录的像素颜色”",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

        g = self._ensure_current_group()
        g.atoms.append(Atom(id=uuid.uuid4().hex, kind="pixel_skill", ref_id=s.id, value=int(tol), neg=bool(neg)))
        self._rebuild_tabs(select_group_id=g.id)
        self._apply_form_to_current()

    def _on_add_skill_cast_atom(self) -> None:
        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        if not skills:
            self._notify.error("当前 Profile 下没有技能，请先在“技能配置”页面添加。")
            return

        items = [f"{s.name or '(未命名)'} [{(s.id or '')[-6:]}]" for s in skills]
        choice, ok = QInputDialog.getItem(self, "选择技能", "请选择要检查施放次数的技能：", items, 0, False)
        if not ok:
            return

        try:
            idx = items.index(choice)
        except Exception:
            idx = 0
        s = skills[idx]

        cnt, ok_cnt = QInputDialog.getInt(self, "设置次数", "施放次数 (>=1)：", 1, 1, 10**6, 1)
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

        g = self._ensure_current_group()
        g.atoms.append(Atom(id=uuid.uuid4().hex, kind="skill_cast_ge", ref_id=s.id, value=int(cnt), neg=bool(neg)))
        self._rebuild_tabs(select_group_id=g.id)
        self._apply_form_to_current()

    def _on_delete_atom(self) -> None:
        gid = self._current_group_id()
        g = self._find_group(gid or "")
        if g is None:
            self._notify.error("请先选择组合（上方 Tab）")
            return

        tab_idx = self._tabs.currentIndex()
        page = self._tabs.widget(tab_idx)
        if page is None:
            self._notify.error("当前组合页面不存在")
            return

        tree = page.findChild(QTreeWidget)
        if tree is None:
            self._notify.error("当前组合没有条件列表")
            return

        item = tree.currentItem()
        if item is None:
            self._notify.error("请先选择要删除的原子条件")
            return

        atom_id = item.data(0, Qt.UserRole)
        if not isinstance(atom_id, str) or not atom_id:
            self._notify.error("无法识别当前选中的条件（atom_id 缺失）")
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

        before = len(g.atoms)
        g.atoms = [a for a in g.atoms if a.id != atom_id]
        if len(g.atoms) == before:
            return

        self._rebuild_tabs(select_group_id=g.id)
        self._apply_form_to_current()

    def _on_atoms_context_menu(self, group_id: str, tree: QTreeWidget, pos: QPoint) -> None:
        item = tree.itemAt(pos)
        if item is None:
            return
        tree.setCurrentItem(item)

        menu = QMenu(self)
        act_del = menu.addAction("删除此原子条件")
        action = menu.exec(tree.viewport().mapToGlobal(pos))
        if action == act_del:
            # 切到对应 group tab
            for i in range(self._tabs.count()):
                gid = self._group_id_for_tab(i)
                if gid == group_id:
                    self._tabs.setCurrentIndex(i)
                    break
            self._on_delete_atom()

    # -----------------------------
    # 应用到网关
    # -----------------------------

    def _on_apply_to_gateway(self) -> None:
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
        self._reload_condition_list()

    def _on_clear_gateway(self) -> None:
        if self._gateway is None:
            return
        if not self._gateway.condition_id:
            self._notify.status_msg("当前网关节点未绑定条件", ttl_ms=1500)
            return
        self._gateway.condition_id = None
        self._mark_dirty()
        self._notify.status_msg("已清除网关节点条件", ttl_ms=1500)
        self._reload_condition_list()

    # -----------------------------
    # 描述
    # -----------------------------

    def _describe_point(self, pid: str) -> str:
        pts: List[Point] = list(getattr(self._ctx.points, "points", []) or [])
        for p in pts:
            if p.id == pid:
                return f"{p.name or '(未命名)'} [{(p.id or '')[-6:]}]"
        return f"(点位缺失: {(pid or '')[-6:]})"

    def _describe_skill(self, sid: str) -> str:
        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        for s in skills:
            if s.id == sid:
                return f"{s.name or '(未命名)'} [{(s.id or '')[-6:]}]"
        return f"(技能缺失: {(sid or '')[-6:]})"

    # -----------------------------
    # expr <-> groups
    # -----------------------------

    def _parse_groups(self, expr: Dict[str, Any]) -> List[Group]:
        groups: List[Group] = []
        raw_groups = expr.get("groups", [])
        if not isinstance(raw_groups, list):
            return []

        for rg in raw_groups:
            if not isinstance(rg, dict):
                continue
            gid = str(rg.get("id") or "").strip() or uuid.uuid4().hex
            op = str(rg.get("op") or "and").strip().lower()
            if op not in ("and", "or"):
                op = "and"

            atoms: List[Atom] = []
            raw_atoms = rg.get("atoms", [])
            if isinstance(raw_atoms, list):
                for ra in raw_atoms:
                    if not isinstance(ra, dict):
                        continue
                    aid = str(ra.get("id") or "").strip() or uuid.uuid4().hex
                    t = str(ra.get("type") or "").strip().lower()

                    neg = bool(ra.get("neg", False))

                    if t == "pixel_point":
                        pid = str(ra.get("point_id") or "").strip()
                        tol = int(ra.get("tolerance", 0) or 0)
                        tol = max(0, min(255, tol))
                        if pid:
                            atoms.append(Atom(id=aid, kind="pixel_point", ref_id=pid, value=tol, neg=neg))
                    elif t == "pixel_skill":
                        sid = str(ra.get("skill_id") or "").strip()
                        tol = int(ra.get("tolerance", 0) or 0)
                        tol = max(0, min(255, tol))
                        if sid:
                            atoms.append(Atom(id=aid, kind="pixel_skill", ref_id=sid, value=tol, neg=neg))
                    elif t == "skill_cast_ge":
                        sid = str(ra.get("skill_id") or "").strip()
                        cnt = int(ra.get("count", 0) or 0)
                        if sid and cnt > 0:
                            atoms.append(Atom(id=aid, kind="skill_cast_ge", ref_id=sid, value=cnt, neg=neg))

            groups.append(Group(id=gid, op=op, atoms=atoms))

        return groups

    def _build_expr(self, groups: List[Group]) -> Dict[str, Any]:
        out_groups: List[Dict[str, Any]] = []
        for g in groups or []:
            atoms_out: List[Dict[str, Any]] = []
            for a in g.atoms or []:
                k = (a.kind or "").strip().lower()
                base: Dict[str, Any] = {"id": a.id, "neg": bool(a.neg)}
                if k == "pixel_point":
                    base.update({"type": "pixel_point", "point_id": a.ref_id, "tolerance": int(max(0, min(255, a.value)))})
                elif k == "pixel_skill":
                    base.update({"type": "pixel_skill", "skill_id": a.ref_id, "tolerance": int(max(0, min(255, a.value)))})
                elif k == "skill_cast_ge":
                    cnt = int(a.value)
                    if cnt <= 0:
                        cnt = 1
                    base.update({"type": "skill_cast_ge", "skill_id": a.ref_id, "count": cnt})
                else:
                    continue
                atoms_out.append(base)

            op = (g.op or "and").strip().lower()
            if op not in ("and", "or"):
                op = "and"

            out_groups.append(
                {
                    "id": g.id,
                    "op": op,
                    "atoms": atoms_out,
                }
            )

        return {"groups": out_groups}

    # -----------------------------
    # 脏标记
    # -----------------------------

    def _mark_dirty(self) -> None:
        try:
            self._mark_dirty_cb()
        except Exception:
            log.exception("ConditionEditorDialog: mark_dirty failed")