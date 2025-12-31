# rotation_editor/qt_presets_page.py
from __future__ import annotations

from typing import Optional, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QTextEdit,
    QStyle,
    QInputDialog,
    QMessageBox,
)

from core.profiles import ProfileContext
from core.store.app_store import AppStore
from qtui.notify import UiNotify
from qtui.icons import load_icon

from rotation_editor.core.services import RotationService


class RotationPresetsPage(QWidget):
    """
    轨道方案管理页（MVP）：

    - 左侧：方案列表（RotationPreset）
    - 右侧：当前选中方案的名称/描述编辑
    - 右侧额外有“编辑此方案...”按钮，切换到循环编辑器页
    - 底部：新建/复制/重命名/删除 + 重新加载/保存

    不编辑 Mode/Track/Node，只管理 presets。
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        store: AppStore,
        notify: UiNotify,
        open_editor: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._store = store
        self._notify = notify
        self._open_editor = open_editor

        self._svc = RotationService(
            store=self._store,
            notify_dirty=self._on_service_dirty,
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )

        self._current_id: Optional[str] = None
        self._building_form = False

        self._dirty_ui = False

        self._build_ui()
        self._subscribe_store_dirty()
        self.refresh_list()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 标题
        header = QHBoxLayout()
        lbl_title = QLabel("循环 / 轨道方案", self)
        f = lbl_title.font()
        f.setPointSize(16)
        f.setBold(True)
        lbl_title.setFont(f)
        header.addWidget(lbl_title)

        header.addStretch(1)

        self._lbl_dirty = QLabel("", self)
        header.addWidget(self._lbl_dirty)

        root.addLayout(header)

        # 分割器：左列表 + 右表单
        splitter = QSplitter(Qt.Horizontal, self)
        root.addWidget(splitter, 1)

        # 左侧：列表 + 按钮
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        style = self.style()

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)

        icon_add = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_copy = load_icon("copy", style, QStyle.StandardPixmap.SP_DirLinkIcon)
        icon_rename = load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogDetailedView)
        icon_del = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        self._btn_new = QPushButton("新建", self)
        self._btn_new.setIcon(icon_add)
        self._btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(self._btn_new)

        self._btn_copy = QPushButton("复制", self)
        self._btn_copy.setIcon(icon_copy)
        self._btn_copy.clicked.connect(self._on_copy)
        btn_row.addWidget(self._btn_copy)

        self._btn_rename = QPushButton("重命名", self)
        self._btn_rename.setIcon(icon_rename)
        self._btn_rename.clicked.connect(self._on_rename)
        btn_row.addWidget(self._btn_rename)

        self._btn_delete = QPushButton("删除", self)
        self._btn_delete.setIcon(icon_del)
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_delete)

        left_layout.addLayout(btn_row)

        # 列表
        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.currentItemChanged.connect(self._on_select)
        left_layout.addWidget(self._list, 1)

        splitter.addWidget(left)

        # 右侧：表单
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        form_row1 = QHBoxLayout()
        lbl_name = QLabel("名称:", right)
        self._edit_name = QLineEdit(right)
        form_row1.addWidget(lbl_name)
        form_row1.addWidget(self._edit_name, 1)
        right_layout.addLayout(form_row1)

        lbl_desc = QLabel("描述:", right)
        right_layout.addWidget(lbl_desc)
        self._edit_desc = QTextEdit(right)
        self._edit_desc.setPlaceholderText("方案用途、备注等...")
        right_layout.addWidget(self._edit_desc, 1)

        # 编辑按钮
        edit_row = QHBoxLayout()
        self._btn_edit = QPushButton("编辑此方案...", right)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_edit.setEnabled(False)
        edit_row.addWidget(self._btn_edit)
        edit_row.addStretch(1)
        right_layout.addLayout(edit_row)

        # 底部：重载/保存
        btn_bottom = QHBoxLayout()
        btn_bottom.addStretch(1)

        icon_reload = load_icon("reload", style, QStyle.StandardPixmap.SP_BrowserReload)
        icon_save = load_icon("save", style, QStyle.StandardPixmap.SP_DialogSaveButton)

        self._btn_reload = QPushButton("重新加载(放弃未保存)", self)
        self._btn_reload.setIcon(icon_reload)
        self._btn_reload.clicked.connect(self._on_reload)
        btn_bottom.addWidget(self._btn_reload)

        self._btn_save = QPushButton("保存", self)
        self._btn_save.setIcon(icon_save)
        self._btn_save.clicked.connect(self._on_save)
        btn_bottom.addWidget(self._btn_save)

        right_layout.addLayout(btn_bottom)

        splitter.addWidget(right)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([320, 780])

        # 表单变更 -> 写回模型（标记 dirty）
        self._edit_name.textChanged.connect(self._on_form_changed)
        self._edit_desc.textChanged.connect(self._on_form_changed)

    # ---------- Store dirty 订阅 ----------

    def _subscribe_store_dirty(self) -> None:
        try:
            self._store.subscribe_dirty(self._on_store_dirty)
        except Exception:
            pass

    def _on_store_dirty(self, parts) -> None:
        try:
            parts_set = set(parts or [])
        except Exception:
            parts_set = set()
        self._dirty_ui = "rotations" in parts_set
        self._update_dirty_ui()

    def _on_service_dirty(self) -> None:
        # service 内部调用 mark_dirty 后再回调这里；
        # 实际 UI 更新仍然走 store.subscribe_dirty 通道。
        pass

    def _update_dirty_ui(self) -> None:
        self._lbl_dirty.setText("未保存*" if self._dirty_ui else "")
        if self._dirty_ui:
            self._btn_save.setStyleSheet("color: orange;")
        else:
            self._btn_save.setStyleSheet("")

    # ---------- 上下文切换与刷新 ----------

    def set_context(self, ctx: ProfileContext) -> None:
        """
        当 Profile 切换时，从新的 ctx.rotations 填充 UI。
        """
        self._ctx = ctx
        self._current_id = None
        self.refresh_list()

    def refresh_list(self) -> None:
        """
        刷新左侧方案列表，尽量保持当前选中。
        """
        prev = self._current_id
        self._list.blockSignals(True)
        self._list.clear()

        presets = self._svc.list_presets()
        for p in presets:
            item = QListWidgetItem(p.name or "(未命名)")
            item.setData(Qt.UserRole, p.id)
            self._list.addItem(item)

        self._list.blockSignals(False)

        # 恢复选中
        if prev:
            self._select_id(prev)
        else:
            self._select_first_if_any()

    def _select_first_if_any(self) -> None:
        if self._list.count() == 0:
            self._current_id = None
            self._clear_form()
            return
        item = self._list.item(0)
        self._list.setCurrentItem(item)

    def _select_id(self, pid: str) -> None:
        pid = (pid or "").strip()
        if not pid:
            self._select_first_if_any()
            return
        for i in range(self._list.count()):
            item = self._list.item(i)
            val = item.data(Qt.UserRole)
            if isinstance(val, str) and val == pid:
                self._list.setCurrentItem(item)
                return
        self._select_first_if_any()

    # ---------- 表单加载/应用 ----------

    def _clear_form(self) -> None:
        self._building_form = True
        try:
            self._edit_name.clear()
            self._edit_desc.clear()
            if hasattr(self, "_btn_edit"):
                self._btn_edit.setEnabled(False)
        finally:
            self._building_form = False

    def _load_into_form(self, pid: str) -> None:
        p = self._svc.find_preset(pid)
        self._current_id = pid if p is not None else None
        self._building_form = True
        try:
            if p is None:
                self._clear_form()
                return
            self._edit_name.setText(p.name)
            self._edit_desc.setPlainText(p.description or "")
            if hasattr(self, "_btn_edit"):
                self._btn_edit.setEnabled(True)
        finally:
            self._building_form = False

    def _apply_form_to_current(self) -> None:
        if self._building_form:
            return
        pid = self._current_id
        if not pid:
            return
        name = self._edit_name.text()
        desc = self._edit_desc.toPlainText()
        changed = self._svc.update_preset_basic(pid, name=name, description=desc)
        if changed:
            # 更新列表显示的名称
            for i in range(self._list.count()):
                item = self._list.item(i)
                val = item.data(Qt.UserRole)
                if isinstance(val, str) and val == pid:
                    item.setText((name or "").strip() or "(未命名)")
                    break

    # ---------- 事件回调 ----------

    def _on_select(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if curr is None:
            self._current_id = None
            self._clear_form()
            return
        pid = curr.data(Qt.UserRole)
        if not isinstance(pid, str):
            self._current_id = None
            self._clear_form()
            return

        # 在切换前先把表单内容应用到上一个
        if prev is not None:
            try:
                self._apply_form_to_current()
            except Exception:
                pass

        self._load_into_form(pid)

    def _on_form_changed(self) -> None:
        if self._building_form:
            return
        self._apply_form_to_current()

    def _on_edit(self) -> None:
        """
        点击“编辑此方案...”时调用外部回调，
        由 MainWindow 切换到循环编辑器页并定位到当前方案。
        """
        pid = self._current_id
        if not pid:
            self._notify.error("请先选择一个方案再编辑")
            return
        try:
            self._apply_form_to_current()
        except Exception:
            pass
        try:
            self._open_editor(pid)
        except Exception as e:
            self._notify.error("打开编辑器失败", detail=str(e))

    # ---------- 按钮行为：新建/复制/重命名/删除 ----------

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(self, "新建方案", "请输入方案名称：", text="新方案")
        if not ok:
            return
        try:
            p = self._svc.create_preset(name)
            self._notify.info(f"已新建方案: {p.name}")
            self.refresh_list()
            self._select_id(p.id)
        except Exception as e:
            self._notify.error("新建方案失败", detail=str(e))

    def _on_copy(self) -> None:
        if not self._current_id:
            self._notify.error("请先选择要复制的方案")
            return
        src = self._svc.find_preset(self._current_id)
        if src is None:
            self._notify.error("源方案不存在")
            return

        name, ok = QInputDialog.getText(
            self,
            "复制方案",
            f"复制自：{src.name}\n请输入新方案名称：",
            text=f"{src.name} (副本)",
        )
        if not ok:
            return
        try:
            clone = self._svc.clone_preset(src.id, name)
            if clone is None:
                self._notify.error("复制失败：源方案不存在")
                return
            self._notify.info(f"已复制方案: {clone.name}")
            self.refresh_list()
            self._select_id(clone.id)
        except Exception as e:
            self._notify.error("复制方案失败", detail=str(e))

    def _on_rename(self) -> None:
        if not self._current_id:
            self._notify.error("请先选择要重命名的方案")
            return
        p = self._svc.find_preset(self._current_id)
        if p is None:
            self._notify.error("当前方案不存在")
            return

        name, ok = QInputDialog.getText(
            self,
            "重命名方案",
            "请输入新名称：",
            text=p.name,
        )
        if not ok:
            return

        try:
            changed = self._svc.rename_preset(p.id, name)
            if not changed:
                self._notify.status_msg("名称未变化", ttl_ms=1500)
                return
            self._notify.info(f"已重命名方案为: {name.strip() or '(未命名)'}")
            self.refresh_list()
            self._select_id(p.id)
        except Exception as e:
            self._notify.error("重命名方案失败", detail=str(e))

    def _on_delete(self) -> None:
        if not self._current_id:
            self._notify.error("请先选择要删除的方案")
            return
        p = self._svc.find_preset(self._current_id)
        if p is None:
            self._notify.error("当前方案不存在")
            return

        ok = QMessageBox.question(
            self,
            "删除方案",
            f"确认删除方案：{p.name} ？\n\n该操作仅删除循环配置，不影响 skills/points。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        try:
            if not self._svc.delete_preset(p.id):
                self._notify.error("删除失败：方案不存在")
                return
            self._notify.info(f"已删除方案: {p.name}")
            self._current_id = None
            self.refresh_list()
        except Exception as e:
            self._notify.error("删除方案失败", detail=str(e))

    # ---------- 重载 / 保存 ----------

    def _on_reload(self) -> None:
        ok = QMessageBox.question(
            self,
            "重新加载",
            "将从磁盘重新加载 rotation.json，放弃当前未保存更改。\n\n确认继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        try:
            self._svc.reload_cmd()
            self._current_id = None
            self.refresh_list()
            self._notify.info("已重新加载循环配置")
        except Exception as e:
            self._notify.error("重新加载失败", detail=str(e))

    def _on_save(self) -> None:
        try:
            self._apply_form_to_current()
        except Exception:
            pass

        saved = self._svc.save_cmd()
        if saved:
            self._notify.info("rotation.json 已保存")
        else:
            self._notify.status_msg("没有需要保存的更改", ttl_ms=1500)

    # ---------- 提供给 UnsavedGuard 的 flush 接口 ----------

    def flush_to_model(self) -> None:
        """
        将右侧表单内容写回 ctx.rotations（不保存到磁盘）。
        """
        try:
            self._apply_form_to_current()
        except Exception:
            pass