from __future__ import annotations

from typing import Optional, List, Dict, Tuple

from PySide6.QtCore import Qt, QRectF, Signal, QPointF
from PySide6.QtGui import QColor, QBrush, QPen, QFont, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
)

from core.profiles import ProfileContext
from rotation_editor.core.models import RotationPreset, Node, SkillNode, GatewayNode
from rotation_editor.ui.editor.timeline_layout import (
    NodeVisualSpec,
    TrackVisualSpec,
    build_timeline_layout,
)
from rotation_editor.ui.editor.timeline_reflow import reflow_row_items_for_drag


class TimelineCanvas(QGraphicsView):
    """
    多轨时间轴总览（QGraphicsView）：

    set_data(ctx, preset, current_mode_id):
        - ctx: 用于查技能读条时间
        - preset: 当前 RotationPreset
        - current_mode_id:
            * None/"" => 仅显示全局轨道
            * 非空 => 显示全局轨道 + 对应模式下所有轨道

    功能：
    - 左键点击节点块 -> nodeClicked(mode_id, track_id, node_index)
    - 左键拖拽节点块（同一轨道内）：
        * 拖动过程中当前块紧贴鼠标，其他块“主动避让”、按插槽重新排布
        * 松开时发出 nodesReordered(mode_id, track_id, node_ids)
    - 右键节点 -> nodeContextMenuRequested(mode_id, track_id, node_index, global_x, global_y)
    - 右键轨道空白 -> trackContextMenuRequested(mode_id, track_id, global_x, global_y)
    """

    nodeClicked = Signal(str, str, int)
    nodesReordered = Signal(str, str, list)
    nodeContextMenuRequested = Signal(str, str, int, int, int)
    trackContextMenuRequested = Signal(str, str, int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # 轨道和节点尺寸
        self._row_height = 52
        self._row_gap = 10
        self._label_width = 160
        self._node_height = 30
        self._x_gap = 8
        self._base_width = 90
        self._row_keys: Dict[int, Tuple[str, str]] = {}

        # 抗锯齿、拖动、更新策略
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # 背景跟随主题
        app = QApplication.instance()
        if app is not None:
            pal = app.palette()
            bg = pal.color(QPalette.Base)
            self.setBackgroundBrush(bg)
        else:
            self.setBackgroundBrush(QColor(40, 40, 40))

        # 当前数据快照
        self._ctx: Optional[ProfileContext] = None
        self._preset: Optional[RotationPreset] = None
        self._current_mode_id: Optional[str] = None

        # 拖拽状态
        self._drag_item: Optional[QGraphicsRectItem] = None
        self._drag_row_key: Optional[Tuple[str, str]] = None
        self._drag_start_pos: QPointF = QPointF()
        self._drag_start_scene_pos: QPointF = QPointF()
        self._drag_row_y: float = 0.0

        # 每个轨道对应的 rect items 顺序：key=(mode_id, track_id)
        self._track_items: Dict[Tuple[str, str], List[QGraphicsRectItem]] = {}

    # ---------- 公共 API ----------

    def set_data(
        self,
        ctx: Optional[ProfileContext],
        preset: Optional[RotationPreset],
        current_mode_id: Optional[str],
    ) -> None:
        """
        设置时间轴数据并重绘。
        """
        self._scene.clear()
        self._track_items.clear()
        self._row_keys.clear()
        self._ctx = ctx
        self._preset = preset
        self._current_mode_id = (current_mode_id or "").strip() or None

        if ctx is None or preset is None:
            return

        # 布局引擎负责计算节点持续时间和宽度、行顺序
        rows: List[TrackVisualSpec] = build_timeline_layout(
            ctx,
            preset,
            self._current_mode_id,
            base_width=float(self._base_width),
        )

        font = QFont(self.font())
        font.setPointSize(9)

        row_index = 0
        x_max = 0.0

        for row in rows:
            y_top = row_index * (self._row_height + self._row_gap)
            y_center = y_top + self._row_height / 2.0

            # 轨道标签
            label_item = QGraphicsSimpleTextItem(row.title)
            label_item.setFont(font)
            label_item.setBrush(QColor(230, 230, 230))
            label_item.setPos(
                4,
                y_top + (self._row_height - label_item.boundingRect().height()) / 2.0,
            )
            self._scene.addItem(label_item)

            key = (row.mode_id, row.track_id)
            self._row_keys[row_index] = key

            x = self._label_width
            rect_items: List[QGraphicsRectItem] = []

            for idx, nvs in enumerate(row.nodes):
                w = nvs.width

                rect = QRectF(0, -self._node_height / 2.0, w, self._node_height)
                item = QGraphicsRectItem(rect)
                item.setPos(x, y_center)

                # 颜色区分类型
                kind = (nvs.kind or "").lower()
                if kind == "skill":
                    fill = QColor(80, 160, 230)
                elif kind == "gateway":
                    fill = QColor(240, 170, 60)
                else:
                    fill = QColor(130, 130, 130)

                pen = QPen(QColor(210, 210, 210), 1.0)
                item.setPen(pen)
                item.setBrush(QBrush(fill))
                item.setToolTip(self._node_tooltip_meta(nvs))

                # 元数据：mode_id / track_id / node_index / node_id
                item.setData(0, row.mode_id)
                item.setData(1, row.track_id)
                item.setData(2, idx)
                item.setData(3, nvs.node_id)

                self._scene.addItem(item)

                # 文本作为子项，局部坐标内居中
                text_item = QGraphicsSimpleTextItem(nvs.label, parent=item)
                text_item.setFont(font)
                tb = text_item.boundingRect()
                text_x = (w - tb.width()) / 2.0
                text_y = (-self._node_height / 2.0) + (self._node_height - tb.height()) / 2.0
                text_item.setPos(text_x, text_y)
                text_item.setBrush(QColor(255, 255, 255))

                rect_items.append(item)
                x += w + self._x_gap

            self._track_items[key] = rect_items
            x_max = max(x_max, x)
            row_index += 1

        total_height = row_index * (self._row_height + self._row_gap)
        self._scene.setSceneRect(
            0,
            0,
            max(x_max + 40, self._label_width + 300),
            max(total_height, 240),
        )

    # ---------- 鼠标事件：点击 & 拖拽 ----------

    def mousePressEvent(self, event) -> None:
        scene_pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(scene_pos, self.transform())

        # 如果点到了文字，取父 rect
        if isinstance(item, QGraphicsSimpleTextItem) and isinstance(item.parentItem(), QGraphicsRectItem):
            item = item.parentItem()

        if event.button() == Qt.LeftButton:
            if isinstance(item, QGraphicsRectItem):
                self._drag_item = item
                self._drag_start_pos = item.pos()
                self._drag_start_scene_pos = scene_pos
                self._drag_row_y = item.pos().y()
                mid = item.data(0)
                tid = item.data(1)
                idx = item.data(2)
                if isinstance(mid, str) and isinstance(tid, str) and isinstance(idx, int):
                    self._drag_row_key = (mid, tid)
                    self.nodeClicked.emit(mid, tid, idx)
                else:
                    self._drag_row_key = None
            else:
                self._drag_item = None
                self._drag_row_key = None

        elif event.button() == Qt.RightButton:
            # 右键：节点块 -> 节点菜单；否则尝试轨道空白菜单
            if isinstance(item, QGraphicsRectItem):
                mid = item.data(0)
                tid = item.data(1)
                idx = item.data(2)
                if isinstance(mid, str) and isinstance(tid, str) and isinstance(idx, int):
                    self.nodeContextMenuRequested.emit(
                        mid,
                        tid,
                        idx,
                        event.globalX(),
                        event.globalY(),
                    )
                    return
            else:
                row_height_total = self._row_height + self._row_gap
                if row_height_total > 0:
                    y = scene_pos.y()
                    row_index = int(y // row_height_total)
                    row_top = row_index * row_height_total
                    if row_top <= y <= row_top + self._row_height:
                        key = self._row_keys.get(row_index)
                        if key is not None:
                            mid, tid = key
                            self.trackContextMenuRequested.emit(
                                mid,
                                tid,
                                event.globalX(),
                                event.globalY(),
                            )
                            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_item is not None and self._drag_row_key is not None:
            scene_pos = self.mapToScene(event.pos())
            dx = scene_pos.x() - self._drag_start_scene_pos.x()

            new_x = self._drag_start_pos.x() + dx
            if new_x < self._label_width:
                new_x = self._label_width
            # 更新拖拽块的 X，Y 固定在该行
            self._drag_item.setPos(new_x, self._drag_row_y)

            # 行内重排交给独立函数处理
            key = self._drag_row_key
            items = self._track_items.get(key, [])
            if items:
                new_items = reflow_row_items_for_drag(
                    items=items,
                    drag_item=self._drag_item,
                    label_width=float(self._label_width),
                    x_gap=float(self._x_gap),
                )
                self._track_items[key] = new_items
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_item is not None and self._drag_row_key is not None:
            key = self._drag_row_key
            items = self._track_items.get(key, [])
            if items:
                node_ids: List[str] = []
                for it in items:
                    nid = it.data(3)
                    if isinstance(nid, str):
                        node_ids.append(nid)

                if len(node_ids) >= 2:
                    mid, tid = key
                    self.nodesReordered.emit(mid, tid, node_ids)

            self._drag_item = None
            self._drag_row_key = None

        super().mouseReleaseEvent(event)

    # ---------- 工具 ----------

    def _node_tooltip_meta(self, nvs: NodeVisualSpec) -> str:
        """
        根据 NodeVisualSpec 构造 tooltip 文本。
        """
        kind = (nvs.kind or "").lower()
        if kind == "skill":
            return f"SkillNode: {nvs.label}\nnode_id={nvs.node_id}, duration={nvs.duration_ms}ms"
        if kind == "gateway":
            return f"GatewayNode: {nvs.label}\nnode_id={nvs.node_id}, duration={nvs.duration_ms}ms"
        return f"Node: {nvs.label}\nnode_id={nvs.node_id}, duration={nvs.duration_ms}ms"

    def _node_tooltip(self, n: Node) -> str:
        """
        保留原始 Node 对象 tooltip 的实现（目前未直接使用，只保留兼容）。
        """
        if isinstance(n, SkillNode):
            return f"SkillNode: {n.label or ''}\nskill_id={n.skill_id}"
        if isinstance(n, GatewayNode):
            return (
                f"GatewayNode: {n.label or ''}\n"
                f"action={n.action}, target_mode_id={n.target_mode_id or ''}"
            )
        return f"Node: {getattr(n, 'kind', '')}"