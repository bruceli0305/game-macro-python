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
)


class DebugStatsDialog(QDialog):
    """
    简单调试面板：周期性拉取引擎统计快照并显示。
    """

    def __init__(
        self,
        *,
        get_snapshot: Callable[[], List[Dict[str, Any]]],
        get_lock_state: Callable[[], bool],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("执行调试面板")
        self.resize(820, 420)

        self._get_snapshot = get_snapshot
        self._get_lock_state = get_lock_state

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        top = QHBoxLayout()
        self._lbl_lock = QLabel("施法锁：?", self)
        top.addWidget(self._lbl_lock)

        top.addStretch(1)

        self._btn_refresh = QPushButton("刷新", self)
        self._btn_refresh.clicked.connect(self.refresh_now)
        top.addWidget(self._btn_refresh)

        self._btn_close = QPushButton("关闭", self)
        self._btn_close.clicked.connect(self.close)
        top.addWidget(self._btn_close)

        root.addLayout(top)

        self._table = QTableWidget(self)
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels([
            "技能",
            "node_exec",
            "ready_false",
            "attempt",
            "retry",
            "cast_start",
            "success",
            "fail",
            "last_result",
            "skill_id(后6)",
        ])
        self._table.setSortingEnabled(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        root.addWidget(self._table, 1)

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

    def refresh_now(self) -> None:
        locked = False
        try:
            locked = bool(self._get_lock_state())
        except Exception:
            locked = False
        self._lbl_lock.setText(f"施法锁：{'占用中' if locked else '空闲'}")

        try:
            rows = list(self._get_snapshot() or [])
        except Exception:
            rows = []

        self._table.setRowCount(len(rows))

        for i, d in enumerate(rows):
            name = (d.get("skill_name") or "") or "(未命名)"
            sid = (d.get("skill_id") or "")
            sid6 = sid[-6:] if isinstance(sid, str) else ""

            def _cell(v) -> QTableWidgetItem:
                it = QTableWidgetItem(str(v))
                it.setTextAlignment(Qt.AlignCenter)
                return it

            self._table.setItem(i, 0, QTableWidgetItem(str(name)))
            self._table.setItem(i, 1, _cell(d.get("node_exec", 0)))
            self._table.setItem(i, 2, _cell(d.get("ready_false", 0)))
            self._table.setItem(i, 3, _cell(d.get("attempt", 0)))
            self._table.setItem(i, 4, _cell(d.get("retry", 0)))
            self._table.setItem(i, 5, _cell(d.get("cast_start", 0)))
            self._table.setItem(i, 6, _cell(d.get("success", 0)))
            self._table.setItem(i, 7, _cell(d.get("fail", 0)))

            lr = d.get("last_result", "") or ""
            self._table.setItem(i, 8, QTableWidgetItem(str(lr)))
            self._table.setItem(i, 9, _cell(sid6))

        self._table.resizeColumnsToContents()