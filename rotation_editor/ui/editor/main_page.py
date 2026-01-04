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
from core.app.session import ProfileSession

from qtui.notify import UiNotify
from qtui.icons import load_icon

from rotation_editor.core.services.rotation_service import RotationService
from rotation_editor.core.services.rotation_edit_service import RotationEditService
from rotation_editor.core.models import RotationPreset, GatewayNode
from rotation_editor.ui.editor.node_panel import NodeListPanel
from rotation_editor.ui.editor.timeline_canvas import TimelineCanvas
from rotation_editor.ui.editor.mode_bar import ModeTabBar

from rotation_editor.core.runtime.engine import (
    MacroEngine,
    EngineConfig,
    ExecutionCursor,
    Scheduler,
)


class RotationEditorPage(QWidget):
    """
    循环编辑器页 + 执行引擎控制：

    - 顶部：方案下拉 + 开始 / 暂停 / 单步 / 停止 + 保存/重载 + 缩放控件 + 脏标记
    - 中间：TimelineCanvas
    - 引擎控制：
        * 开始：start()
        * 暂停 / 继续：pause() / resume()
        * 单步：step()（执行一轮调度迭代）
        * 停止：stop()
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        session: ProfileSession,
        notify: UiNotify,
        dispatcher: Scheduler,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._session = session
        self._notify = notify
        self._dispatcher = dispatcher

        self._preset_svc = RotationService(
            session=self._session,
            notify_dirty=self._on_service_dirty,
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )
        self._edit_svc = RotationEditService(
            session=self._session,
            notify_dirty=None,
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )

        self._current_preset_id: Optional[str] = None
        self._current_mode_id: Optional[str] = None

        self._building = False
        self._dirty_ui = False

        # 执行引擎
        self._engine: Optional[MacroEngine] = None
        self._engine_running: bool = False
        self._engine_paused: bool = False

        self._build_ui()
        self._subscribe_store_dirty()
        self._rebuild_preset_combo()
        self._select_first_preset_if_any()

        self._update_zoom_label()
        self._update_engine_buttons()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        style = self.style()

        # 顶部：标题 + preset 下拉 + 控制按钮 + 保存/重载 + 缩放控件 + 脏标记
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

        # 控制按钮：开始 / 暂停(继续) / 单步 / 停止
        self._btn_start = QPushButton("开始", self)
        self._btn_start.clicked.connect(self._on_start_clicked)
        header.addWidget(self._btn_start)

        self._btn_pause = QPushButton("暂停", self)
        self._btn_pause.clicked.connect(self._on_pause_clicked)
        header.addWidget(self._btn_pause)

        self._btn_step = QPushButton("单步", self)
        self._btn_step.clicked.connect(self._on_step_clicked)
        header.addWidget(self._btn_step)

        self._btn_stop = QPushButton("停止", self)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop_clicked)
        header.addWidget(self._btn_stop)

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
        self._timeline_canvas.stepChanged.connect(self._on_timeline_step_changed)  # 新增
        self._timeline_canvas.zoomChanged.connect(self._on_canvas_zoom_changed)

        root.addWidget(self._timeline_canvas, 1)

    # ---------- Store dirty ----------

    def _subscribe_store_dirty(self) -> None:
        try:
            self._session.subscribe_dirty(self._on_store_dirty)
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
        self._refresh_timeline()
        self._update_zoom_label()

    def _on_zoom_in_clicked(self) -> None:
        self._timeline_canvas.zoom_in()

    def _on_zoom_out_clicked(self) -> None:
        self._timeline_canvas.zoom_out()

    def _on_zoom_reset_clicked(self) -> None:
        self._timeline_canvas.reset_zoom()

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

        if self._engine is not None and self._engine.is_running():
            self._engine.stop("context_changed")

    # ---------- 外部：指定当前 preset ----------

    def set_current_preset(self, preset_id: str) -> None:
        pid = (preset_id or "").strip()
        if not pid:
            return
        for i in range(self._cmb_preset.count()):
            data = self._cmb_preset.itemData(i)
            if isinstance(data, str) and data == pid:
                self._cmb_preset.setCurrentIndex(i)
                return

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
        self._panel_nodes.set_target(mid, track.id if track else None)
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

        node = self._edit_svc.get_node(
            preset=preset,
            mode_id=mode_id_s or None,
            track_id=track_id_s or None,
            index=int(node_index),
        )
        is_gateway = isinstance(node, GatewayNode)

        menu = QMenu(self)
        act_edit = menu.addAction("编辑节点属性...")
        act_cond = None
        if is_gateway:
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

        elif act_cond is not None and action == act_cond:
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
        if self._engine_running:
            self._notify.error("请先停止循环，再重新加载循环配置")
            return

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
        if self._engine_running:
            self._notify.error("请先停止循环，再保存循环配置")
            return

        saved = self._preset_svc.save_cmd()
        if saved:
            self._notify.info("rotation.json 已保存")
        else:
            self._notify.status_msg("没有需要保存的更改", ttl_ms=1500)

    # ---------- flush_to_model ----------

    def flush_to_model(self) -> None:
        pass

    # ---------- 执行引擎：启动 / 暂停 / 单步 / 停止 ----------

    def _ensure_engine(self) -> MacroEngine:
        if self._engine is None:
            self._engine = MacroEngine(
                ctx=self._ctx,
                scheduler=self._dispatcher,
                callbacks=self,
                config=EngineConfig(),
            )
        return self._engine

    def _update_engine_buttons(self) -> None:
        running = bool(self._engine_running)
        paused = bool(self._engine_paused)
        has_preset = self._cmb_preset.count() > 0

        self._btn_start.setEnabled((not running) and has_preset)
        self._btn_stop.setEnabled(running)

        self._btn_pause.setEnabled(running)
        self._btn_step.setEnabled(running and paused)

        if paused:
            self._btn_pause.setText("继续")
        else:
            self._btn_pause.setText("暂停")

        # 运行时禁止切换方案 / 保存 / 重新加载
        self._cmb_preset.setEnabled(not running)
        self._btn_reload.setEnabled(not running)
        self._btn_save.setEnabled(not running)

    def _on_start_clicked(self) -> None:
        preset = self._current_preset()
        if preset is None:
            self._notify.error("请先选择一个方案再启动循环")
            return

        eng = self._ensure_engine()
        if eng.is_running():
            self._notify.status_msg("循环已在运行中", ttl_ms=1500)
            return

        try:
            eng.start(preset)
        except Exception as e:
            self._notify.error("启动循环失败", detail=str(e))

    def _on_pause_clicked(self) -> None:
        if self._engine is None or not self._engine_running:
            return

        if not self._engine_paused:
            self._engine.pause()
            self._engine_paused = True
            self._notify.status_msg("循环已暂停", ttl_ms=1500)
        else:
            self._engine.resume()
            self._engine_paused = False
            self._notify.status_msg("循环已继续", ttl_ms=1500)

        self._update_engine_buttons()

    def _on_step_clicked(self) -> None:
        if self._engine is None or not self._engine_running:
            return

        # 确保处于暂停状态
        self._engine.pause()
        self._engine_paused = True
        self._engine.step()
        self._notify.status_msg("单步执行一次", ttl_ms=1500)
        self._update_engine_buttons()

    def _on_stop_clicked(self) -> None:
        if self._engine is None or not self._engine.is_running():
            return
        try:
            self._engine.stop("user_stop")
        except Exception as e:
            self._notify.error("停止循环失败", detail=str(e))

    # ---------- 引擎回调 ----------

    def on_started(self, preset_id: str) -> None:
        self._engine_running = True
        self._engine_paused = False
        self._update_engine_buttons()
        self._notify.status_msg(f"循环执行已启动: {preset_id}", ttl_ms=2500)

    def on_stopped(self, reason: str) -> None:
        self._engine_running = False
        self._engine_paused = False
        self._update_engine_buttons()
        # 清除时间轴高亮
        self._timeline_canvas.set_current_node(None, "", -1)
        self._notify.status_msg(f"循环执行已停止: {reason}", ttl_ms=2500)

    def on_node_executed(self, cursor: ExecutionCursor, node) -> None:
        label = getattr(node, "label", "") or getattr(node, "name", "") or "(节点)"
        self._notify.status_msg(f"执行节点: {label}", ttl_ms=800)

        # 若执行发生在新的模式，则切换到该模式
        mode_id = cursor.mode_id or ""
        track_id = cursor.track_id
        idx = int(cursor.node_index)

        preset = self._current_preset()
        if preset is None:
            return

        if mode_id and mode_id != (self._current_mode_id or ""):
            self._current_mode_id = mode_id
            self._tab_modes.blockSignals(True)
            try:
                for i in range(self._tab_modes.count()):
                    if self._tab_modes.tabData(i) == mode_id:
                        self._tab_modes.setCurrentIndex(i)
                        break
            finally:
                self._tab_modes.blockSignals(False)

            self._panel_nodes.set_context(self._ctx, preset=preset)
            self._panel_nodes.set_target(mode_id, None)
            self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

        # 高亮当前执行节点（包含全局轨道；mode_id 为空字符串时表示全局）
        self._timeline_canvas.set_current_node(mode_id or None, track_id, idx)

    def on_error(self, msg: str, detail: str) -> None:
        self._notify.error(msg, detail=detail)
        
    def _on_timeline_step_changed(
        self,
        mode_id: str,
        track_id: str,
        node_id: str,
        step_index: int,
    ) -> None:
        """
        时间轴横向拖拽节点后，修改该节点的 step_index。
        - mode_id: "" 表示全局轨道
        """
        preset = self._current_preset()
        if preset is None:
            return

        mid = (mode_id or "").strip() or None
        tid = (track_id or "").strip() or None

        changed = self._edit_svc.set_node_step(
            preset=preset,
            mode_id=mid,
            track_id=tid,
            node_id=node_id or "",
            step_index=int(step_index),
        )
        if not changed:
            return

        # 重新渲染时间轴
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

        # NodeListPanel 也同步刷新（显示新的步骤值）
        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mid, tid)