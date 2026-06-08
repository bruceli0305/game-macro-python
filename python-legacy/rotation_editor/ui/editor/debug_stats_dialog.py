from __future__ import annotations

from typing import Callable, List, Dict, Any, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QWidget,
)


_STATE_CN = {
    "IDLE": "空闲",
    "READY_CHECK": "可释放检查",
    "LOCK_WAIT": "等待施法锁",
    "PREPARING": "准备施法",
    "START_WAIT": "等待开始信号",
    "CASTING": "施法中",
    "COMPLETE_WAIT": "等待完成信号",
    "SUCCESS": "成功",
    "FAILED": "失败",
    "STOPPED": "已停止",
}

_RESULT_CN = {
    "success": "成功",
    "failed": "失败",
    "stopped": "已停止",
}

_REASON_CN = {
    "timeout": "超时",
    "no_cast_start": "未进入施法中",
    "send_key_error": "发键失败",
    "no_key": "未配置按键",
    "cast_bar_unavailable": "施法条信号不可用",
    "complete_signal_missing": "缺少完成信号",
    "stopped": "已停止",
    "unknown": "未知",
}


def _bi(cn: str, en: str) -> str:
    return f"{cn}({en})"


def _fmt_state(v: object) -> str:
    s = (str(v or "IDLE")).strip().upper()
    cn = _STATE_CN.get(s, "未知状态")
    return f"{cn}({s})"


def _fmt_result(v: object) -> str:
    s = (str(v or "")).strip().lower()
    cn = _RESULT_CN.get(s, "未知结果")
    return f"{cn}({s or 'unknown'})"


def _fmt_reason(v: object) -> str:
    s = (str(v or "")).strip().lower()
    if not s:
        return ""
    cn = _REASON_CN.get(s, "未知原因")
    return f"{cn}({s})"


_ENGINE_STOP_REASON_CN = {
    "": "未运行",
    "finished": "正常结束",
    "user_stop": "手动停止",
    "gateway_end": "网关结束",
    "max_exec_nodes": "达到最大节点数",
    "max_run_seconds": "达到最长时间",
    "no_tracks": "没有可执行轨道",
    "error": "执行错误",
    "internal_error": "引擎内部错误",
    "stopped": "停止",
}


def _fmt_engine_state(d: Dict[str, Any]) -> str:
    running = bool(d.get("running", False))
    paused = bool(d.get("paused", False))
    reason = (str(d.get("stop_reason", "") or "")).strip().lower()

    if running:
        return _bi("运行中", "running")
    if paused:
        return _bi("暂停", "paused")

    if not reason:
        return _bi("未运行", "not running")
    cn = _ENGINE_STOP_REASON_CN.get(reason, f"未知原因({reason})")
    return f"{_bi('已停止', 'stopped')} - {cn}"


