from __future__ import annotations

from typing import Optional, Protocol, Callable

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
)
from rotation_editor.core.runtime.executor.skill_attempt import (
    SkillAttemptConfig,
    StartSignalConfig,
    CompleteSignalConfig,
)
from rotation_editor.core.runtime.executor.lock_policy import LockPolicyConfig

import logging  # 新增

log = logging.getLogger(__name__)  # 新增

class SchedulerLike(Protocol):
    """
    简单的调度器协议：
    - MacroEngine 只依赖一个 call_soon(fn) 方法
    - QtDispatcher / 其他实现只要提供同名方法即可作为 dispatcher 使用
    """
    def call_soon(self, fn: Callable[[], None]) -> None: ...

class RotationEditorPage(QWidget):
    """
    循环编辑器页 + 执行引擎控制（修复版）：
    - 保证 _on_start_clicked 等方法存在，避免 AttributeError
    - 新增轨道规则：
        1) 没有 mode 不允许新增轨道
        2) 有 mode 时：新增轨道只能选 全局 / 当前模式
    - 右键轨道菜单：增加“打开调试面板...”
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        session: ProfileSession,
        notify: UiNotify,
        dispatcher: SchedulerLike,
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
        self._engine: Optional[MacroEngine] = None   # <<< 这里改成 MacroEngineNew
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

        # 顶部：标题 + preset 下拉 + 引擎按钮 + 保存/重载 + 缩放 + 脏标记
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

        # 缩放控件
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

        # NodeListPanel（逻辑组件，不显示）
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
        self._timeline_canvas.stepChanged.connect(self._on_timeline_step_changed)
        self._timeline_canvas.zoomChanged.connect(self._on_canvas_zoom_changed)

        root.addWidget(self._timeline_canvas, 1)

    # ---------- Store dirty ----------

    def _subscribe_store_dirty(self) -> None:
        try:
            self._session.subscribe_dirty(self._on_store_dirty)
        except Exception:
            pass

    def _on_store_dirty(self, parts) -> None:
        """
        监听 ProfileSession.dirty 变化：
        - 更新“未保存*”指示
        - 若引擎正在运行，points/skills/rotations 变更时刷新 capture plan
        """
        try:
            parts_set = set(parts or [])
        except Exception:
            # 不应该发生，但如果 parts 不是可迭代，记录日志并降级为空集合
            log.exception("_on_store_dirty: unexpected parts value, treat as empty")
            parts_set = set()

        self._dirty_ui = "rotations" in parts_set
        self._update_dirty_ui()

        # points/skills/rotations 变更时，若引擎运行则重建 capture plan
        if self._engine is not None and self._engine.is_running():
            if any(p in parts_set for p in ("points", "skills", "rotations")):
                try:
                    self._engine.invalidate_capture_plan()
                except Exception:
                    # 记录异常，但不影响后续 UI 操作
                    log.exception("invalidate_capture_plan failed in _on_store_dirty")

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
            self._current_mode_id = None
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

    # ---------- 模式 tabs ----------

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

    # ---------- 模式 CRUD ----------

    def _on_mode_add_clicked(self) -> None:
        preset = self._current_preset()
        if preset is None:
            self._notify.error("请先创建一个方案")
            return

        name, ok = QInputDialog.getText(self, "新建模式", "模式名称：", text="新模式")
        if not ok:
            return

        m = self._edit_svc.create_mode(preset, name)
        self._current_mode_id = m.id
        self._rebuild_mode_tabs()

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(self._current_mode_id, None)
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

        preset2 = self._current_preset()
        self._panel_nodes.set_context(self._ctx, preset=preset2)
        self._panel_nodes.set_target(self._current_mode_id, None)
        self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)

    # ---------- 新增轨道：规则实现 ----------
    # 1) 没有 mode 不允许新增
    # 2) 有 mode 时，只允许 全局 / 当前模式（不允许选其它 mode）

    def _on_timeline_track_add_requested(self, mode_id: str) -> None:
        preset = self._current_preset()
        if preset is None:
            self._notify.error("请先创建一个方案")
            return

        modes = list(preset.modes or [])
        if not modes:
            self._notify.error("请先新增模式后再创建轨道")
            return

        preferred_mid = (mode_id or "").strip() or (self._current_mode_id or "").strip()
        if not preferred_mid:
            for m in modes:
                mid = (m.id or "").strip()
                if mid:
                    preferred_mid = mid
                    break
        if not preferred_mid:
            self._notify.error("模式 ID 无效：mode.id 不能为空")
            return

        mode_name = next((m.name or "" for m in modes if (m.id or "").strip() == preferred_mid), "") or "当前模式"

        scope_items = [f"仅当前模式：{mode_name}", "全局轨道"]
        choice, ok = QInputDialog.getItem(self, "新增轨道", "请选择新增到：", scope_items, 0, False)
        if not ok:
            return

        chosen_mid = preferred_mid if choice == scope_items[0] else None

        name, ok = QInputDialog.getText(self, "新建轨道", "轨道名称：", text="新轨道")
        if not ok:
            return

        track = self._edit_svc.create_track(preset=preset, mode_id=chosen_mid, name=name)
        if track is None:
            self._notify.error("新建轨道失败")
            return

        if chosen_mid:
            self._current_mode_id = chosen_mid
            self._tab_modes.blockSignals(True)
            try:
                for i in range(self._tab_modes.count()):
                    if self._tab_modes.tabData(i) == chosen_mid:
                        self._tab_modes.setCurrentIndex(i)
                        break
            finally:
                self._tab_modes.blockSignals(False)

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(chosen_mid, track.id)
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

    # ---------- Timeline 联动 ----------

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
        act_cond = menu.addAction("设置条件...") if is_gateway else None
        act_del = menu.addAction("删除节点")

        action = menu.exec(QPoint(int(gx), int(gy)))
        if action is None:
            return

        if action == act_edit:
            try:
                self._panel_nodes.edit_current_node()
                preset2 = self._current_preset()
                self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)
            except Exception as e:
                self._notify.error("编辑节点失败", detail=str(e))

        elif action == act_del:
            try:
                self._panel_nodes.delete_current_node()
                preset2 = self._current_preset()
                self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)
            except Exception as e:
                self._notify.error("删除节点失败", detail=str(e))

        elif act_cond is not None and action == act_cond:
            try:
                self._panel_nodes.set_condition_for_current()
                preset2 = self._current_preset()
                self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)
            except Exception as e:
                self._notify.error("设置条件失败", detail=str(e))

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
        menu.addSeparator()
        act_debug = menu.addAction("打开调试面板...")
        menu.addSeparator()
        act_del_track = menu.addAction("删除此轨道")

        action = menu.exec(QPoint(int(gx), int(gy)))
        if action is None:
            return

        if action == act_debug:
            try:
                from rotation_editor.ui.editor.debug_stats_dialog import DebugStatsDialog
            except Exception as e:
                self._notify.error("打开调试面板失败", detail=str(e))
                return

            eng = self._ensure_engine()

            def get_snapshot():
                try:
                    return eng.get_skill_stats_snapshot()  # type: ignore[attr-defined]
                except Exception:
                    return []

            def get_lock():
                try:
                    return bool(eng.is_cast_locked())  # type: ignore[attr-defined]
                except Exception:
                    return False

            dlg = DebugStatsDialog(get_snapshot=get_snapshot, get_lock_state=get_lock, parent=self)
            dlg.setAttribute(Qt.WA_DeleteOnClose, True)
            dlg.show()
            return

        if action == act_new_skill or action == act_new_gw:
            try:
                if action == act_new_skill:
                    self._panel_nodes.add_skill_node()
                else:
                    self._panel_nodes.add_gateway_node()
            except Exception as e:
                self._notify.error("新增节点失败", detail=str(e))
                return

            preset2 = self._current_preset()
            self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)
            return

        if action == act_del_track:
            if not track_id_s:
                self._notify.error("当前轨道没有有效 ID，无法删除")
                return

            t = self._edit_svc.get_track(preset, mode_id_s or None, track_id_s or None)
            t_name = t.name if (t is not None and getattr(t, "name", None)) else ""
            ok = QMessageBox.question(
                self,
                "删除轨道",
                f"确认删除轨道：{t_name or '(未命名轨道)'} ？\n\n该操作将删除此轨道上的所有节点。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ok != QMessageBox.Yes:
                return

            deleted = self._edit_svc.delete_track(preset=preset, mode_id=mode_id_s or None, track_id=track_id_s or None)
            if not deleted:
                self._notify.error("删除轨道失败：轨道不存在")
                return

            preset2 = self._current_preset()
            self._panel_nodes.set_context(self._ctx, preset=preset2)
            self._panel_nodes.set_target(mode_id_s or None, None)
            self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)
            self._notify.info("已删除轨道")
            return

    def _on_timeline_step_changed(self, mode_id: str, track_id: str, node_id: str, step_index: int) -> None:
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

        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)
        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mid, tid)

    # ---------- 保存 / 重载 ----------

    def _on_reload(self) -> None:
        if self._engine_running:
            self._notify.error("请先停止循环，再重新加载循环配置")
            return
        ok = QMessageBox.question(
            self,
            "重新加载",
            "将从磁盘重新加载 rotations，放弃当前未保存更改。\n\n确认继续？",
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
            self._notify.info("循环配置已保存")
        else:
            self._notify.status_msg("没有需要保存的更改", ttl_ms=1500)

    def flush_to_model(self) -> None:
        pass

    # ---------- 引擎控制 ----------
    def _ensure_engine(self) -> MacroEngine:
        """
        获取或创建执行引擎 (MacroEngine)：

        - 若已有引擎实例（无论是否在运行），则直接返回该实例；
        - 若尚未创建过，则按当前 ctx.base.exec / ctx.base.cast_bar 配置构造一个新的引擎。

        注意：
        - 为避免 UI（调试面板等）持有旧实例导致状态不同步，这里不再在“未运行时”自动重建引擎。
          若需要让新配置生效，可在未来显式实现“重建引擎”按钮。
        """
        # 修复点：只要已有 _engine，就一律复用，不再在 is_running()==False 时重建
        if self._engine is not None:
            return self._engine

        ex = getattr(self._ctx.base, "exec", None)
        cb = getattr(self._ctx.base, "cast_bar", None)

        def _get_int(name: str, default: int, lo: int = 0, hi: int = 10**9) -> int:
            try:
                v = int(getattr(ex, name, default) if ex is not None else default)
            except Exception:
                v = int(default)
            if v < lo:
                v = lo
            if v > hi:
                v = hi
            return v

        def _get_str(name: str, default: str) -> str:
            try:
                v = str(getattr(ex, name, default) if ex is not None else default)
            except Exception:
                v = default
            v = (v or "").strip()
            return v or default

        # gap / poll
        gap = _get_int("default_skill_gap_ms", 50, 0, 10**6)
        poll_not_ready = _get_int("poll_not_ready_ms", 50, 10, 10**6)

        # start signal mode
        start_mode = _get_str("start_signal_mode", "pixel").lower()
        if start_mode not in ("pixel", "cast_bar", "none"):
            start_mode = "pixel"

        start_timeout = _get_int("start_timeout_ms", 20, 1, 10**6)
        start_poll = _get_int("start_poll_ms", 10, 5, 10**6)
        max_retries = _get_int("max_retries", 3, 0, 1000)
        retry_gap = _get_int("retry_gap_ms", 30, 0, 10**6)

        # cast_bar settings for complete policy
        cb_mode = (getattr(cb, "mode", "timer") or "timer").strip().lower() if cb is not None else "timer"
        cb_point = (getattr(cb, "point_id", "") or "").strip() if cb is not None else ""
        try:
            cb_tol = int(getattr(cb, "tolerance", 15) or 15) if cb is not None else 15
        except Exception:
            cb_tol = 15
        cb_tol = max(0, min(255, cb_tol))

        try:
            cb_poll = int(getattr(cb, "poll_interval_ms", 30) or 30) if cb is not None else 30
        except Exception:
            cb_poll = 30
        cb_poll = max(10, min(1000, cb_poll))

        try:
            cb_factor = float(getattr(cb, "max_wait_factor", 1.5) or 1.5) if cb is not None else 1.5
        except Exception:
            cb_factor = 1.5
        if cb_factor < 0.1:
            cb_factor = 0.1
        if cb_factor > 10.0:
            cb_factor = 10.0

        # completion policy: bar -> require signal；否则 assume success
        if cb_mode == "bar" and cb_point:
            complete_policy = "REQUIRE_SIGNAL"
        else:
            complete_policy = "ASSUME_SUCCESS"

        attempt_cfg = SkillAttemptConfig(
            default_gap_ms=gap,
            poll_not_ready_ms=poll_not_ready,
            lock=LockPolicyConfig(
                policy="SKIP_AND_ADVANCE",
                wait_timeout_ms=300,
                wait_poll_ms=15,
                skip_delay_ms=poll_not_ready,
            ),
            start=StartSignalConfig(
                mode=start_mode,  # pixel/cast_bar/none
                timeout_ms=start_timeout,
                poll_ms=start_poll,
                max_retries=max_retries,
                retry_gap_ms=retry_gap,
                cast_bar_point_id=cb_point,
                cast_bar_tolerance=cb_tol,
            ),
            complete=CompleteSignalConfig(
                policy=complete_policy,  # ASSUME_SUCCESS / REQUIRE_SIGNAL
                poll_ms=cb_poll,
                max_wait_factor=cb_factor,
                cast_bar_point_id=cb_point,
                cast_bar_tolerance=cb_tol,
            ),
            sample_log_throttle_ms=80,
        )

        self._engine = MacroEngine(
            ctx=self._ctx,
            scheduler=self._dispatcher,
            callbacks=self,
            config=EngineConfig(
                poll_interval_ms=20,
                stop_on_error=True,
                gateway_poll_delay_ms=10,
            ),
            attempt_cfg=attempt_cfg,
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

        self._btn_pause.setText("继续" if paused else "暂停")

        self._cmb_preset.setEnabled(not running)
        self._btn_reload.setEnabled(not running)
        self._btn_save.setEnabled(not running)

        self._set_edit_enabled(not running)

    def _set_edit_enabled(self, enabled: bool) -> None:
        self._timeline_canvas.setEnabled(enabled)
        self._panel_nodes.setEnabled(enabled)
        self._btn_mode_add.setEnabled(enabled)
        self._btn_mode_rename.setEnabled(enabled)
        self._btn_mode_delete.setEnabled(enabled)

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
        self._timeline_canvas.set_current_node(None, "", -1)
        self._notify.status_msg(f"循环执行已停止: {reason}", ttl_ms=2500)

    def on_node_executed(self, cursor: ExecutionCursor, node) -> None:
        label = getattr(node, "label", "") or "(节点)"
        self._notify.status_msg(f"执行节点: {label}", ttl_ms=800)

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

        self._timeline_canvas.set_current_node(mode_id or None, track_id, idx)

    def on_error(self, msg: str, detail: str) -> None:
        self._notify.error(msg, detail=detail)

    # ---------- 热键接口 ----------

    def toggle_engine_via_hotkey(self) -> None:
        preset = self._current_preset()
        if preset is None:
            self._notify.error("请先在“循环编辑器”中选择一个方案")
            return

        if not self._engine_running:
            self._on_start_clicked()
        else:
            self._on_stop_clicked()