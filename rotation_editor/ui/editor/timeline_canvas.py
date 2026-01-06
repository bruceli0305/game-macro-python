from __future__ import annotations

from typing import Optional, List, Dict, Tuple

from PySide6.QtCore import Qt, QRectF, Signal, QPointF
from PySide6.QtGui import (
    QColor,
    QBrush,
    QPen,
    QFont,
    QPainter,
    QPalette,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGraphicsItem,
)

from core.profiles import ProfileContext
from rotation_editor.core.models import RotationPreset, Node, SkillNode, GatewayNode
from rotation_editor.ui.editor.timeline_layout import (
    NodeVisualSpec,
    TrackVisualSpec,
    build_timeline_layout,
)
from rotation_editor.ui.editor.timeline_reflow import (
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
    - 顶部时间刻度线 + 垂直网格（依据 time_scale_px_per_ms）
    - 左键点击节点块 -> nodeClicked(mode_id, track_id, node_index)
    - 左键拖拽节点块：
        * 同一轨道内：拖拽过程中只有该节点移动，松开后发 nodesReordered(mode_id, track_id, node_ids)
        * 跨轨道：拖拽节点在视觉上跟随鼠标移动，松开后发 nodeCrossMoved(...)
    - 右键节点 -> nodeContextMenuRequested(mode_id, track_id, node_index, global_x, global_y)
    - 右键轨道空白 -> trackContextMenuRequested(mode_id, track_id, global_x, global_y)
    - 在最后一条轨道之后（或无轨道时）画一个“新增轨道”按钮，下方 -> trackAddRequested(mode_id)
      * mode_id == "" 表示新增全局轨道
    - Ctrl+滚轮缩放时间轴（仅改变时间→像素映射，不改变业务数据），缩放变化时发 zoomChanged()

    新增：
    - set_current_node(mode_id, track_id, node_index) 高亮当前执行节点：
        * 使用黄色粗描边 + 提升 Z 值
        * 自动滚动到节点位置附近
    """

    nodeClicked = Signal(str, str, int)
    nodesReordered = Signal(str, str, list)
    nodeCrossMoved = Signal(str, str, str, str, int, str)

    stepChanged = Signal(str, str, str, int)

    nodeContextMenuRequested = Signal(str, str, int, int, int)
    trackContextMenuRequested = Signal(str, str, int, int)

    trackAddRequested = Signal(str)  # mode_id（空串表示全局轨道）
    zoomChanged = Signal()           # 缩放比例变化时发出（不带参数）

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # 顶部标尺高度
        self._ruler_height = 24
        # 轨道行（高度 + 间距）与左侧标签宽度
        self._row_height = 44
        self._row_gap = 4
        self._label_width = 160
        self._node_height = 30
        self._x_gap = 8

        # 时间缩放（像素 / 毫秒）
        self._time_scale_default = 0.06  # 1s ≈ 60px
        self._time_scale_px_per_ms = self._time_scale_default
        self._time_scale_min = 0.01      # 1s ≈ 10px
        self._time_scale_max = 0.3       # 1s ≈ 300px

        # 步骤对应的“显示毫秒”：必须和 build_timeline_layout 里的 STEP_MS 一致
        self._step_ms = 1000

        self._row_keys: Dict[int, Tuple[str, str]] = {}

        # 每个轨道对应的 rect items 顺序：key=(mode_id, track_id)
        self._track_items: Dict[Tuple[str, str], List[QGraphicsRectItem]] = {}

        # 拖拽状态
        self._drag_item: Optional[QGraphicsRectItem] = None
        self._drag_row_key: Optional[Tuple[str, str]] = None
        self._drag_start_pos: QPointF = QPointF()
        self._drag_start_scene_pos: QPointF = QPointF()
        self._drag_row_y: float = 0.0

        # 当前高亮节点
        self._current_item: Optional[QGraphicsRectItem] = None
        self._current_key: Optional[Tuple[str, str]] = None
        self._current_index: Optional[int] = None

        # 标准画笔
        self._normal_pen = QPen(QColor(210, 210, 210), 1.0)
        self._highlight_pen = QPen(QColor(255, 255, 0), 2.0)

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

    # ---------- 时间缩放 API ----------

    def set_time_scale(self, scale: float) -> None:
        try:
            s = float(scale)
        except Exception:
            return

        if s < self._time_scale_min:
            s = self._time_scale_min
        if s > self._time_scale_max:
            s = self._time_scale_max

        if abs(s - self._time_scale_px_per_ms) < 1e-6:
            return

        self._time_scale_px_per_ms = s
        self.zoomChanged.emit()

    def zoom_in(self, factor: float = 1.25) -> None:
        self.set_time_scale(self._time_scale_px_per_ms * factor)

    def zoom_out(self, factor: float = 1.25) -> None:
        self.set_time_scale(self._time_scale_px_per_ms / factor)

    def reset_zoom(self) -> None:
        self.set_time_scale(self._time_scale_default)

    def zoom_ratio(self) -> float:
        if self._time_scale_default <= 0:
            return 1.0
        return self._time_scale_px_per_ms / self._time_scale_default

    # ---------- 公共 API: 绘制 ----------

    def set_data(
        self,
        ctx: Optional[ProfileContext],
        preset: Optional[RotationPreset],
        current_mode_id: Optional[str],
    ) -> None:
        """
        重建场景内容：

        - ctx / preset 为 None 时清空。
        - rows 由 build_timeline_layout 构建：
            * 每个 TrackVisualSpec 包含 nodes 的 start_ms / width。
        - 本方法根据 NodeVisualSpec.start_ms * time_scale_px_per_ms
          计算节点的 X 位置，而不再简单按顺序平铺。
        """
        self._scene.clear()
        self._track_items.clear()
        self._row_keys.clear()
        self._ctx = ctx
        self._preset = preset
        self._current_mode_id = (current_mode_id or "").strip() or None

        # 不清除 key/index，只清除旧的 item 引用，后续重建后会尝试重新应用高亮
        self._current_item = None

        if ctx is None or preset is None:
            return

        rows: List[TrackVisualSpec] = build_timeline_layout(
            ctx,
            preset,
            self._current_mode_id,
            time_scale_px_per_ms=float(self._time_scale_px_per_ms),
        )

        font = QFont(self.font())
        font.setPointSize(9)

        row_index = 0
        x_max = 0.0

        # 若有轨道，计算最大总时长（用于时间刻度）；若全为空，则默认 5s 范围
        if rows:
            max_time_ms = max((r.total_duration_ms for r in rows), default=0)
            if max_time_ms <= 0:
                max_time_ms = 5000
        else:
            max_time_ms = 5000

        track_area_top = self._ruler_height

        # 无轨道
        if not rows:
            x_extent = float(self._label_width + 300)
            view = self.viewport()
            if view is not None:
                vw = view.width()
                if vw > 0:
                    x_extent = max(x_extent, float(vw))

            self._draw_time_ruler_and_grid(
                font,
                max_time_ms,
                x_extent=x_extent,
                grid_bottom=self._ruler_height + self._row_height,
            )

            y_top = track_area_top

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

            total_height = max(
                track_area_top + self._row_height + self._row_gap + btn_h + 20,
                240,
            )

            self._scene.setSceneRect(
                0,
                0,
                max(x_extent, 320.0),
                total_height,
            )
            return

        # 有轨道
        for row in rows:
            y_top = track_area_top + row_index * (self._row_height + self._row_gap)
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

            key = (row.mode_id or "", row.track_id or "")
            self._row_keys[row_index] = key

            rect_items: List[QGraphicsRectItem] = []
            row_x_max = float(self._label_width)

            for idx, nvs in enumerate(row.nodes):
                w = nvs.width

                # 根据 start_ms 映射到像素坐标
                x = float(self._label_width) + float(nvs.start_ms) * float(self._time_scale_px_per_ms)

                rect = QRectF(0, -self._node_height / 2.0, w, self._node_height)
                item = QGraphicsRectItem(rect)
                item.setPos(x, y_center)

                kind = (nvs.kind or "").lower()

                # 基础颜色
                if kind == "skill":
                    fill = QColor(80, 160, 230)        # 蓝色
                elif kind == "gateway":
                    # 网关节点：若有条件则高亮为紫色，否则橙色
                    if getattr(nvs, "has_condition", False):
                        fill = QColor(180, 100, 220)   # 紫色，高亮
                    else:
                        fill = QColor(240, 170, 60)    # 橙色
                else:
                    fill = QColor(130, 130, 130)

                item.setPen(self._normal_pen)
                item.setBrush(QBrush(fill))
                item.setToolTip(self._node_tooltip_meta(nvs))

                item.setData(0, row.mode_id or "")   # mode_id
                item.setData(1, row.track_id or "")  # track_id
                item.setData(2, idx)                 # node_index（行内索引，用于点击）
                item.setData(3, nvs.node_id)         # node_id

                self._scene.addItem(item)

                text_item2 = QGraphicsSimpleTextItem(nvs.label, parent=item)
                text_item2.setFont(font)
                tb2 = text_item2.boundingRect()
                text_x2 = (w - tb2.width()) / 2.0
                text_y2 = (-self._node_height / 2.0) + (self._node_height - tb2.height()) / 2.0
                text_item2.setPos(text_x2, text_y2)
                text_item2.setBrush(QColor(255, 255, 255))

                rect_items.append(item)
                row_x_max = max(row_x_max, x + w)

            self._track_items[key] = rect_items
            x_max = max(x_max, row_x_max)
            row_index += 1

        last_row_index = len(rows) - 1
        last_y_top = track_area_top + last_row_index * (self._row_height + self._row_gap)
        grid_bottom = last_y_top + self._row_height

        # 最后一条轨道之后的“新增轨道”按钮
        btn_w, btn_h = 64.0, 22.0
        btn_x = 6.0
        btn_y = last_y_top + self._row_height + self._row_gap / 2.0 - btn_h / 2.0
        plus_rect = QGraphicsRectItem(0, 0, btn_w, btn_h)
        plus_rect.setPos(btn_x, btn_y)
        plus_rect.setBrush(QBrush(QColor(80, 160, 80)))
        plus_rect.setPen(QPen(QColor(30, 80, 30), 1.0))
        plus_rect.setData(0, "add_track_button")

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

        # 时间尺/网格横向边界
        x_max_time = self._label_width + max_time_ms * self._time_scale_px_per_ms
        x_extent = max(x_max + 40, x_max_time + 40, self._label_width + 300)

        # 保证场景宽度至少覆盖当前视口宽度
        view = self.viewport()
        if view is not None:
            vw = view.width()
            if vw > 0:
                x_extent = max(x_extent, float(vw))

        total_height = max(btn_y + btn_h + 20.0, grid_bottom + self._row_gap)

        self._draw_time_ruler_and_grid(font, max_time_ms, x_extent, grid_bottom)

        self._scene.setSceneRect(
            0,
            0,
            x_extent,
            max(total_height, 240),
        )

        # 若之前有记忆的 current_key/index，则尝试恢复高亮
        if self._current_key is not None and self._current_index is not None:
            self._reapply_highlight()

    # ---------- 高亮当前节点 ----------

    def _clear_highlight(self) -> None:
        if self._current_item is not None:
            try:
                self._current_item.setPen(self._normal_pen)
                self._current_item.setZValue(0)
            except Exception:
                pass
        self._current_item = None

    def _reapply_highlight(self) -> None:
        key = self._current_key
        idx = self._current_index
        if key is None or idx is None:
            return
        items = self._track_items.get(key)
        if not items:
            return
        if idx < 0 or idx >= len(items):
            return
        self._apply_highlight(items[idx])

    def _apply_highlight(self, item: QGraphicsRectItem) -> None:
        # 清除旧的
        self._clear_highlight()
        # 应用于新的
        self._current_item = item
        try:
            item.setPen(self._highlight_pen)
            item.setZValue(10)
            # 自动滚动到节点附近
            rect = item.sceneBoundingRect().adjusted(-20, -20, 20, 20)
            self.ensureVisible(rect, xMargin=10, yMargin=10)
        except Exception:
            pass

    def set_current_node(self, mode_id: Optional[str], track_id: str, node_index: int) -> None:
        """
        高亮当前执行节点（由引擎回调驱动）：
        - mode_id: None/"" 表示全局轨道
        - track_id: 轨道 ID
        - node_index: 节点在轨道中的索引；若 <0 则清除高亮
        """
        if node_index < 0:
            # 清除高亮
            self._current_key = None
            self._current_index = None
            self._clear_highlight()
            return

        key = ((mode_id or "") or "", track_id or "")
        self._current_key = key
        self._current_index = int(node_index)

        items = self._track_items.get(key)
        if not items:
            # 当前视图中不含该轨道（可能在其他模式），不做处理
            return
        idx = int(node_index)
        if idx < 0 or idx >= len(items):
            return
        self._apply_highlight(items[idx])

    # ---------- 时间刻度线 + 网格 ----------

    def _draw_time_ruler_and_grid(
        self,
        font: QFont,
        max_time_ms: int,
        x_extent: float,
        grid_bottom: float,
    ) -> None:
        """
        绘制顶部标尺 + 垂直网格（步骤版本）：

        - 不再按“秒”刻度（0s / 5s / 10s），改为按 Step 刻度：
            * Step0, Step1, Step2, ... （整数步骤）
        - 每个 Step 的显示宽度由 _step_ms * _time_scale_px_per_ms 决定，
          必须与 build_timeline_layout 里使用的 STEP_MS 一致。
        - 轨道标题和步骤数字都是“纯装饰”，不参与交互，不可选中。
        """
        scale = float(self._time_scale_px_per_ms)
        if scale <= 0:
            return

        # 步骤对应的“显示毫秒”（与 build_timeline_layout 中 STEP_MS 保持一致）
        try:
            step_ms = int(getattr(self, "_step_ms", 1000) or 1000)
        except Exception:
            step_ms = 1000
        if step_ms <= 0:
            step_ms = 1000

        start_x = float(self._label_width)
        ruler_bottom = float(self._ruler_height) - 2.0

        if max_time_ms <= 0:
            max_time_ms = step_ms

        # 覆盖“场景中真实需要的时间范围”和“当前视口宽度反推的可见范围”
        visible_ms = int(max(0.0, (x_extent - start_x) / scale))
        max_ms = max(max_time_ms, visible_ms)

        import math
        max_step = max(1, int(math.ceil(max_ms / float(step_ms))))

        pen_grid = QPen(QColor(70, 70, 70), 1.0, Qt.DashLine)
        pen_ruler = QPen(QColor(150, 150, 150), 1.0)

        font_small = QFont(font)
        font_small.setPointSize(max(font.pointSize() - 1, 6))

        # 顶部横线
        self._scene.addLine(
            start_x,
            ruler_bottom,
            x_extent,
            ruler_bottom,
            pen_ruler,
        )

        for step in range(0, max_step + 1):
            t = step * step_ms
            x = start_x + t * scale
            if x > x_extent:
                break

            # 垂直网格线
            self._scene.addLine(
                x,
                ruler_bottom,
                x,
                grid_bottom,
                pen_grid,
            )

            # 刻度小线
            tick_len = 6.0
            self._scene.addLine(
                x,
                ruler_bottom,
                x,
                ruler_bottom - tick_len,
                pen_ruler,
            )

            # 步骤号文字：0, 1, 2, ...
            label = f"{step}"
            text_item = QGraphicsSimpleTextItem(label)
            text_item.setFont(font_small)
            text_item.setBrush(QColor(200, 200, 200))
            tb = text_item.boundingRect()
            tx = x - tb.width() / 2.0
            ty = ruler_bottom - tick_len - tb.height()
            text_item.setPos(tx, ty)

            # 关键：不接受鼠标，不可选中，不可获得焦点
            text_item.setAcceptedMouseButtons(Qt.NoButton)
            text_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            text_item.setFlag(QGraphicsItem.ItemIsFocusable, False)

            self._scene.addItem(text_item)

    # ---------- 鼠标事件：点击 & 拖拽 & 缩放 ----------

    def mousePressEvent(self, event) -> None:
        scene_pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(scene_pos, self.transform())

        # 新增轨道按钮：可能点到文字，也可能点到矩形
        if isinstance(item, QGraphicsSimpleTextItem) and isinstance(item.parentItem(), QGraphicsRectItem):
            item = item.parentItem()

        # 特殊处理：点击“裸的”文字（轨道名 / 步骤数字）时，什么也不做，直接刷新一遍
        #
        # 这些文字是我们自己加的 QGraphicsSimpleTextItem，parentItem() 为 None：
        # - 轨道标题：[模式:XXX] 轨道名
        # - 顶部步骤数字：0 / 1 / 2 / ...
        #
        # Qt 在点击它们时可能会应用选中/高亮效果，导致看起来“消失”；
        # 这里直接拦截点击并重建场景，保证它们按我们自己的颜色重新画出来。
        if isinstance(item, QGraphicsSimpleTextItem) and item.parentItem() is None:
            # 强制重建当前视图
            try:
                self.set_data(self._ctx, self._preset, self._current_mode_id)
            except Exception:
                pass
            return

        # 新增轨道按钮：矩形本体
        if isinstance(item, QGraphicsRectItem):
            tag = item.data(0)
            if tag == "add_track_button":
                mid = item.data(1)
                if isinstance(mid, str):
                    self.trackAddRequested.emit(mid)  # mid 为空串 => 全局轨道
                return

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
                    y = scene_pos.y() - self._ruler_height
                    if y < 0:
                        return
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

            # 纵向吸附到最近的行中心
            new_y = float(self._drag_row_y)
            row_height_total = self._row_height + self._row_gap
            if self._row_keys and row_height_total > 0:
                y = scene_pos.y() - self._ruler_height
                max_row_index = max(self._row_keys.keys())
                row_index = int(y // row_height_total)
                if row_index < 0:
                    row_index = 0
                if row_index > max_row_index:
                    row_index = max_row_index
                new_y = self._ruler_height + row_index * row_height_total + self._row_height / 2.0

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
                y = scene_pos.y() - self._ruler_height
                row_index = int(y // row_height_total)
                row_top = row_index * row_height_total
                if row_top <= y <= row_top + self._row_height:
                    dest_key = self._row_keys.get(row_index)

            # ---------- 同一轨道内拖拽：解释为“修改 step_index” ----------
            if dest_key is None or dest_key == src_key:
                # 计算新的 step_index（按拖拽后位置四舍五入到最近的 Step 列）
                rect = self._drag_item.rect()
                x_item = float(self._drag_item.pos().x())
                center_x = x_item + rect.width() / 2.0

                step_w = max(float(self._time_scale_px_per_ms) * float(self._step_ms), 1.0)
                rel = center_x - float(self._label_width)
                if rel < 0.0:
                    rel = 0.0
                new_step = int(round(rel / step_w))
                if new_step < 0:
                    new_step = 0

                # 将拖拽的 item 临时吸附到新的 Step 列（视觉上不留在“中间”）
                new_x = float(self._label_width) + new_step * step_w
                self._drag_item.setPos(new_x, self._drag_item.pos().y())

                # 发出步骤变化信号：由外层编辑器负责写回模型并刷新画布
                src_mid, src_tid = src_key
                nid = self._drag_item.data(3)
                if isinstance(nid, str):
                    self.stepChanged.emit(
                        src_mid or "",
                        src_tid or "",
                        nid,
                        int(new_step),
                    )

            # ---------- 跨轨道拖拽：仍然走“节点跨轨道移动”逻辑 ----------
            else:
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

    def wheelEvent(self, event: QWheelEvent) -> None:
        mods = QApplication.keyboardModifiers()
        if mods & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in(1.1)
            elif delta < 0:
                self.zoom_out(1.1)
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        if self._ctx is None or self._preset is None:
            return

        try:
            h = self.horizontalScrollBar().value()
            v = self.verticalScrollBar().value()
        except Exception:
            h = v = 0

        self.set_data(self._ctx, self._preset, self._current_mode_id)

        try:
            self.horizontalScrollBar().setValue(h)
            self.verticalScrollBar().setValue(v)
        except Exception:
            pass

    # ---------- 工具 ----------

    def _node_tooltip_meta(self, nvs: NodeVisualSpec) -> str:
        kind = (nvs.kind or "").lower()
        if kind == "skill":
            return f"SkillNode: {nvs.label}\nnode_id={nvs.node_id}, duration={nvs.duration_ms}ms"
        if kind == "gateway":
            lines = [
                f"GatewayNode: {nvs.label}",
                f"node_id={nvs.node_id}, duration={nvs.duration_ms}ms",
            ]
            if getattr(nvs, "has_condition", False) and getattr(nvs, "condition_name", ""):
                lines.append(f"condition={nvs.condition_name}")
            return "\n".join(lines)
        return f"Node: {nvs.label}\nnode_id={nvs.node_id}, duration={nvs.duration_ms}ms"