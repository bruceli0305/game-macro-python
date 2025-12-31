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
    左侧“模式 + 轨道”子面板：

    - set_preset(preset): 绑定当前正在编辑的 RotationPreset
    - 内部管理：
        - 模式列表：新增 / 重命名 / 删除
        - 轨道列表：新增 / 重命名 / 删除
    - 通过 Qt 信号 modeChanged / trackChanged 将当前选中 ID 通知外部

    注意：本组件直接修改传入的 RotationPreset 对象（dataclass），
          外部需要通过 mark_dirty 回调标记 AppStore 的 "rotations" 为脏。
    """

    modeChanged = Signal(str)   # 当前模式 ID（空串表示无选中）
    trackChanged = Signal(str)  # 当前轨道 ID（空串表示无选中）

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
        self._building = False

        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        style = self.style()

        # 模式
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

        # 轨道
        lbl_tracks = QLabel("轨道 (Tracks):", self)
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

    # ---------- 外部 API ----------

    def set_preset(self, preset: Optional[RotationPreset]) -> None:
        """
        绑定当前正在编辑的 preset。
        会刷新模式/轨道列表，并重置选中。
        """
        self._preset = preset
        self._current_mode_id = None
        self._current_track_id = None
        self._rebuild_modes()
        self._rebuild_tracks()

    def current_mode_id(self) -> Optional[str]:
        return self._current_mode_id

    def current_track_id(self) -> Optional[str]:
        return self._current_track_id

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
        m = self._current_mode()
        tid = self._current_track_id
        if m is None or not tid:
            return None
        for t in m.tracks:
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

        # 自动选中第一个
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
                self._current_track_id = None
                self.trackChanged.emit("")
                return
            for t in m.tracks:
                item = QListWidgetItem(t.name or "(未命名)")
                item.setData(Qt.UserRole, t.id)
                self._list_tracks.addItem(item)
        finally:
            self._building = False

        if self._list_tracks.count() > 0:
            self._list_tracks.setCurrentRow(0)
        else:
            self._current_track_id = None
            self.trackChanged.emit("")

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
        # 模式变更后，轨道列表重建
        self._current_track_id = None
        self._rebuild_tracks()

    def _on_track_selected(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if self._building:
            return
        if curr is None:
            self._current_track_id = None
            self.trackChanged.emit("")
            return
        tid = curr.data(Qt.UserRole)
        if not isinstance(tid, str):
            self._current_track_id = None
            self.trackChanged.emit("")
            return
        self._current_track_id = tid
        self.trackChanged.emit(tid)

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

    # ---------- 轨道操作 ----------

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

    def _on_rename_track(self) -> None:
        t = self._current_track()
        if t is None:
            self._notify.error("请先选择要重命名的轨道")
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

    def _on_delete_track(self) -> None:
        m = self._current_mode()
        t = self._current_track()
        if m is None or t is None:
            self._notify.error("请先选择要删除的轨道")
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
        self._rebuild_tracks()

    # ---------- 标记脏 ----------

    def _mark_dirty(self) -> None:
        try:
            self._mark_dirty_cb()
        except Exception:
            pass