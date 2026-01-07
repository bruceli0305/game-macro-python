from __future__ import annotations

from typing import Optional, Any, Dict, List

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
    - 开始 / 暂停 / 停止 按钮
    - 简短状态显示（运行中 / 暂停 / 已停止 + 原因）

    依赖：
    - ctx: ProfileContext（读取 rotations.presets）
    - engine_host: RotationEditorPage 实例，需提供：
        * start_engine_for_preset(preset_id: str)
        * stop_engine()
        * toggle_pause_engine()
        * get_engine_state_snapshot() -> Dict[str, Any]
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        engine_host: Any,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._ctx = ctx
        self._engine_host = engine_host

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

        row_ctrl.addStretch(1)
        root.addLayout(row_ctrl)

        # 状态行
        row_state = QHBoxLayout()
        row_state.addWidget(QLabel("状态:", self))
        self._lbl_state = QLabel("未运行", self)
        row_state.addWidget(self._lbl_state, 1)
        root.addLayout(row_state)

        self.setFixedWidth(320)

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

    # ---------- 按钮行为 ----------

    def _on_start_clicked(self) -> None:
        pid = (self._current_preset_id() or "").strip()
        if not pid:
            # 不做复杂提示，避免打扰；可以后续接入 notify
            return
        try:
            # 让编辑器页选中该 preset 并启动引擎
            if hasattr(self._engine_host, "start_engine_for_preset"):
                self._engine_host.start_engine_for_preset(pid)
        except Exception:
            # 外层 MainWindow 有 notify；这里保持静默
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

    # ---------- 状态刷新 ----------

    def _refresh_state(self) -> None:
        """
        定时从 engine_host 获取状态快照，更新按钮可用性和状态文本。
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

        # 文本
        if running:
            if paused:
                txt = "暂停中 (running=paused)"
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

        # 按钮状态：
        # - 未运行：只允许“开始”，禁用暂停/停止
        # - 运行中：允许暂停/停止，禁用“开始”
        # - 暂停中：允许“继续”(按钮文案切换)、停止
        if running:
            self._btn_start.setEnabled(False)
            self._btn_stop.setEnabled(True)
            self._btn_pause.setEnabled(True)
            self._btn_pause.setText("继续" if paused else "暂停")
        else:
            # 未运行或已停止
            has_presets = self._cmb_preset.count() > 0
            self._btn_start.setEnabled(has_presets)
            self._btn_stop.setEnabled(False)
            self._btn_pause.setEnabled(False)
            self._btn_pause.setText("暂停")