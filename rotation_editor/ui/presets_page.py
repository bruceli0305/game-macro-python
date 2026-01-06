from __future__ import annotations

from typing import Optional, Callable, List

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
    QComboBox,
    QSizePolicy,
    QSpinBox,
)

from core.profiles import ProfileContext
from core.app.session import ProfileSession
from qtui.notify import UiNotify
from qtui.icons import load_icon

from rotation_editor.core.services.rotation_service import RotationService
from rotation_editor.core.models import RotationPreset
from rotation_editor.core.services.validation_service import ValidationService


class RotationPresetsPage(QWidget):
    """
    轨道方案管理页（MVP）：

    - 左侧：方案列表（RotationPreset）
    - 右侧：当前选中方案的名称/描述/入口模式/入口轨道编辑
    - 右侧额外有：
        * “编辑此方案...”按钮：切换到循环编辑器页
        * “检查引用”按钮：检查 skill/point 引用是否缺失
        * “最大执行节点数 / 最长运行时间” 安全限制配置
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        session: ProfileSession,
        notify: UiNotify,
        open_editor: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._session = session
        self._notify = notify
        self._open_editor = open_editor

        self._svc = RotationService(
            session=self._session,
            notify_dirty=self._on_service_dirty,
            notify_error=lambda m, d="": self._notify.error(m, detail=d),
        )

        # 新增：统一校验器（包含引用检查 + 入口/网关/expr 校验）
        self._validator = ValidationService()

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

        splitter = QSplitter(Qt.Horizontal, self)
        root.addWidget(splitter, 1)

        # 左侧：列表 + 按钮
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        style = self.style()

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)

        icon_add = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_copy = load_icon("copy", style, QStyle.StandardPixmap.SP_DirLinkIcon)
        icon_rename = load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogDetailedView)
        icon_del = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        self._btn_new = QPushButton("新建", self)
        self._btn_new.setIcon(icon_add)
        self._btn_new.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(self._btn_new)

        self._btn_copy = QPushButton("复制", self)
        self._btn_copy.setIcon(icon_copy)
        self._btn_copy.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._btn_copy.clicked.connect(self._on_copy)
        btn_row.addWidget(self._btn_copy)

        self._btn_rename = QPushButton("重命名", self)
        self._btn_rename.setIcon(icon_rename)
        self._btn_rename.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._btn_rename.clicked.connect(self._on_rename)
        btn_row.addWidget(self._btn_rename)

        self._btn_delete = QPushButton("删除", self)
        self._btn_delete.setIcon(icon_del)
        self._btn_delete.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_delete)

        btn_row.addStretch(1)
        left_layout.addLayout(btn_row)

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

        # 名称
        form_row1 = QHBoxLayout()
        lbl_name = QLabel("名称:", right)
        self._edit_name = QLineEdit(right)
        form_row1.addWidget(lbl_name)
        form_row1.addWidget(self._edit_name, 1)
        right_layout.addLayout(form_row1)

        # 描述
        lbl_desc = QLabel("描述:", right)
        right_layout.addWidget(lbl_desc)
        self._edit_desc = QTextEdit(right)
        self._edit_desc.setPlaceholderText("方案用途、备注等...")
        right_layout.addWidget(self._edit_desc, 1)

        # 入口模式
        row_entry_mode = QHBoxLayout()
        row_entry_mode.addWidget(QLabel("入口模式:", right))
        self._cmb_entry_mode = QComboBox(right)
        row_entry_mode.addWidget(self._cmb_entry_mode, 1)
        right_layout.addLayout(row_entry_mode)

        # 入口轨道
        row_entry_track = QHBoxLayout()
        row_entry_track.addWidget(QLabel("入口轨道:", right))
        self._cmb_entry_track = QComboBox(right)
        row_entry_track.addWidget(self._cmb_entry_track, 1)
        right_layout.addLayout(row_entry_track)

        # 入口节点（新增）
        row_entry_node = QHBoxLayout()
        row_entry_node.addWidget(QLabel("入口节点:", right))
        self._cmb_entry_node = QComboBox(right)
        row_entry_node.addWidget(self._cmb_entry_node, 1)
        right_layout.addLayout(row_entry_node)

        # 安全限制
        row_max_exec = QHBoxLayout()
        row_max_exec.addWidget(QLabel("最大执行节点数(0=无限):", right))
        self._spin_max_exec_nodes = QSpinBox(right)
        self._spin_max_exec_nodes.setRange(0, 10**9)
        self._spin_max_exec_nodes.setSingleStep(100)
        row_max_exec.addWidget(self._spin_max_exec_nodes)
        right_layout.addLayout(row_max_exec)

        row_max_time = QHBoxLayout()
        row_max_time.addWidget(QLabel("最长运行时间(秒,0=无限):", right))
        self._spin_max_run_secs = QSpinBox(right)
        self._spin_max_run_secs.setRange(0, 10**7)
        self._spin_max_run_secs.setSingleStep(10)
        row_max_time.addWidget(self._spin_max_run_secs)
        right_layout.addLayout(row_max_time)

        # 编辑 & 检查引用
        action_row = QHBoxLayout()

        self._btn_edit = QPushButton("编辑此方案...", right)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_edit.setEnabled(False)
        action_row.addWidget(self._btn_edit)

        self._btn_check_refs = QPushButton("检查引用", right)
        self._btn_check_refs.clicked.connect(self._on_check_refs)
        action_row.addWidget(self._btn_check_refs)

        action_row.addStretch(1)
        right_layout.addLayout(action_row)

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
        splitter.setStretchFactor(1, 2)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([600, 400])

        # 表单变更 -> 写回模型
        self._edit_name.textChanged.connect(self._on_form_changed)
        self._edit_desc.textChanged.connect(self._on_form_changed)
        self._cmb_entry_mode.currentIndexChanged.connect(self._on_entry_mode_changed)

        # 入口轨道变化时：重建 entry_node 并写回
        self._cmb_entry_track.currentIndexChanged.connect(self._on_entry_track_changed)

        # 入口节点变化：直接写回
        self._cmb_entry_node.currentIndexChanged.connect(self._on_form_changed)

        self._spin_max_exec_nodes.valueChanged.connect(self._on_form_changed)
        self._spin_max_run_secs.valueChanged.connect(self._on_form_changed)
    
    # ---------- Store dirty 订阅 ----------

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
        if self._dirty_ui:
            self._btn_save.setStyleSheet("color: orange;")
        else:
            self._btn_save.setStyleSheet("")

    # ---------- 上下文切换与刷新 ----------

    def set_context(self, ctx: ProfileContext) -> None:
        self._ctx = ctx
        self._current_id = None
        self.refresh_list()

    def refresh_list(self) -> None:
        prev = self._current_id
        self._list.blockSignals(True)
        self._list.clear()

        presets = self._svc.list_presets()
        for p in presets:
            item = QListWidgetItem(p.name or "(未命名)")
            item.setData(Qt.UserRole, p.id)
            self._list.addItem(item)

        self._list.blockSignals(False)

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
            if hasattr(self, "_cmb_entry_mode"):
                self._cmb_entry_mode.clear()
            if hasattr(self, "_cmb_entry_track"):
                self._cmb_entry_track.clear()
            if hasattr(self, "_spin_max_exec_nodes"):
                self._spin_max_exec_nodes.setValue(0)
            if hasattr(self, "_spin_max_run_secs"):
                self._spin_max_run_secs.setValue(0)
        finally:
            self._building_form = False

    def _load_entry_mode_track_for_preset(self, p: RotationPreset) -> None:
        """
        根据 RotationPreset.entry（EntryPoint）加载入口模式/轨道/节点到三个下拉框。
        """
        self._cmb_entry_mode.blockSignals(True)
        self._cmb_entry_track.blockSignals(True)
        self._cmb_entry_node.blockSignals(True)
        try:
            self._cmb_entry_mode.clear()
            self._cmb_entry_track.clear()
            self._cmb_entry_node.clear()

            # 入口模式：第一个为“全局”，后面为各 Mode
            self._cmb_entry_mode.addItem("（全局）", userData="")
            for m in (p.modes or []):
                self._cmb_entry_mode.addItem(m.name or "(未命名)", userData=m.id or "")

            entry = getattr(p, "entry", None)
            scope = (getattr(entry, "scope", "global") or "global").strip().lower() if entry is not None else "global"
            em = ""
            et = ""
            en = ""
            if entry is not None:
                if scope == "mode":
                    em = (getattr(entry, "mode_id", "") or "").strip()
                et = (getattr(entry, "track_id", "") or "").strip()
                en = (getattr(entry, "node_id", "") or "").strip()

            # 选中入口模式
            idx_mode = 0
            if em:
                for i in range(self._cmb_entry_mode.count()):
                    data = self._cmb_entry_mode.itemData(i)
                    if isinstance(data, str) and data == em:
                        idx_mode = i
                        break
            self._cmb_entry_mode.setCurrentIndex(idx_mode)

            # 按入口模式构建轨道下拉
            self._rebuild_entry_track_combo(p, em)

            # 当前轨道选择
            et_data = self._cmb_entry_track.currentData()
            cur_track = et_data if isinstance(et_data, str) else ""

            # 按模式+轨道构建节点下拉
            self._rebuild_entry_node_combo(p, em, cur_track)

            # 定位到 entry.node_id（若存在）
            if en:
                for i in range(self._cmb_entry_node.count()):
                    data = self._cmb_entry_node.itemData(i)
                    if isinstance(data, str) and data == en:
                        self._cmb_entry_node.setCurrentIndex(i)
                        break

        finally:
            self._cmb_entry_mode.blockSignals(False)
            self._cmb_entry_track.blockSignals(False)
            self._cmb_entry_node.blockSignals(False)

    def _rebuild_entry_track_combo(self, p: RotationPreset, mode_id: str) -> None:
        """
        重建“入口轨道”下拉框：
        - mode_id 为空 => 使用 global_tracks
        - mode_id 非空 => 使用对应 Mode.tracks
        初始选中：尽量与 preset.entry.track_id 对齐。
        """
        self._cmb_entry_track.clear()
        self._cmb_entry_track.addItem("（未指定）", userData="")

        tracks = []
        mid = (mode_id or "").strip()
        if not mid:
            tracks = list(p.global_tracks or [])
        else:
            m = next((m for m in (p.modes or []) if (m.id or "") == mid), None)
            if m is not None:
                tracks = list(m.tracks or [])

        for t in tracks:
            self._cmb_entry_track.addItem(t.name or "(未命名)", userData=t.id or "")

        # 根据 entry.track_id 尝试选中
        entry = getattr(p, "entry", None)
        et = (getattr(entry, "track_id", "") or "").strip() if entry is not None else ""
        if et:
            for i in range(self._cmb_entry_track.count()):
                data = self._cmb_entry_track.itemData(i)
                if isinstance(data, str) and data == et:
                    self._cmb_entry_track.setCurrentIndex(i)
                    break

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

            self._load_entry_mode_track_for_preset(p)

            # 安全限制
            self._spin_max_exec_nodes.setValue(int(getattr(p, "max_exec_nodes", 0) or 0))
            self._spin_max_run_secs.setValue(int(getattr(p, "max_run_seconds", 0) or 0))

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

        em_data = self._cmb_entry_mode.currentData() if hasattr(self, "_cmb_entry_mode") else ""
        et_data = self._cmb_entry_track.currentData() if hasattr(self, "_cmb_entry_track") else ""
        en_data = self._cmb_entry_node.currentData() if hasattr(self, "_cmb_entry_node") else ""

        em = em_data if isinstance(em_data, str) else ""
        et = et_data if isinstance(et_data, str) else ""
        en = en_data if isinstance(en_data, str) else ""

        max_exec = int(self._spin_max_exec_nodes.value()) if hasattr(self, "_spin_max_exec_nodes") else 0
        max_secs = int(self._spin_max_run_secs.value()) if hasattr(self, "_spin_max_run_secs") else 0

        changed = self._svc.update_preset_basic(
            pid,
            name=name,
            description=desc,
            entry_mode_id=em,
            entry_track_id=et,
            entry_node_id=en,
            max_exec_nodes=max_exec,
            max_run_seconds=max_secs,
        )
        if changed:
            for i in range(self._list.count()):
                item = self._list.item(i)
                val = item.data(Qt.UserRole)
                if isinstance(val, str) and val == pid:
                    item.setText((name or "").strip() or "(未命名)")
                    break

    # ---------- 事件回调 ----------

    def _on_select(self, curr: QListWidgetItem, prev: QListWidgetItem) -> None:  # type: ignore[override]
        if self._building_form:
            return
        if prev is not None:
            try:
                self._apply_form_to_current()
            except Exception:
                pass

        if curr is None:
            self._current_id = None
            self._clear_form()
            return
        pid = curr.data(Qt.UserRole)
        if not isinstance(pid, str):
            self._current_id = None
            self._clear_form()
            return

        self._load_into_form(pid)

    def _on_form_changed(self) -> None:
        if self._building_form:
            return
        self._apply_form_to_current()

    def _on_entry_mode_changed(self) -> None:
        if self._building_form:
            return
        pid = self._current_id
        if not pid:
            return
        p = self._svc.find_preset(pid)
        if p is None:
            return

        data = self._cmb_entry_mode.currentData()
        mid = data if isinstance(data, str) else ""

        self._building_form = True
        try:
            self._rebuild_entry_track_combo(p, mid)

            # track rebuild 后，按当前 track 再 rebuild node
            et_data = self._cmb_entry_track.currentData()
            et = et_data if isinstance(et_data, str) else ""
            self._rebuild_entry_node_combo(p, mid, et)
        finally:
            self._building_form = False

        self._apply_form_to_current()

    def _on_edit(self) -> None:
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

    def _on_check_refs(self) -> None:
        pid = self._current_id
        if not pid:
            self._notify.error("请先选择要检查的方案")
            return
        p = self._svc.find_preset(pid)
        if p is None:
            self._notify.error("当前方案不存在")
            return

        try:
            report = self._validator.validate_preset(p, ctx=self._ctx)
        except Exception as e:
            self._notify.error("校验失败", detail=str(e))
            return

        ds = list(report.diagnostics or [])
        err_cnt = sum(1 for d in ds if d.level == "error")
        warn_cnt = sum(1 for d in ds if d.level == "warning")
        info_cnt = sum(1 for d in ds if d.level == "info")

        preset_name = p.name or "(未命名)"
        summary_lines = [
            f"方案：{preset_name}",
            f"错误：{err_cnt}，警告：{warn_cnt}，信息：{info_cnt}",
        ]

        # 简短摘要（MessageBox 主文本）
        if err_cnt == 0 and warn_cnt == 0:
            summary_lines.append("")
            summary_lines.append("校验通过：未发现问题。")
            icon = QMessageBox.Information
        else:
            summary_lines.append("")
            summary_lines.append("发现问题：请展开“详细信息”查看具体位置与原因。")
            icon = QMessageBox.Warning if err_cnt > 0 else QMessageBox.Information

        # 详细信息（可滚动复制）
        detail = report.format_text(max_lines=400)

        box = QMessageBox(self)
        box.setWindowTitle("校验 / 引用检查结果")
        box.setIcon(icon)
        box.setText("\n".join(summary_lines))
        box.setDetailedText(detail)
        box.exec()

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
            "将从磁盘重新加载 rotation.json（实际从 profile.json 的 rotations 部分），放弃当前未保存更改。\n\n确认继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ok != QMessageBox.Yes:
            return

        try:
            self._apply_form_to_current()
        except Exception:
            pass

        try:
            self._svc.reload_cmd()
        except Exception as e:
            self._notify.error("重新加载失败", detail=str(e))
            return

        self._current_id = None
        self.refresh_list()
        self._notify.info("已重新加载循环配置")

    def _on_save(self) -> None:
        try:
            self._apply_form_to_current()
        except Exception:
            pass

        saved = self._svc.save_cmd()
        if saved:
            self._notify.info("循环配置已保存（写入 profile.json）")
        else:
            self._notify.status_msg("没有需要保存的更改", ttl_ms=1500)

    # ---------- flush 接口 ----------

    def flush_to_model(self) -> None:
        try:
            self._apply_form_to_current()
        except Exception:
            pass

    def _on_entry_track_changed(self) -> None:
        if self._building_form:
            return
        pid = self._current_id
        if not pid:
            return
        p = self._svc.find_preset(pid)
        if p is None:
            return

        em_data = self._cmb_entry_mode.currentData()
        et_data = self._cmb_entry_track.currentData()
        em = em_data if isinstance(em_data, str) else ""
        et = et_data if isinstance(et_data, str) else ""

        self._building_form = True
        try:
            self._rebuild_entry_node_combo(p, em, et)
        finally:
            self._building_form = False

        self._apply_form_to_current()

    def _rebuild_entry_node_combo(self, p: RotationPreset, mode_id: str, track_id: str) -> None:
        self._cmb_entry_node.clear()
        self._cmb_entry_node.addItem("（未指定）", userData="")

        mid = (mode_id or "").strip()
        tid = (track_id or "").strip()
        if not tid:
            return

        # 找轨道
        tr = None
        if not mid:
            tr = next((t for t in (p.global_tracks or []) if (t.id or "").strip() == tid), None)
        else:
            m = next((m for m in (p.modes or []) if (m.id or "").strip() == mid), None)
            if m is not None:
                tr = next((t for t in (m.tracks or []) if (t.id or "").strip() == tid), None)

        if tr is None or not (tr.nodes or []):
            return

        for n in (tr.nodes or []):
            nid = (getattr(n, "id", "") or "").strip()
            if not nid:
                continue
            label = (getattr(n, "label", "") or "").strip()
            kind = (getattr(n, "kind", "") or "").strip()
            text = label or kind or "(节点)"
            self._cmb_entry_node.addItem(f"{text} [{nid[-6:]}]", userData=nid)