from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QStyle,
    QMessageBox,
    QMenu,
    QInputDialog,
)

from core.profiles import ProfileContext
from core.store.app_store import AppStore

from qtui.notify import UiNotify
from qtui.icons import load_icon

from rotation_editor.core.services.rotation_service import RotationService
from rotation_editor.core.services.rotation_edit_service import RotationEditService
from rotation_editor.core.models import RotationPreset
from rotation_editor.ui.editor.node_panel import NodeListPanel
from rotation_editor.ui.editor.timeline_canvas import TimelineCanvas
from rotation_editor.ui.editor.mode_bar import ModeTabBar


class RotationEditorPage(QWidget):
    """
    循环编辑器页：

    - 顶部：方案下拉 + 保存/重载 + 缩放控件 + 脏标记
    - 模式：ModeTabBar + 新增/重命名/删除模式
    - 中间：TimelineCanvas（全局 + 当前模式下轨道，含时间刻度线和网格）
    - NodeListPanel：隐藏逻辑组件，负责节点 CRUD / 条件编辑
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

        self._preset_svc = RotationService(
            store=self._store,
            notify_dirty=self._on_service_dirty,
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )
        self._edit_svc = RotationEditService(
            store=self._store,
            notify_dirty=None,
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )

        self._current_preset_id: Optional[str] = None
        self._current_mode_id: Optional[str] = None

        self._building = False
        self._dirty_ui = False

        self._build_ui()
        self._subscribe_store_dirty()
        self._rebuild_preset_combo()
        self._select_first_preset_if_any()

        self._update_zoom_label()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        style = self.style()

        # 顶部：标题 + preset 下拉 + 保存/重载 + 缩放控件 + 脏标记
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

        # 缩放控件 [-] 100% [+]
        header.addSpacing(10)
        self._btn_zoom_out = QPushButton("-", self)
        self._btn_zoom_out.setFixedWidth(26)
        self._btn_zoom_out.clicked.connect(self._on_zoom_out_clicked)
        header.addWidget(self._btn_zoom_out)

        self._lbl_zoom = QLabel("100%", self)
        self._lbl_zoom.setFixedWidth(48)
        self._lbl_zoom.setAlignment(Qt.AlignCenter)
        header.addWidget(self._lbl_zoom)

        self._btn_zoom_in = QPushButton("+", self)
        self._btn_zoom_in.setFixedWidth(26)
        self._btn_zoom_in.clicked.connect(self._on_zoom_in_clicked)
        header.addWidget(self._btn_zoom_in)

        header.addSpacing(4)
        self._btn_zoom_reset = QPushButton("1x", self)
        self._btn_zoom_reset.setFixedWidth(32)
        self._btn_zoom_reset.clicked.connect(self._on_zoom_reset_clicked)
        header.addWidget(self._btn_zoom_reset)

        header.addSpacing(10)
        self._lbl_dirty = QLabel("", self)
        header.addWidget(self._lbl_dirty)

        root.addLayout(header)

        # 模式操作行
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)

        mode_row.addWidget(QLabel("模式:", self))

        self._tab_modes = ModeTabBar(self)
        self._tab_modes.modeChanged.connect(self._on_mode_changed_from_tab)
        mode_row.addWidget(self._tab_modes, 1)

        self._btn_mode_add = QPushButton("新增模式", self)
        self._btn_mode_add.clicked.connect(self._on_mode_add_clicked)
        mode_row.addWidget(self._btn_mode_add)

        self._btn_mode_rename = QPushButton("重命名模式", self)
        self._btn_mode_rename.clicked.connect(self._on_mode_rename_clicked)
        mode_row.addWidget(self._btn_mode_rename)

        self._btn_mode_delete = QPushButton("删除模式", self)
        self._btn_mode_delete.clicked.connect(self._on_mode_delete_clicked)
        mode_row.addWidget(self._btn_mode_delete)

        root.addLayout(mode_row)

        # NodeListPanel：逻辑组件，不显示
        self._panel_nodes = NodeListPanel(
            ctx=self._ctx,
            edit_svc=self._edit_svc,
            notify=self._notify,
            parent=self,
        )
        self._panel_nodes.hide()

        # 时间轴画布
        self._timeline_canvas = TimelineCanvas(self)
        self._timeline_canvas.nodeClicked.connect(self._on_timeline_node_clicked)
        self._timeline_canvas.nodesReordered.connect(self._on_timeline_nodes_reordered)
        self._timeline_canvas.nodeCrossMoved.connect(self._on_timeline_node_moved_cross)
        self._timeline_canvas.nodeContextMenuRequested.connect(self._on_timeline_node_context_menu)
        self._timeline_canvas.trackContextMenuRequested.connect(self._on_timeline_track_context_menu)
        self._timeline_canvas.trackAddRequested.connect(self._on_timeline_track_add_requested)
        self._timeline_canvas.zoomChanged.connect(self._on_canvas_zoom_changed)

        root.addWidget(self._timeline_canvas, 1)

    # ---------- Store dirty ----------

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
        pass

    def _update_dirty_ui(self) -> None:
        self._lbl_dirty.setText("未保存*" if self._dirty_ui else "")
        self._btn_save.setStyleSheet("color: orange;" if self._dirty_ui else "")

    # ---------- 缩放 ----------

    def _on_canvas_zoom_changed(self) -> None:
        """
        TimelineCanvas 内部缩放变化（例如 Ctrl+滚轮）时调用：
        - 重绘时间轴
        - 更新缩放百分比显示
        """
        self._refresh_timeline()
        self._update_zoom_label()

    def _on_zoom_in_clicked(self) -> None:
        self._timeline_canvas.zoom_in()
        # zoomChanged 信号会触发 _on_canvas_zoom_changed

    def _on_zoom_out_clicked(self) -> None:
        self._timeline_canvas.zoom_out()
        # zoomChanged 信号会触发 _on_canvas_zoom_changed

    def _on_zoom_reset_clicked(self) -> None:
        self._timeline_canvas.reset_zoom()
        # zoomChanged 信号会触发 _on_canvas_zoom_changed

    def _update_zoom_label(self) -> None:
        ratio = self._timeline_canvas.zoom_ratio()
        pct = int(round(ratio * 100))
        self._lbl_zoom.setText(f"{pct:d}%")

    def _refresh_timeline(self) -> None:
        preset = self._current_preset()
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

    # ---------- 上下文切换 ----------

    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        self._current_preset_id = None
        self._current_mode_id = None

        self._panel_nodes.set_context(self._ctx, preset=None)
        self._panel_nodes.set_target(None, None)
        self._timeline_canvas.set_data(self._ctx, None, None)

        self._rebuild_preset_combo()
        self._select_first_preset_if_any()
        self._update_zoom_label()

    # ---------- preset 相关 ----------

    def _rebuild_preset_combo(self) -> None:
        self._building = True
        try:
            self._cmb_preset.clear()
            presets = self._preset_svc.list_presets()
            for p in presets:
                self._cmb_preset.addItem(p.name or "(未命名)", userData=p.id)
        finally:
            self._building = False

    def _select_first_preset_if_any(self) -> None:
        if self._cmb_preset.count() == 0:
            self._current_preset_id = None
            self._rebuild_mode_tabs()
            self._panel_nodes.set_context(self._ctx, preset=None)
            self._panel_nodes.set_target(None, None)
            self._timeline_canvas.set_data(self._ctx, None, None)
            return
        self._cmb_preset.setCurrentIndex(0)
        self._on_preset_changed(0)

    def _current_preset(self) -> Optional[RotationPreset]:
        pid = self._current_preset_id
        if not pid:
            return None
        return self._preset_svc.find_preset(pid)

    def _on_preset_changed(self, index: int) -> None:
        if self._building:
            return
        data = self._cmb_preset.currentData()
        if not isinstance(data, str):
            self._current_preset_id = None
            self._current_mode_id = None
            self._rebuild_mode_tabs()
            self._panel_nodes.set_context(self._ctx, preset=None)
            self._panel_nodes.set_target(None, None)
            self._timeline_canvas.set_data(self._ctx, None, None)
            return

        self._current_preset_id = data
        preset = self._current_preset()

        self._current_mode_id = None
        self._rebuild_mode_tabs()

        mode_id = self._tab_modes.current_mode_id()
        self._current_mode_id = mode_id or None

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(self._current_mode_id, None)
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)
        self._update_zoom_label()

    # ---------- 模式标签栏 ----------

    def _rebuild_mode_tabs(self) -> None:
        preset = self._current_preset()
        if preset is None:
            self._tab_modes.set_modes([], None)
            self._current_mode_id = None
            return

        self._tab_modes.set_modes(preset.modes or [], self._current_mode_id)
        self._current_mode_id = self._tab_modes.current_mode_id() or None

    def _on_mode_changed_from_tab(self, mode_id: str) -> None:
        preset = self._current_preset()
        if preset is None:
            self._current_mode_id = None
            self._timeline_canvas.set_data(self._ctx, None, None)
            self._panel_nodes.set_target(None, None)
            return

        self._current_mode_id = (mode_id or "").strip() or None

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(self._current_mode_id, None)
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

    def _on_mode_add_clicked(self) -> None:
        preset = self._current_preset()
        if preset is None:
            self._notify.error("请先在“循环/轨道方案”页面创建一个方案")
            return

        name, ok = QInputDialog.getText(self, "新建模式", "模式名称：", text="新模式")
        if not ok:
            return
        m = self._edit_svc.create_mode(preset, name)
        self._current_mode_id = m.id

        self._rebuild_mode_tabs()

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(m.id, None)
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

    def _on_mode_rename_clicked(self) -> None:
        preset = self._current_preset()
        if preset is None:
            return

        mid = self._tab_modes.current_mode_id()
        if not mid:
            self._notify.error("请先选择要重命名的模式")
            return

        name, ok = QInputDialog.getText(self, "重命名模式", "新名称：")
        if not ok:
            return

        changed = self._edit_svc.rename_mode(preset, mid, name)
        if not changed:
            self._notify.status_msg("名称未变化", ttl_ms=1500)
            return

        self._rebuild_mode_tabs()

    def _on_mode_delete_clicked(self) -> None:
        preset = self._current_preset()
        if preset is None:
            return

        mid = self._tab_modes.current_mode_id()
        if not mid:
            self._notify.error("请先选择要删除的模式")
            return
        mode = next((m for m in preset.modes if m.id == mid), None)
        if mode is None:
            return

        ok = QMessageBox.question(
            self,
            "删除模式",
            f"确认删除模式：{mode.name} ？\n\n将删除该模式下的所有轨道和节点。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        deleted = self._edit_svc.delete_mode(preset, mid)
        if not deleted:
            return

        self._current_mode_id = None
        self._rebuild_mode_tabs()

        mode_id = self._tab_modes.current_mode_id()
        self._current_mode_id = mode_id or None

        preset2 = self._current_preset()
        self._panel_nodes.set_context(self._ctx, preset=preset2)
        self._panel_nodes.set_target(self._current_mode_id, None)
        self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)

    # ---------- 轨道新增（来自画布“+”） ----------

    def _on_timeline_track_add_requested(self, mode_id: str) -> None:
        """
        处理画布左下角“+ 新增轨道”按钮：
        - mode_id 非空 => 在该模式下新增轨道
        - mode_id 为空 => 新增全局轨道
        """
        preset = self._current_preset()
        if preset is None:
            self._notify.error("请先在“循环/轨道方案”页面创建一个方案")
            return

        name, ok = QInputDialog.getText(self, "新建轨道", "轨道名称：", text="新轨道")
        if not ok:
            return

        mid = (mode_id or "").strip() or None
        track = self._edit_svc.create_track(
            preset=preset,
            mode_id=mid,
            name=name,
        )

        if mid:
            self._current_mode_id = mid
            self._tab_modes.blockSignals(True)
            try:
                for i in range(self._tab_modes.count()):
                    if self._tab_modes.tabData(i) == mid:
                        self._tab_modes.setCurrentIndex(i)
                        break
            finally:
                self._tab_modes.blockSignals(False)

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mid, track.id)
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

    # ---------- Timeline / NodeList 联动 ----------

    def _on_timeline_node_clicked(self, mode_id: str, track_id: str, node_index: int) -> None:
        preset = self._current_preset()
        if preset is None:
            return

        mode_id_s = (mode_id or "").strip()
        track_id_s = (track_id or "").strip()

        if mode_id_s:
            self._current_mode_id = mode_id_s
            self._tab_modes.blockSignals(True)
            try:
                for i in range(self._tab_modes.count()):
                    if self._tab_modes.tabData(i) == mode_id_s:
                        self._tab_modes.setCurrentIndex(i)
                        break
            finally:
                self._tab_modes.blockSignals(False)

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mode_id_s or None, track_id_s or None)
        self._panel_nodes.select_node_index(node_index)

    def _on_timeline_nodes_reordered(self, mode_id: str, track_id: str, node_ids: list) -> None:
        preset = self._current_preset()
        if preset is None or not node_ids:
            return

        mode_id_s = (mode_id or "").strip()
        track_id_s = (track_id or "").strip()

        changed = self._edit_svc.reorder_nodes_by_ids(
            preset=preset,
            mode_id=mode_id_s or None,
            track_id=track_id_s or None,
            node_ids=list(node_ids),
        )
        if not changed:
            return

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mode_id_s or None, track_id_s or None)
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

    def _on_timeline_node_moved_cross(
        self,
        src_mode_id: str,
        src_track_id: str,
        dst_mode_id: str,
        dst_track_id: str,
        dst_index: int,
        node_id: str,
    ) -> None:
        preset = self._current_preset()
        if preset is None:
            return

        moved = self._edit_svc.move_node_between_tracks(
            preset=preset,
            src_mode_id=src_mode_id or None,
            src_track_id=src_track_id or None,
            dst_mode_id=dst_mode_id or None,
            dst_track_id=dst_track_id or None,
            node_id=node_id,
            dst_index=int(dst_index),
        )
        if not moved:
            return

        dst_mid = (dst_mode_id or "").strip()
        if dst_mid:
            self._current_mode_id = dst_mid
            self._tab_modes.blockSignals(True)
            try:
                for i in range(self._tab_modes.count()):
                    if self._tab_modes.tabData(i) == dst_mid:
                        self._tab_modes.setCurrentIndex(i)
                        break
            finally:
                self._tab_modes.blockSignals(False)

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(dst_mid or None, dst_track_id or None)

        t = self._edit_svc.get_track(preset, dst_mid or None, dst_track_id or None)
        if t is not None:
            idx = -1
            for i, n in enumerate(t.nodes):
                if getattr(n, "id", "") == node_id:
                    idx = i
                    break
            if idx >= 0:
                self._panel_nodes.select_node_index(idx)

        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

    def _on_timeline_node_context_menu(
        self,
        mode_id: str,
        track_id: str,
        node_index: int,
        gx: int,
        gy: int,
    ) -> None:
        preset = self._current_preset()
        if preset is None:
            return

        mode_id_s = (mode_id or "").strip()
        track_id_s = (track_id or "").strip()

        if mode_id_s:
            self._current_mode_id = mode_id_s
            self._tab_modes.blockSignals(True)
            try:
                for i in range(self._tab_modes.count()):
                    if self._tab_modes.tabData(i) == mode_id_s:
                        self._tab_modes.setCurrentIndex(i)
                        break
            finally:
                self._tab_modes.blockSignals(False)

        try:
            self._panel_nodes.set_context(self._ctx, preset=preset)
            self._panel_nodes.set_target(mode_id_s or None, track_id_s or None)
            self._panel_nodes.select_node_index(node_index)
        except Exception:
            pass

        menu = QMenu(self)
        act_edit = menu.addAction("编辑节点属性...")
        act_cond = menu.addAction("设置条件...")
        act_del = menu.addAction("删除节点")

        pos = QPoint(int(gx), int(gy))
        action = menu.exec(pos)
        if action is None:
            return

        changed = False

        if action == act_edit:
            try:
                self._panel_nodes.edit_current_node()
                changed = True
            except Exception as e:
                self._notify.error("编辑节点失败", detail=str(e))
        elif action == act_del:
            try:
                self._panel_nodes.delete_current_node()
                changed = True
            except Exception as e:
                self._notify.error("删除节点失败", detail=str(e))
        elif action == act_cond:
            try:
                self._panel_nodes.set_condition_for_current()
                changed = False
            except Exception as e:
                self._notify.error("设置条件失败", detail=str(e))

        if changed:
            preset2 = self._current_preset()
            self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)

    def _on_timeline_track_context_menu(self, mode_id: str, track_id: str, gx: int, gy: int) -> None:
        preset = self._current_preset()
        if preset is None:
            return

        mode_id_s = (mode_id or "").strip()
        track_id_s = (track_id or "").strip()

        if mode_id_s:
            self._current_mode_id = mode_id_s
            self._tab_modes.blockSignals(True)
            try:
                for i in range(self._tab_modes.count()):
                    if self._tab_modes.tabData(i) == mode_id_s:
                        self._tab_modes.setCurrentIndex(i)
                        break
            finally:
                self._tab_modes.blockSignals(False)

        try:
            self._panel_nodes.set_context(self._ctx, preset=preset)
            self._panel_nodes.set_target(mode_id_s or None, track_id_s or None)
        except Exception:
            pass

        menu = QMenu(self)
        act_new_skill = menu.addAction("新增技能节点...")
        act_new_gw = menu.addAction("新增网关节点...")

        pos = QPoint(int(gx), int(gy))
        action = menu.exec(pos)
        if action is None:
            return

        try:
            if action == act_new_skill:
                self._panel_nodes.add_skill_node()
            elif action == act_new_gw:
                self._panel_nodes.add_gateway_node()
        except Exception as e:
            self._notify.error("新增节点失败", detail=str(e))
            return

        preset2 = self._current_preset()
        self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)

    # ---------- 保存 / 重载 ----------

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
            self._preset_svc.reload_cmd()
            self._rebuild_preset_combo()
            self._select_first_preset_if_any()
            self._notify.info("已重新加载循环配置")
        except Exception as e:
            self._notify.error("重新加载失败", detail=str(e))

    def _on_save(self) -> None:
        saved = self._preset_svc.save_cmd()
        if saved:
            self._notify.info("rotation.json 已保存")
        else:
            self._notify.status_msg("没有需要保存的更改", ttl_ms=1500)

    # ---------- flush_to_model ----------

    def flush_to_model(self) -> None:
        pass