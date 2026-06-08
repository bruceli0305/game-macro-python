"""
可视化条件构建器 — 用点选方式组合释放条件。

支持的条件类型：
1. 技能图标颜色匹配（CD检测）— PixelMatchSkill
2. 点位颜色匹配 — PixelMatchPoint
3. 施法条变化 — CastBarChanged
4. 技能指标 ≥ N — SkillMetricGE

组合方式：
- AND（全部满足）
- OR（任一满足）
- NOT（取反）

UI 设计：
┌──────────────────────────────────────────────────┐
│  释放条件:                                        │
│  ┌──────────────────────────────────────────────┐ │
│  │  [全部满足 ▼]                                  │ │
│  │  ① 技能A 图标颜色 ≈ #FF0000 (容差10)  [×]    │ │
│  │  ② 点位X 颜色 ≈ #00FF00 (容差15)     [×]     │ │
│  │  ③ 非: 技能B 已释放≥3次              [×]     │ │
│  └──────────────────────────────────────────────┘ │
│  [+ 添加条件]                                     │
└──────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QFrame,
    QSizePolicy,
    QMenu,
    QInputDialog,
)

log = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AST 构建工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ast_and(*children: dict) -> dict:
    return {"type": "and", "children": list(children)}


def _ast_or(*children: dict) -> dict:
    return {"type": "or", "children": list(children)}


def _ast_not(child: dict) -> dict:
    return {"type": "not", "child": child}


def _ast_pixel_skill(skill_id: str, tolerance: int = 10) -> dict:
    return {"type": "pixel_skill", "skill_id": skill_id, "tolerance": tolerance}


def _ast_pixel_point(point_id: str, tolerance: int = 10) -> dict:
    return {"type": "pixel_point", "point_id": point_id, "tolerance": tolerance}


def _ast_cast_bar(point_id: str, tolerance: int = 10) -> dict:
    return {"type": "cast_bar_changed", "point_id": point_id, "tolerance": tolerance}


def _ast_skill_metric(skill_id: str, metric: str, count: int) -> dict:
    return {"type": "skill_metric_ge", "skill_id": skill_id, "metric": metric, "count": count}


METRIC_LABELS = {
    "success": "释放成功",
    "attempt_started": "开始尝试",
    "key_sent_ok": "按键发送",
    "cast_started": "进入施法",
    "fail": "失败",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  单个条件行
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ConditionRow(QFrame):
    """
    单个条件的编辑行。

    根据条件类型显示不同的表单：
    - pixel_skill: 技能选择 + 容差
    - pixel_point: 点位选择 + 容差
    - cast_bar_changed: 点位选择 + 容差
    - skill_metric_ge: 技能选择 + 指标类型 + 次数

    每行都有 NOT 取反开关和删除按钮。
    """

    changed = Signal()
    deleted = Signal()

    def __init__(
        self,
        *,
        cond_type: str = "pixel_skill",
        available_skills: List[Dict[str, str]] = None,
        available_points: List[Dict[str, str]] = None,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._cond_type = cond_type
        self._available_skills = available_skills or []
        self._available_points = available_points or []
        self._negated = False

        self.setFrameShape(QFrame.NoFrame)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # NOT 取反开关
        self._btn_not = QPushButton("是", self)
        self._btn_not.setFixedWidth(30)
        self._btn_not.setToolTip("点击切换为「非」（取反条件）")
        self._btn_not.setStyleSheet("QPushButton { font-size: 10px; }")
        self._btn_not.clicked.connect(self._toggle_not)
        layout.addWidget(self._btn_not)

        # 条件类型标签
        self._lbl_type = QLabel(self._type_label(), self)
        self._lbl_type.setFixedWidth(70)
        layout.addWidget(self._lbl_type)

        # 动态表单区
        self._form_container = QWidget(self)
        self._form_layout = QHBoxLayout(self._form_container)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.setSpacing(4)
        layout.addWidget(self._form_container, 1)

        self._build_form()

        # 删除按钮
        btn_del = QPushButton("×", self)
        btn_del.setFixedSize(20, 20)
        btn_del.setToolTip("删除此条件")
        btn_del.clicked.connect(self.deleted.emit)
        layout.addWidget(btn_del)

    def _type_label(self) -> str:
        return {
            "pixel_skill": "技能CD",
            "pixel_point": "点位颜色",
            "cast_bar": "施法条",
            "skill_metric": "技能次数",
        }.get(self._cond_type, "条件")

    def _build_form(self) -> None:
        """根据条件类型构建不同的表单。"""
        # 清空
        while self._form_layout.count() > 0:
            item = self._form_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if self._cond_type == "pixel_skill":
            self._build_pixel_skill_form()
        elif self._cond_type == "pixel_point":
            self._build_pixel_point_form()
        elif self._cond_type == "cast_bar":
            self._build_cast_bar_form()
        elif self._cond_type == "skill_metric":
            self._build_skill_metric_form()

    # ── 技能图标颜色 ──
    def _build_pixel_skill_form(self) -> None:
        self._cmb_skill = QComboBox(self)
        self._cmb_skill.setMinimumWidth(100)
        for sk in self._available_skills:
            self._cmb_skill.addItem(sk["name"], sk["id"])
        self._cmb_skill.currentIndexChanged.connect(lambda: self.changed.emit())
        self._form_layout.addWidget(self._cmb_skill)

        self._form_layout.addWidget(QLabel("图标颜色 ≈", self))

        self._spin_tol = QSpinBox(self)
        self._spin_tol.setRange(0, 255)
        self._spin_tol.setValue(10)
        self._spin_tol.setToolTip("容差：越大越宽松，建议 5~20")
        self._spin_tol.valueChanged.connect(lambda: self.changed.emit())
        self._form_layout.addWidget(self._spin_tol)

        self._form_layout.addWidget(QLabel("(容差)", self))

    # ── 点位颜色 ──
    def _build_pixel_point_form(self) -> None:
        self._cmb_point = QComboBox(self)
        self._cmb_point.setMinimumWidth(100)
        for pt in self._available_points:
            self._cmb_point.addItem(pt["name"], pt["id"])
        self._cmb_point.currentIndexChanged.connect(lambda: self.changed.emit())
        self._form_layout.addWidget(self._cmb_point)

        self._form_layout.addWidget(QLabel("颜色 ≈", self))

        self._spin_tol = QSpinBox(self)
        self._spin_tol.setRange(0, 255)
        self._spin_tol.setValue(10)
        self._spin_tol.valueChanged.connect(lambda: self.changed.emit())
        self._form_layout.addWidget(self._spin_tol)

        self._form_layout.addWidget(QLabel("(容差)", self))

    # ── 施法条变化 ──
    def _build_cast_bar_form(self) -> None:
        self._cmb_point = QComboBox(self)
        self._cmb_point.setMinimumWidth(100)
        for pt in self._available_points:
            self._cmb_point.addItem(pt["name"], pt["id"])
        self._cmb_point.currentIndexChanged.connect(lambda: self.changed.emit())
        self._form_layout.addWidget(self._cmb_point)

        self._form_layout.addWidget(QLabel("施法条变化 >", self))

        self._spin_tol = QSpinBox(self)
        self._spin_tol.setRange(0, 255)
        self._spin_tol.setValue(10)
        self._spin_tol.valueChanged.connect(lambda: self.changed.emit())
        self._form_layout.addWidget(self._spin_tol)

    # ── 技能指标 ──
    def _build_skill_metric_form(self) -> None:
        self._cmb_skill = QComboBox(self)
        self._cmb_skill.setMinimumWidth(80)
        for sk in self._available_skills:
            self._cmb_skill.addItem(sk["name"], sk["id"])
        self._cmb_skill.currentIndexChanged.connect(lambda: self.changed.emit())
        self._form_layout.addWidget(self._cmb_skill)

        self._cmb_metric = QComboBox(self)
        self._cmb_metric.setMinimumWidth(70)
        for key, label in METRIC_LABELS.items():
            self._cmb_metric.addItem(label, key)
        self._cmb_metric.currentIndexChanged.connect(lambda: self.changed.emit())
        self._form_layout.addWidget(self._cmb_metric)

        self._form_layout.addWidget(QLabel("≥", self))

        self._spin_count = QSpinBox(self)
        self._spin_count.setRange(1, 9999)
        self._spin_count.setValue(1)
        self._spin_count.valueChanged.connect(lambda: self.changed.emit())
        self._form_layout.addWidget(self._spin_count)

        self._form_layout.addWidget(QLabel("次", self))

    # ── NOT 取反 ──
    def _toggle_not(self) -> None:
        self._negated = not self._negated
        self._btn_not.setText("非" if self._negated else "是")
        self._btn_not.setStyleSheet(
            "QPushButton { font-size: 10px; color: #f44336; font-weight: bold; }"
            if self._negated else
            "QPushButton { font-size: 10px; }"
        )
        self.changed.emit()

    # ── 构建 AST ──
    def build_ast(self) -> Optional[dict]:
        """根据当前表单状态构建 AST JSON。"""
        if self._cond_type == "pixel_skill":
            sid = self._cmb_skill.currentData() or ""
            if not sid:
                return None
            ast = _ast_pixel_skill(sid, self._spin_tol.value())

        elif self._cond_type == "pixel_point":
            pid = self._cmb_point.currentData() or ""
            if not pid:
                return None
            ast = _ast_pixel_point(pid, self._spin_tol.value())

        elif self._cond_type == "cast_bar":
            pid = self._cmb_point.currentData() or ""
            if not pid:
                return None
            ast = _ast_cast_bar(pid, self._spin_tol.value())

        elif self._cond_type == "skill_metric":
            sid = self._cmb_skill.currentData() or ""
            metric = self._cmb_metric.currentData() or "success"
            count = self._spin_count.value()
            if not sid:
                return None
            ast = _ast_skill_metric(sid, metric, count)

        else:
            return None

        if self._negated:
            ast = _ast_not(ast)
        return ast

    def describe(self) -> str:
        """生成人类可读的条件描述。"""
        neg = "非: " if self._negated else ""

        if self._cond_type == "pixel_skill":
            name = self._cmb_skill.currentText() or "?"
            tol = self._spin_tol.value()
            return f"{neg}{name} 图标颜色匹配 (容差{tol})"

        elif self._cond_type == "pixel_point":
            name = self._cmb_point.currentText() or "?"
            tol = self._spin_tol.value()
            return f"{neg}{name} 颜色匹配 (容差{tol})"

        elif self._cond_type == "cast_bar":
            name = self._cmb_point.currentText() or "?"
            tol = self._spin_tol.value()
            return f"{neg}{name} 施法条变化 (>{tol})"

        elif self._cond_type == "skill_metric":
            name = self._cmb_skill.currentText() or "?"
            metric_label = self._cmb_metric.currentText() or "?"
            count = self._spin_count.value()
            return f"{neg}{name} {metric_label} ≥ {count}次"

        return f"{neg}(未知条件)"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  条件构建器（主组件）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ConditionBuilder(QFrame):
    """
    可视化条件构建器。

    将多个 ConditionRow 组合为一个 AND/OR 表达式。
    用户通过点选添加条件，系统自动编译为 AST JSON。

    用法：
        builder = ConditionBuilder(
            available_skills=[{"id": "xxx", "name": "火球"}],
            available_points=[{"id": "yyy", "name": "血条"}],
        )
        builder.set_ast(existing_ast_dict)  # 加载已有条件
        ast = builder.build_ast()           # 获取编译后的 AST
    """

    changed = Signal()

    def __init__(
        self,
        *,
        available_skills: List[Dict[str, str]] = None,
        available_points: List[Dict[str, str]] = None,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._available_skills = available_skills or []
        self._available_points = available_points or []
        self._rows: List[ConditionRow] = []

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "ConditionBuilder { background-color: #1e1e1e; border: 1px solid #444; border-radius: 6px; }"
        )

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 标题行
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("释放条件:", self))

        # 组合模式（AND/OR）
        self._cmb_logic = QComboBox(self)
        self._cmb_logic.addItem("全部满足 (AND)", "and")
        self._cmb_logic.addItem("任一满足 (OR)", "or")
        self._cmb_logic.setFixedWidth(120)
        self._cmb_logic.currentIndexChanged.connect(lambda: self.changed.emit())
        title_row.addWidget(self._cmb_logic)

        title_row.addStretch(1)

        # 预览文字
        self._lbl_preview = QLabel("无条件（仅检查CD）", self)
        self._lbl_preview.setStyleSheet("color: #666; font-size: 11px;")
        title_row.addWidget(self._lbl_preview)

        layout.addLayout(title_row)

        # 条件行容器
        self._rows_container = QWidget(self)
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        layout.addWidget(self._rows_container)

        # 添加条件按钮
        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ 添加条件", self)
        btn_add.clicked.connect(self._on_add_condition)
        btn_row.addWidget(btn_add)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _on_add_condition(self) -> None:
        """弹出条件类型选择菜单。"""
        menu = QMenu(self)

        menu.addAction("🎯 技能CD就绪（图标颜色匹配）", lambda: self._add_row("pixel_skill"))
        menu.addAction("📍 点位颜色匹配", lambda: self._add_row("pixel_point"))
        menu.addAction("📊 施法条变化", lambda: self._add_row("cast_bar"))
        menu.addAction("🔢 技能释放次数 ≥ N", lambda: self._add_row("skill_metric"))

        menu.exec(self.cursor().pos())

    def _add_row(self, cond_type: str) -> None:
        row = ConditionRow(
            cond_type=cond_type,
            available_skills=self._available_skills,
            available_points=self._available_points,
            parent=self._rows_container,
        )
        row.changed.connect(self._on_row_changed)
        row.deleted.connect(lambda: self._remove_row(row))
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._on_row_changed()

    def _remove_row(self, row: ConditionRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
            self._rows_layout.removeWidget(row)
            row.deleteLater()
            self._on_row_changed()

    def _on_row_changed(self) -> None:
        """任何条件行变化时，更新预览文字。"""
        ast = self.build_ast()
        if ast is None:
            self._lbl_preview.setText("无条件（仅检查CD）")
            self._lbl_preview.setStyleSheet("color: #666; font-size: 11px;")
        else:
            desc = self.describe()
            self._lbl_preview.setText(desc)
            self._lbl_preview.setStyleSheet("color: #FFC107; font-size: 11px;")
        self.changed.emit()

    # ── 公共 API ──

    def build_ast(self) -> Optional[dict]:
        """
        将所有条件行编译为 AST JSON。

        - 0 个条件 → None（无条件）
        - 1 个条件 → 直接返回该条件的 AST
        - 2+ 条件 → 用 AND/OR 组合
        """
        asts = []
        for row in self._rows:
            ast = row.build_ast()
            if ast is not None:
                asts.append(ast)

        if not asts:
            return None

        if len(asts) == 1:
            return asts[0]

        logic = self._cmb_logic.currentData() or "and"
        if logic == "or":
            return _ast_or(*asts)
        else:
            return _ast_and(*asts)

    def describe(self) -> str:
        """生成人类可读的条件描述。"""
        descs = [row.describe() for row in self._rows]
        if not descs:
            return "无条件（仅检查CD）"
        logic = self._cmb_logic.currentData() or "and"
        sep = " 且 " if logic == "and" else " 或 "
        return sep.join(descs)

    def set_ast(self, ast: Optional[dict]) -> None:
        """
        从已有的 AST JSON 加载条件到 UI。

        支持的结构：
        - None / 空 → 清空所有条件
        - 单个原子 → 添加一行
        - And(children=[...]) → 设置为 AND 模式，每行一个子条件
        - Or(children=[...]) → 设置为 OR 模式，每行一个子条件
        - Not(child=...) → 添加一行并设置取反
        """
        # 清空现有行
        for row in self._rows[:]:
            self._remove_row(row)

        if ast is None or not isinstance(ast, dict):
            return

        cond_type = (ast.get("type") or "").strip().lower()

        # 处理组合节点
        if cond_type in ("and", "or"):
            self._cmb_logic.setCurrentIndex(0 if cond_type == "and" else 1)
            children = ast.get("children", [])
            for child in children:
                if isinstance(child, dict):
                    self._add_row_from_ast(child)
            return

        # 单个原子或 NOT
        self._add_row_from_ast(ast)

    def _add_row_from_ast(self, ast: dict) -> None:
        """从单个 AST 节点添加一行条件。"""
        cond_type = (ast.get("type") or "").strip().lower()
        negated = False

        # 处理 NOT
        if cond_type == "not":
            child = ast.get("child", {})
            if isinstance(child, dict):
                ast = child
                cond_type = (ast.get("type") or "").strip().lower()
                negated = True

        # 映射 AST 类型到 UI 类型
        ui_type = {
            "pixel_skill": "pixel_skill",
            "pixel_point": "pixel_point",
            "cast_bar_changed": "cast_bar",
            "skill_metric_ge": "skill_metric",
        }.get(cond_type)

        if ui_type is None:
            return

        self._add_row(ui_type)
        row = self._rows[-1]

        # 填充表单值
        if ui_type == "pixel_skill":
            sid = ast.get("skill_id", "")
            tol = ast.get("tolerance", 10)
            for i in range(row._cmb_skill.count()):
                if row._cmb_skill.itemData(i) == sid:
                    row._cmb_skill.setCurrentIndex(i)
                    break
            row._spin_tol.setValue(int(tol))

        elif ui_type == "pixel_point":
            pid = ast.get("point_id", "")
            tol = ast.get("tolerance", 10)
            for i in range(row._cmb_point.count()):
                if row._cmb_point.itemData(i) == pid:
                    row._cmb_point.setCurrentIndex(i)
                    break
            row._spin_tol.setValue(int(tol))

        elif ui_type == "cast_bar":
            pid = ast.get("point_id", "")
            tol = ast.get("tolerance", 10)
            for i in range(row._cmb_point.count()):
                if row._cmb_point.itemData(i) == pid:
                    row._cmb_point.setCurrentIndex(i)
                    break
            row._spin_tol.setValue(int(tol))

        elif ui_type == "skill_metric":
            sid = ast.get("skill_id", "")
            metric = ast.get("metric", "success")
            count = ast.get("count", 1)
            for i in range(row._cmb_skill.count()):
                if row._cmb_skill.itemData(i) == sid:
                    row._cmb_skill.setCurrentIndex(i)
                    break
            for i in range(row._cmb_metric.count()):
                if row._cmb_metric.itemData(i) == metric:
                    row._cmb_metric.setCurrentIndex(i)
                    break
            row._spin_count.setValue(int(count))

        if negated:
            row._toggle_not()

    def update_available(self, *, skills: List[Dict[str, str]], points: List[Dict[str, str]]) -> None:
        """更新可用的技能和点位列表（当 Profile 切换时调用）。"""
        self._available_skills = skills
        self._available_points = points
        # 重建所有行的下拉选项
        for row in self._rows:
            if hasattr(row, "_cmb_skill"):
                current = row._cmb_skill.currentData()
                row._cmb_skill.blockSignals(True)
                row._cmb_skill.clear()
                for sk in skills:
                    row._cmb_skill.addItem(sk["name"], sk["id"])
                for i in range(row._cmb_skill.count()):
                    if row._cmb_skill.itemData(i) == current:
                        row._cmb_skill.setCurrentIndex(i)
                        break
                row._cmb_skill.blockSignals(False)
            if hasattr(row, "_cmb_point"):
                current = row._cmb_point.currentData()
                row._cmb_point.blockSignals(True)
                row._cmb_point.clear()
                for pt in points:
                    row._cmb_point.addItem(pt["name"], pt["id"])
                for i in range(row._cmb_point.count()):
                    if row._cmb_point.itemData(i) == current:
                        row._cmb_point.setCurrentIndex(i)
                        break
                row._cmb_point.blockSignals(False)
