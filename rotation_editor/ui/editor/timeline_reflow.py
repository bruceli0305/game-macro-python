from __future__ import annotations

from typing import List

from PySide6.QtWidgets import QGraphicsRectItem


def reflow_row_items_for_drag(
    items: List[QGraphicsRectItem],
    drag_item: QGraphicsRectItem,
    label_width: float,
    x_gap: float,
) -> List[QGraphicsRectItem]:
    """
    根据 drag_item 当前的 X 坐标，在该轨道内重新计算“插槽顺序”，
    让其他节点自动避让，始终不重叠。

    算法说明（与最初在 TimelineCanvas 里的版本等价）：
    1. 把 drag_item 从 items 中拿出来，其余称为 others（保持原顺序）。
    2. 对于所有可能的插入位置 k ∈ [0, len(others)]：
       - 从 label_width 开始，按 others[0:k]、drag_item、others[k:] 的顺序
         重新“虚拟排布”，计算每个节点的中心位置；
       - 记拖拽节点虚拟中心为 c_drag_virtual；
       - 与当前实际中心 drag_center_x 的差值 |c_drag_virtual - drag_center_x| 越小越好。
    3. 选取差值最小的插入位置 best_k，构造 new_order = others[:best_k] + [drag_item] + others[best_k:]。
    4. 重新排布：
       - 从 label_width 开始，依次设置其它节点的 X；
       - 拖拽节点的 X 不变（仅锁定 Y），保证跟随鼠标；
       - 同时更新每个 item 的 data(2) 为新的 node_index。

    返回：
    - new_order：新的 items 顺序（包含 drag_item）。
    """
    if not items or drag_item not in items:
        return items

    row_y = float(drag_item.pos().y())
    drag_w = float(drag_item.rect().width())
    drag_center_x = float(drag_item.pos().x()) + drag_w / 2.0

    others = [it for it in items if it is not drag_item]
    if not others:
        # 只有一个节点，无需重排
        drag_item.setPos(drag_item.pos().x(), row_y)
        drag_item.setData(2, 0)
        return [drag_item]

    best_k = 0
    best_diff = float("inf")

    # 枚举插入位置 k
    for k in range(len(others) + 1):
        x_tmp = float(label_width)

        # 前半部分 others[0:k]
        for it in others[:k]:
            w_it = float(it.rect().width())
            x_tmp += w_it + float(x_gap)

        # 拖拽节点的虚拟中心
        c_drag_virtual = x_tmp + drag_w / 2.0

        diff = abs(c_drag_virtual - drag_center_x)
        if diff < best_diff:
            best_diff = diff
            best_k = k

    # 计算最终顺序
    new_order: List[QGraphicsRectItem] = []
    new_order.extend(others[:best_k])
    new_order.append(drag_item)
    new_order.extend(others[best_k:])

    # 重新排布位置：拖拽节点保持当前 X，Y 锁在行内；其它按插槽对齐
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