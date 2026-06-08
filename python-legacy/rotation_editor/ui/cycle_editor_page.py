"""
循环阶段编辑器 — 专为 CyclePhase 优先级调度模型设计的可视化编辑器。

设计理念：
- 卡片式布局：每个阶段是一张卡片，技能是卡片内的行
- 可视化优先级：技能按优先级从上到下排列，拖拽可调整
- 实时执行状态：活跃阶段高亮，当前技能脉冲，已释放技能打勾
- 最少配置：添加技能+设置优先级即可运行，条件可选

布局：
┌──────────────────────────────────────────────────────────────┐
│  [方案选择▼] [+新建] [▶开始] [⏸暂停] [⏹停止]  状态: 运行中   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ Phase 1: 先打A和B ──────── complete_when: all_fired ─┐  │
│  │  ① [技能A▼]  条件: 无        [✓已释放]  [×] [↕]       │  │
│  │  ② [技能B▼]  条件: 无        [·待释放]  [×] [↕]       │  │
│  │  [+ 添加技能]                                         │  │
│  └────────────────────────────────────────────────────────┘  │
│           ↓ Phase 完成后进入下一阶段                          │
│  ┌─ Phase 2: 放D ────────────── complete_when: all_fired ─┐  │
│  │  ① [技能D▼]  条件: 无        [·待释放]  [×] [↕]       │  │
│  │  [+ 添加技能]                                         │  │
│  └────────────────────────────────────────────────────────┘  │
│           ↓                                                  │
│  ┌─ Phase 3: 放C ────────────── complete_when: all_fired ─┐  │
│  │  ① [技能C▼]  条件: 无        [·待释放]  [×] [↕]       │  │
│  │  [+ 添加技能]                                         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  [+ 添加新阶段]                                              │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  执行日志:                                                   │
│  [Phase1] ① 技能A → SUCCESS (120ms)                         │
│  [Phase1] ② 技能B → SUCCESS (80ms)                          │
│  [Phase1→2] 阶段完成，推进                                   │
│  [Phase2] ① 技能D → SUCCESS (100ms)                         │
└──────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QScrollArea,
    QFrame,
    QGroupBox,
    QSpinBox,
    QSizePolicy,
    QStyle,
    QInputDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
)

from core.profiles import ProfileContext
from core.app.session import ProfileSession
from qtui.notify import UiNotify

from rotation_editor.core.models.cycle import CycleConfig, CyclePhase, SkillSlot
from rotation_editor.core.runtime.cycle_executor import CycleExecutor, CycleExecLogEntry

import logging

log = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  颜色常量
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE_ACTIVE_BG = "#2d4a2d"      # 活跃阶段背景（深绿）
PHASE_IDLE_BG = "#2a2a2a"        # 空闲阶段背景
PHASE_ACTIVE_BORDER = "#4CAF50"  # 活跃阶段边框

SKILL_FIRED_BG = "#1b3a1b"       # 已释放技能背景
SKILL_READY_BG = "#3a3a1b"       # 就绪技能背景（黄）
SKILL_WAITING_BG = "#2a2a2a"     # 等待技能背景

SKILL_FIRED_TEXT = "#4CAF50"     # 已释放文字（绿）
SKILL_READY_TEXT = "#FFC107"     # 就绪文字（黄）
SKILL_WAITING_TEXT = "#888"      # 等待文字（灰）


class CyclePhaseCard(QFrame):
    """
    单个阶段的卡片组件。

    内部包含：
    - 标题行：阶段名称 + 完成条件 + 状态指示
    - 技能行列表：每行一个 SkillSlotRow
    - 底部：添加技能按钮
    """

    changed = Signal()  # 任何修改时发射

    def __init__(
        self,
        phase: CyclePhase,
        phase_index: int,
        *,
        available_skills: List[Dict[str, str]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._phase = phase
        self._phase_index = phase_index
        self._available_skills = available_skills  # [{"id": ..., "name": ...}, ...]
        self._is_active = False
        self._fired_skills: set = set()

        self.setFrameShape(QFrame.StyledPanel)
        self._build_ui()
        self._refresh_skills()
        self._update_style()

    def _build_ui(self) -> None:
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(6)

        # ── 标题行 ──
        title_row = QHBoxLayout()

        self._lbl_phase_num = QLabel(f"Phase {self._phase_index + 1}", self)
        font = self._lbl_phase_num.font()
        font.setBold(True)
        font.setPointSize(11)
        self._lbl_phase_num.setFont(font)
        title_row.addWidget(self._lbl_phase_num)

        self._lbl_status = QLabel("", self)
        title_row.addWidget(self._lbl_status)

        title_row.addStretch(1)

        # 完成条件下拉
        title_row.addWidget(QLabel("完成条件:", self))
        self._cmb_complete = QComboBox(self)
        self._cmb_complete.addItem("全部释放", "all_fired")
        self._cmb_complete.addItem("任一释放", "any_fired")
        self._cmb_complete.addItem("执行一次", "always")
        # 设置当前值
        for i in range(self._cmb_complete.count()):
            if self._cmb_complete.itemData(i) == self._phase.complete_when:
                self._cmb_complete.setCurrentIndex(i)
                break
        self._cmb_complete.currentIndexChanged.connect(self._on_complete_changed)
        title_row.addWidget(self._cmb_complete)

        # 删除阶段按钮
        btn_del_phase = QPushButton("×", self)
        btn_del_phase.setFixedSize(24, 24)
        btn_del_phase.setToolTip("删除此阶段")
        btn_del_phase.clicked.connect(self._on_delete_phase)
        title_row.addWidget(btn_del_phase)

        self._layout.addLayout(title_row)

        # ── 技能列表区 ──
        self._skills_container = QWidget(self)
        self._skills_layout = QVBoxLayout(self._skills_container)
        self._skills_layout.setContentsMargins(0, 0, 0, 0)
        self._skills_layout.setSpacing(2)
        self._layout.addWidget(self._skills_container)

        # ── 添加技能按钮 ──
        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ 添加技能", self)
        btn_add.clicked.connect(self._on_add_skill)
        btn_row.addWidget(btn_add)
        btn_row.addStretch(1)
        self._layout.addLayout(btn_row)

    def _refresh_skills(self) -> None:
        """重建技能行列表。"""
        # 清空
        while self._skills_layout.count() > 0:
            item = self._skills_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # 重建
        for i, slot in enumerate(self._phase.skills):
            row = self._create_skill_row(slot, i)
            self._skills_layout.addWidget(row)

    def _create_skill_row(self, slot: SkillSlot, index: int) -> QFrame:
        """创建单个技能行。"""
        row = QFrame(self._skills_container)
        row.setFrameShape(QFrame.NoFrame)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.setSpacing(8)

        # 优先级编号
        lbl_pri = QLabel(f"  {slot.priority}  ", row)
        pri_font = lbl_pri.font()
        pri_font.setBold(True)
        pri_font.setPointSize(10)
        lbl_pri.setFont(pri_font)
        lbl_pri.setAlignment(Qt.AlignCenter)
        lbl_pri.setFixedWidth(30)
        row_layout.addWidget(lbl_pri)

        # 技能选择下拉
        cmb_skill = QComboBox(row)
        cmb_skill.setMinimumWidth(120)
        cmb_skill.addItem("（未选择）", "")
        for sk in self._available_skills:
            cmb_skill.addItem(sk["name"], sk["id"])
        # 设置当前值
        for i in range(cmb_skill.count()):
            if cmb_skill.itemData(i) == slot.skill_id:
                cmb_skill.setCurrentIndex(i)
                break
        cmb_skill.currentIndexChanged.connect(
            lambda idx, s=slot, c=cmb_skill: self._on_skill_changed(s, c)
        )
        row_layout.addWidget(cmb_skill, 1)

        # 条件状态 — 可点击打开条件构建器
        has_cond = slot.condition_expr is not None
        btn_cond = QPushButton("有条件 ✓" if has_cond else "条件...", row)
        btn_cond.setStyleSheet(
            f"QPushButton {{ color: {'#FFC107' if has_cond else '#888'}; font-size: 11px; border: none; text-align: left; }}"
            "QPushButton:hover { color: #fff; }"
        )
        btn_cond.setToolTip("点击设置释放条件")
        btn_cond.setFixedWidth(70)
        btn_cond.clicked.connect(lambda: self._open_condition_builder(slot, btn_cond))
        row_layout.addWidget(btn_cond)

        # 释放状态（执行时更新）
        lbl_fired = QLabel("·", row)
        lbl_fired.setObjectName(f"fired_{index}")
        lbl_fired.setFixedWidth(50)
        lbl_fired.setAlignment(Qt.AlignCenter)
        row_layout.addWidget(lbl_fired)

        # 上移按钮
        btn_up = QPushButton("↑", row)
        btn_up.setFixedSize(24, 24)
        btn_up.setToolTip("提高优先级")
        btn_up.clicked.connect(lambda: self._on_move_skill(index, -1))
        row_layout.addWidget(btn_up)

        # 下移按钮
        btn_down = QPushButton("↓", row)
        btn_down.setFixedSize(24, 24)
        btn_down.setToolTip("降低优先级")
        btn_down.clicked.connect(lambda: self._on_move_skill(index, 1))
        row_layout.addWidget(btn_down)

        # 删除按钮
        btn_del = QPushButton("×", row)
        btn_del.setFixedSize(24, 24)
        btn_del.setToolTip("移除此技能")
        btn_del.clicked.connect(lambda: self._on_remove_skill(index))
        row_layout.addWidget(btn_del)

        # 根据释放状态设置背景
        skill_id = slot.skill_id
        if skill_id in self._fired_skills:
            row.setStyleSheet(f"QFrame {{ background-color: {SKILL_FIRED_BG}; border-radius: 4px; }}")
            lbl_fired.setText("✓")
            lbl_fired.setStyleSheet(f"color: {SKILL_FIRED_TEXT}; font-weight: bold;")
        elif self._is_active:
            row.setStyleSheet(f"QFrame {{ background-color: {SKILL_READY_BG}; border-radius: 4px; }}")
            lbl_fired.setText("●")
            lbl_fired.setStyleSheet(f"color: {SKILL_READY_TEXT};")
        else:
            lbl_fired.setStyleSheet(f"color: {SKILL_WAITING_TEXT};")

        return row

    def _on_skill_changed(self, slot: SkillSlot, combo: QComboBox) -> None:
        slot.skill_id = combo.currentData() or ""
        self.changed.emit()

    def _on_complete_changed(self) -> None:
        self._phase.complete_when = self._cmb_complete.currentData() or "all_fired"
        self.changed.emit()

    def _open_condition_builder(self, slot: SkillSlot, btn: QPushButton) -> None:
        """打开条件构建器对话框，编辑技能的释放条件。"""
        from qtui.widgets.condition_builder import ConditionBuilder
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton as QBtn

        # 获取可用的点位列表
        available_points = []
        try:
            for pt in (self._available_skills[0] if False else []):  # placeholder
                pass
            # 从 parent 的 parent 获取 ctx（CycleEditorPage）
            parent_page = self.parent()
            while parent_page is not None and not hasattr(parent_page, '_ctx'):
                parent_page = parent_page.parent()
            if parent_page is not None:
                ctx = parent_page._ctx
                for pt in (ctx.points.points or []):
                    pid = getattr(pt, "id", "") or ""
                    name = getattr(pt, "name", "") or pid[-6:]
                    if pid:
                        available_points.append({"id": pid, "name": name})
        except Exception:
            pass

        dlg = QDialog(self)
        dlg.setWindowTitle(f"设置释放条件 — {slot.label or slot.skill_id or '技能'}")
        dlg.setMinimumWidth(500)
        dlg.setMinimumHeight(200)

        dlg_layout = QVBoxLayout(dlg)

        builder = ConditionBuilder(
            available_skills=self._available_skills,
            available_points=available_points,
            parent=dlg,
        )
        builder.set_ast(slot.condition_expr)
        dlg_layout.addWidget(builder, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        btn_clear = QBtn("清除条件", dlg)
        btn_clear.clicked.connect(lambda: (slot.__setattr__('condition_expr', None), dlg.accept()))
        btn_row.addWidget(btn_clear)

        btn_ok = QBtn("确定", dlg)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_ok)

        btn_cancel = QBtn("取消", dlg)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)

        dlg_layout.addLayout(btn_row)

        if dlg.exec() == QDialog.Accepted:
            ast = builder.build_ast()
            slot.condition_expr = ast
            # 更新按钮文字
            if ast is not None:
                btn.setText("有条件 ✓")
                btn.setStyleSheet(
                    "QPushButton { color: #FFC107; font-size: 11px; border: none; text-align: left; }"
                    "QPushButton:hover { color: #fff; }"
                )
            else:
                btn.setText("条件...")
                btn.setStyleSheet(
                    "QPushButton { color: #888; font-size: 11px; border: none; text-align: left; }"
                    "QPushButton:hover { color: #fff; }"
                )
            self.changed.emit()

    def _on_add_skill(self) -> None:
        pri = len(self._phase.skills) + 1
        self._phase.skills.append(SkillSlot(priority=pri))
        self._refresh_skills()
        self.changed.emit()

    def _on_remove_skill(self, index: int) -> None:
        if 0 <= index < len(self._phase.skills):
            self._phase.skills.pop(index)
            # 重排优先级
            for i, s in enumerate(self._phase.skills):
                s.priority = i + 1
            self._refresh_skills()
            self.changed.emit()

    def _on_move_skill(self, index: int, direction: int) -> None:
        new_idx = index + direction
        if 0 <= new_idx < len(self._phase.skills):
            self._phase.skills[index], self._phase.skills[new_idx] = \
                self._phase.skills[new_idx], self._phase.skills[index]
            # 重排优先级
            for i, s in enumerate(self._phase.skills):
                s.priority = i + 1
            self._refresh_skills()
            self.changed.emit()

    def _on_delete_phase(self) -> None:
        # 由父组件处理
        self.parent().deletePhase(self._phase_index) if hasattr(self.parent(), 'deletePhase') else None

    # ── 执行状态更新 ──

    def set_active(self, active: bool) -> None:
        self._is_active = active
        self._update_style()

    def set_fired_skills(self, fired: set) -> None:
        self._fired_skills = fired
        self._refresh_skills()

    def _update_style(self) -> None:
        if self._is_active:
            self.setStyleSheet(
                f"CyclePhaseCard {{ background-color: {PHASE_ACTIVE_BG}; "
                f"border: 2px solid {PHASE_ACTIVE_BORDER}; border-radius: 8px; }}"
            )
            self._lbl_status.setText("◀ 执行中")
            self._lbl_status.setStyleSheet(f"color: {PHASE_ACTIVE_BORDER}; font-weight: bold;")
        else:
            self.setStyleSheet(
                f"CyclePhaseCard {{ background-color: {PHASE_IDLE_BG}; "
                f"border: 1px solid #444; border-radius: 8px; }}"
            )
            self._lbl_status.setText("")
            self._lbl_status.setStyleSheet("")


class CycleEditorPage(QWidget):
    """
    循环阶段编辑器主页。

    布局：
    - 顶部：配置选择 + 控制按钮
    - 中部：可滚动的阶段卡片列表
    - 底部：执行日志表格
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        session: ProfileSession,
        notify: UiNotify,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._session = session
        self._notify = notify

        self._current_config: Optional[CycleConfig] = None
        self._executor: Optional[CycleExecutor] = None
        self._cards: List[CyclePhaseCard] = []
        self._dirty = False

        self._build_ui()
        self._refresh_config_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── 顶部工具栏 ──
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("循环方案:", self))
        self._cmb_configs = QComboBox(self)
        self._cmb_configs.setMinimumWidth(200)
        self._cmb_configs.currentIndexChanged.connect(self._on_config_selected)
        toolbar.addWidget(self._cmb_configs)

        btn_new = QPushButton("新建", self)
        btn_new.clicked.connect(self._on_new_config)
        toolbar.addWidget(btn_new)

        btn_save = QPushButton("保存", self)
        btn_save.clicked.connect(self._on_save)
        toolbar.addWidget(btn_save)

        toolbar.addStretch(1)

        # 执行控制
        self._btn_start = QPushButton("▶ 开始", self)
        self._btn_start.setStyleSheet("QPushButton { background-color: #2e7d32; color: white; font-weight: bold; padding: 6px 16px; }")
        self._btn_start.clicked.connect(self._on_start)
        toolbar.addWidget(self._btn_start)

        self._btn_pause = QPushButton("⏸ 暂停", self)
        self._btn_pause.setEnabled(False)
        self._btn_pause.clicked.connect(self._on_pause)
        toolbar.addWidget(self._btn_pause)

        self._btn_stop = QPushButton("⏹ 停止", self)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop)
        toolbar.addWidget(self._btn_stop)

        self._lbl_status = QLabel("就绪", self)
        self._lbl_status.setStyleSheet("color: #888; padding-left: 12px;")
        toolbar.addWidget(self._lbl_status)

        root.addLayout(toolbar)

        # ── 主内容区（上下分割） ──
        splitter = QSplitter(Qt.Vertical, self)
        root.addWidget(splitter, 1)

        # 上部：阶段卡片（可滚动）
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(4, 4, 4, 4)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch(1)
        scroll.setWidget(self._cards_container)
        splitter.addWidget(scroll)

        # 下部：执行日志
        log_widget = QWidget(self)
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)

        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("执行日志", self))
        log_header.addStretch(1)
        btn_clear = QPushButton("清空", self)
        btn_clear.clicked.connect(lambda: self._table_log.setRowCount(0))
        log_header.addWidget(btn_clear)
        log_layout.addLayout(log_header)

        self._table_log = QTableWidget(self)
        self._table_log.setColumnCount(6)
        self._table_log.setHorizontalHeaderLabels(["时间", "阶段", "事件", "技能", "结果", "原因"])
        self._table_log.verticalHeader().setVisible(False)
        self._table_log.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table_log.setSelectionBehavior(QTableWidget.SelectRows)
        self._table_log.horizontalHeader().setStretchLastSection(True)
        log_layout.addWidget(self._table_log, 1)

        splitter.addWidget(log_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  配置管理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _refresh_config_list(self) -> None:
        self._cmb_configs.blockSignals(True)
        self._cmb_configs.clear()
        self._cmb_configs.addItem("（选择方案）", "")
        for cfg in self._ctx.rotations.cycles:
            self._cmb_configs.addItem(cfg.name or "未命名", cfg.name)
        self._cmb_configs.blockSignals(False)

    def _on_config_selected(self) -> None:
        name = self._cmb_configs.currentData() or ""
        if not name:
            self._current_config = None
            self._rebuild_cards()
            return
        for cfg in self._ctx.rotations.cycles:
            if cfg.name == name:
                self._current_config = cfg
                self._rebuild_cards()
                return

    def _on_new_config(self) -> None:
        name, ok = QInputDialog.getText(self, "新建循环方案", "方案名称:", text="我的循环")
        if not ok or not name.strip():
            return
        cfg = CycleConfig(name=name.strip())
        # 默认添加一个空阶段
        cfg.phases.append(CyclePhase(name="阶段1"))
        self._ctx.rotations.cycles.append(cfg)
        self._refresh_config_list()
        # 选中新方案
        for i in range(self._cmb_configs.count()):
            if self._cmb_configs.itemData(i) == cfg.name:
                self._cmb_configs.setCurrentIndex(i)
                break
        self._dirty = True
        self._notify.info(f"已创建方案: {cfg.name}")

    def _on_save(self) -> None:
        if self._current_config is None:
            self._notify.error("没有选中的方案")
            return
        try:
            self._session.mark_dirty("rotations")
            self._session.commit(parts={"rotations"})
            self._dirty = False
            self._notify.info(f"已保存: {self._current_config.name}")
        except Exception as e:
            self._notify.error("保存失败", detail=str(e))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  阶段卡片管理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _rebuild_cards(self) -> None:
        """根据当前配置重建所有阶段卡片。"""
        # 清空
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        # 清空布局中的所有 widget（保留 stretch）
        while self._cards_layout.count() > 0:
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if self._current_config is None:
            self._cards_layout.addStretch(1)
            return

        available = self._get_available_skills()

        for i, phase in enumerate(self._current_config.phases):
            card = CyclePhaseCard(
                phase=phase,
                phase_index=i,
                available_skills=available,
                parent=self._cards_container,
            )
            card.changed.connect(self._on_card_changed)
            self._cards.append(card)
            self._cards_layout.addWidget(card)

            # 阶段之间的箭头指示
            if i < len(self._current_config.phases) - 1:
                arrow = QLabel("  ↓ 完成后进入下一阶段", self._cards_container)
                arrow.setStyleSheet("color: #666; padding-left: 20px;")
                self._cards_layout.addWidget(arrow)

        # 添加阶段按钮
        btn_add_phase = QPushButton("+ 添加新阶段", self._cards_container)
        btn_add_phase.clicked.connect(self._on_add_phase)
        self._cards_layout.addWidget(btn_add_phase)

        self._cards_layout.addStretch(1)

    def _get_available_skills(self) -> List[Dict[str, str]]:
        """获取当前 Profile 中所有可用技能。"""
        skills = []
        for s in (self._ctx.skills.skills or []):
            sid = getattr(s, "id", "") or ""
            name = getattr(s, "name", "") or sid[-6:]
            if sid:
                skills.append({"id": sid, "name": name})
        return skills

    def _on_card_changed(self) -> None:
        self._dirty = True

    def _on_add_phase(self) -> None:
        if self._current_config is None:
            return
        idx = len(self._current_config.phases) + 1
        self._current_config.phases.append(CyclePhase(name=f"阶段{idx}"))
        self._rebuild_cards()
        self._dirty = True

    def deletePhase(self, phase_index: int) -> None:
        """删除指定阶段（由卡片的删除按钮调用）。"""
        if self._current_config is None:
            return
        if 0 <= phase_index < len(self._current_config.phases):
            name = self._current_config.phases[phase_index].name
            self._current_config.phases.pop(phase_index)
            self._rebuild_cards()
            self._dirty = True
            self._notify.info(f"已删除阶段: {name}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  执行控制
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _on_start(self) -> None:
        if self._current_config is None:
            self._notify.error("请先选择一个循环方案")
            return
        if not self._current_config.phases:
            self._notify.error("方案中没有阶段")
            return

        # 检查是否有技能配置
        total_skills = sum(len(p.skills) for p in self._current_config.phases)
        if total_skills == 0:
            self._notify.error("方案中没有配置任何技能")
            return

        # 保存脏数据
        if self._dirty:
            self._on_save()

        try:
            from rotation_editor.core.runtime.engine import EngineConfig

            self._executor = CycleExecutor(
                ctx=self._ctx,
                config=self._current_config,
                scheduler=self._make_scheduler(),
                callbacks=self._make_callbacks(),
                store=None,
                key_sender=None,
                attempt_cfg=None,
            )
            self._executor.start()

            self._btn_start.setEnabled(False)
            self._btn_pause.setEnabled(True)
            self._btn_stop.setEnabled(True)
            self._lbl_status.setText("运行中...")
            self._lbl_status.setStyleSheet("color: #4CAF50; font-weight: bold; padding-left: 12px;")

            # 启动状态刷新定时器
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setInterval(200)
            self._refresh_timer.timeout.connect(self._refresh_exec_state)
            self._refresh_timer.start()

        except Exception as e:
            self._notify.error("启动失败", detail=str(e))

    def _on_pause(self) -> None:
        if self._executor is None:
            return
        if self._executor._paused:
            self._executor.resume()
            self._btn_pause.setText("⏸ 暂停")
            self._lbl_status.setText("运行中...")
            self._lbl_status.setStyleSheet("color: #4CAF50; font-weight: bold; padding-left: 12px;")
        else:
            self._executor.pause()
            self._btn_pause.setText("▶ 继续")
            self._lbl_status.setText("已暂停")
            self._lbl_status.setStyleSheet("color: #FFC107; font-weight: bold; padding-left: 12px;")

    def _on_stop(self) -> None:
        if self._executor is None:
            return
        self._executor.stop("user_stop")
        self._btn_start.setEnabled(True)
        self._btn_pause.setEnabled(False)
        self._btn_stop.setEnabled(False)
        self._btn_pause.setText("⏸ 暂停")
        self._lbl_status.setText("已停止")
        self._lbl_status.setStyleSheet("color: #888; padding-left: 12px;")

        if hasattr(self, "_refresh_timer"):
            self._refresh_timer.stop()

    def _refresh_exec_state(self) -> None:
        """定时刷新执行状态到 UI。"""
        if self._executor is None:
            return
        if not self._executor.is_running():
            self._on_stop()
            return

        state = self._executor.get_state()

        # 更新每个卡片的活跃状态
        for i, card in enumerate(self._cards):
            is_active = (i == state.phase_index)
            card.set_active(is_active)
            if is_active:
                card.set_fired_skills(state.fired_in_phase)
            else:
                card.set_fired_skills(set())

        # 更新状态文字
        phase_name = ""
        if self._current_config and 0 <= state.phase_index < len(self._current_config.phases):
            phase_name = self._current_config.phases[state.phase_index].name
        self._lbl_status.setText(
            f"运行中 | 循环 #{state.cycle_count + 1} | 阶段: {phase_name} | 已执行: {state.total_executed}"
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  调度器和回调适配
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _make_scheduler(self) -> Any:
        """创建一个将回调调度到 UI 线程的 scheduler。"""
        from qtui.dispatcher import QtDispatcher
        dispatcher = QtDispatcher(self)

        class _Scheduler:
            def __init__(self, disp):
                self._disp = disp
            def call_soon(self, fn):
                self._disp.call_soon(fn)

        return _Scheduler(dispatcher)

    def _make_callbacks(self) -> Any:
        """创建引擎回调对象。"""
        editor = self

        class _Callbacks:
            def on_started(self, preset_id: str) -> None:
                pass

            def on_stopped(self, reason: str) -> None:
                pass

            def on_error(self, msg: str, detail: str) -> None:
                editor._notify.error(msg, detail=detail)

            def on_node_executed(self, cursor, node) -> None:
                pass

            def on_exec_log(self, entry) -> None:
                editor._append_log(entry)

        return _Callbacks()

    def _append_log(self, entry: CycleExecLogEntry) -> None:
        """将日志条目添加到表格。"""
        table = self._table_log
        row = table.rowCount()
        table.insertRow(row)

        ts = getattr(entry, "ts_ms", 0)
        phase = getattr(entry, "phase_name", "")
        event = getattr(entry, "event", "")
        skill = getattr(entry, "skill_name", "") or getattr(entry, "skill_id", "")
        outcome = getattr(entry, "outcome", "")
        reason = getattr(entry, "reason", "")

        # 事件类型中文
        event_cn = {
            "select": "选择",
            "execute": "执行",
            "skip": "跳过",
            "result": "结果",
            "phase_complete": "阶段完成",
            "cycle_reset": "循环重置",
        }.get(event, event)

        table.setItem(row, 0, QTableWidgetItem(str(ts)))
        table.setItem(row, 1, QTableWidgetItem(phase))

        event_item = QTableWidgetItem(event_cn)
        if event == "execute":
            event_item.setBackground(QColor("#1565C0"))
        elif event == "phase_complete":
            event_item.setBackground(QColor("#2E7D32"))
        elif event == "skip":
            event_item.setBackground(QColor("#424242"))
        table.setItem(row, 2, event_item)

        table.setItem(row, 3, QTableWidgetItem(skill))

        outcome_item = QTableWidgetItem(outcome)
        if "SUCCESS" in outcome:
            outcome_item.setForeground(QColor("#4CAF50"))
        elif "FAILED" in outcome:
            outcome_item.setForeground(QColor("#f44336"))
        elif "NOT_READY" in outcome:
            outcome_item.setForeground(QColor("#FFC107"))
        table.setItem(row, 4, outcome_item)

        table.setItem(row, 5, QTableWidgetItem(reason))

        table.scrollToBottom()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  上下文切换
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def set_context(self, ctx: ProfileContext) -> None:
        """Profile 切换时调用。"""
        self._ctx = ctx
        if self._executor is not None and self._executor.is_running():
            self._executor.stop("profile_switch")
        self._refresh_config_list()
        self._current_config = None
        self._rebuild_cards()
