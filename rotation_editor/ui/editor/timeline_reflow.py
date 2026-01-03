from __future__ import annotations

from typing import List

from PySide6.QtWidgets import QGraphicsRectItem


def _compute_best_insert_index(
    others: List[QGraphicsRectItem],
    drag_width: float,
    drag_center_x: float,
    label_width: float,
    x_gap: float,
) -> int:
    """
    核心插槽算法：给定其它节点（不含 drag_item）、拖拽块宽度/当前中心位置，
    枚举插入位置 k，找出虚拟布局中拖拽块中心最接近当前中心的位置。
    """
    if not others:
        return 0

    best_k = 0
    best_diff = float("inf")

    for k in range(len(others) + 1):
        x_tmp = float(label_width)

        # 前半部分 others[0:k]
        for it in others[:k]:
            w_it = float(it.rect().width())
            x_tmp += w_it + float(x_gap)

        # 拖拽节点的虚拟中心
        c_drag_virtual = x_tmp + float(drag_width) / 2.0

        diff = abs(c_drag_virtual - float(drag_center_x))
        if diff < best_diff:
            best_diff = diff
            best_k = k

    return best_k


def reflow_row_items_for_drag(
    items: List[QGraphicsRectItem],
    drag_item: QGraphicsRectItem,
    label_width: float,
    x_gap: float,
) -> List[QGraphicsRectItem]:
    """
    根据 drag_item 当前的 X 坐标，在该轨道内重新计算“插槽顺序”，
    让其他节点自动避让，始终不重叠。

    算法：
    1. 把 drag_item 从 items 中拿出来，其余称为 others（保持原顺序）。
    2. 用 _compute_best_insert_index 计算最佳插入位置 best_k。
    3. new_order = others[:best_k] + [drag_item] + others[best_k:].
    4. 重新排布：
       - 从 label_width 开始，依次设置其它节点 X；
       - 拖拽节点的 X 不变（仅锁行内 Y）；
       - 更新每个 item 的 data(2) 为新的 node_index。
    """
    if not items or drag_item not in items:
        return items

    row_y = float(drag_item.pos().y())
    drag_w = float(drag_item.rect().width())
    drag_center_x = float(drag_item.pos().x()) + drag_w / 2.0

    others = [it for it in items if it is not drag_item]
    if not others:
        drag_item.setPos(drag_item.pos().x(), row_y)
        drag_item.setData(2, 0)
        return [drag_item]

    best_k = _compute_best_insert_index(others, drag_w, drag_center_x, label_width, x_gap)

    new_order: List[QGraphicsRectItem] = []
    new_order.extend(others[:best_k])
    new_order.append(drag_item)
    new_order.extend(others[best_k:])

    x = float(label_width)
    for idx, it in enumerate(new_order):
        w = float(it.rect().width())
        if it is drag_item:
            it.setPos(float(it.pos().x()), row_y)
        else:
            it.setPos(x, row_y)
        it.setData(2, idx)
        x += w + float(x_gap)

    return new_order


def compute_insert_index_for_cross_track(
    dest_items: List[QGraphicsRectItem],
    drag_width: float,
    drag_center_x: float,
    label_width: float,
    x_gap: float,
) -> int:
    """
    供跨轨道拖拽使用：给定目标轨道当前的 items（不含 drag_item），
    以及拖拽节点的当前宽度和中心位置，计算应插入的索引位置。
    """
    return _compute_best_insert_index(dest_items, drag_width, drag_center_x, label_width, x_gap)