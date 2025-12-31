# qtui/pages/record_crud_page.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QSplitter,
    QSizePolicy,
    QStyle,
)
from PySide6.QtCore import Qt

from core.store.app_store import AppStore

from qtui.notify import UiNotify
from qtui.icons import load_icon


@dataclass
class ColumnDef:
    key: str
    heading: str
    width: int = 80
    anchor: str = "center"  # "w" | "center"


class RecordCrudPage(QWidget):
    """
    通用 CRUD 页面基类（Qt 版）：

    - 左侧：工具栏（新增/复制/删除/重新加载/保存） + QTreeWidget 列表
    - 右侧：标题 + “未保存*” 标签 + 表单容器（right_body）
    - 中间使用 QSplitter，可调整左右宽度比例
    - 工具栏按钮放在一个固定宽度的小 QWidget 里，始终贴左上角，不随宽度漂移
    - 脏状态指示：enable_uow_dirty_indicator(part_key, store) 订阅 AppStore.dirty
    """

    def __init__(
        self,
        *,
        ctx: Any,
        notify: UiNotify,
        page_title: str,
        record_noun: str,
        columns: List[ColumnDef],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._notify = notify

        self._page_title_text = page_title
        self._record_noun = record_noun
        self._columns = columns

        self._current_id: str | None = None
        self._suppress_select = False

        self._dirty_ui = False
        self._uow_part_key: str | None = None

        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 页面标题
        lbl_page = QLabel(self._page_title_text, self)
        f = lbl_page.font()
        f.setPointSize(16)
        f.setBold(True)
        lbl_page.setFont(f)
        root.addWidget(lbl_page)

        # 使用 QSplitter 管理左右区域
        splitter = QSplitter(Qt.Horizontal, self)
        root.addWidget(splitter, 1)

        style = self.style()

        # 左侧容器：工具栏 + 列表
        left_container = QWidget(self)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # ---- 工具栏区域：用一个单独的小 QWidget 承载，贴左上角 ----
        toolbar_widget = QWidget(self)
        toolbar_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)

        # 工具栏按钮，SizePolicy 固定，避免被拉成长条
        btn_add = QPushButton("新增", toolbar_widget)
        icon_add = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        btn_add.setIcon(icon_add)
        btn_add.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_add.clicked.connect(self._on_add)
        toolbar_layout.addWidget(btn_add)

        btn_dup = QPushButton("复制", toolbar_widget)
        icon_copy = load_icon("copy", style, QStyle.StandardPixmap.SP_DirLinkIcon)
        btn_dup.setIcon(icon_copy)
        btn_dup.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_dup.clicked.connect(self._on_duplicate)
        toolbar_layout.addWidget(btn_dup)

        btn_del = QPushButton("删除", toolbar_widget)
        icon_del = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)
        btn_del.setIcon(icon_del)
        btn_del.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_del.clicked.connect(self._on_delete)
        toolbar_layout.addWidget(btn_del)

        toolbar_layout.addSpacing(12)

        btn_reload = QPushButton("重新加载", toolbar_widget)
        icon_reload = load_icon("reload", style, QStyle.StandardPixmap.SP_BrowserReload)
        btn_reload.setIcon(icon_reload)
        btn_reload.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_reload.clicked.connect(self._on_reload_clicked)
        toolbar_layout.addWidget(btn_reload)

        self._btn_save = QPushButton("保存", toolbar_widget)
        icon_save = load_icon("save", style, QStyle.StandardPixmap.SP_DialogSaveButton)
        self._btn_save.setIcon(icon_save)
        self._btn_save.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._btn_save.clicked.connect(self._on_save_clicked)
        toolbar_layout.addWidget(self._btn_save)

        # 把 toolbar_widget 贴左上角
        left_layout.addWidget(toolbar_widget, 0, Qt.AlignLeft)

        # 列表
        self._tv = QTreeWidget(self)
        self._tv.setRootIsDecorated(False)
        self._tv.setAlternatingRowColors(True)
        self._tv.setSelectionMode(QTreeWidget.SingleSelection)
        self._tv.setSelectionBehavior(QTreeWidget.SelectRows)

        headers = [c.heading for c in self._columns]
        self._tv.setHeaderLabels(headers)

        for idx, c in enumerate(self._columns):
            self._tv.setColumnWidth(idx, c.width)
            align = Qt.AlignCenter
            if c.anchor == "w":
                align = Qt.AlignLeft | Qt.AlignVCenter
            self._tv.headerItem().setTextAlignment(idx, align)

        self._tv.itemSelectionChanged.connect(self._on_select)
        left_layout.addWidget(self._tv, 1)

        # 右侧容器：标题 + 脏状态 + 表单容器
        right_container = QWidget(self)
        right_col = QVBoxLayout(right_container)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(8)

        header = QHBoxLayout()
        right_col.addLayout(header)

        self._lbl_title = QLabel("未选择", self)
        f2 = self._lbl_title.font()
        f2.setPointSize(11)
        f2.setBold(True)
        self._lbl_title.setFont(f2)
        header.addWidget(self._lbl_title)

        header.addStretch(1)

        self._lbl_dirty = QLabel("", self)
        header.addWidget(self._lbl_dirty)

        self.right_body = QWidget(self)
        rb_layout = QVBoxLayout(self.right_body)
        rb_layout.setContentsMargins(0, 0, 0, 0)
        rb_layout.setSpacing(0)
        right_col.addWidget(self.right_body, 1)

        # 把左右容器添加到 splitter
        splitter.addWidget(left_container)
        splitter.addWidget(right_container)

        # 左侧列表稍微宽一点，右侧表单相对收窄，用户可以手动拖动
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([420, 580])

        self._update_dirty_ui()

    # ---------- 脏状态 ----------

    def enable_uow_dirty_indicator(self, *, part_key: str, store: AppStore) -> None:
        """
        使用 AppStore.dirty 状态更新“未保存*”指示。
        """
        self._uow_part_key = str(part_key)
        try:
            store.subscribe_dirty(self._on_store_dirty)
        except Exception:
            pass

    def _on_store_dirty(self, parts) -> None:
        key = self._uow_part_key
        if not key:
            return
        try:
            parts_set = set(parts or [])
        except Exception:
            parts_set = set()
        self._set_dirty_ui(key in parts_set)

    def _set_dirty_ui(self, flag: bool) -> None:
        self._dirty_ui = bool(flag)
        self._update_dirty_ui()

    def _update_dirty_ui(self) -> None:
        self._lbl_dirty.setText("未保存*" if self._dirty_ui else "")
        if self._dirty_ui:
            self._btn_save.setStyleSheet("color: orange;")
        else:
            self._btn_save.setStyleSheet("")

    # ---------- 公共 API ----------

    @property
    def current_id(self) -> str | None:
        return self._current_id

    def set_header_title(self, text: str) -> None:
        self._lbl_title.setText(text)

    # ---------- 列表操作 ----------

    def refresh_tree(self) -> None:
        selected = self._current_id
        self._tv.clear()

        for r in self._records():
            rid = self._record_id(r)
            if not rid:
                continue
            vals = list(self._record_row_values(r))
            item = QTreeWidgetItem(vals)
            item.setData(0, Qt.UserRole, rid)
            self._tv.addTopLevelItem(item)

        if selected:
            self._select_id(selected)
        else:
            self._select_first_if_any()

    def update_tree_row(self, rid: str) -> None:
        r = self._find_record_by_id(rid)
        if r is None or not rid:
            return

        item = self._find_item_by_id(rid)
        values = list(self._record_row_values(r))

        if item is None:
            item = QTreeWidgetItem(values)
            item.setData(0, Qt.UserRole, rid)
            self._tv.addTopLevelItem(item)
        else:
            for i, v in enumerate(values):
                item.setText(i, str(v))

    def delete_tree_row(self, rid: str) -> None:
        item = self._find_item_by_id(rid)
        if item is None:
            return
        idx = self._tv.indexOfTopLevelItem(item)
        if idx >= 0:
            self._tv.takeTopLevelItem(idx)

    def _select_first_if_any(self) -> None:
        count = self._tv.topLevelItemCount()
        if count == 0:
            self._current_id = None
            self._lbl_title.setText("未选择")
            self._clear_form()
            return
        item = self._tv.topLevelItem(0)
        self._select_item(item)

    def _select_id(self, rid: str) -> None:
        item = self._find_item_by_id(rid)
        if item is None:
            self._current_id = None
            self._lbl_title.setText("未选择")
            self._clear_form()
            return
        self._select_item(item)

    def _select_item(self, item: QTreeWidgetItem) -> None:
        self._suppress_select = True
        try:
            self._tv.setCurrentItem(item)
        finally:
            self._suppress_select = False
        rid = item.data(0, Qt.UserRole)
        if isinstance(rid, str):
            self._load_into_form(rid)

    def _on_select(self) -> None:
        if self._suppress_select:
            return
        item = self._tv.currentItem()
        if item is None:
            return

        rid = item.data(0, Qt.UserRole)
        if not isinstance(rid, str):
            return

        if self._current_id is not None:
            self._apply_form_to_current(auto_save=False)

        self._load_into_form(rid)

    def _find_item_by_id(self, rid: str) -> QTreeWidgetItem | None:
        for i in range(self._tv.topLevelItemCount()):
            item = self._tv.topLevelItem(i)
            val = item.data(0, Qt.UserRole)
            if val == rid:
                return item
        return None

    # ---------- CRUD ----------

    def _on_add(self) -> None:
        self._apply_form_to_current(auto_save=False)

        rec = self._make_new_record()
        rid = self._record_id(rec)
        if not rid:
            self.refresh_tree()
            return

        self.update_tree_row(rid)
        self._select_id(rid)
        self._notify.info(f"已新增{self._record_noun}: {rid[-6:]}")

    def _on_duplicate(self) -> None:
        item = self._tv.currentItem()
        if item is None:
            self._notify.error(f"请先选择要复制的{self._record_noun}")
            return

        self._apply_form_to_current(auto_save=False)

        rid = item.data(0, Qt.UserRole)
        if not isinstance(rid, str):
            self._notify.error(f"源{self._record_noun}不存在")
            return

        src = self._find_record_by_id(rid)
        if src is None:
            self._notify.error(f"源{self._record_noun}不存在")
            return

        clone = self._clone_record(src)
        new_id = self._record_id(clone)
        if not new_id:
            self.refresh_tree()
            return

        self.update_tree_row(new_id)
        self._select_id(new_id)
        self._notify.info(f"已复制{self._record_noun}: {new_id[-6:]}")

    def _on_delete(self) -> None:
        item = self._tv.currentItem()
        if item is None:
            self._notify.error(f"请先选择要删除的{self._record_noun}")
            return

        rid = item.data(0, Qt.UserRole)
        if not isinstance(rid, str):
            self._notify.error(f"{self._record_noun}不存在")
            return

        rec = self._find_record_by_id(rid)
        if rec is None:
            self._notify.error(f"{self._record_noun}不存在")
            return

        ok = QMessageBox.question(
            self,
            f"删除{self._record_noun}",
            f"确认删除该{self._record_noun}？\n\n{self._record_title(rec)}\nID: {rid}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        try:
            self._delete_record_by_id(rid)
        except Exception as e:
            self._notify.error("删除失败", detail=str(e))
            return

        is_current = (self._current_id == rid)
        self.delete_tree_row(rid)

        if is_current:
            self._current_id = None
            self._select_first_if_any()

        self._notify.info(f"已删除{self._record_noun}: {rid[-6:]}")

    # ---------- 重载 / 保存 ----------

    def _on_reload_clicked(self) -> None:
        ok = QMessageBox.question(
            self,
            "重新加载",
            f"将从磁盘重新加载 {self._record_noun} 数据，放弃当前未保存更改。\n\n确认继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        try:
            self._apply_form_to_current(auto_save=False)
        except Exception:
            pass

        try:
            self._reload_from_disk()
        except Exception as e:
            self._notify.error("重新加载失败", detail=str(e))
            return

        self._current_id = None
        self.refresh_tree()
        self._notify.info("已重新加载")

    def _on_save_clicked(self) -> None:
        if not self._apply_form_to_current(auto_save=False):
            return
        if self._save_to_disk():
            self._notify.info(f"{self._record_noun}已保存")

    # ---------- 抽象接口（子类实现） ----------

    def _reload_from_disk(self) -> None:
        raise NotImplementedError

    def _records(self) -> list:
        raise NotImplementedError

    def _save_to_disk(self) -> bool:
        raise NotImplementedError

    def _make_new_record(self) -> Any:
        raise NotImplementedError

    def _clone_record(self, record: Any) -> Any:
        raise NotImplementedError

    def _delete_record_by_id(self, rid: str) -> None:
        raise NotImplementedError

    def _record_id(self, record: Any) -> str:
        raise NotImplementedError

    def _record_title(self, record: Any) -> str:
        raise NotImplementedError

    def _record_row_values(self, record: Any) -> tuple:
        raise NotImplementedError

    def _load_into_form(self, rid: str) -> None:
        raise NotImplementedError

    def _apply_form_to_current(self, *, auto_save: bool) -> bool:
        raise NotImplementedError

    def _clear_form(self) -> None:
        raise NotImplementedError

    # ---------- 辅助 ----------

    def _find_record_by_id(self, rid: str) -> Any | None:
        for r in self._records():
            if self._record_id(r) == rid:
                return r
        return None