from __future__ import annotations

from typing import Optional, List, Dict, Tuple

from PySide6.QtCore import Qt, QRectF, Signal, QPointF, QVariantAnimation, QEasingCurve
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
from rotation_editor.core.models import RotationPreset
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

    - Step 网格：竖向虚线表示 step 边界（0,1,2,...），数字标在区间中点（1 表示 0~1）。
    - 节点绘制在“区间中心”，即永远在两条线中间，而不是在线上。
    - 当前约束：同一轨道的同一 step 只能有 1 个节点。
      * 同轨拖拽：若目标 step 已被占用，释放后弹回原 step。
      * 跨轨拖拽：若目标轨道同 step 已被占用，释放后不跨轨，弹回原轨道原 step。
      * 跨轨成功时，会有一个平滑的“飞过去”动画（OutCubic 缓出），增加阻尼感。
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

        # 垂直上下 lane 偏移量（目前容量为 1，但保留参数）
        self._lane_offset = 10.0

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
        # 新增：拖拽过程中的平滑位置（阻尼用）
        self._drag_smoothed_pos: Optional[QPointF] = None
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
            * 每个 TrackVisualSpec 包含 nodes 的 start_ms / width / lane。
        - 本方法将节点绘制在每个 step 区间的中点，而不是 step 边界线上。
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

                # 将节点绘制在 step 区间中点：
                center_ms = float(nvs.start_ms) + float(self._step_ms) / 2.0
                x_center = float(self._label_width) + center_ms * float(self._time_scale_px_per_ms)
                x = x_center - w / 2.0

                rect = QRectF(0, -self._node_height / 2.0, w, self._node_height)
                item = QGraphicsRectItem(rect)

                # 垂直 lane 布局：-1=居中，0=上，1=下
                lane = getattr(nvs, "lane", -1)
                if lane < 0:
                    y_item = y_center
                elif lane == 0:
                    y_item = y_center - self._lane_offset
                else:
                    y_item = y_center + self._lane_offset

                item.setPos(x, y_item)

                kind = (nvs.kind or "").lower()

                # 基础颜色
                if kind == "skill":
                    fill = QColor(80, 160, 230)        # 蓝色
                elif kind == "gateway":
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
                item.setData(2, idx)                 # node_index（行内索引）
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
        self._clear_highlight()
        self._current_item = item
        try:
            item.setPen(self._highlight_pen)
            item.setZValue(10)
            rect = item.sceneBoundingRect().adjusted(-20, -20, 20, 20)
            self.ensureVisible(rect, xMargin=10, yMargin=10)
        except Exception:
            pass

    def set_current_node(self, mode_id: Optional[str], track_id: str, node_index: int) -> None:
        if node_index < 0:
            self._current_key = None
            self._current_index = None
            self._clear_highlight()
            return

        key = ((mode_id or "") or "", track_id or "")
        self._current_key = key
        self._current_index = int(node_index)

        items = self._track_items.get(key)
        if not items:
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
        scale = float(self._time_scale_px_per_ms)
        if scale <= 0:
            return

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

        # 1) 画所有竖线（step 边界）+ 小刻度
        tick_len = 6.0
        step_x_positions: List[float] = []

        for step in range(0, max_step + 1):
            t = step * step_ms
            x = start_x + t * scale
            if x > x_extent:
                break

            step_x_positions.append(x)

            self._scene.addLine(
                x,
                ruler_bottom,
                x,
                grid_bottom,
                pen_grid,
            )

            self._scene.addLine(
                x,
                ruler_bottom,
                x,
                ruler_bottom - tick_len,
                pen_ruler,
            )

        # 2) 区间数字：1..N，画在两个 step_x_positions 之间的中点
        for step in range(1, len(step_x_positions)):
            x_left = step_x_positions[step - 1]
            x_right = step_x_positions[step]
            x_mid = (x_left + x_right) / 2.0

            label = f"{step}"
            text_item = QGraphicsSimpleTextItem(label)
            text_item.setFont(font_small)
            text_item.setBrush(QColor(200, 200, 200))
            tb = text_item.boundingRect()
            tx = x_mid - tb.width() / 2.0
            ty = ruler_bottom - tick_len - tb.height()
            text_item.setPos(tx, ty)

            text_item.setAcceptedMouseButtons(Qt.NoButton)
            text_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            text_item.setFlag(QGraphicsItem.ItemIsFocusable, False)

            self._scene.addItem(text_item)

    # ---------- 拖拽 & 缩放 ----------

    def mousePressEvent(self, event) -> None:
        scene_pos = self.mapToScene(event.pos())
        item = self._scene.itemAt(scene_pos, self.transform())

        # 新增轨道按钮：可能点到文字，也可能点到矩形
        if isinstance(item, QGraphicsSimpleTextItem) and isinstance(item.parentItem(), QGraphicsRectItem):
            item = item.parentItem()

        # 点击“裸的”文字（轨道名 / 步骤数字）时，仅刷新，不参与拖拽
        if isinstance(item, QGraphicsSimpleTextItem) and item.parentItem() is None:
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
                    self.trackAddRequested.emit(mid)
                return

        if event.button() == Qt.LeftButton:
            if isinstance(item, QGraphicsRectItem):
                self._drag_item = item
                self._drag_start_pos = item.pos()
                self._drag_start_scene_pos = scene_pos
                self._drag_row_y = item.pos().y()
                self._drag_smoothed_pos = QPointF(item.pos())  # 新增：初始平滑位置
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
        """
        拖拽过程：
        - 节点实时跟随鼠标移动；
        - 垂直方向吸附到最近轨道行中心；
        - 水平方向靠近某个 step 区间中心时，会“磁吸”到该中心；
        - 位置更新采用阻尼平滑（当前值向目标值缓动），避免生硬和抖动。
        """
        if self._drag_item is not None and self._drag_row_key is not None:
            scene_pos = self.mapToScene(event.pos())
            dx = scene_pos.x() - self._drag_start_scene_pos.x()

            # 1) 计算理想目标位置（未加阻尼）
            # 基础水平移动
            target_x = self._drag_start_pos.x() + dx
            if target_x < self._label_width:
                target_x = self._label_width

            # 垂直吸附到最近轨道行中心
            target_y = float(self._drag_row_y)
            row_height_total = self._row_height + self._row_gap
            if self._row_keys and row_height_total > 0:
                y_mouse = scene_pos.y() - self._ruler_height
                max_row_index = max(self._row_keys.keys())
                row_index = int(y_mouse // row_height_total)
                if row_index < 0:
                    row_index = 0
                if row_index > max_row_index:
                    row_index = max_row_index
                target_y = self._ruler_height + row_index * row_height_total + self._row_height / 2.0

            # 水平 Step “磁吸”：基于区间中心 (step + 0.5)
            rect = self._drag_item.rect()
            step_w = max(float(self._time_scale_px_per_ms) * float(self._step_ms), 1.0)
            if step_w > 0:
                center_x = target_x + rect.width() / 2.0
                rel = center_x - float(self._label_width)
                # cell index: 0 => 第一个区间 [0,1) 的中心
                raw_cell = rel / step_w - 0.5
                nearest = round(raw_cell)
                diff_px = abs(raw_cell - nearest) * step_w
                snap_threshold = step_w * 0.25  # 可调：越小越“难”吸附

                if diff_px <= snap_threshold:
                    snapped_center_x = float(self._label_width) + (nearest + 0.5) * step_w
                    target_x = snapped_center_x - rect.width() / 2.0

            # 2) 阻尼平滑：当前平滑位置向 target 缓动
            if self._drag_smoothed_pos is None:
                self._drag_smoothed_pos = QPointF(target_x, target_y)
            else:
                # 阻尼系数：0.3~0.5 之间，越大越“跟手”，越小越“慵懒”
                alpha = 0.35
                cur = self._drag_smoothed_pos
                new_x = float(cur.x()) + (target_x - float(cur.x())) * alpha
                new_y = float(cur.y()) + (target_y - float(cur.y())) * alpha
                self._drag_smoothed_pos = QPointF(new_x, new_y)

            self._drag_item.setPos(self._drag_smoothed_pos)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_item is not None and self._drag_row_key is not None:
            src_key = self._drag_row_key
            rect = self._drag_item.rect()
            item_pos = self._drag_item.pos()

            # 使用节点中心 Y 判定落入哪条轨道
            center_y = float(item_pos.y())
            row_height_total = self._row_height + self._row_gap
            dest_key: Optional[Tuple[str, str]] = None
            dest_row_index: Optional[int] = None
            if row_height_total > 0:
                y_rel = center_y - self._ruler_height
                row_index = int(y_rel // row_height_total)
                row_top = row_index * row_height_total
                if row_top <= y_rel <= row_top + self._row_height:
                    dest_key = self._row_keys.get(row_index)
                    dest_row_index = row_index

            # ---------- 同一轨道内拖拽：修改 step_index（若目标空闲） ----------
            if dest_key is None or dest_key == src_key:
                step_w = max(float(self._time_scale_px_per_ms) * float(self._step_ms), 1.0)
                center_x = float(item_pos.x()) + rect.width() / 2.0
                rel = center_x - float(self._label_width)
                if rel < 0.0:
                    rel = 0.0
                # 按“区间中心”计算 cell index：0 => 第一个区间 [0,1)
                raw_cell = rel / step_w - 0.5
                new_step = int(round(raw_cell))
                if new_step < 0:
                    new_step = 0

                src_mid, src_tid = src_key
                nid = self._drag_item.data(3)
                if isinstance(nid, str):
                    orig_step = self._get_node_step_from_model(src_mid or "", src_tid or "", nid or "")
                    if new_step != orig_step and self._is_step_occupied_in_model(src_mid or "", src_tid or "", new_step, nid or ""):
                        target_step = orig_step
                    else:
                        target_step = new_step

                    self.stepChanged.emit(
                        src_mid or "",
                        src_tid or "",
                        nid,
                        int(target_step),
                    )

            # ---------- 跨轨道拖拽：节点跨轨道移动（若目标轨道该 step 空闲） ----------
            else:
                src_mid, src_tid = src_key
                dst_mid, dst_tid = dest_key
                nid = self._drag_item.data(3)

                if isinstance(nid, str):
                    orig_step = self._get_node_step_from_model(src_mid or "", src_tid or "", nid or "")

                    # 若目标轨道该 step 已被其它节点占用，则不跨轨，弹回原轨原 step
                    if self._is_step_occupied_in_model(dst_mid or "", dst_tid or "", orig_step, nid or ""):
                        self.stepChanged.emit(
                            src_mid or "",
                            src_tid or "",
                            nid,
                            int(orig_step),
                        )
                    else:
                        # 目标轨道该 step 空闲：允许跨轨，并做一次“飞过去”的动画
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

                        # 计算目标轨道该 step 的视觉位置（用于动画终点）
                        if dest_row_index is None:
                            # 兜底：再根据 dest_key 查一次行号
                            for i, k in self._row_keys.items():
                                if k == dest_key:
                                    dest_row_index = i
                                    break

                        if dest_row_index is not None:
                            dest_y = self._ruler_height + dest_row_index * row_height_total + self._row_height / 2.0
                        else:
                            dest_y = item_pos.y()

                        step_w = max(float(self._time_scale_px_per_ms) * float(self._step_ms), 1.0)
                        target_center_x = float(self._label_width) + (orig_step + 0.5) * step_w
                        target_x = target_center_x - rect.width() / 2.0

                        # 做一次 OutCubic 的动画，然后再真正发 nodeCrossMoved
                        def _on_finished():
                            self.nodeCrossMoved.emit(
                                src_mid or "",
                                src_tid or "",
                                dst_mid or "",
                                dst_tid or "",
                                int(dst_index),
                                nid,
                            )

                        self._animate_item_to(self._drag_item, QPointF(target_x, dest_y), 160, _on_finished)

            self._drag_item = None
            self._drag_row_key = None
            self._drag_smoothed_pos = None  # 新增
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

    # ---------- 模型辅助：查询 Track / 节点 Step / Step 是否占用 ----------

    def _find_track_for_key(self, mode_id: str, track_id: str):
        if self._preset is None:
            return None
        tid = (track_id or "").strip()
        if not tid:
            return None
        mid = (mode_id or "").strip()
        if not mid:
            # global
            for t in (self._preset.global_tracks or []):
                if (t.id or "").strip() == tid:
                    return t
            return None
        # mode
        for m in (self._preset.modes or []):
            if (m.id or "").strip() == mid:
                for t in (m.tracks or []):
                    if (t.id or "").strip() == tid:
                        return t
                break
        return None

    def _get_node_step_from_model(self, mode_id: str, track_id: str, node_id: str) -> int:
        tr = self._find_track_for_key(mode_id, track_id)
        if tr is None:
            return 0
        nid = (node_id or "").strip()
        if not nid:
            return 0
        for n in (tr.nodes or []):
            if (getattr(n, "id", "") or "").strip() == nid:
                try:
                    s = int(getattr(n, "step_index", 0) or 0)
                except Exception:
                    s = 0
                if s < 0:
                    s = 0
                return s
        return 0

    def _is_step_occupied_in_model(self, mode_id: str, track_id: str, step_index: int, exclude_node_id: str) -> bool:
        tr = self._find_track_for_key(mode_id, track_id)
        if tr is None:
            return False
        nid_ex = (exclude_node_id or "").strip()
        for n in (tr.nodes or []):
            nid = (getattr(n, "id", "") or "").strip()
            if not nid or nid == nid_ex:
                continue
            try:
                s = int(getattr(n, "step_index", 0) or 0)
            except Exception:
                s = 0
            if s < 0:
                s = 0
            if s == int(step_index):
                return True
        return False

    # ---------- 动画辅助 ----------

    def _animate_item_to(self, item: QGraphicsRectItem, target_pos: QPointF, duration_ms: int, on_finished) -> None:
        """
        用 QVariantAnimation 平滑移动一个节点到指定位置，然后调用 on_finished。
        仅用于跨轨成功时的“飞过去”动画。
        """
        try:
            start_pos = item.pos()
        except Exception:
            # 如果 item 已经无效，就直接回调
            on_finished()
            return

        anim = QVariantAnimation(self)
        anim.setDuration(max(30, int(duration_ms)))
        anim.setStartValue(start_pos)
        anim.setEndValue(target_pos)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _on_value(v):
            try:
                item.setPos(v)
            except Exception:
                pass

        def _on_finished_internal():
            try:
                on_finished()
            except Exception:
                pass

        anim.valueChanged.connect(_on_value)
        anim.finished.connect(_on_finished_internal)
        anim.start(QVariantAnimation.DeleteWhenStopped)

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