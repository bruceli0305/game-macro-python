# rotation_editor/ui/editor/condition_dialog.py
from __future__ import annotations

import uuid
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
    QStyle,
)

from qtui.icons import load_icon
from qtui.notify import UiNotify
from rotation_editor.core.models import RotationPreset, Condition, GatewayNode


class ConditionEditorDialog(QDialog):
    """
    条件编辑对话框（针对某个 RotationPreset）：

    - 左侧：条件列表（name）
    - 右侧：当前条件的 name / kind / expr 文本（占位）
    - 按钮：
        - 新建 / 删除 条件
        - 应用到当前网关节点（将 gateway.condition_id 设为选中的条件 ID）
        - 清除当前网关条件（condition_id = None）
        - 关闭

    expr 策略（MVP）：
    - 只用一个 "text" 字段保存自由文本，存入 Condition.expr["text"]
    - 若用户输入的是合法 JSON，则直接用 JSON 对象存入 expr
    - 否则，以 {"text": 原始字符串} 形式保存
    """

    def __init__(
        self,
        *,
        preset: RotationPreset,
        gateway: Optional[GatewayNode],
        notify: NotifyLike,
        mark_dirty,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑条件")
        self.resize(520, 380)

        self._preset = preset
        self._gateway = gateway
        self._notify = notify
        self._mark_dirty_cb = mark_dirty

        self._current_cond_id: Optional[str] = None
        self._building = False

        self._build_ui()
        self._reload_from_preset()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # 顶部提示
        lbl_tip = QLabel(
            "说明：当前仅提供简单条件占位。\n"
            "- name: 条件名称（用于网关节点显示）\n"
            "- kind: 条件类型（例如 pixel / buff / expr ...）\n"
            "- 表达式: 可填写 JSON 或任意文本，暂不会实际求值。",
            self,
        )
        lbl_tip.setWordWrap(True)
        layout.addWidget(lbl_tip)

        # 主区：列表 + 表单
        body_row = QHBoxLayout()
        layout.addLayout(body_row, 1)

        # 左侧列表
        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.currentItemChanged.connect(self._on_select)
        body_row.addWidget(self._list, 1)

        # 右侧表单
        right = QVBoxLayout()
        right.setSpacing(4)

        row_name = QHBoxLayout()
        row_name.addWidget(QLabel("名称:", self))
        self._edit_name = QLineEdit(self)
        row_name.addWidget(self._edit_name, 1)
        right.addLayout(row_name)

        row_kind = QHBoxLayout()
        row_kind.addWidget(QLabel("类型(kind):", self))
        self._edit_kind = QLineEdit(self)
        row_kind.addWidget(self._edit_kind, 1)
        right.addLayout(row_kind)

        right.addWidget(QLabel("表达式(JSON 或任意文本):", self))
        self._edit_expr = QPlainTextEdit(self)
        self._edit_expr.setPlaceholderText('例如: {"kind": "pixel", "point_id": "..."} 或任意说明文字')
        right.addWidget(self._edit_expr, 1)

        body_row.addLayout(right, 2)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        layout.addLayout(btn_row)

        style = self.style()
        icon_add = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_del = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        self._btn_new = QPushButton("新建条件", self)
        self._btn_new.setIcon(icon_add)
        self._btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(self._btn_new)

        self._btn_delete = QPushButton("删除条件", self)
        self._btn_delete.setIcon(icon_del)
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_delete)

        btn_row.addStretch(1)

        self._btn_apply = QPushButton("应用到当前网关节点", self)
        self._btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self._btn_apply)

        self._btn_clear = QPushButton("清除当前网关条件", self)
        self._btn_clear.clicked.connect(self._on_clear_gateway)
        btn_row.addWidget(self._btn_clear)

        self._btn_close = QPushButton("关闭", self)
        self._btn_close.clicked.connect(self.close)
        btn_row.addWidget(self._btn_close)

        # 表单变更事件
        self._edit_name.textChanged.connect(self._on_form_changed)
        self._edit_kind.textChanged.connect(self._on_form_changed)
        self._edit_expr.textChanged.connect(self._on_form_changed)

        # 若当前没有 gateway（理论上不会），禁用应用/清除按钮
        if self._gateway is None:
            self._btn_apply.setEnabled(False)
            self._btn_clear.setEnabled(False)

    # ---------- 载入/刷新 ----------

    def _reload_from_preset(self) -> None:
        prev = self._current_cond_id
        self._building = True
        try:
            self._list.clear()
            for c in self._preset.conditions:
                item = QListWidgetItem(c.name or "(未命名)")
                item.setData(Qt.UserRole, c.id)
                self._list.addItem(item)
        finally:
            self._building = False

        # 恢复选中
        if prev:
            for i in range(self._list.count()):
                item = self._list.item(i)
                cid = item.data(Qt.UserRole)
                if isinstance(cid, str) and cid == prev:
                    self._list.setCurrentItem(item)
                    return

        # 若 gateway 已绑定条件，尝试选中对应条件
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
            self._edit_kind.clear()
            self._edit_expr.clear()
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
            self._edit_kind.setText(c.kind or "")
            # expr: 尝试取 "text"，否则当作 JSON 串展示
            expr_text = ""
            if isinstance(c.expr, dict):
                if "text" in c.expr and isinstance(c.expr["text"], str):
                    expr_text = c.expr["text"]
                else:
                    try:
                        expr_text = json.dumps(c.expr, ensure_ascii=False, indent=2)
                    except Exception:
                        expr_text = str(c.expr)
            self._edit_expr.setPlainText(expr_text)
        finally:
            self._building = False

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
        kind = (self._edit_kind.text() or "").strip()
        expr_raw = self._edit_expr.toPlainText()

        changed = False
        if name and name != c.name:
            c.name = name
            changed = True
        if kind != (c.kind or ""):
            c.kind = kind
            changed = True

        # expr：尝试解析为 JSON；如果失败，则包装成 {"text": 原始字符串}
        expr_raw_str = expr_raw.strip()
        new_expr = c.expr
        try:
            if expr_raw_str:
                parsed = json.loads(expr_raw_str)
                if isinstance(parsed, dict):
                    new_expr = parsed
                else:
                    new_expr = {"value": parsed}
            else:
                new_expr = {}
        except Exception:
            # 非 JSON，则以 text 存储
            new_expr = {"text": expr_raw}

        if new_expr != (c.expr or {}):
            c.expr = new_expr
            changed = True

        if changed:
            self._mark_dirty()
            # 更新列表项显示名称
            for i in range(self._list.count()):
                item = self._list.item(i)
                cid2 = item.data(Qt.UserRole)
                if isinstance(cid2, str) and cid2 == cid:
                    item.setText(c.name or "(未命名)")
                    break

    # ---------- 列表事件 ----------

    def _on_select(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if self._building:
            return
        # 先把之前的表单写回
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

    # ---------- 新建 / 删除 条件 ----------

    def _on_new(self) -> None:
        cid = uuid.uuid4().hex
        cond = Condition(
            id=cid,
            name="新条件",
            kind="",
            expr={"text": ""},
        )
        self._preset.conditions.append(cond)
        self._mark_dirty()
        self._reload_from_preset()
        # 选中新建的
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
            f"确认删除条件：{c.name or '(未命名)'} ？\n"
            f"（若有网关节点引用该条件，其 condition_id 将可能失效）",
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

    def _on_clear_gateway(self) -> None:
        if self._gateway is None:
            return
        if not self._gateway.condition_id:
            self._notify.status_msg("当前网关节点未绑定条件", ttl_ms=1500)
            return
        self._gateway.condition_id = None
        self._mark_dirty()
        self._notify.status_msg("已清除网关节点条件", ttl_ms=1500)

    # ---------- 辅助 ----------

    def _mark_dirty(self) -> None:
        try:
            self._mark_dirty_cb()
        except Exception:
            pass