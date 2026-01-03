# rotation_editor/ui/editor/timeline_view.py
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFontMetrics
from PySide6.QtWidgets import QWidget

from rotation_editor.core.models import Node, SkillNode, GatewayNode


class TrackTimelineView(QWidget):
    """
    简单时间轴视图（单行）：

    - set_nodes(nodes): 旧 API，等宽绘制所有节点（保留兼容）
    - set_nodes_with_durations(nodes, durations): 新 API，可传入每个节点的持续时长（毫秒）

    目前逻辑：
    - 如果传入 durations，则按照相对时长缩放盒子宽度：
        * 找到 durations 中的最大值 max_d
        * base_width = 80
        * 每个盒子宽度 = base_width * (0.5 + 0.5 * d / max_d)，并 clamp 在 [base_width * 0.5, base_width * 1.5]
    - 如果没传 durations 或 durations 长度与 nodes 不匹配，则退回等宽模式。
    """

    nodeClicked = Signal(int)  # index

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._nodes: List[Node] = []
        self._durations: Optional[List[int]] = None
        self._current_index: int = -1

        self._base_width = 80
        self._box_height = 32
        self._h_gap = 8
        self._margin = 8

        # 用于点击检测：每次绘制时记录盒子矩形
        self._box_rects: List[QRect] = []

        self.setMinimumHeight(self._box_height + self._margin * 2)

    # ---------- 公共 API ----------

    def set_nodes(self, nodes: List[Node]) -> None:
        """
        旧 API：不带时长，所有节点等宽绘制。
        """
        self.set_nodes_with_durations(nodes, None)

    def set_nodes_with_durations(self, nodes: List[Node], durations: Optional[List[int]]) -> None:
        """
        新 API：传入节点列表及对应时长（毫秒）。
        - durations 为 None 或长度与 nodes 不符时，退回等宽绘制。
        """
        self._nodes = list(nodes or [])
        if durations is not None and len(durations) == len(self._nodes):
            self._durations = [int(max(0, d)) for d in durations]
        else:
            self._durations = None

        self._update_size()
        self.update()

    def set_current_index(self, index: int) -> None:
        self._current_index = int(index) if index is not None else -1
        self.update()

    # ---------- 尺寸 ----------

    def _compute_widths(self) -> List[int]:
        """
        根据 durations 或等宽策略计算每个盒子的宽度（像素）。
        """
        n = len(self._nodes)
        if n <= 0:
            return []

        # 没有 durations：等宽
        if not self._durations:
            return [self._base_width] * n

        ds = [max(0, int(d)) for d in self._durations]
        max_d = max(ds) if ds else 0
        if max_d <= 0:
            return [self._base_width] * n

        widths: List[int] = []
        for d in ds:
            # 比例在 0..1 之间
            ratio = d / max_d if max_d > 0 else 1.0
            # 0.5 ~ 1.5 倍 base_width
            scale = 0.5 + 0.5 * ratio
            w = int(self._base_width * scale)
            if w < int(self._base_width * 0.5):
                w = int(self._base_width * 0.5)
            if w > int(self._base_width * 1.5):
                w = int(self._base_width * 1.5)
            widths.append(w)
        return widths

    def _update_size(self) -> None:
        n = len(self._nodes)
        if n <= 0:
            w = 200
        else:
            widths = self._compute_widths()
            total_w = sum(widths) + (n - 1) * self._h_gap
            w = self._margin * 2 + total_w
        h = self._box_height + self._margin * 2
        self.setMinimumWidth(w)
        self.setMinimumHeight(h)
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        n = len(self._nodes)
        if n <= 0:
            w = 200
        else:
            widths = self._compute_widths()
            total_w = sum(widths) + (n - 1) * self._h_gap
            w = self._margin * 2 + total_w
        h = self._box_height + self._margin * 2
        return QSize(w, h)

    # ---------- 绘制 ----------

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._nodes:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        fm = QFontMetrics(painter.font())
        widths = self._compute_widths()

        self._box_rects = []

        x = self._margin
        y = self._margin

        for idx, node in enumerate(self._nodes):
            w = widths[idx] if idx < len(widths) else self._base_width
            rect = QRect(x, y, w, self._box_height)
            self._box_rects.append(rect)

            # 颜色区分类型
            if isinstance(node, SkillNode):
                fill = QColor(70, 130, 180)      # steelblue
            elif isinstance(node, GatewayNode):
                fill = QColor(220, 140, 30)      # orange-ish
            else:
                fill = QColor(100, 100, 100)

            # 选中高亮边框
            if idx == self._current_index:
                pen = QPen(QColor(255, 215, 0), 2.0)  # gold
            else:
                pen = QPen(QColor(60, 60, 60), 1.0)

            painter.setPen(pen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 4, 4)

            # 文本（节点 label 或 kind）
            label = getattr(node, "label", "") or ""
            if not label:
                if isinstance(node, SkillNode):
                    label = "Skill"
                elif isinstance(node, GatewayNode):
                    label = "GW"
                else:
                    label = node.kind or "N"

            text = fm.elidedText(label, Qt.ElideRight, rect.width() - 8)
            painter.setPen(Qt.white)
            painter.drawText(rect.adjusted(4, 0, -4, 0), Qt.AlignCenter, text)

            x += w + self._h_gap

        painter.end()

    # ---------- 交互 ----------

    def mousePressEvent(self, event) -> None:
        if not self._nodes or not self._box_rects:
            return
        if event.button() != Qt.LeftButton:
            return

        # PySide6 中 position() 返回 QPointF；兼容 event.x()
        try:
            pos = event.position()
            x = int(pos.x())
            y = int(pos.y())
        except Exception:
            x = event.x()
            y = event.y()

        for idx, rect in enumerate(self._box_rects):
            if rect.contains(x, y):
                self.nodeClicked.emit(idx)
                break

        super().mousePressEvent(event)