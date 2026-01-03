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
from core.models.skill import Skill
from rotation_editor.core.models import RotationPreset, Mode, Track, SkillNode, GatewayNode, Node


class TimelineCanvas(QGraphicsView):
    """
    多轨时间轴总览（QGraphicsView）：

    - set_data(ctx, preset, current_mode_id):
        - ctx: 用于查技能读条时间
        - preset: 当前 RotationPreset
        - current_mode_id: 当前模式 ID（None 或 "" 表示仅全局轨道）

    功能：
    - 显示全局轨道 + 当前模式下所有轨道的“时间轴”预览
    - 左键点击节点块 -> nodeClicked(mode_id, track_id, node_index)
    - 左键拖拽节点块（同一轨道内）：
        * 拖动过程中当前块紧贴鼠标，其他块“主动避让”、按插槽重新排布
        * 松开时发出 nodesReordered(mode_id, track_id, node_ids)，由外部重排 Track.nodes 顺序并刷新
    """

    nodeClicked = Signal(str, str, int)          # (mode_id, track_id, node_index)
    nodesReordered = Signal(str, str, list)      # (mode_id, track_id, node_ids)

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
        self._drag_row_key: Optional[Tuple[str, str]] = None  # (mode_id, track_id)
        self._drag_start_pos: QPointF = QPointF()             # item 的初始 pos()
        self._drag_start_scene_pos: QPointF = QPointF()       # 鼠标初始场景坐标
        self._drag_row_y: float = 0.0                         # 当前行 y（保持不变）

        # 记录每个轨道的 rect items，表示当前“插槽顺序”（用于拖拽重排）
        # key: (mode_id, track_id) -> List[QGraphicsRectItem]
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
        self._ctx = ctx
        self._preset = preset
        self._current_mode_id = (current_mode_id or "").strip() or None

        if ctx is None or preset is None:
            return

        # 收集技能读条时间
        skills_by_id: Dict[str, Skill] = {}
        try:
            for s in getattr(ctx.skills, "skills", []) or []:
                if s.id:
                    skills_by_id[s.id] = s
        except Exception:
            pass

        row = 0
        x_max = 0.0

        font = QFont(self.font())
        font.setPointSize(9)

        # -------- helper: 绘制一条轨道，并记录 rect items --------
        def draw_track_row(
            track: Track,
            title_prefix: str,
            row_index: int,
            mode_id_for_track: str,
        ) -> None:
            nonlocal x_max

            y_top = row_index * (self._row_height + self._row_gap)
            y_center = y_top + self._row_height / 2.0

            # 轨道标签
            title = f"{title_prefix}{track.name or '(未命名)'}"
            label_item = QGraphicsSimpleTextItem(title)
            label_item.setFont(font)
            label_item.setBrush(QColor(230, 230, 230))
            label_item.setPos(4, y_top + (self._row_height - label_item.boundingRect().height()) / 2.0)
            self._scene.addItem(label_item)

            # 计算每个节点时长（毫秒）
            durations: List[int] = []
            for n in track.nodes:
                d = 1000  # 默认
                try:
                    if isinstance(n, SkillNode):
                        if n.override_cast_ms is not None and n.override_cast_ms > 0:
                            d = int(n.override_cast_ms)
                        else:
                            s = skills_by_id.get(n.skill_id or "", None)
                            if s is not None and getattr(s.cast, "readbar_ms", 0) > 0:
                                d = int(s.cast.readbar_ms)
                    elif isinstance(n, GatewayNode):
                        d = 500
                    else:
                        d = 800
                except Exception:
                    d = 1000
                durations.append(d)

            if not durations:
                return

            max_d = max(durations)
            # 按比例映射到 [0.6*base, 1.6*base]
            widths: List[float] = []
            for d in durations:
                if max_d <= 0:
                    scale = 1.0
                else:
                    ratio = d / max_d
                    scale = 0.5 + 0.5 * ratio
                w = self._base_width * scale
                if w < self._base_width * 0.6:
                    w = self._base_width * 0.6
                if w > self._base_width * 1.6:
                    w = self._base_width * 1.6
                widths.append(w)

            # 绘制节点块（局部 rect + 全局 pos）
            x = self._label_width
            key = (mode_id_for_track, track.id or "")
            row_items: List[QGraphicsRectItem] = []

            for idx, n in enumerate(track.nodes):
                w = widths[idx] if idx < len(widths) else self._base_width

                # 局部 rect（以 (0,0) 左上，高度为 _node_height），中心在 Y=0
                rect = QRectF(0, -self._node_height / 2.0, w, self._node_height)
                item = QGraphicsRectItem(rect)
                # 全局位置：中心在 (x + w/2, y_center)；这里简化为 pos=(x, y_center)
                item.setPos(x, y_center)

                # 颜色区分类型
                if isinstance(n, SkillNode):
                    fill = QColor(80, 160, 230)      # 较亮的蓝
                elif isinstance(n, GatewayNode):
                    fill = QColor(240, 170, 60)      # 亮橙
                else:
                    fill = QColor(130, 130, 130)

                pen = QPen(QColor(210, 210, 210), 1.0)
                item.setPen(pen)
                item.setBrush(QBrush(fill))
                item.setToolTip(self._node_tooltip(n))

                # 存储元信息：mode_id / track_id / node_index / node_id
                item.setData(0, mode_id_for_track)
                item.setData(1, track.id or "")
                item.setData(2, idx)
                item.setData(3, getattr(n, "id", ""))

                self._scene.addItem(item)

                # 文本作为子项，局部坐标内居中
                label = getattr(n, "label", "") or ""
                if not label:
                    if isinstance(n, SkillNode):
                        label = "Skill"
                    elif isinstance(n, GatewayNode):
                        label = "GW"
                    else:
                        label = getattr(n, "kind", "") or "N"

                text_item = QGraphicsSimpleTextItem(label, parent=item)
                text_item.setFont(font)
                tb = text_item.boundingRect()
                text_x = (w - tb.width()) / 2.0
                text_y = (-self._node_height / 2.0) + (self._node_height - tb.height()) / 2.0
                text_item.setPos(text_x, text_y)
                text_item.setBrush(QColor(255, 255, 255))

                row_items.append(item)
                x += w + self._x_gap

            if x > x_max:
                x_max = x
            self._track_items[key] = row_items

        # -------- 全局轨道 --------
        for gtrack in preset.global_tracks or []:
            draw_track_row(gtrack, title_prefix="[全局] ", row_index=row, mode_id_for_track="")
            row += 1

        # -------- 当前模式轨道 --------
        mid = (self._current_mode_id or "").strip()
        if mid:
            mode: Optional[Mode] = None
            for m in preset.modes or []:
                if m.id == mid:
                    mode = m
                    break
            if mode is not None:
                for t in mode.tracks or []:
                    draw_track_row(
                        t,
                        title_prefix=f"[模式:{mode.name}] ",
                        row_index=row,
                        mode_id_for_track=mode.id or "",
                    )
                    row += 1

        # 设置 scene 边界
        total_height = row * (self._row_height + self._row_gap)
        self._scene.setSceneRect(
            0,
            0,
            max(x_max + 40, self._label_width + 300),
            max(total_height, 240),
        )

    # ---------- 行内“插槽”重排（主动避让） ----------

    def _reflow_row_for_drag(self, key: Tuple[str, str], drag_item: QGraphicsRectItem) -> None:
        """
        根据 drag_item 当前的 X 坐标，在该轨道内重新计算“插槽顺序”，
        让其他节点自动避让，始终不重叠。
        """
        items = self._track_items.get(key)
        if not items or drag_item not in items:
            return

        # 当前行 Y（所有块的 y 相同）
        row_y = drag_item.pos().y()
        # 拖拽目标的中心 X
        drag_w = drag_item.rect().width()
        drag_center_x = drag_item.pos().x() + drag_w / 2.0

        # 其他节点：保持当前 items 顺序的相对关系
        others = [it for it in items if it is not drag_item]

        # 计算“插槽”序列：positions[0..n-1] 为“插槽中心”的 X 坐标（不含拖拽）
        # 但为了简单，我们按当前 others 的顺序，从左到右依次排开。
        slot_centers: List[float] = []
        x = self._label_width
        for it in others:
            w = it.rect().width()
            center = x + w / 2.0
            slot_centers.append(center)
            x += w + self._x_gap

        # 拖拽节点本身也需要一个插槽：我们允许它插入到 [0..len(others)] 的任何位置。
        # 对于每个可能位置 k，插入后将形成新的顺序；我们选择使拖拽中心最近的插槽位置。
        best_k = 0
        best_diff = float("inf")

        # 预先计算“拖拽节点宽度”插入后的位置
        for k in range(len(others) + 1):
            # 重新从左到右计算插槽中心，包括拖拽节点
            x_tmp = self._label_width
            centers_tmp: List[Tuple[QGraphicsRectItem, float]] = []

            # 前半部分 others[0:k]
            for it in others[:k]:
                w_it = it.rect().width()
                c_it = x_tmp + w_it / 2.0
                centers_tmp.append((it, c_it))
                x_tmp += w_it + self._x_gap

            # 拖拽节点
            c_drag = x_tmp + drag_w / 2.0
            centers_tmp.append((drag_item, c_drag))
            x_tmp += drag_w + self._x_gap

            # 后半部分 others[k:]
            for it in others[k:]:
                w_it = it.rect().width()
                c_it = x_tmp + w_it / 2.0
                centers_tmp.append((it, c_it))
                x_tmp += w_it + self._x_gap

            # 此时 centers_tmp 里，拖拽节点的插槽中心为 c_drag
            diff = abs(c_drag - drag_center_x)
            if diff < best_diff:
                best_diff = diff
                best_k = k

        # 计算最终顺序：在 best_k 位置插入 drag_item
        new_order: List[QGraphicsRectItem] = []
        new_order.extend(others[:best_k])
        new_order.append(drag_item)
        new_order.extend(others[best_k:])

        # 按新顺序重新排布每个块的位置（插槽排布），但拖拽块的 X 使用当前拖拽位置
        x = self._label_width
        for idx, it in enumerate(new_order):
            w = it.rect().width()
            if it is drag_item:
                # 拖拽块：仅锁定 Y，X 保持跟随鼠标
                it.setPos(drag_item.pos().x(), row_y)
            else:
                # 其他块按插槽对齐
                it.setPos(x, row_y)
            # 更新 node_index 元信息，供 nodeClicked 使用
            it.setData(2, idx)
            x += w + self._x_gap

        self._track_items[key] = new_order

    # ---------- 鼠标事件：点击 & 拖拽 ----------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            item = self._scene.itemAt(scene_pos, self.transform())

            # 如果点到了文字，取父 rect
            if isinstance(item, QGraphicsSimpleTextItem) and isinstance(item.parentItem(), QGraphicsRectItem):
                item = item.parentItem()

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
                    # 点击选中
                    self.nodeClicked.emit(mid, tid, idx)
                else:
                    self._drag_row_key = None
            else:
                self._drag_item = None
                self._drag_row_key = None

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_item is not None and self._drag_row_key is not None:
            scene_pos = self.mapToScene(event.pos())
            dx = scene_pos.x() - self._drag_start_scene_pos.x()

            # 水平移动 rect；纵向锁定在原行
            new_x = self._drag_start_pos.x() + dx
            if new_x < self._label_width:
                new_x = self._label_width
            self._drag_item.setPos(new_x, self._drag_row_y)

            # 动态重排该行：其它节点会“主动避让”
            self._reflow_row_for_drag(self._drag_row_key, self._drag_item)
            # 不调用 super()，避免 ScrollHandDrag 抢走拖动
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_item is not None and self._drag_row_key is not None:
            key = self._drag_row_key
            items = self._track_items.get(key, [])
            if items:
                # 此时 items 已按 _reflow_row_for_drag() 的顺序排好
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

    def _node_tooltip(self, n: Node) -> str:
        if isinstance(n, SkillNode):
            return f"SkillNode: {n.label or ''}\nskill_id={n.skill_id}"
        if isinstance(n, GatewayNode):
            return (
                f"GatewayNode: {n.label or ''}\n"
                f"action={n.action}, target_mode_id={n.target_mode_id or ''}"
            )
        return f"Node: {getattr(n, 'kind', '')}"