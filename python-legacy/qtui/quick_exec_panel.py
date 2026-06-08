from __future__ import annotations

from typing import Optional, Any, Dict, List, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QSizePolicy,
)

from core.profiles import ProfileContext


class QuickExecPanel(QWidget):
    """
    快捷执行面板（始终置顶的小窗口）：

    - 显示当前 Profile 名称
    - Preset 下拉选择（使用 preset.entry 作为入口）
    - 开始 / 暂停 / 停止 / 打开编辑器 按钮
    - 显示引擎状态 + 最近执行的节点 + 发键模式/诊断

    依赖：
    - ctx: ProfileContext（读取 rotations.presets）
    - engine_host: RotationEditorPage 实例，需提供：
        * start_engine_for_preset(preset_id: str)
        * stop_engine()
        * toggle_pause_engine()
        * get_engine_state_snapshot() -> Dict[str, Any]
        * get_last_executed_node_label() -> str
        * get_key_sender_info() -> Dict[str,str]  (mode/detail)
    - open_editor_cb: Callable[[str], None]，打开编辑器到指定 preset 的回调
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        engine_host: Any,
        open_editor_cb: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._ctx = ctx
        self._engine_host = engine_host
        self._open_editor_cb = open_editor_cb

        # 窗口标志：工具窗 + 置顶 + 有标题和关闭按钮
        flags = Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setWindowTitle("快捷执行面板")

        self._building = False

        self._build_ui()

        # 定时刷新引擎状态
        self._timer = QTimer(self)
        self._timer.setInterval(300)  # 300ms 刷新一次
        self._timer.timeout.connect(self._refresh_state)
        self._timer.start()

        # 初次加载
        self.set_context(self._ctx)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Profile 行
        row_profile = QHBoxLayout()
        row_profile.addWidget(QLabel("Profile:", self))
        self._lbl_profile = QLabel("", self)
        self._lbl_profile.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_profile.addWidget(self._lbl_profile, 1)
        root.addLayout(row_profile)

        # Preset 行
        row_preset = QHBoxLayout()
        row_preset.addWidget(QLabel("方案(Preset):", self))
        self._cmb_preset = QComboBox(self)
        self._cmb_preset.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_preset.addWidget(self._cmb_preset, 1)
        root.addLayout(row_preset)

        # 控制按钮行
        row_ctrl = QHBoxLayout()

        self._btn_start = QPushButton("开始", self)
        self._btn_start.clicked.connect(self._on_start_clicked)
        row_ctrl.addWidget(self._btn_start)

        self._btn_pause = QPushButton("暂停", self)
        self._btn_pause.clicked.connect(self._on_pause_clicked)
        row_ctrl.addWidget(self._btn_pause)

        self._btn_stop = QPushButton("停止", self)
        self._btn_stop.clicked.connect(self._on_stop_clicked)
        row_ctrl.addWidget(self._btn_stop)

        # 打开编辑器按钮
        self._btn_open_editor = QPushButton("打开编辑器", self)
        self._btn_open_editor.clicked.connect(self._on_open_editor_clicked)
        row_ctrl.addWidget(self._btn_open_editor)

        row_ctrl.addStretch(1)
        root.addLayout(row_ctrl)

        # 状态行
        row_state = QHBoxLayout()
        row_state.addWidget(QLabel("状态:", self))
        self._lbl_state = QLabel("未运行", self)
        self._lbl_state.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_state.addWidget(self._lbl_state, 1)
        root.addLayout(row_state)

        # 最近节点行
        row_node = QHBoxLayout()
        row_node.addWidget(QLabel("最近节点:", self))
        self._lbl_last_node = QLabel("-", self)
        self._lbl_last_node.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_node.addWidget(self._lbl_last_node, 1)
        root.addLayout(row_node)

        # 发键模式行
        row_sender = QHBoxLayout()
        row_sender.addWidget(QLabel("发键:", self))
        self._lbl_sender = QLabel("-", self)
        self._lbl_sender.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row_sender.addWidget(self._lbl_sender, 1)
        root.addLayout(row_sender)

        self.setFixedWidth(380)

    # ---------- 上下文 & Preset 列表 ----------

    def set_context(self, ctx: ProfileContext) -> None:
        """
        切换 ProfileContext 时调用：
        - 更新 Profile 名称
        - 重新加载 preset 列表
        """
        self._ctx = ctx
        name = getattr(ctx, "profile_name", "") or ""
        self._lbl_profile.setText(name or "(未命名 Profile)")
        self._reload_presets()

    def _reload_presets(self) -> None:
        self._building = True
        try:
            self._cmb_preset.clear()
            rotations = getattr(getattr(self._ctx, "profile", None), "rotations", None)
            presets = getattr(rotations, "presets", []) if rotations is not None else []
            presets = presets or []

            for p in presets:
                pid = getattr(p, "id", "") or ""
                name = getattr(p, "name", "") or "(未命名)"
                suffix = f"[{pid[-6:]}]" if pid else ""
                self._cmb_preset.addItem(f"{name} {suffix}", userData=pid)

            if self._cmb_preset.count() > 0:
                self._cmb_preset.setCurrentIndex(0)
        finally:
            self._building = False

    def _current_preset_id(self) -> str:
        data = self._cmb_preset.currentData()
        return data if isinstance(data, str) else ""

    def _select_preset_in_combo(self, preset_id: str) -> None:
        """
        在 combo 中选中指定 preset_id（若存在），不触发额外逻辑。
        仅用于“引擎正在运行某个 preset”时的 UI 同步。
        """
        pid = (preset_id or "").strip()
        if not pid:
            return
        self._building = True
        try:
            for i in range(self._cmb_preset.count()):
                data = self._cmb_preset.itemData(i)
                if isinstance(data, str) and data == pid:
                    if self._cmb_preset.currentIndex() != i:
                        self._cmb_preset.setCurrentIndex(i)
                    break
        finally:
            self._building = False

    # ---------- 按钮行为 ----------

    def _on_start_clicked(self) -> None:
        pid = (self._current_preset_id() or "").strip()
        if not pid:
            return
        try:
            if hasattr(self._engine_host, "start_engine_for_preset"):
                self._engine_host.start_engine_for_preset(pid)
        except Exception:
            pass

    def _on_pause_clicked(self) -> None:
        try:
            if hasattr(self._engine_host, "toggle_pause_engine"):
                self._engine_host.toggle_pause_engine()
        except Exception:
            pass

    def _on_stop_clicked(self) -> None:
        try:
            if hasattr(self._engine_host, "stop_engine"):
                self._engine_host.stop_engine()
        except Exception:
            pass

    def _on_open_editor_clicked(self) -> None:
        """
        打开编辑器并选中当前 preset（如果回调可用）。
        """
        pid = (self._current_preset_id() or "").strip()
        if not pid:
            return
        cb = self._open_editor_cb
        if cb is None:
            return
        try:
            cb(pid)
        except Exception:
            pass

    # ---------- 状态刷新 ----------

    def _refresh_state(self) -> None:
        """
        定时从 engine_host 获取状态快照，更新按钮可用性和状态文本。
        并同步最近执行节点、实际运行的 preset 和发键模式信息。
        """
        snap: Dict[str, Any]
        try:
            if hasattr(self._engine_host, "get_engine_state_snapshot"):
                snap = self._engine_host.get_engine_state_snapshot()
            else:
                snap = {}
        except Exception:
            snap = {}

        running = bool(snap.get("running", False))
        paused = bool(snap.get("paused", False))
        reason = str(snap.get("stop_reason", "") or "").strip()
        last_err = str(snap.get("last_error", "") or "").strip()
        last_err_detail = str(snap.get("last_error_detail", "") or "").strip()
        preset_running = str(snap.get("preset_id", "") or "").strip()

        # 文本
        if running:
            if paused:
                txt = "暂停中"
            else:
                txt = "运行中"
        else:
            if reason:
                txt = f"已停止: {reason}"
            else:
                txt = "未运行"

        if last_err:
            if last_err_detail:
                txt += f" | 错误: {last_err} ({last_err_detail})"
            else:
                txt += f" | 错误: {last_err}"

        self._lbl_state.setText(txt)

        # 最近执行节点
        last_node = ""
        try:
            if hasattr(self._engine_host, "get_last_executed_node_label"):
                last_node = self._engine_host.get_last_executed_node_label()
        except Exception:
            last_node = ""
        self._lbl_last_node.setText(last_node or "-")

        # 发键模式 & 诊断
        sender_mode = ""
        sender_detail = ""
        try:
            if hasattr(self._engine_host, "get_key_sender_info"):
                info = self._engine_host.get_key_sender_info() or {}
                sender_mode = str(info.get("mode", "") or "")
                sender_detail = str(info.get("detail", "") or "")
        except Exception:
            sender_mode = ""
            sender_detail = ""

        if sender_mode:
            txt_sender = sender_mode
            if sender_detail:
                txt_sender = f"{sender_mode} | {sender_detail}"
        else:
            txt_sender = "-"

        self._lbl_sender.setText(txt_sender)

        # 如果引擎正在运行某个 preset，则尝试在 combo 中高亮它
        if running and preset_running:
            self._select_preset_in_combo(preset_running)

        # 按钮状态：
        has_presets = self._cmb_preset.count() > 0
        if running:
            self._btn_start.setEnabled(False)
            self._btn_stop.setEnabled(True)
            self._btn_pause.setEnabled(True)
            self._btn_pause.setText("继续" if paused else "暂停")
        else:
            self._btn_start.setEnabled(has_presets)
            self._btn_stop.setEnabled(False)
            self._btn_pause.setEnabled(False)
            self._btn_pause.setText("暂停")