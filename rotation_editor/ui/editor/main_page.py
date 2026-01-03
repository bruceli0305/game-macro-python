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
from rotation_editor.core.models import RotationPreset, Track, Mode
from rotation_editor.ui.editor.node_panel import NodeListPanel
from rotation_editor.ui.editor.timeline_canvas import TimelineCanvas
from rotation_editor.ui.editor.mode_bar import ModeTabBar


class RotationEditorPage(QWidget):
    """
    循环编辑器页：

    布局：
    - 顶部：方案下拉 + 保存/重载 + 脏标记
    - 下一行：模式标签栏 [模式A][模式B]... + 新增/重命名/删除 按钮
    - 中间：TimelineCanvas（多轨时间轴预览 + 编辑）

    说明：
    - 模式通过 ModeTabBar 管理，对应 RotationPreset.modes。
    - TimelineCanvas 显示：
        - 全局轨道（global_tracks）
        - 当前模式下的所有轨道
    - NodeListPanel 仅作为逻辑协助（不加入布局），负责节点 CRUD / 条件编辑等。
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

        # preset 级服务（新增/删除/重命名方案 & 保存/重载）
        self._preset_svc = RotationService(
            store=self._store,
            notify_dirty=self._on_service_dirty,
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )
        # 轨道/节点编辑服务
        self._edit_svc = RotationEditService(
            store=self._store,
            notify_dirty=None,  # store.mark_dirty 已触发 subscribe_dirty
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )

        self._current_preset_id: Optional[str] = None
        self._current_mode_id: Optional[str] = None  # 当前模式 ID；None => 仅显示全局轨道

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

        style = self.style()

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

        # 模式标签栏
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)

        mode_row.addWidget(QLabel("模式:", self))

        self._tab_modes = ModeTabBar(self)
        self._tab_modes.modeChanged.connect(self._on_mode_changed_from_tab)
        mode_row.addWidget(self._tab_modes, 1)

        self._btn_mode_add = QPushButton("新增", self)
        self._btn_mode_add.clicked.connect(self._on_mode_add_clicked)
        mode_row.addWidget(self._btn_mode_add)

        self._btn_mode_rename = QPushButton("重命名", self)
        self._btn_mode_rename.clicked.connect(self._on_mode_rename_clicked)
        mode_row.addWidget(self._btn_mode_rename)

        self._btn_mode_delete = QPushButton("删除", self)
        self._btn_mode_delete.clicked.connect(self._on_mode_delete_clicked)
        mode_row.addWidget(self._btn_mode_delete)

        root.addLayout(mode_row)

        # 中间：仅 TimelineCanvas
        # NodeListPanel 仅作逻辑，不显示
        self._panel_nodes = NodeListPanel(
            ctx=self._ctx,
            edit_svc=self._edit_svc,
            notify=self._notify,
            parent=self,
        )
        self._panel_nodes.hide()

        self._timeline_canvas = TimelineCanvas(self)
        self._timeline_canvas.nodeClicked.connect(self._on_timeline_node_clicked)
        self._timeline_canvas.nodesReordered.connect(self._on_timeline_nodes_reordered)
        self._timeline_canvas.nodeContextMenuRequested.connect(self._on_timeline_node_context_menu)
        self._timeline_canvas.trackContextMenuRequested.connect(self._on_timeline_track_context_menu)

        root.addWidget(self._timeline_canvas, 1)

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
        self._current_mode_id = None

        self._panel_nodes.set_context(self._ctx, preset=None)
        self._panel_nodes.set_target(None, None)
        self._timeline_canvas.set_data(self._ctx, None, None)

        self._rebuild_preset_combo()
        self._select_first_preset_if_any()

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

        # 切换 preset 时，当前模式清空，由 _rebuild_mode_tabs 选出第一个
        self._current_mode_id = None
        self._rebuild_mode_tabs()

        mode_id = self._tab_modes.current_mode_id()
        self._current_mode_id = mode_id or None

        self._panel_nodes.set_context(self._ctx, preset=preset)
        self._panel_nodes.set_target(mode_id or None, None)
        self._timeline_canvas.set_data(self._ctx, preset, self._current_mode_id)

    # ---------- 模式标签栏 ----------

    def _rebuild_mode_tabs(self) -> None:
        """
        使用 ModeTabBar 管理模式标签。
        """
        preset = self._current_preset()
        if preset is None:
            self._tab_modes.set_modes([], None)
            self._current_mode_id = None
            return

        self._tab_modes.set_modes(preset.modes or [], self._current_mode_id)
        self._current_mode_id = self._tab_modes.current_mode_id() or None

    def _on_mode_changed_from_tab(self, mode_id: str) -> None:
        """
        ModeTabBar 发出的模式切换信号。
        """
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
        nm = (name or "").strip() or "新模式"

        m = self._edit_svc.create_mode(preset, nm)
        self._current_mode_id = m.id

        self._rebuild_mode_tabs()

        # 刷新 NodeListPanel & 时间轴
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
        mode = next((m for m in preset.modes if m.id == mid), None)
        if mode is None:
            return

        name, ok = QInputDialog.getText(self, "重命名模式", "新名称：", text=mode.name)
        if not ok:
            return
        nm = (name or "").strip()
        if not nm or nm == mode.name:
            self._notify.status_msg("名称未变化", ttl_ms=1500)
            return

        changed = self._edit_svc.rename_mode(preset, mid, nm)
        if not changed:
            return

        self._rebuild_mode_tabs()
        # 名称变化只影响标签，不影响 NodeListPanel / 时间轴结构

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

        # 重新构建 Tab，并更新当前模式
        self._current_mode_id = None
        self._rebuild_mode_tabs()

        mode_id = self._tab_modes.current_mode_id()
        self._current_mode_id = mode_id or None

        preset2 = self._current_preset()
        self._panel_nodes.set_context(self._ctx, preset=preset2)
        self._panel_nodes.set_target(self._current_mode_id, None)
        self._timeline_canvas.set_data(self._ctx, preset2, self._current_mode_id)
    # ---------- Timeline / NodeList 联动 ----------

    def _on_timeline_node_clicked(self, mode_id: str, track_id: str, node_index: int) -> None:
        """
        时间轴上左键点击节点块：
        - 如有 mode_id，则同步当前模式标签
        - NodeListPanel 切到对应轨道并选中该节点
        """
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
        """
        时间轴上某条轨道被拖拽重排后：
        - 调用 RotationEditService.reorder_nodes_by_ids 重建 Track.nodes
        - 刷新 NodeListPanel + TimelineCanvas
        """
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

    def _on_timeline_node_context_menu(
        self,
        mode_id: str,
        track_id: str,
        node_index: int,
        gx: int,
        gy: int,
    ) -> None:
        """
        时间轴上右键点击节点：
        - 切换到对应模式（如有）
        - NodeListPanel 切到该轨道并选中节点
        - 弹出菜单：编辑节点属性 / 设置条件 / 删除
        - 有改变时刷新时间轴
        """
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
        """
        时间轴轨道空白处右键：
        - 若有 mode_id，则同步当前模式
        - NodeListPanel 切到该轨道
        - 弹出菜单：新增技能节点 / 新增网关节点
        """
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
        """
        当前所有编辑直接写入 ctx.rotations，无额外缓存，这里无需操作。
        放在接口上，方便未来有中间状态时统一 flush。
        """
        pass

    # ---------- 标记脏（已由服务统一处理） ----------

    def _mark_rotations_dirty(self) -> None:
        """
        以前用于 UI 直接标记 store.dirty('rotations')。
        现在 RotationEditService/RotationService 已统一调用 mark_dirty，
        此方法只保留兼容接口，不再使用。
        """
        try:
            self._store.mark_dirty("rotations")  # type: ignore[arg-type]
        except Exception:
            pass