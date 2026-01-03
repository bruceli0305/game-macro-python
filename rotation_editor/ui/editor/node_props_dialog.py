from __future__ import annotations

from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QWidget,  # 需要 QWidget
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QMessageBox,
)

from core.profiles import ProfileContext
from core.models.skill import Skill
from qtui.icons import load_icon
from qtui.notify import UiNotify
from rotation_editor.core.models import RotationPreset, SkillNode, GatewayNode, Mode


class NodePropertiesDialog(QDialog):
    """
    节点属性编辑对话框：

    - 支持两种节点：
        - SkillNode: 选择技能 / 修改 label / 覆盖读条时间 / 备注
        - GatewayNode: 修改 label / 动作 / 目标模式（目前只支持 switch_mode）
    - 直接修改传入的 node 实例（dataclass 引用），调用方负责 mark_dirty & 刷新 UI
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        preset: RotationPreset,
        node: object,
        notify: UiNotify,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑节点属性")
        self.resize(420, 320)

        self._ctx = ctx
        self._preset = preset
        self._node = node
        self._notify = notify

        self._build_ui()
        self._load_from_node()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 顶部类型信息
        self._lbl_type = QLabel("", self)
        layout.addWidget(self._lbl_type)

        # 通用部分：标签
        row_label = QHBoxLayout()
        row_label.addWidget(QLabel("显示标签(label):", self))
        self._edit_label = QLineEdit(self)
        row_label.addWidget(self._edit_label, 1)
        layout.addLayout(row_label)

        # --- SkillNode 部分 ---
        self._panel_skill = QWidget(self)
        skill_layout = QVBoxLayout(self._panel_skill)
        skill_layout.setContentsMargins(0, 0, 0, 0)
        skill_layout.setSpacing(4)

        row_skill = QHBoxLayout()
        row_skill.addWidget(QLabel("技能:", self._panel_skill))
        self._cmb_skill = QComboBox(self._panel_skill)
        row_skill.addWidget(self._cmb_skill, 1)
        skill_layout.addLayout(row_skill)

        row_cast = QHBoxLayout()
        row_cast.addWidget(QLabel("覆盖读条时间(ms，0=不覆盖):", self._panel_skill))
        self._spin_cast = QSpinBox(self._panel_skill)
        self._spin_cast.setRange(0, 10**9)
        self._spin_cast.setSingleStep(50)
        row_cast.addWidget(self._spin_cast)
        skill_layout.addLayout(row_cast)

        self._txt_comment = QPlainTextEdit(self._panel_skill)
        self._txt_comment.setPlaceholderText("备注（可选）")
        skill_layout.addWidget(self._txt_comment, 1)

        layout.addWidget(self._panel_skill)

        # --- GatewayNode 部分 ---
        self._panel_gw = QWidget(self)
        gw_layout = QVBoxLayout(self._panel_gw)
        gw_layout.setContentsMargins(0, 0, 0, 0)
        gw_layout.setSpacing(4)

        row_action = QHBoxLayout()
        row_action.addWidget(QLabel("动作(action):", self._panel_gw))
        self._cmb_action = QComboBox(self._panel_gw)
        # 当前只支持 switch_mode
        self._cmb_action.addItem("切换模式 (switch_mode)", userData="switch_mode")
        row_action.addWidget(self._cmb_action, 1)
        gw_layout.addLayout(row_action)

        row_target_mode = QHBoxLayout()
        row_target_mode.addWidget(QLabel("目标模式:", self._panel_gw))
        self._cmb_target_mode = QComboBox(self._panel_gw)
        row_target_mode.addWidget(self._cmb_target_mode, 1)
        gw_layout.addLayout(row_target_mode)

        layout.addWidget(self._panel_gw)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        style = self.style()
        icon_ok = load_icon("save", style, QStyle.StandardPixmap.SP_DialogApplyButton)
        icon_cancel = load_icon("delete", style, QStyle.StandardPixmap.SP_DialogCancelButton)

        self._btn_ok = QPushButton("确定", self)
        self._btn_ok.setIcon(icon_ok)
        self._btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(self._btn_ok)

        self._btn_cancel = QPushButton("取消", self)
        self._btn_cancel.setIcon(icon_cancel)
        self._btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_cancel)

        layout.addLayout(btn_row)

    # ---------- 载入 ----------

    def _load_from_node(self) -> None:
        n = self._node

        if isinstance(n, SkillNode):
            self._lbl_type.setText("节点类型：技能节点 (SkillNode)")
            self._panel_skill.setVisible(True)
            self._panel_gw.setVisible(False)
            self._load_skills()
            # 填充字段
            self._edit_label.setText(n.label or "")
            # 找到对应技能
            sid = n.skill_id or ""
            idx = 0
            if sid:
                for i in range(self._cmb_skill.count()):
                    data = self._cmb_skill.itemData(i)
                    if isinstance(data, str) and data == sid:
                        idx = i
                        break
            self._cmb_skill.setCurrentIndex(idx)

            if n.override_cast_ms is None or n.override_cast_ms <= 0:
                self._spin_cast.setValue(0)
            else:
                self._spin_cast.setValue(int(n.override_cast_ms))

            self._txt_comment.setPlainText(n.comment or "")

        elif isinstance(n, GatewayNode):
            self._lbl_type.setText("节点类型：网关节点 (GatewayNode)")
            self._panel_skill.setVisible(False)
            self._panel_gw.setVisible(True)

            self._edit_label.setText(n.label or "")

            # 动作：目前仅 switch_mode
            action = (n.action or "switch_mode").strip() or "switch_mode"
            idx = 0
            for i in range(self._cmb_action.count()):
                data = self._cmb_action.itemData(i)
                if isinstance(data, str) and data == action:
                    idx = i
                    break
            self._cmb_action.setCurrentIndex(idx)

            # 目标模式列表
            self._load_modes()
            tid = n.target_mode_id or ""
            idx2 = 0
            if tid:
                for i in range(self._cmb_target_mode.count()):
                    data = self._cmb_target_mode.itemData(i)
                    if isinstance(data, str) and data == tid:
                        idx2 = i
                        break
            self._cmb_target_mode.setCurrentIndex(idx2)

        else:
            # 未知类型：只允许改 label
            self._lbl_type.setText(f"节点类型：{getattr(n, 'kind', 'unknown')}")
            self._panel_skill.setVisible(False)
            self._panel_gw.setVisible(False)
            self._edit_label.setText(getattr(n, "label", "") or "")

    def _load_skills(self) -> None:
        self._cmb_skill.clear()
        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        if not skills:
            self._cmb_skill.addItem("（无技能，请先在“技能配置”页面添加）", userData="")
            self._cmb_skill.setEnabled(False)
            return
        self._cmb_skill.setEnabled(True)
        for s in skills:
            text = f"{s.name or '(未命名)'} [{(s.id or '')[-6:]}]"
            self._cmb_skill.addItem(text, userData=s.id or "")

    def _load_modes(self) -> None:
        self._cmb_target_mode.clear()
        modes: List[Mode] = list(self._preset.modes or [])
        if not modes:
            self._cmb_target_mode.addItem("（无模式，请先新增模式）", userData="")
            self._cmb_target_mode.setEnabled(False)
            return
        self._cmb_target_mode.setEnabled(True)
        for m in modes:
            text = m.name or "(未命名)"
            self._cmb_target_mode.addItem(text, userData=m.id or "")

    # ---------- 确认 ----------

    def _on_ok(self) -> None:
        n = self._node

        label = (self._edit_label.text() or "").strip()

        if isinstance(n, SkillNode):
            # 技能节点
            if self._cmb_skill.count() == 0 or not self._cmb_skill.isEnabled():
                QMessageBox.warning(self, "错误", "当前没有可用技能，请先在“技能配置”页面添加技能。")
                return
            sid = self._cmb_skill.currentData()
            if not isinstance(sid, str) or not sid.strip():
                QMessageBox.warning(self, "错误", "请选择一个技能。")
                return
            n.skill_id = sid.strip()
            n.label = label or n.label or "Skill"

            cast = int(self._spin_cast.value())
            if cast <= 0:
                n.override_cast_ms = None
            else:
                n.override_cast_ms = cast

            n.comment = self._txt_comment.toPlainText().rstrip("\n")

        elif isinstance(n, GatewayNode):
            # 网关节点
            n.label = label or n.label or "Gateway"

            # 动作
            act = self._cmb_action.currentData()
            if not isinstance(act, str) or not act.strip():
                act = "switch_mode"
            n.action = act.strip()

            # 目标模式（仅在 switch_mode 下有效）
            if act == "switch_mode":
                if self._cmb_target_mode.count() == 0 or not self._cmb_target_mode.isEnabled():
                    QMessageBox.warning(self, "错误", "当前没有可用模式，请先新增模式。")
                    return
                tid = self._cmb_target_mode.currentData()
                if not isinstance(tid, str) or not tid.strip():
                    QMessageBox.warning(self, "错误", "请选择一个目标模式。")
                    return
                n.target_mode_id = tid.strip()
            else:
                # 预留其他动作类型时的处理
                pass

        else:
            # 通用节点：只更新 label
            if hasattr(n, "label"):
                setattr(n, "label", label)

        self.accept()