# rotation_editor/ui/editor/main_page.py
from __future__ import annotations

from typing import Optional, List

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
    QTabWidget,
)

from core.profiles import ProfileContext
from core.store.app_store import AppStore

from qtui.notify import UiNotify
from qtui.icons import load_icon

from rotation_editor.core.services import RotationService
from rotation_editor.core.models import RotationPreset, Track
from rotation_editor.ui.editor.mode_track_panel import ModeTrackPanel
from rotation_editor.ui.editor.node_panel import NodeListPanel
from rotation_editor.ui.editor.timeline_canvas import TimelineCanvas


class RotationEditorPage(QWidget):
    """
    循环编辑器页（拆分版 + 多轨时间轴预览）：

    - 顶部：
        - 当前方案选择（preset 下拉）
        - 入口模式 / 入口轨道 下拉（决定 executor 从哪里开始）
        - 保存 / 重新加载 + 脏状态
    - 中间：左右分栏
        - 左侧：ModeTrackPanel（模式 + 模式轨道 + 全局轨道）
        - 右侧：TabWidget
            - Tab1：NodeListPanel（列表编辑）
            - Tab2：TimelineCanvas（多轨时间轴预览）

    当前版本：
      - 编辑操作仍在 Tab1（列表编辑）完成；
      - Tab2 只做整体时间轴预览，不做编辑。
      - 后续可以在 TimelineCanvas 上逐步加入拖拽编辑能力。
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
        self._current_mode_id_for_timeline: Optional[str] = None

        self._building = False
        self._building_entry = False
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

        # 顶部：标题 + preset 下拉 + 保存/重载 + 脏标记
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

        # 入口模式 / 入口轨道
        entry_row = QHBoxLayout()
        entry_row.setSpacing(6)

        entry_row.addWidget(QLabel("入口模式:", self))
        self._cmb_entry_mode = QComboBox(self)
        entry_row.addWidget(self._cmb_entry_mode, 1)

        entry_row.addSpacing(10)
        entry_row.addWidget(QLabel("入口轨道:", self))
        self._cmb_entry_track = QComboBox(self)
        entry_row.addWidget(self._cmb_entry_track, 1)

        root.addLayout(entry_row)

        self._cmb_entry_mode.currentIndexChanged.connect(self._on_entry_mode_changed)
        self._cmb_entry_track.currentIndexChanged.connect(self._on_entry_track_changed)

        # 中间：ModeTrackPanel + 右侧 Tab（列表编辑 / 时间轴预览）
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
        self._panel_mode_track.structureChanged.connect(self._on_structure_changed)
        splitter.addWidget(self._panel_mode_track)

        # 右侧 Tab：列表编辑 + 时间轴预览
        self._tabs = QTabWidget(self)

        # Tab1：NodeListPanel
        self._panel_nodes = NodeListPanel(
            ctx=self._ctx,
            notify=self._notify,
            mark_dirty=self._mark_rotations_dirty,
            parent=self,
        )
        self._tabs.addTab(self._panel_nodes, "列表编辑")

        # Tab2：TimelineCanvas
        self._timeline_canvas = TimelineCanvas(self)
        self._timeline_canvas.nodeClicked.connect(self._on_timeline_node_clicked)
        self._timeline_canvas.nodesReordered.connect(self._on_timeline_nodes_reordered)
        self._tabs.addTab(self._timeline_canvas, "时间轴预览")

        splitter.addWidget(self._tabs)

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
        self._current_mode_id_for_timeline = None

        # 更新子面板
        self._panel_nodes.set_context(self._ctx, preset=None)
        self._timeline_canvas.set_data(self._ctx, None, None)

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
            self._timeline_canvas.set_data(self._ctx, None, None)
            self._rebuild_entry_combos()
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
            self._timeline_canvas.set_data(self._ctx, None, None)
            self._rebuild_entry_combos()
            return

        self._current_preset_id = data
        preset = self._current_preset()
        self._panel_mode_track.set_preset(preset)
        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id_for_timeline)
        self._rebuild_entry_combos()

    def set_current_preset(self, preset_id: str) -> None:
        """
        由外部调用：指定当前要编辑的方案 ID。
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
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id_for_timeline)
        self._rebuild_entry_combos()

    # ---------- 入口模式 / 入口轨道 ----------

    def _rebuild_entry_combos(self) -> None:
        self._building_entry = True
        try:
            self._cmb_entry_mode.clear()
            self._cmb_entry_track.clear()

            preset = self._current_preset()
            if preset is None:
                self._cmb_entry_mode.setEnabled(False)
                self._cmb_entry_track.setEnabled(False)
                return

            self._cmb_entry_mode.setEnabled(True)
            self._cmb_entry_track.setEnabled(True)

            # 入口模式：第一个选项代表“全局”
            self._cmb_entry_mode.addItem("（全局）", userData="")

            for m in preset.modes:
                text = m.name or "(未命名)"
                self._cmb_entry_mode.addItem(text, userData=m.id or "")

            # 选中当前 entry_mode_id
            mode_id = preset.entry_mode_id or ""
            idx_mode = 0
            if mode_id:
                for i in range(self._cmb_entry_mode.count()):
                    data = self._cmb_entry_mode.itemData(i)
                    if isinstance(data, str) and data == mode_id:
                        idx_mode = i
                        break
            self._cmb_entry_mode.setCurrentIndex(idx_mode)

            # 再根据当前入口模式构建入口轨道列表
            self._rebuild_entry_track_combo()
        finally:
            self._building_entry = False

    def _rebuild_entry_track_combo(self) -> None:
        self._building_entry = True
        try:
            self._cmb_entry_track.clear()
            preset = self._current_preset()
            if preset is None:
                return

            data = self._cmb_entry_mode.currentData()
            mode_id = data if isinstance(data, str) else ""

            tracks: List[Track] = []
            if mode_id:
                # 某个模式下的轨道
                m = next((m for m in preset.modes if m.id == mode_id), None)
                if m is not None:
                    tracks = m.tracks or []
            else:
                # 全局轨道
                tracks = preset.global_tracks or []

            for t in tracks:
                text = t.name or "(未命名)"
                self._cmb_entry_track.addItem(text, userData=t.id or "")

            # 根据 preset.entry_track_id 选中入口轨道（仅在同一模式/全局下匹配）
            tid = preset.entry_track_id or ""
            idx_track = 0
            if tid and self._cmb_entry_track.count() > 0:
                for i in range(self._cmb_entry_track.count()):
                    data = self._cmb_entry_track.itemData(i)
                    if isinstance(data, str) and data == tid:
                        idx_track = i
                        break
            if self._cmb_entry_track.count() > 0:
                self._cmb_entry_track.setCurrentIndex(idx_track)
        finally:
            self._building_entry = False

    def _on_entry_mode_changed(self, index: int) -> None:
        if self._building_entry:
            return
        preset = self._current_preset()
        if preset is None:
            return

        data = self._cmb_entry_mode.itemData(index)
        mode_id = data if isinstance(data, str) else ""

        preset.entry_mode_id = mode_id
        self._rebuild_entry_track_combo()
        self._mark_rotations_dirty()

    def _on_entry_track_changed(self, index: int) -> None:
        if self._building_entry:
            return
        preset = self._current_preset()
        if preset is None:
            return

        if self._cmb_entry_track.count() == 0:
            preset.entry_track_id = ""
            self._mark_rotations_dirty()
            return

        data = self._cmb_entry_track.itemData(index)
        tid = data if isinstance(data, str) else ""
        preset.entry_track_id = tid
        self._mark_rotations_dirty()

    # ---------- ModeTrackPanel 选中 / 结构变化 ----------

    def _on_mode_changed(self, mode_id: str) -> None:
        """
        Mode 改变 -> 通知节点面板更新目标 + 刷新时间轴。
        """
        self._current_mode_id_for_timeline = mode_id or None
        track_id = self._panel_mode_track.current_track_id()
        preset = self._current_preset()
        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mode_id, track_id)
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id_for_timeline)

    def _on_track_changed(self, track_id: str) -> None:
        mode_id = self._panel_mode_track.current_mode_id()
        preset = self._current_preset()
        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mode_id, track_id)
        # 轨道改变不影响大图结构，只影响 NodeListPanel，时间轴保持当前 mode 视图

    def _on_structure_changed(self) -> None:
        """
        模式/轨道结构发生变化（新增/删除/重命名），需要刷新入口下拉和时间轴。
        """
        preset = self._current_preset()
        self._rebuild_entry_combos()
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id_for_timeline)

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

    def select_node_index(self, index: int) -> None:
        """
        供外部调用：根据索引选中当前轨道上的某个节点。
        """
        if index < 0 or index >= self._tree.topLevelItemCount():
            return
        item = self._tree.topLevelItem(index)
        if item is not None:
            self._tree.setCurrentItem(item)

    def _on_timeline_node_clicked(self, mode_id: str, track_id: str, node_index: int) -> None:
        """
        时间轴上点击某个节点块时：
        - 左侧 ModeTrackPanel 选中对应模式/轨道
        - 右侧 NodeListPanel 选中对应节点
        """
        preset = self._current_preset()
        if preset is None:
            return

        # 更新左侧模式/轨道选中（会触发 modeChanged/trackChanged，从而驱动 NodeListPanel 切换轨道）
        try:
            self._panel_mode_track.select_location(mode_id, track_id)
        except Exception:
            pass

        # 记录当前用于时间轴的模式 ID（方便下次 set_data）
        self._current_mode_id_for_timeline = (mode_id or None)

        # 选中右侧列表中的指定节点
        try:
            self._panel_nodes.select_node_index(node_index)
        except Exception:
            pass
    def _on_timeline_node_clicked(self, mode_id: str, track_id: str, node_index: int) -> None:
        """
        时间轴上点击某个节点块时：
        - 左侧 ModeTrackPanel 选中对应模式/轨道
        - 右侧 NodeListPanel 选中对应节点
        - 记录当前模式用于下一次时间轴刷新
        """
        preset = self._current_preset()
        if preset is None:
            return

        # 选中左侧模式/轨道（会触发 modeChanged/trackChanged，从而驱动 NodeListPanel 切换轨道）
        try:
            self._panel_mode_track.select_location(mode_id, track_id)
        except Exception:
            pass

        # 更新当前用于时间轴的模式 ID（下次 set_data 用）
        self._current_mode_id_for_timeline = mode_id or None

        # 选中右侧列表中的指定节点
        try:
            self._panel_nodes.select_node_index(node_index)
        except Exception:
            pass
    def _on_timeline_nodes_reordered(self, mode_id: str, track_id: str, node_ids: list) -> None:
        """
        时间轴上某条轨道被拖拽重排后：
        - 根据 node_ids 的顺序重建 Track.nodes
        - 标记 rotations 脏
        - 刷新 NodeListPanel + TimelineCanvas
        """
        preset = self._current_preset()
        if preset is None or not node_ids:
            return

        # 找到对应 Track
        mode_id = (mode_id or "").strip()
        track_id = (track_id or "").strip()
        track: Optional[Track] = None

        if mode_id:
            # 模式轨道
            mode = next((m for m in preset.modes if m.id == mode_id), None)
            if mode is not None:
                track = next((t for t in mode.tracks if t.id == track_id), None)
        else:
            # 全局轨道
            track = next((t for t in preset.global_tracks if t.id == track_id), None)

        if track is None:
            return

        # 根据 node_ids 重排 nodes
        id2node = {getattr(n, "id", ""): n for n in track.nodes}
        new_nodes = []
        for nid in node_ids:
            n = id2node.get(nid)
            if n is not None:
                new_nodes.append(n)

        # 若有剩余（不在 node_ids 里），依原顺序追加（理论上不会发生）
        for n in track.nodes:
            if n not in new_nodes:
                new_nodes.append(n)

        track.nodes = new_nodes

        # 标记脏并刷新列表+时间轴
        self._mark_rotations_dirty()
        # 刷新 NodeListPanel
        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(self._panel_mode_track.current_mode_id(), track_id)
        # 刷新时间轴
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id_for_timeline)