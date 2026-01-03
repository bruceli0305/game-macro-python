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
from rotation_editor.ui.editor.timeline_reflow import (
    reflow_row_items_for_drag,
    compute_insert_index_for_cross_track,
)


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
    - 左键拖拽节点块：
        * 同一轨道内：拖拽过程中只有该节点移动，松开后发 nodesReordered(mode_id, track_id, node_ids)
        * 跨轨道：拖拽节点在视觉上跟着鼠标移动，松开后发 nodeCrossMoved(...)，由上层完成数据迁移并重绘
    - 右键节点 -> nodeContextMenuRequested(mode_id, track_id, node_index, global_x, global_y)
    - 右键轨道空白 -> trackContextMenuRequested(mode_id, track_id, global_x, global_y)
    - 在最后一条轨道之后（或无轨道时）画一个“新增轨道”按钮，下方 -> trackAddRequested(mode_id)
      * mode_id == "" 表示新增全局轨道
    """

    nodeClicked = Signal(str, str, int)
    nodesReordered = Signal(str, str, list)
    nodeCrossMoved = Signal(str, str, str, str, int, str)

    nodeContextMenuRequested = Signal(str, str, int, int, int)
    trackContextMenuRequested = Signal(str, str, int, int)

    trackAddRequested = Signal(str)  # mode_id（空串表示全局轨道）

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # 行高 / 间距 / 左侧标签区宽度
        self._row_height = 52
        self._row_gap = 10
        self._label_width = 160
        self._node_height = 30
        self._x_gap = 8
        self._base_width = 90
        self._row_keys: Dict[int, Tuple[str, str]] = {}

        # 渲染参数
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

        # 无任何轨道：提示 + 下方新增全局轨道按钮
        if not rows:
            y_top = 0
            y_center = y_top + self._row_height / 2.0

            hint = QGraphicsSimpleTextItem("（当前无轨道，点击下方 + 新建全局轨道）")
            hint.setFont(font)
            hint.setBrush(QColor(200, 200, 200))
            hint.setPos(
                4,
                y_top + (self._row_height - hint.boundingRect().height()) / 2.0,
            )
            self._scene.addItem(hint)

            btn_w, btn_h = 44.0, 20.0
            btn_x = 6.0
            btn_y = y_top + self._row_height + self._row_gap / 2.0 - btn_h / 2.0
            plus_rect = QGraphicsRectItem(0, 0, btn_w, btn_h)
            plus_rect.setPos(btn_x, btn_y)
            plus_rect.setBrush(QBrush(QColor(80, 160, 80)))
            plus_rect.setPen(QPen(QColor(30, 80, 30), 1.0))
            plus_rect.setData(0, "add_track_button")
            plus_rect.setData(1, "")  # 空串 => 全局轨道
            self._scene.addItem(plus_rect)

            text_item = QGraphicsSimpleTextItem("+", plus_rect)
            text_item.setFont(font)
            tb = text_item.boundingRect()
            text_x = (btn_w - tb.width()) / 2.0
            text_y = (btn_h - tb.height()) / 2.0
            text_item.setPos(text_x, text_y)
            text_item.setBrush(QColor(255, 255, 255))

            self._scene.setSceneRect(
                0,
                0,
                max(self._label_width + 300, 320),
                max(self._row_height + self._row_gap + btn_h + 20, 240),
            )
            return

        # 有轨道：画所有轨道，并在最后一条轨道之后画一个“新增轨道”按钮
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

                item.setData(0, row.mode_id)   # mode_id
                item.setData(1, row.track_id)  # track_id
                item.setData(2, idx)           # node_index
                item.setData(3, nvs.node_id)   # node_id

                self._scene.addItem(item)

                text_item2 = QGraphicsSimpleTextItem(nvs.label, parent=item)
                text_item2.setFont(font)
                tb2 = text_item2.boundingRect()
                text_x2 = (w - tb2.width()) / 2.0
                text_y2 = (-self._node_height / 2.0) + (self._node_height - tb2.height()) / 2.0
                text_item2.setPos(text_x2, text_y2)
                text_item2.setBrush(QColor(255, 255, 255))

                rect_items.append(item)
                x += w + self._x_gap

            self._track_items[key] = rect_items
            x_max = max(x_max, x)
            row_index += 1

        # 最后一条轨道之后的“新增轨道”按钮
        last_row_index = len(rows) - 1
        last_y_top = last_row_index * (self._row_height + self._row_gap)

        btn_w, btn_h = 64.0, 22.0
        btn_x = 6.0
        btn_y = last_y_top + self._row_height + self._row_gap / 2.0 - btn_h / 2.0
        plus_rect = QGraphicsRectItem(0, 0, btn_w, btn_h)
        plus_rect.setPos(btn_x, btn_y)
        plus_rect.setBrush(QBrush(QColor(80, 160, 80)))
        plus_rect.setPen(QPen(QColor(30, 80, 30), 1.0))
        plus_rect.setData(0, "add_track_button")

        # mode_id 用 current_mode_id（若存在）；否则用最后一条轨道的 mode_id（全局/模式）
        if self._current_mode_id:
            mid_for_plus = self._current_mode_id
        else:
            mid_for_plus = rows[-1].mode_id or ""
        plus_rect.setData(1, mid_for_plus)

        self._scene.addItem(plus_rect)

        text_item = QGraphicsSimpleTextItem("+ 新增轨道", plus_rect)
        text_item.setFont(font)
        tb = text_item.boundingRect()
        text_x = (btn_w - tb.width()) / 2.0
        text_y = (btn_h - tb.height()) / 2.0
        text_item.setPos(text_x, text_y)
        text_item.setBrush(QColor(255, 255, 255))

        total_height = (len(rows)) * (self._row_height + self._row_gap) + self._row_gap + btn_h
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

        # 先处理“新增轨道”按钮：可能点到文字，也可能点到矩形
        if isinstance(item, QGraphicsSimpleTextItem) and isinstance(item.parentItem(), QGraphicsRectItem):
            item = item.parentItem()

        if isinstance(item, QGraphicsRectItem):
            tag = item.data(0)
            if tag == "add_track_button":
                mid = item.data(1)
                if isinstance(mid, str):
                    self.trackAddRequested.emit(mid)  # mid 为空串 => 全局轨道
                return

        # 节点拖拽/右键逻辑
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

            # 只更新拖拽节点的 X/Y，其它节点保持不动
            new_x = self._drag_start_pos.x() + dx
            if new_x < self._label_width:
                new_x = self._label_width

            # 纵向吸附到最近的行中心
            new_y = float(self._drag_row_y)
            row_height_total = self._row_height + self._row_gap
            if self._row_keys and row_height_total > 0:
                y = scene_pos.y()
                max_row_index = max(self._row_keys.keys())
                row_index = int(y // row_height_total)
                if row_index < 0:
                    row_index = 0
                if row_index > max_row_index:
                    row_index = max_row_index
                new_y = row_index * row_height_total + self._row_height / 2.0

            self._drag_item.setPos(new_x, new_y)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_item is not None and self._drag_row_key is not None:
            src_key = self._drag_row_key
            src_items = self._track_items.get(src_key, [])

            scene_pos = self.mapToScene(event.pos())
            dest_key: Optional[Tuple[str, str]] = None
            row_height_total = self._row_height + self._row_gap
            if row_height_total > 0:
                y = scene_pos.y()
                row_index = int(y // row_height_total)
                row_top = row_index * row_height_total
                if row_top <= y <= row_top + self._row_height:
                    dest_key = self._row_keys.get(row_index)

            if dest_key is None or dest_key == src_key:
                # 同一轨道内：在此刻调用一次重排算法得到新顺序，然后发 nodesReordered
                if src_items:
                    new_items = reflow_row_items_for_drag(
                        items=src_items,
                        drag_item=self._drag_item,
                        label_width=float(self._label_width),
                        x_gap=float(self._x_gap),
                    )
                    self._track_items[src_key] = new_items
                    node_ids: List[str] = []
                    for it in new_items:
                        nid = it.data(3)
                        if isinstance(nid, str):
                            node_ids.append(nid)
                    if len(node_ids) >= 2:
                        mid, tid = src_key
                        self.nodesReordered.emit(mid, tid, node_ids)
            else:
                # 跨轨道移动：根据拖拽终点计算目标轨道中的插入位置
                dst_items = self._track_items.get(dest_key, [])
                if dst_items:
                    drag_w = float(self._drag_item.rect().width())
                    drag_center_x = float(self._drag_item.pos().x()) + drag_w / 2.0
                    dst_index = compute_insert_index_for_cross_track(
                        dst_items,
                        drag_w,
                        drag_center_x,
                        float(self._label_width),
                        float(self._x_gap),
                    )
                else:
                    dst_index = 0

                src_mid, src_tid = src_key
                dst_mid, dst_tid = dest_key
                nid = self._drag_item.data(3)
                if isinstance(nid, str):
                    self.nodeCrossMoved.emit(
                        src_mid or "",
                        src_tid or "",
                        dst_mid or "",
                        dst_tid or "",
                        int(dst_index),
                        nid,
                    )

            self._drag_item = None
            self._drag_row_key = None

        super().mouseReleaseEvent(event)

    # ---------- 工具 ----------

    def _node_tooltip_meta(self, nvs: NodeVisualSpec) -> str:
        kind = (nvs.kind or "").lower()
        if kind == "skill":
            return f"SkillNode: {nvs.label}\nnode_id={nvs.node_id}, duration={nvs.duration_ms}ms"
        if kind == "gateway":
            return f"GatewayNode: {nvs.label}\nnode_id={nvs.node_id}, duration={nvs.duration_ms}ms"
        return f"Node: {nvs.label}\nnode_id={nvs.node_id}, duration={nvs.duration_ms}ms"

    def _node_tooltip(self, n: Node) -> str:
        if isinstance(n, SkillNode):
            return f"SkillNode: {n.label or ''}\nskill_id={n.skill_id}"
        if isinstance(n, GatewayNode):
            return (
                f"GatewayNode: {n.label or ''}\n"
                f"action={n.action}, target_mode_id={n.target_mode_id or ''}"
            )
        return f"Node: {getattr(n, 'kind', '')}"