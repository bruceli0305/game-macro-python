# rotation_editor/qt_editor_page.py
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QComboBox,
    QStyle,
    QMessageBox,
)

from core.profiles import ProfileContext
from core.store.app_store import AppStore

from qtui.notify import UiNotify
from qtui.icons import load_icon

from rotation_editor.core.services import RotationService
from rotation_editor.core.models import RotationPreset
from rotation_editor.ui.editor.mode_track_panel import ModeTrackPanel
from rotation_editor.ui.editor.node_panel import NodeListPanel


class RotationEditorPage(QWidget):
    """
    循环编辑器页（拆分版）：

    - 顶部：当前方案选择（preset 下拉） + 保存 / 重新加载 + 脏状态
    - 左侧：ModeTrackPanel（模式 + 轨道）
    - 右侧：NodeListPanel（节点列表）

    本类只负责：
      - 选择当前 preset
      - 将 preset 传给 ModeTrackPanel
      - 根据 ModeTrackPanel 的当前模式/轨道，通知 NodeListPanel
      - 触发 RotationService 的 save/reload
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        store: AppStore,
        notify: UiNotify,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._store = store
        self._notify = notify

        self._svc = RotationService(
            store=self._store,
            notify_dirty=self._on_service_dirty,
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )

        self._current_preset_id: Optional[str] = None
        self._building = False
        self._dirty_ui = False

        self._build_ui()
        self._subscribe_store_dirty()
        self._rebuild_preset_combo()
        self._select_first_preset_if_any()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 顶部：标题 + preset 下拉 + 保存/重载
        header = QHBoxLayout()
        lbl_title = QLabel("循环编辑器", self)
        f = lbl_title.font()
        f.setPointSize(16)
        f.setBold(True)
        lbl_title.setFont(f)
        header.addWidget(lbl_title)

        header.addSpacing(20)
        header.addWidget(QLabel("方案:", self))

        self._cmb_preset = QComboBox(self)
        self._cmb_preset.currentIndexChanged.connect(self._on_preset_changed)
        header.addWidget(self._cmb_preset, 1)

        header.addSpacing(10)

        style = self.style()
        icon_reload = load_icon("reload", style, QStyle.StandardPixmap.SP_BrowserReload)
        icon_save = load_icon("save", style, QStyle.StandardPixmap.SP_DialogSaveButton)

        self._btn_reload = QPushButton("重新加载", self)
        self._btn_reload.setIcon(icon_reload)
        self._btn_reload.clicked.connect(self._on_reload)
        header.addWidget(self._btn_reload)

        self._btn_save = QPushButton("保存", self)
        self._btn_save.setIcon(icon_save)
        self._btn_save.clicked.connect(self._on_save)
        header.addWidget(self._btn_save)

        header.addSpacing(10)
        self._lbl_dirty = QLabel("", self)
        header.addWidget(self._lbl_dirty)

        root.addLayout(header)

        # 中间：ModeTrackPanel + NodeListPanel
        splitter = QSplitter(Qt.Horizontal, self)
        root.addWidget(splitter, 1)

        # 左侧模式/轨道面板
        self._panel_mode_track = ModeTrackPanel(
            notify=self._notify,
            mark_dirty=self._mark_rotations_dirty,
            parent=self,
        )
        self._panel_mode_track.modeChanged.connect(self._on_mode_changed)
        self._panel_mode_track.trackChanged.connect(self._on_track_changed)
        splitter.addWidget(self._panel_mode_track)

        # 右侧节点面板
        self._panel_nodes = NodeListPanel(
            ctx=self._ctx,
            notify=self._notify,
            mark_dirty=self._mark_rotations_dirty,
            parent=self,
        )
        splitter.addWidget(self._panel_nodes)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([360, 740])

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
        # RotationService 内部 mark_dirty 后回调这里；
        # 实际 UI 更新仍然走 store.subscribe_dirty 通道。
        pass

    def _update_dirty_ui(self) -> None:
        self._lbl_dirty.setText("未保存*" if self._dirty_ui else "")
        if self._dirty_ui:
            self._btn_save.setStyleSheet("color: orange;")
        else:
            self._btn_save.setStyleSheet("")

    # ---------- 上下文切换 ----------

    def set_context(self, ctx: ProfileContext) -> None:
        """
        Profile 切换时调用。
        """
        self._ctx = ctx
        self._current_preset_id = None
        # 更新 NodeListPanel 的 ctx
        self._panel_nodes.set_context(self._ctx, preset=None)
        self._rebuild_preset_combo()
        self._select_first_preset_if_any()

    # ---------- preset 相关 ----------

    def _rebuild_preset_combo(self) -> None:
        self._building = True
        try:
            self._cmb_preset.clear()
            presets = self._svc.list_presets()
            for p in presets:
                self._cmb_preset.addItem(p.name or "(未命名)", userData=p.id)
        finally:
            self._building = False

    def _select_first_preset_if_any(self) -> None:
        if self._cmb_preset.count() == 0:
            self._current_preset_id = None
            self._panel_mode_track.set_preset(None)
            self._panel_nodes.set_context(self._ctx, preset=None)
            return
        self._cmb_preset.setCurrentIndex(0)
        self._on_preset_changed(0)

    def _current_preset(self) -> Optional[RotationPreset]:
        pid = self._current_preset_id
        if not pid:
            return None
        return self._svc.find_preset(pid)

    def _on_preset_changed(self, index: int) -> None:
        if self._building:
            return
        data = self._cmb_preset.currentData()
        if not isinstance(data, str):
            self._current_preset_id = None
            self._panel_mode_track.set_preset(None)
            self._panel_nodes.set_context(self._ctx, preset=None)
            return
        self._current_preset_id = data
        preset = self._current_preset()
        # 将 preset 传递给左右子面板
        self._panel_mode_track.set_preset(preset)
        self._panel_nodes.set_context(self._ctx, preset=preset)

    def set_current_preset(self, preset_id: str) -> None:
        """
        由外部调用：指定当前要编辑的方案 ID。
        - 会刷新 preset 下拉框
        - 将下拉框切换到对应方案
        - 触发子面板刷新
        """
        pid = (preset_id or "").strip()
        if not pid:
            return
        self._rebuild_preset_combo()
        for i in range(self._cmb_preset.count()):
            data = self._cmb_preset.itemData(i)
            if isinstance(data, str) and data == pid:
                self._cmb_preset.setCurrentIndex(i)
                break
        else:
            return
        self._current_preset_id = pid
        preset = self._current_preset()
        self._panel_mode_track.set_preset(preset)
        self._panel_nodes.set_context(self._ctx, preset=preset)

    # ---------- ModeTrackPanel 选中变化 ----------

    def _on_mode_changed(self, mode_id: str) -> None:
        # Mode 改变 -> 通知节点面板更新目标
        track_id = self._panel_mode_track.current_track_id()
        preset = self._current_preset()
        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mode_id, track_id)

    def _on_track_changed(self, track_id: str) -> None:
        mode_id = self._panel_mode_track.current_mode_id()
        preset = self._current_preset()
        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mode_id, track_id)

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
            self._rebuild_preset_combo()
            self._select_first_preset_if_any()
            self._notify.info("已重新加载循环配置")
        except Exception as e:
            self._notify.error("重新加载失败", detail=str(e))

    def _on_save(self) -> None:
        saved = self._svc.save_cmd()
        if saved:
            self._notify.info("rotation.json 已保存")
        else:
            self._notify.status_msg("没有需要保存的更改", ttl_ms=1500)

    # ---------- flush_to_model 提供给 UnsavedGuard ----------

    def flush_to_model(self) -> None:
        """
        当前所有编辑直接写入 ctx.rotations，无额外缓存，这里无需操作。
        放在接口上，方便未来有中间状态时统一 flush。
        """
        pass

    # ---------- 脏标记 ----------

    def _mark_rotations_dirty(self) -> None:
        try:
            self._store.mark_dirty("rotations")  # type: ignore[arg-type]
        except Exception:
            pass

    # ---------- end ----------