class DebugStatsDialog(QDialog):
    """
    调试面板（适配 StateStore 快照）：
    - 顶部：引擎状态（运行中 / 已停止 + 原因） + 施法锁状态
    - 上表：技能统计 + 当前状态
    - 下表：选中技能的最近 attempt 明细
    """

    def __init__(
        self,
        *,
        get_snapshot: Callable[[], List[Dict[str, Any]]],
        get_lock_state: Callable[[], bool],
        get_engine_state: Callable[[], Dict[str, Any]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("执行调试面板(Debug Panel)")
        self.resize(1080, 600)

        self._get_snapshot = get_snapshot
        self._get_lock_state = get_lock_state
        self._get_engine_state = get_engine_state
        self._rows: List[Dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        top = QHBoxLayout()

        # 引擎状态标签
        self._lbl_engine = QLabel(_bi("引擎状态", "Engine") + ": ?", self)
        top.addWidget(self._lbl_engine)

        top.addSpacing(18)

        # 施法锁状态
        self._lbl_lock = QLabel(_bi("施法锁", "Cast Lock") + ": ?", self)
        top.addWidget(self._lbl_lock)

        top.addStretch(1)

        self._btn_refresh = QPushButton(_bi("刷新", "Refresh"), self)
        self._btn_refresh.clicked.connect(self.refresh_now)
        top.addWidget(self._btn_refresh)

        self._btn_close = QPushButton(_bi("关闭", "Close"), self)
        self._btn_close.clicked.connect(self.close)
        top.addWidget(self._btn_close)

        root.addLayout(top)

        splitter = QSplitter(Qt.Vertical, self)
        root.addWidget(splitter, 1)

        # 使用 TabWidget 组织两个视图
        self._tabs = QTabWidget(self)
        splitter.addWidget(self._tabs)

        # Tab 1: 技能统计 + attempt 明细
        tab_stats = QWidget(self._tabs)
        stats_layout = QVBoxLayout(tab_stats)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_splitter = QSplitter(Qt.Vertical, tab_stats)
        stats_layout.addWidget(stats_splitter)

        # 上表：技能统计
        self._table = QTableWidget(self)
        self._table.setColumnCount(14)
        self._table.setHorizontalHeaderLabels([
            _bi("技能", "Skill"),
            _bi("状态", "State"),
            _bi("状态时长ms", "State Age ms"),
            _bi("轮询次数", "Node Exec"),
            _bi("不可用次数", "Ready False"),
            _bi("锁忙跳过", "Skipped Lock"),
            _bi("禁用跳过", "Skipped Disabled"),
            _bi("Attempt(开始)", "Attempt Started"),
            _bi("发键成功", "Key Sent OK"),
            _bi("进入施法中", "Cast Started"),
            _bi("成功次数", "Success"),
            _bi("失败次数", "Fail"),
            _bi("重试(当前)", "Retry Index"),
            _bi("技能ID后6", "Skill ID (last6)"),
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.itemSelectionChanged.connect(self._on_select_row)
        stats_splitter.addWidget(self._table)

        # 下表：attempt 明细
        self._table_attempts = QTableWidget(self)
        self._table_attempts.setColumnCount(9)
        self._table_attempts.setHorizontalHeaderLabels([
            _bi("尝试ID后6", "Attempt ID (last6)"),
            _bi("结果", "Result"),
            _bi("失败原因", "Fail Reason"),
            _bi("开始信号", "Start Mode"),
            _bi("重试次数", "Retries"),
            _bi("读条ms", "Readbar ms"),
            _bi("耗时ms", "Duration ms"),
            _bi("距今ms", "Age ms"),
            _bi("节点ID后6", "Node ID (last6)"),
        ])
        self._table_attempts.verticalHeader().setVisible(False)
        self._table_attempts.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table_attempts.setSelectionBehavior(QTableWidget.SelectRows)
        self._table_attempts.setSelectionMode(QTableWidget.SingleSelection)
        stats_splitter.addWidget(self._table_attempts)

        stats_splitter.setStretchFactor(0, 3)
        stats_splitter.setStretchFactor(1, 2)

        self._tabs.addTab(tab_stats, _bi("技能统计", "Skill Stats"))

        # Tab 2: 执行日志
        tab_log = QWidget(self._tabs)
        log_layout = QVBoxLayout(tab_log)
        log_layout.setContentsMargins(0, 0, 0, 0)

        log_toolbar = QHBoxLayout()
        self._lbl_log_count = QLabel("0 条日志", tab_log)
        log_toolbar.addWidget(self._lbl_log_count)
        log_toolbar.addStretch(1)
        self._btn_clear_log = QPushButton(_bi("清空日志", "Clear Log"), tab_log)
        self._btn_clear_log.clicked.connect(self._clear_exec_log)
        log_toolbar.addWidget(self._btn_clear_log)
        self._chk_auto_scroll = QPushButton(_bi("自动滚动", "Auto Scroll"), tab_log)
        self._chk_auto_scroll.setCheckable(True)
        self._chk_auto_scroll.setChecked(True)
        log_toolbar.addWidget(self._chk_auto_scroll)
        log_layout.addLayout(log_toolbar)

        self._table_log = QTableWidget(tab_log)
        self._table_log.setColumnCount(8)
        self._table_log.setHorizontalHeaderLabels([
            _bi("时间ms", "Time ms"),
            _bi("类型", "Kind"),
            _bi("结果", "Outcome"),
            _bi("轨道", "Track"),
            _bi("技能", "Skill"),
            _bi("原因", "Reason"),
            _bi("推进", "Advance"),
            _bi("详情", "Detail"),
        ])
        self._table_log.verticalHeader().setVisible(False)
        self._table_log.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table_log.setSelectionBehavior(QTableWidget.SelectRows)
        self._table_log.setSelectionMode(QTableWidget.SingleSelection)
        self._table_log.horizontalHeader().setStretchLastSection(True)
        log_layout.addWidget(self._table_log, 1)

        self._tabs.addTab(tab_log, _bi("执行日志", "Exec Log"))

        # 执行日志缓冲（由 append_exec_log 添加）
        self._exec_log_entries: List[Any] = []
        self._exec_log_max = 500

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.refresh_now)
        self._timer.start()

        self.refresh_now()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            self._timer.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def _cell(self, v, *, center: bool = True) -> QTableWidgetItem:
        it = QTableWidgetItem(str(v))
        if center:
            it.setTextAlignment(Qt.AlignCenter)
        return it

    def refresh_now(self) -> None:
        # 引擎状态
        try:
            state = self._get_engine_state() or {}
        except Exception:
            state = {}
        self._lbl_engine.setText(_fmt_engine_state(state))

        # 施法锁状态
        locked = False
        try:
            locked = bool(self._get_lock_state())
        except Exception:
            locked = False
        lock_txt = _bi("施法锁", "Cast Lock") + ": " + (_bi("占用中", "Busy") if locked else _bi("空闲", "Idle"))
        self._lbl_lock.setText(lock_txt)

        # 快照
        try:
            self._rows = list(self._get_snapshot() or [])
        except Exception:
            self._rows = []

        # 保留当前选择 skill_id
        selected_skill_id = ""
        try:
            row = self._table.currentRow()
            if 0 <= row < len(self._rows):
                selected_skill_id = str(self._rows[row].get("skill_id") or "")
        except Exception:
            selected_skill_id = ""

        self._table.setRowCount(len(self._rows))

        for i, d in enumerate(self._rows):
            name = (d.get("skill_name") or "") or "(未命名)"
            sid = (d.get("skill_id") or "")
            sid6 = sid[-6:] if isinstance(sid, str) else ""

            state_disp = _fmt_state(d.get("state", "IDLE"))
            age = d.get("state_age_ms", 0)

            retry_index = d.get("retry_index", 0)
            fail_reason = d.get("fail_reason", "")

            # 失败原因可做 tooltip
            state_item = QTableWidgetItem(state_disp)
            if fail_reason:
                state_item.setToolTip(_bi("失败原因", "Fail Reason") + f": {fail_reason}")

            self._table.setItem(i, 0, QTableWidgetItem(str(name)))
            self._table.setItem(i, 1, state_item)
            self._table.setItem(i, 2, self._cell(age))
            self._table.setItem(i, 3, self._cell(d.get("node_exec", 0)))
            self._table.setItem(i, 4, self._cell(d.get("ready_false", 0)))
            self._table.setItem(i, 5, self._cell(d.get("skipped_lock", 0)))
            self._table.setItem(i, 6, self._cell(d.get("skipped_disabled", 0)))
            self._table.setItem(i, 7, self._cell(d.get("attempt_started", 0)))
            self._table.setItem(i, 8, self._cell(d.get("key_sent_ok", 0)))
            self._table.setItem(i, 9, self._cell(d.get("cast_started", 0)))
            self._table.setItem(i, 10, self._cell(d.get("success", 0)))
            self._table.setItem(i, 11, self._cell(d.get("fail", 0)))
            self._table.setItem(i, 12, self._cell(retry_index))
            self._table.setItem(i, 13, self._cell(sid6))

        self._table.resizeColumnsToContents()

        # 恢复选择并刷新 attempts
        if selected_skill_id:
            for i, d in enumerate(self._rows):
                if str(d.get("skill_id") or "") == selected_skill_id:
                    self._table.setCurrentCell(i, 0)
                    break
        else:
            self._on_select_row()

    def _on_select_row(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rows):
            self._table_attempts.setRowCount(0)
            return

        d = self._rows[row]
        attempts = d.get("recent_attempts", [])
        if not isinstance(attempts, list):
            attempts = []

        self._table_attempts.setRowCount(len(attempts))

        for i, a in enumerate(attempts):
            if not isinstance(a, dict):
                continue

            aid = str(a.get("attempt_id") or "")
            aid6 = aid[-6:] if aid else ""

            node_id = str(a.get("node_id") or "")
            node6 = node_id[-6:] if node_id else ""

            result_disp = _fmt_result(a.get("result", ""))
            reason_disp = _fmt_reason(a.get("reason", ""))

            mode = str(a.get("mode", "") or "")
            mode_disp = mode
            if mode:
                mode_disp = f"{mode}({mode})" if "(" not in mode else mode

            self._table_attempts.setItem(i, 0, self._cell(aid6))
            self._table_attempts.setItem(i, 1, QTableWidgetItem(result_disp))
            self._table_attempts.setItem(i, 2, QTableWidgetItem(reason_disp))
            self._table_attempts.setItem(i, 3, self._cell(mode_disp))
            self._table_attempts.setItem(i, 4, self._cell(a.get("retries", 0)))
            self._table_attempts.setItem(i, 5, self._cell(a.get("readbar_ms", 0)))
            self._table_attempts.setItem(i, 6, self._cell(a.get("duration_ms", 0)))
            self._table_attempts.setItem(i, 7, self._cell(a.get("age_ms", 0)))
            self._table_attempts.setItem(i, 8, self._cell(node6))

        self._table_attempts.resizeColumnsToContents()

        # 刷新执行日志表格
        self._refresh_exec_log_table()

    # ---------- 执行日志 ----------

    def append_exec_log(self, entry) -> None:
        """
        由引擎回调（on_exec_log）调用，将日志条目添加到缓冲区。
        实际的 UI 刷新在 refresh_now() 中批量处理。
        """
        self._exec_log_entries.append(entry)
        if len(self._exec_log_entries) > self._exec_log_max:
            self._exec_log_entries = self._exec_log_entries[-self._exec_log_max:]

    def _clear_exec_log(self) -> None:
        self._exec_log_entries.clear()
        self._table_log.setRowCount(0)
        self._lbl_log_count.setText("0 条日志")

    def _refresh_exec_log_table(self) -> None:
        """刷新执行日志表格（在 refresh_now 中调用）。"""
        entries = self._exec_log_entries
        count = len(entries)
        self._lbl_log_count.setText(f"{count} 条日志")

        # 只更新新增的行（避免每次全量刷新）
        current_rows = self._table_log.rowCount()
        if current_rows == count:
            return

        self._table_log.setRowCount(count)
        for i in range(current_rows, count):
            e = entries[i]
            kind = getattr(e, "kind", "")
            outcome = getattr(e, "outcome", "")
            track_id = getattr(e, "track_id", "")
            skill_name = getattr(e, "skill_name", "") or getattr(e, "skill_id", "")
            reason = getattr(e, "reason", "")
            advance = getattr(e, "advance", "")
            detail = getattr(e, "detail", "")
            ts_ms = getattr(e, "ts_ms", 0)

            # 颜色编码
            outcome_item = QTableWidgetItem(outcome)
            if "SUCCESS" in outcome or "TRUE" in outcome:
                outcome_item.setBackground(Qt.darkGreen)
            elif "FALSE" in outcome or "SKIP" in outcome:
                outcome_item.setBackground(Qt.darkGray)
            elif "ERROR" in outcome or "FAIL" in outcome:
                outcome_item.setBackground(Qt.darkRed)
            elif "END" in outcome or "STOP" in outcome:
                outcome_item.setBackground(Qt.darkYellow)

            kind_item = QTableWidgetItem(kind)
            if kind == "skill":
                kind_item.setBackground(Qt.darkBlue)
            elif kind == "gateway":
                kind_item.setBackground(Qt.darkMagenta)

            self._table_log.setItem(i, 0, self._cell(ts_ms))
            self._table_log.setItem(i, 1, kind_item)
            self._table_log.setItem(i, 2, outcome_item)
            self._table_log.setItem(i, 3, QTableWidgetItem(track_id))
            self._table_log.setItem(i, 4, QTableWidgetItem(skill_name))
            self._table_log.setItem(i, 5, QTableWidgetItem(reason))
            self._table_log.setItem(i, 6, self._cell(advance))
            self._table_log.setItem(i, 7, QTableWidgetItem(detail))

        self._table_log.resizeColumnsToContents()

        # 自动滚动到底部
        if self._chk_auto_scroll.isChecked() and count > 0:
            self._table_log.scrollToBottom()