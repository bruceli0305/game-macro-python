# rotation_editor/ui/editor/mode_track_panel.py
from __future__ import annotations

import uuid
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QInputDialog,
    QMessageBox,
    QStyle,
)

from qtui.notify import UiNotify
from qtui.icons import load_icon
from rotation_editor.core.models import RotationPreset, Mode, Track


class ModeTrackPanel(QWidget):
    """
    左侧“模式 + 模式轨道 + 全局轨道”子面板：

    - set_preset(preset): 绑定当前正在编辑的 RotationPreset
    - 内部管理：
        - 模式列表：新增 / 重命名 / 删除
        - 模式下的轨道列表：新增 / 重命名 / 删除
        - 全局轨道列表：新增 / 重命名 / 删除（不隶属于任何模式）
    - 信号：
        - modeChanged(str): 当前模式 ID（空串表示“全局”）
        - trackChanged(str): 当前轨道 ID（空串表示无选中）
        - structureChanged(): 模式/轨道/全局轨道结构有变时发出（供编辑器刷新入口等）
    """

    modeChanged = Signal(str)       # 当前模式 ID（空串表示“全局”）
    trackChanged = Signal(str)      # 当前轨道 ID（空串表示无选中）
    structureChanged = Signal()     # 结构（模式/轨道/全局轨道）变化

    def __init__(
        self,
        *,
        notify: UiNotify,
        mark_dirty,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._notify = notify
        self._mark_dirty_cb = mark_dirty

        self._preset: Optional[RotationPreset] = None
        self._current_mode_id: Optional[str] = None
        self._current_track_id: Optional[str] = None
        self._current_track_scope: str = "mode"  # "mode" | "global"
        self._building = False

        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        style = self.style()

        # ---- 模式 ----
        lbl_modes = QLabel("模式 (Modes):", self)
        root.addWidget(lbl_modes)

        mode_row = QHBoxLayout()
        self._list_modes = QListWidget(self)
        self._list_modes.setSelectionMode(QListWidget.SingleSelection)
        self._list_modes.currentItemChanged.connect(self._on_mode_selected)
        mode_row.addWidget(self._list_modes, 1)

        btn_mode_col = QVBoxLayout()
        btn_mode_col.setSpacing(4)

        icon_add_mode = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_rename_mode = load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogDetailedView)
        icon_del_mode = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        self._btn_add_mode = QPushButton("新建模式", self)
        self._btn_add_mode.setIcon(icon_add_mode)
        self._btn_add_mode.clicked.connect(self._on_add_mode)
        btn_mode_col.addWidget(self._btn_add_mode)

        self._btn_rename_mode = QPushButton("重命名", self)
        self._btn_rename_mode.setIcon(icon_rename_mode)
        self._btn_rename_mode.clicked.connect(self._on_rename_mode)
        btn_mode_col.addWidget(self._btn_rename_mode)

        self._btn_del_mode = QPushButton("删除", self)
        self._btn_del_mode.setIcon(icon_del_mode)
        self._btn_del_mode.clicked.connect(self._on_delete_mode)
        btn_mode_col.addWidget(self._btn_del_mode)

        btn_mode_col.addStretch(1)
        mode_row.addLayout(btn_mode_col)
        root.addLayout(mode_row)

        root.addSpacing(10)

        # ---- 模式下轨道 ----
        lbl_tracks = QLabel("模式轨道 (Tracks in Mode):", self)
        root.addWidget(lbl_tracks)

        track_row = QHBoxLayout()
        self._list_tracks = QListWidget(self)
        self._list_tracks.setSelectionMode(QListWidget.SingleSelection)
        self._list_tracks.currentItemChanged.connect(self._on_track_selected)
        track_row.addWidget(self._list_tracks, 1)

        btn_track_col = QVBoxLayout()
        btn_track_col.setSpacing(4)

        icon_add_track = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_rename_track = load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogDetailedView)
        icon_del_track = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        self._btn_add_track = QPushButton("新建轨道", self)
        self._btn_add_track.setIcon(icon_add_track)
        self._btn_add_track.clicked.connect(self._on_add_track)
        btn_track_col.addWidget(self._btn_add_track)

        self._btn_rename_track = QPushButton("重命名", self)
        self._btn_rename_track.setIcon(icon_rename_track)
        self._btn_rename_track.clicked.connect(self._on_rename_track)
        btn_track_col.addWidget(self._btn_rename_track)

        self._btn_del_track = QPushButton("删除", self)
        self._btn_del_track.setIcon(icon_del_track)
        self._btn_del_track.clicked.connect(self._on_delete_track)
        btn_track_col.addWidget(self._btn_del_track)

        btn_track_col.addStretch(1)
        track_row.addLayout(btn_track_col)
        root.addLayout(track_row)

        root.addSpacing(10)

        # ---- 全局轨道 ----
        lbl_global = QLabel("全局轨道 (Global Tracks):", self)
        root.addWidget(lbl_global)

        global_row = QHBoxLayout()
        self._list_global = QListWidget(self)
        self._list_global.setSelectionMode(QListWidget.SingleSelection)
        self._list_global.currentItemChanged.connect(self._on_global_track_selected)
        global_row.addWidget(self._list_global, 1)

        btn_global_col = QVBoxLayout()
        btn_global_col.setSpacing(4)

        icon_add_global = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_rename_global = load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogDetailedView)
        icon_del_global = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        self._btn_add_global = QPushButton("新建全局轨道", self)
        self._btn_add_global.setIcon(icon_add_global)
        self._btn_add_global.clicked.connect(self._on_add_global_track)
        btn_global_col.addWidget(self._btn_add_global)

        self._btn_rename_global = QPushButton("重命名", self)
        self._btn_rename_global.setIcon(icon_rename_global)
        self._btn_rename_global.clicked.connect(self._on_rename_global_track)
        btn_global_col.addWidget(self._btn_rename_global)

        self._btn_del_global = QPushButton("删除", self)
        self._btn_del_global.setIcon(icon_del_global)
        self._btn_del_global.clicked.connect(self._on_delete_global_track)
        btn_global_col.addWidget(self._btn_del_global)

        btn_global_col.addStretch(1)
        global_row.addLayout(btn_global_col)
        root.addLayout(global_row)

    # ---------- 外部 API ----------

    def set_preset(self, preset: Optional[RotationPreset]) -> None:
        """
        绑定当前正在编辑的 preset。
        """
        self._preset = preset
        self._current_mode_id = None
        self._current_track_id = None
        self._current_track_scope = "mode"
        self._rebuild_modes()
        self._rebuild_tracks()
        self._rebuild_global_tracks()

    def current_mode_id(self) -> Optional[str]:
        return self._current_mode_id

    def current_track_id(self) -> Optional[str]:
        return self._current_track_id

    def select_location(self, mode_id: str, track_id: str) -> None:
        """
        供外部（TimelineCanvas 点击）调用：
        - 当 mode_id 非空：选中对应模式和其下的某条轨道
        - 当 mode_id 为空：选中某条全局轨道
        会触发自身的 modeChanged/trackChanged 信号，从而驱动 NodeListPanel 等更新。
        """
        mode_id = (mode_id or "").strip()
        track_id = (track_id or "").strip()

        if mode_id:
            # 选中模式
            for i in range(self._list_modes.count()):
                item = self._list_modes.item(i)
                val = item.data(Qt.UserRole)
                if isinstance(val, str) and val == mode_id:
                    self._list_modes.setCurrentItem(item)
                    break
            # 选中模式轨道
            if track_id:
                for i in range(self._list_tracks.count()):
                    item = self._list_tracks.item(i)
                    val = item.data(Qt.UserRole)
                    if isinstance(val, str) and val == track_id:
                        self._list_tracks.setCurrentItem(item)
                        break
        else:
            # 全局轨道
            if track_id:
                self._list_modes.clearSelection()
                for i in range(self._list_global.count()):
                    item = self._list_global.item(i)
                    val = item.data(Qt.UserRole)
                    if isinstance(val, str) and val == track_id:
                        self._list_global.setCurrentItem(item)
                        break

    # ---------- 内部：获取当前对象 ----------

    def _current_mode(self) -> Optional[Mode]:
        p = self._preset
        mid = self._current_mode_id
        if p is None or not mid:
            return None
        for m in p.modes:
            if m.id == mid:
                return m
        return None
        
    def _current_track(self) -> Optional[Track]:
        p = self._preset
        tid = self._current_track_id
        if p is None or not tid:
            return None

        if self._current_track_scope == "mode":
            m = self._current_mode()
            if m is None:
                return None
            for t in m.tracks:
                if t.id == tid:
                    return t
            return None

        # global scope
        for t in p.global_tracks:
            if t.id == tid:
                return t
        return None

    # ---------- 重建列表 ----------

    def _rebuild_modes(self) -> None:
        self._building = True
        try:
            self._list_modes.clear()
            p = self._preset
            if p is None:
                self._current_mode_id = None
                self.modeChanged.emit("")
                return
            for m in p.modes:
                item = QListWidgetItem(m.name or "(未命名)")
                item.setData(Qt.UserRole, m.id)
                self._list_modes.addItem(item)
        finally:
            self._building = False

        if self._list_modes.count() > 0:
            self._list_modes.setCurrentRow(0)
        else:
            self._current_mode_id = None
            self.modeChanged.emit("")

    def _rebuild_tracks(self) -> None:
        self._building = True
        try:
            self._list_tracks.clear()
            m = self._current_mode()
            if m is None:
                return
            for t in m.tracks:
                item = QListWidgetItem(t.name or "(未命名)")
                item.setData(Qt.UserRole, t.id)
                self._list_tracks.addItem(item)
        finally:
            self._building = False

    def _rebuild_global_tracks(self) -> None:
        self._building = True
        try:
            self._list_global.clear()
            p = self._preset
            if p is None:
                return
            for t in p.global_tracks:
                item = QListWidgetItem(t.name or "(未命名)")
                item.setData(Qt.UserRole, t.id)
                self._list_global.addItem(item)
        finally:
            self._building = False

    # ---------- 选择变化 ----------

    def _on_mode_selected(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if self._building:
            return
        if curr is None:
            self._current_mode_id = None
            self.modeChanged.emit("")
            self._rebuild_tracks()
            return
        mid = curr.data(Qt.UserRole)
        if not isinstance(mid, str):
            self._current_mode_id = None
            self.modeChanged.emit("")
            self._rebuild_tracks()
            return

        self._current_mode_id = mid
        self.modeChanged.emit(mid)

        self._rebuild_tracks()
        self._current_track_id = None
        self._current_track_scope = "mode"
        self.trackChanged.emit("")

        # 取消全局轨道选中
        self._list_global.blockSignals(True)
        self._list_global.clearSelection()
        self._list_global.blockSignals(False)

    def _on_track_selected(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if self._building:
            return
        if curr is None:
            if self._current_track_scope == "mode":
                self._current_track_id = None
                self.trackChanged.emit("")
            return

        tid = curr.data(Qt.UserRole)
        if not isinstance(tid, str):
            if self._current_track_scope == "mode":
                self._current_track_id = None
                self.trackChanged.emit("")
            return

        self._current_track_scope = "mode"
        self._current_track_id = tid
        self.trackChanged.emit(tid)

        # 取消全局轨道选中
        self._list_global.blockSignals(True)
        self._list_global.clearSelection()
        self._list_global.blockSignals(False)

    def _on_global_track_selected(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if self._building:
            return
        if curr is None:
            if self._current_track_scope == "global":
                self._current_track_id = None
                self.trackChanged.emit("")
            return

        tid = curr.data(Qt.UserRole)
        if not isinstance(tid, str):
            if self._current_track_scope == "global":
                self._current_track_id = None
                self.trackChanged.emit("")
            return

        self._current_track_scope = "global"
        self._current_track_id = tid
        # 选中全局轨道时，mode 视为“全局” => 传空字符串
        self._current_mode_id = None
        self.modeChanged.emit("")
        self.trackChanged.emit(tid)

        # 取消模式轨道选中
        self._list_tracks.blockSignals(True)
        self._list_tracks.clearSelection()
        self._list_tracks.blockSignals(False)

    # ---------- 模式操作 ----------

    def _on_add_mode(self) -> None:
        p = self._preset
        if p is None:
            self._notify.error("请先在“循环/轨道方案”页面创建一个方案")
            return

        name, ok = QInputDialog.getText(self, "新建模式", "模式名称：", text="新模式")
        if not ok:
            return
        nm = (name or "").strip() or "新模式"
        mid = uuid.uuid4().hex
        m = Mode(id=mid, name=nm, tracks=[])
        p.modes.append(m)
        self._mark_dirty()
        self._rebuild_modes()
        self.structureChanged.emit()

    def _on_rename_mode(self) -> None:
        m = self._current_mode()
        if m is None:
            self._notify.error("请先选择要重命名的模式")
            return
        name, ok = QInputDialog.getText(self, "重命名模式", "新名称：", text=m.name)
        if not ok:
            return
        nm = (name or "").strip()
        if not nm or nm == m.name:
            self._notify.status_msg("名称未变化", ttl_ms=1500)
            return
        m.name = nm
        self._mark_dirty()
        self._rebuild_modes()
        self.structureChanged.emit()

    def _on_delete_mode(self) -> None:
        p = self._preset
        m = self._current_mode()
        if p is None or m is None:
            self._notify.error("请先选择要删除的模式")
            return
        ok = QMessageBox.question(
            self,
            "删除模式",
            f"确认删除模式：{m.name} ？\n\n将删除该模式下的所有轨道和节点。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return
        before = len(p.modes)
        p.modes = [x for x in p.modes if x.id != m.id]
        if len(p.modes) != before:
            self._mark_dirty()
        self._rebuild_modes()
        self._rebuild_tracks()
        self.structureChanged.emit()

    # ---------- 模式轨道操作 ----------

    def _on_add_track(self) -> None:
        m = self._current_mode()
        if m is None:
            self._notify.error("请先选择一个模式")
            return
        name, ok = QInputDialog.getText(self, "新建轨道", "轨道名称：", text="新轨道")
        if not ok:
            return
        nm = (name or "").strip() or "新轨道"
        tid = uuid.uuid4().hex
        t = Track(id=tid, name=nm, nodes=[])
        m.tracks.append(t)
        self._mark_dirty()
        self._rebuild_tracks()
        self.structureChanged.emit()

    def _on_rename_track(self) -> None:
        if self._current_track_scope != "mode":
            self._notify.error("当前选中的不是模式轨道")
            return
        t = self._current_track()
        if t is None:
            self._notify.error("请先选择要重命名的模式轨道")
            return
        name, ok = QInputDialog.getText(self, "重命名轨道", "新名称：", text=t.name)
        if not ok:
            return
        nm = (name or "").strip()
        if not nm or nm == t.name:
            self._notify.status_msg("名称未变化", ttl_ms=1500)
            return
        t.name = nm
        self._mark_dirty()
        self._rebuild_tracks()
        self.structureChanged.emit()

    def _on_delete_track(self) -> None:
        if self._current_track_scope != "mode":
            self._notify.error("当前选中的不是模式轨道")
            return
        m = self._current_mode()
        t = self._current_track()
        if m is None or t is None:
            self._notify.error("请先选择要删除的模式轨道")
            return
        ok = QMessageBox.question(
            self,
            "删除轨道",
            f"确认删除轨道：{t.name} ？\n\n将删除该轨道中的所有节点。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return
        before = len(m.tracks)
        m.tracks = [x for x in m.tracks if x.id != t.id]
        if len(m.tracks) != before:
            self._mark_dirty()
        self._current_track_id = None
        self.trackChanged.emit("")
        self._rebuild_tracks()
        self.structureChanged.emit()

    # ---------- 全局轨道操作 ----------

    def _on_add_global_track(self) -> None:
        p = self._preset
        if p is None:
            self._notify.error("请先在“循环/轨道方案”页面创建一个方案")
            return
        name, ok = QInputDialog.getText(self, "新建全局轨道", "轨道名称：", text="全局轨道")
        if not ok:
            return
        nm = (name or "").strip() or "全局轨道"
        tid = uuid.uuid4().hex
        t = Track(id=tid, name=nm, nodes=[])
        p.global_tracks.append(t)
        self._mark_dirty()
        self._rebuild_global_tracks()
        self.structureChanged.emit()

    def _on_rename_global_track(self) -> None:
        if self._current_track_scope != "global":
            self._notify.error("当前选中的不是全局轨道")
            return
        t = self._current_track()
        if t is None:
            self._notify.error("请先选择要重命名的全局轨道")
            return
        name, ok = QInputDialog.getText(self, "重命名全局轨道", "新名称：", text=t.name)
        if not ok:
            return
        nm = (name or "").strip()
        if not nm or nm == t.name:
            self._notify.status_msg("名称未变化", ttl_ms=1500)
            return
        t.name = nm
        self._mark_dirty()
        self._rebuild_global_tracks()
        self.structureChanged.emit()

    def _on_delete_global_track(self) -> None:
        if self._current_track_scope != "global":
            self._notify.error("当前选中的不是全局轨道")
            return
        p = self._preset
        t = self._current_track()
        if p is None or t is None:
            self._notify.error("请先选择要删除的全局轨道")
            return
        ok = QMessageBox.question(
            self,
            "删除全局轨道",
            f"确认删除全局轨道：{t.name} ？\n\n将删除该轨道中的所有节点。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return
        before = len(p.global_tracks)
        p.global_tracks = [x for x in p.global_tracks if x.id != t.id]
        if len(p.global_tracks) != before:
            self._mark_dirty()
        self._current_track_id = None
        self.trackChanged.emit("")
        self._rebuild_global_tracks()
        self.structureChanged.emit()

    # ---------- 标记脏 ----------

    def _mark_dirty(self) -> None:
        try:
            self._mark_dirty_cb()
        except Exception:
            pass
    def select_location(self, mode_id: str, track_id: str) -> None:
        """
        供外部（TimelineCanvas 点击）调用：
        - mode_id 非空：选中对应模式及其下指定轨道
        - mode_id 为空：选中某条全局轨道
        会触发自身的 modeChanged/trackChanged 信号，从而驱动 NodeListPanel 等更新。
        """
        mode_id = (mode_id or "").strip()
        track_id = (track_id or "").strip()

        # 选中模式
        if mode_id:
            # 模式列表
            for i in range(self._list_modes.count()):
                item = self._list_modes.item(i)
                val = item.data(Qt.UserRole)
                if isinstance(val, str) and val == mode_id:
                    # 这会触发 _on_mode_selected，从而重建模式轨道列表
                    self._list_modes.setCurrentItem(item)
                    break

            # 选中该模式下的轨道
            if track_id:
                for i in range(self._list_tracks.count()):
                    item = self._list_tracks.item(i)
                    val = item.data(Qt.UserRole)
                    if isinstance(val, str) and val == track_id:
                        # 这会触发 _on_track_selected
                        self._list_tracks.setCurrentItem(item)
                        break

        else:
            # 全局轨道：清除模式选择，只选中全局轨道列表中的对应项
            self._list_modes.clearSelection()
            if track_id:
                for i in range(self._list_global.count()):
                    item = self._list_global.item(i)
                    val = item.data(Qt.UserRole)
                    if isinstance(val, str) and val == track_id:
                        # 这会触发 _on_global_track_selected
                        self._list_global.setCurrentItem(item)
                        break