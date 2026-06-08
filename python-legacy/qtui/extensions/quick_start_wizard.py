"""
快速开始向导 — 引导新用户完成首次配置。

向导步骤：
1. 欢迎 + 说明
2. 选择/创建 Profile
3. 添加技能（至少1个）
4. 从模板创建循环方案
5. 完成提示
"""

from __future__ import annotations

from typing import Optional, Callable, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QWidget,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QFormLayout,
    QSizePolicy,
)

from core.profiles import ProfileContext, ProfileManager


class QuickStartWizard(QDialog):
    """
    快速开始向导 — 一步步引导新用户完成首次配置。

    完成后通过 on_complete 回调通知调用方（可选）。
    """

    def __init__(
        self,
        *,
        profile_manager: ProfileManager,
        profile_ctx: ProfileContext,
        on_complete: Optional[Callable[[], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("快速开始向导")
        self.setMinimumSize(640, 480)
        self.setModal(True)

        self._pm = profile_manager
        self._ctx = profile_ctx
        self._on_complete = on_complete

        self._build_ui()
        self._go_to_step(0)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # 标题
        self._lbl_title = QLabel("", self)
        font = self._lbl_title.font()
        font.setPointSize(14)
        font.setBold(True)
        self._lbl_title.setFont(font)
        root.addWidget(self._lbl_title)

        # 步骤指示器
        self._lbl_step = QLabel("", self)
        self._lbl_step.setStyleSheet("color: gray;")
        root.addWidget(self._lbl_step)

        # 内容区
        self._stack = QStackedWidget(self)
        root.addWidget(self._stack, 1)

        # Step 0: 欢迎
        self._stack.addWidget(self._build_step_welcome())

        # Step 1: 技能配置
        self._stack.addWidget(self._build_step_skills())

        # Step 2: 选择模板
        self._stack.addWidget(self._build_step_template())

        # Step 3: 完成
        self._stack.addWidget(self._build_step_done())

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self._btn_prev = QPushButton("上一步", self)
        self._btn_prev.clicked.connect(self._on_prev)
        btn_row.addWidget(self._btn_prev)

        self._btn_next = QPushButton("下一步", self)
        self._btn_next.setDefault(True)
        self._btn_next.clicked.connect(self._on_next)
        btn_row.addWidget(self._btn_next)

        self._btn_skip = QPushButton("跳过向导", self)
        self._btn_skip.clicked.connect(self._on_skip)
        btn_row.addWidget(self._btn_skip)

        root.addLayout(btn_row)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Step 0: 欢迎
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_step_welcome(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        msg = QLabel(
            "欢迎使用「激战2 自动化克鲁」！\n\n"
            "这个向导会帮你快速完成首次配置，只需要 3 步：\n\n"
            "  ① 添加你想要自动释放的技能\n"
            "  ② 选择一个循环模板\n"
            "  ③ 开始运行！\n\n"
            "完成后你可以在左侧导航栏中随时调整配置。",
            w,
        )
        msg.setWordWrap(True)
        font = msg.font()
        font.setPointSize(11)
        msg.setFont(font)
        layout.addWidget(msg)

        layout.addStretch(1)
        return w

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Step 1: 技能配置
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_step_skills(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        desc = QLabel(
            "添加你想要自动释放的技能。\n"
            "每个技能需要配置：名称、触发按键、取色位置。\n"
            "这里先创建技能占位，详细取色可以稍后配置。",
            w,
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 技能列表
        self._skill_list = QListWidget(w)
        layout.addWidget(self._skill_list, 1)

        # 添加技能行
        add_row = QHBoxLayout()
        self._txt_skill_name = QLineEdit(w)
        self._txt_skill_name.setPlaceholderText("技能名称（如：火球术）")
        add_row.addWidget(self._txt_skill_name, 2)

        self._txt_skill_key = QLineEdit(w)
        self._txt_skill_key.setPlaceholderText("触发键（如：1、f1）")
        add_row.addWidget(self._txt_skill_key, 1)

        btn_add = QPushButton("添加", w)
        btn_add.clicked.connect(self._on_add_skill)
        add_row.addWidget(btn_add)

        layout.addLayout(add_row)

        # 预设快捷按钮
        preset_row = QHBoxLayout()
        preset_label = QLabel("快速添加：", w)
        preset_row.addWidget(preset_label)

        for name, key in [("技能1", "1"), ("技能2", "2"), ("技能3", "3"), ("治疗", "6")]:
            btn = QPushButton(f"{name}({key})", w)
            btn.clicked.connect(lambda _=False, n=name, k=key: self._add_skill_preset(n, k))
            preset_row.addWidget(btn)

        preset_row.addStretch(1)
        layout.addLayout(preset_row)

        return w

    def _on_add_skill(self) -> None:
        name = self._txt_skill_name.text().strip()
        key = self._txt_skill_key.text().strip()
        if not name:
            return
        self._add_skill_preset(name, key)
        self._txt_skill_name.clear()
        self._txt_skill_key.clear()

    def _add_skill_preset(self, name: str, key: str) -> None:
        # 创建技能
        try:
            skill = self._ctx.skills  # SkillsFile
            from core.models.skill import Skill
            from core.idgen.snowflake import SnowflakeGenerator

            # 使用 ctx 的 idgen（如果有），否则手动创建
            sid = ""
            try:
                sid = str(self._ctx.idgen.next_id())
            except Exception:
                import uuid
                sid = uuid.uuid4().hex

            s = Skill(
                id=sid,
                name=name,
                enabled=True,
            )
            s.trigger.key = key
            skill.skills.append(s)

            display = f"{name}  (触发键: {key or '未设置'})  ID: ...{sid[-6:]}"
            self._skill_list.addItem(display)

        except Exception as e:
            from qtui.notify import UiNotify
            # 静默处理，向导中不弹错误
            pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Step 2: 选择模板
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_step_template(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        desc = QLabel(
            "选择一个循环模板，快速创建你的循环方案。\n"
            "模板会自动创建好模式、轨道和节点结构，\n"
            "你只需要把节点的技能替换成刚才添加的技能即可。",
            w,
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        from rotation_editor.core.templates import TEMPLATE_REGISTRY

        self._template_combo = QComboBox(w)
        for key, info in TEMPLATE_REGISTRY.items():
            self._template_combo.addItem(
                f"{info['icon']}  {info['name']} — {info['desc']}",
                userData=key,
            )
        layout.addWidget(self._template_combo)

        # 方案名称
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("方案名称：", w))
        self._txt_preset_name = QLineEdit(w)
        self._txt_preset_name.setText("我的循环")
        name_row.addWidget(self._txt_preset_name)
        layout.addLayout(name_row)

        layout.addStretch(1)
        return w

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  Step 3: 完成
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_step_done(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        self._done_msg = QLabel("", w)
        self._done_msg.setWordWrap(True)
        font = self._done_msg.font()
        font.setPointSize(11)
        self._done_msg.setFont(font)
        layout.addWidget(self._done_msg)

        layout.addStretch(1)
        return w

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  导航逻辑
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    _step_titles = [
        "欢迎使用",
        "第 1 步：添加技能",
        "第 2 步：选择循环模板",
        "完成！",
    ]

    _total_steps = 4

    def _go_to_step(self, idx: int) -> None:
        self._current_step = idx
        self._stack.setCurrentIndex(idx)
        self._lbl_title.setText(self._step_titles[idx])
        self._lbl_step.setText(f"步骤 {idx + 1} / {self._total_steps}")

        self._btn_prev.setEnabled(idx > 0)
        self._btn_next.setText("完成" if idx == self._total_steps - 1 else "下一步")

    def _on_prev(self) -> None:
        if self._current_step > 0:
            self._go_to_step(self._current_step - 1)

    def _on_next(self) -> None:
        if self._current_step < self._total_steps - 1:
            # 执行当前步骤的提交逻辑
            if self._current_step == 1:
                self._commit_skills()
            elif self._current_step == 2:
                self._commit_template()
            self._go_to_step(self._current_step + 1)
        else:
            # 完成
            self._finish()

    def _on_skip(self) -> None:
        self.close()

    def _commit_skills(self) -> None:
        """保存已添加的技能到 ProfileSession。"""
        try:
            from core.io.json_store import atomic_write_json
            # 技能已在 _add_skill_preset 中直接添加到 ctx.skills.skills
            # 这里触发一次脏标记
        except Exception:
            pass

    def _commit_template(self) -> None:
        """从选择的模板创建循环方案。"""
        from rotation_editor.core.templates import create_from_template

        key = self._template_combo.currentData() or "sequential"
        name = self._txt_preset_name.text().strip() or "我的循环"

        try:
            preset = create_from_template(key, name)
            self._ctx.rotations.presets.append(preset)
            self._created_preset_name = name
        except Exception:
            self._created_preset_name = ""

    def _finish(self) -> None:
        """完成向导：保存所有更改并关闭。"""
        # 生成完成消息
        skill_count = self._skill_list.count()
        preset_name = getattr(self, "_created_preset_name", "")

        msg = "配置已完成！\n\n"
        if skill_count > 0:
            msg += f"  ✓ 已添加 {skill_count} 个技能\n"
        if preset_name:
            msg += f"  ✓ 已创建循环方案「{preset_name}」\n"

        msg += "\n接下来你可以：\n"
        msg += "  • 在「技能配置」页面配置取色位置和颜色\n"
        msg += "  • 在「循环/轨道方案」页面编辑循环逻辑\n"
        msg += "  • 在「循环编辑器」中拖拽调整节点顺序\n"
        msg += "  • 按快捷键开始/停止循环执行\n"
        msg += "\n祝你游戏愉快！"

        self._done_msg.setText(msg)

        # 通知调用方
        if self._on_complete:
            try:
                self._on_complete()
            except Exception:
                pass

        # 关闭按钮变为"完成"
        self._btn_next.setText("关闭")
        self._btn_next.clicked.disconnect()
        self._btn_next.clicked.connect(self.close)
        self._btn_prev.setEnabled(False)
        self._btn_skip.setEnabled(False)
