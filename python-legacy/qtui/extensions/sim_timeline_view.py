from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QBrush,
    QPen,
    QFont,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGraphicsItem,
)

from rotation_editor.sim import SimEvent


class SimulationTimelineView(QGraphicsView):
    """
    简单的推演时间轴视图：

    - 横轴：时间(ms)，按固定比例映射为像素；
    - 纵向：单行事件块（简单起见，不分轨道/模式的行）；
    - 每个 SimEvent 绘制为一个矩形块，颜色按 outcome 分类；
    - 支持点击矩形块发出 eventClicked(index) 信号，index 为事件序号。
    """

    eventClicked = Signal(int)  # index in events list

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._events: List[SimEvent] = []
        self._index_to_item: dict[int, QGraphicsRectItem] = {}

        # 时间缩放：1s ≈ 80px
        self._time_scale_px_per_ms: float = 0.08

        # 当前高亮的块
        self._current_item: Optional[QGraphicsRectItem] = None
        self._normal_pen = QPen(QColor(210, 210, 210), 1.0)
        self._highlight_pen = QPen(QColor(255, 230, 80), 2.0)

        # 渲染设置
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # 背景颜色跟随 Qt Palette
        app = QApplication.instance()
        if app is not None:
            pal = app.palette()
            try:
                bg = pal.color(QPalette.Base)
            except Exception:
                bg = pal.window().color()
            self.setBackgroundBrush(bg)
        else:
            self.setBackgroundBrush(QColor(40, 40, 40))

    # ---------- 对外 API ----------

    def set_events(self, events: List[SimEvent]) -> None:
        """
        重建时间轴内容。
        """
        self._events = list(events or [])
        self._scene.clear()
        self._index_to_item.clear()
        self._current_item = None

        if not self._events:
            self._scene.setSceneRect(0, 0, 400, 120)
            return

        max_t = max(int(e.t_ms) for e in self._events)
        if max_t <= 0:
            max_t = 1000

        left_margin = 60.0
        top_ruler = 24.0
        row_y = top_ruler + 40.0
        block_h = 26.0
        min_width = 40.0

        font = QFont(self.font())
        font.setPointSize(max(font.pointSize() - 1, 7))

        # 先画时间标尺
        x_extent = self._draw_time_ruler(
            font=font,
            left=left_margin,
            top=top_ruler,
            max_time_ms=max_t,
        )

        # 绘制事件块
        x_max = 0.0
        for ev in self._events:
            t_ms = int(ev.t_ms)
            x = left_margin + t_ms * self._time_scale_px_per_ms

            w = min_width

            rect = QGraphicsRectItem(0, 0, w, block_h)
            rect.setPos(x, row_y)
            rect.setPen(self._normal_pen)
            rect.setBrush(QBrush(self._color_for_outcome(ev.outcome)))
            rect.setData(0, int(ev.index))  # 使用事件 index 作为标识

            # tooltip
            tip_lines = [
                f"#{ev.index} @ {ev.t_ms} ms",
                f"scope={ev.scope}",
                f"mode_id={ev.mode_id or ''}",
                f"track_id={ev.track_id or ''}",
                f"label={ev.label}",
                f"kind={ev.node_kind}",
                f"outcome={ev.outcome}",
            ]
            if ev.reason:
                tip_lines.append(f"reason={ev.reason}")
            rect.setToolTip("\n".join(tip_lines))

            self._scene.addItem(rect)
            self._index_to_item[int(ev.index)] = rect

            # 文本
            text = ev.label or ev.node_kind or ""
            text_item = QGraphicsSimpleTextItem(text, rect)
            text_item.setFont(font)
            tb = text_item.boundingRect()
            text_item.setPos(
                (w - tb.width()) / 2.0,
                (block_h - tb.height()) / 2.0,
            )
            text_item.setBrush(QColor(255, 255, 255))

            x_max = max(x_max, x + w)

        total_width = max(x_extent, x_max + 40.0)
        total_height = row_y + block_h + 40.0
        self._scene.setSceneRect(0, 0, total_width, max(total_height, 150.0))

    def highlight_index(self, index: int) -> None:
        """
        高亮指定事件 index 对应的块。
        """
        if self._current_item is not None:
            try:
                self._current_item.setPen(self._normal_pen)
                self._current_item.setZValue(0)
            except Exception:
                pass
        self._current_item = None

        item = self._index_to_item.get(int(index))
        if item is None:
            return

        try:
            item.setPen(self._highlight_pen)
            item.setZValue(10)
            self._current_item = item
            rect = item.sceneBoundingRect().adjusted(-20, -20, 20, 20)
            self.ensureVisible(rect, xMargin=10, yMargin=10)
        except Exception:
            pass

    # ---------- 内部绘制 ----------

    def _draw_time_ruler(
        self,
        *,
        font: QFont,
        left: float,
        top: float,
        max_time_ms: int,
    ) -> float:
        """
        绘制顶部时间刻度线，返回建议的横向扩展宽度。
        """
        scale = float(self._time_scale_px_per_ms)
        if scale <= 0:
            return left + 400.0

        import math

        max_ms = max(1, int(max_time_ms))
        # 取秒级刻度
        step_ms = 1000
        max_step = max(1, int(math.ceil(max_ms / float(step_ms))))

        pen_axis = QPen(QColor(150, 150, 150), 1.0)
        pen_grid = QPen(QColor(70, 70, 70), 1.0, Qt.DashLine)

        axis_y = top - 2.0
        grid_bottom = axis_y + 80.0

        # 顶部横线
        self._scene.addLine(left, axis_y, left + max_ms * scale + 40.0, axis_y, pen_axis)

        font_small = QFont(font)
        font_small.setPointSize(max(font.pointSize() - 1, 6))

        x_max = left

        for i in range(0, max_step + 1):
            t = i * step_ms
            x = left + t * scale
            x_max = max(x_max, x)

            # 竖线 + 小刻度
            self._scene.addLine(x, axis_y, x, grid_bottom, pen_grid)
            self._scene.addLine(x, axis_y, x, axis_y - 4.0, pen_axis)

            # 标签
            text = f"{i}s"
            txt_item = QGraphicsSimpleTextItem(text)
            txt_item.setFont(font_small)
            tb = txt_item.boundingRect()
            tx = x - tb.width() / 2.0
            ty = axis_y - 4.0 - tb.height()
            txt_item.setPos(tx, ty)
            txt_item.setBrush(QColor(200, 200, 200))
            txt_item.setAcceptedMouseButtons(Qt.NoButton)
            txt_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            txt_item.setFlag(QGraphicsItem.ItemIsFocusable, False)
            self._scene.addItem(txt_item)

        return x_max + 40.0

    def _color_for_outcome(self, outcome: str) -> QColor:
        o = (outcome or "").strip().upper()

        if o.startswith("GW_"):
            if o == "GW_COND_FALSE":
                return QColor(180, 180, 90)
            if o == "GW_END":
                return QColor(220, 120, 40)
            if o.startswith("GW_EXEC"):
                return QColor(140, 180, 240)
            return QColor(220, 180, 80)  # 普通网关

        if o == "SUCCESS":
            return QColor(80, 160, 230)
        if o.startswith("SKIPPED"):
            return QColor(130, 130, 130)
        if o == "UNKNOWN_NODE":
            return QColor(180, 80, 80)
        return QColor(200, 120, 120)

    # ---------- 交互 ----------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            item = self._scene.itemAt(scene_pos, self.transform())

            # 若点在文字上，则尝试取父矩形
            if isinstance(item, QGraphicsSimpleTextItem) and isinstance(item.parentItem(), QGraphicsRectItem):
                item = item.parentItem()

            if isinstance(item, QGraphicsRectItem):
                idx = item.data(0)
                if isinstance(idx, int):
                    self.eventClicked.emit(idx)
                    self.highlight_index(idx)
                    return

        super().mousePressEvent(event)