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