from __future__ import annotations

from typing import Optional, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
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
from rotation_editor.core.models import RotationPreset, SkillNode, GatewayNode, Mode, Track


class NodePropertiesDialog(QDialog):
    """
    节点属性编辑对话框：

    - 支持两种节点：
        - SkillNode: 选择技能 / 修改 label / 覆盖读条时间 / 备注
        - GatewayNode:
            * label
            * action:
                - "switch_mode": 切换到目标模式的第一条轨道
                - "jump_track" : 跳转到指定模式/轨道的起点
                - "jump_node"  : 在当前轨道内跳转到指定索引
                - "end"        : 结束执行（内部停止 MacroEngine）
            * 对应的 target_mode_id / target_track_id / target_node_index

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
        self.resize(440, 360)

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

        # 通用部分：步骤索引（step_index）
        row_step = QHBoxLayout()
        row_step.addWidget(QLabel("步骤(step_index):", self))
        self._spin_step = QSpinBox(self)
        self._spin_step.setRange(0, 10**6)
        self._spin_step.setSingleStep(1)
        row_step.addWidget(self._spin_step)
        layout.addLayout(row_step)

        # 通用部分：步骤内顺序（order_in_step）
        row_order = QHBoxLayout()
        row_order.addWidget(QLabel("步骤内顺序(order_in_step):", self))
        self._spin_order = QSpinBox(self)
        self._spin_order.setRange(0, 10**6)
        self._spin_order.setSingleStep(1)
        row_order.addWidget(self._spin_order)
        layout.addLayout(row_order)

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

        # 动作
        row_action = QHBoxLayout()
        row_action.addWidget(QLabel("动作(action):", self._panel_gw))
        self._cmb_action = QComboBox(self._panel_gw)
        # 支持的动作
        self._cmb_action.addItem("切换模式 (switch_mode)", userData="switch_mode")
        self._cmb_action.addItem("跳转轨道 (jump_track)", userData="jump_track")
        self._cmb_action.addItem("跳转节点 (jump_node)", userData="jump_node")
        self._cmb_action.addItem("结束执行 (end)", userData="end")
        row_action.addWidget(self._cmb_action, 1)
        gw_layout.addLayout(row_action)

        # 目标模式
        row_target_mode = QHBoxLayout()
        row_target_mode.addWidget(QLabel("目标模式:", self._panel_gw))
        self._cmb_target_mode = QComboBox(self._panel_gw)
        row_target_mode.addWidget(self._cmb_target_mode, 1)
        gw_layout.addLayout(row_target_mode)

        # 目标轨道
        row_target_track = QHBoxLayout()
        row_target_track.addWidget(QLabel("目标轨道:", self._panel_gw))
        self._cmb_target_track = QComboBox(self._panel_gw)
        row_target_track.addWidget(self._cmb_target_track, 1)
        gw_layout.addLayout(row_target_track)

        # 目标节点索引
        row_target_node = QHBoxLayout()
        row_target_node.addWidget(QLabel("目标节点索引:", self._panel_gw))
        self._spin_target_node = QSpinBox(self._panel_gw)
        self._spin_target_node.setRange(0, 9999)
        self._spin_target_node.setSingleStep(1)
        row_target_node.addWidget(self._spin_target_node)
        gw_layout.addLayout(row_target_node)

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

        # 信号
        self._cmb_action.currentIndexChanged.connect(self._on_action_changed)
        self._cmb_target_mode.currentIndexChanged.connect(self._on_target_mode_changed)

    # ---------- 载入 ----------

    def _load_from_node(self) -> None:
        n = self._node

        # 通用：步骤字段
        try:
            self._spin_step.setValue(max(0, int(getattr(n, "step_index", 0) or 0)))
        except Exception:
            self._spin_step.setValue(0)

        try:
            self._spin_order.setValue(max(0, int(getattr(n, "order_in_step", 0) or 0)))
        except Exception:
            self._spin_order.setValue(0)

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

            # 动作
            act = (n.action or "switch_mode").strip().lower() or "switch_mode"
            idx_act = 0
            for i in range(self._cmb_action.count()):
                data = self._cmb_action.itemData(i)
                if isinstance(data, str) and data == act:
                    idx_act = i
                    break
            self._cmb_action.setCurrentIndex(idx_act)

            # 目标模式 / 轨道
            self._load_modes()

            # 模式
            tm = n.target_mode_id or ""
            idx_mode = 0
            if tm:
                for i in range(self._cmb_target_mode.count()):
                    data = self._cmb_target_mode.itemData(i)
                    if isinstance(data, str) and data == tm:
                        idx_mode = i
                        break
            self._cmb_target_mode.setCurrentIndex(idx_mode)

            # 轨道（基于当前选中模式）
            self._rebuild_tracks_for_current_mode()
            tt = n.target_track_id or ""
            idx_track = 0
            if tt:
                for i in range(self._cmb_target_track.count()):
                    data = self._cmb_target_track.itemData(i)
                    if isinstance(data, str) and data == tt:
                        idx_track = i
                        break
            self._cmb_target_track.setCurrentIndex(idx_track)

            # 目标节点索引
            if n.target_node_index is not None and n.target_node_index >= 0:
                self._spin_target_node.setValue(int(n.target_node_index))
            else:
                self._spin_target_node.setValue(0)

            # 根据动作调整控件启用状态
            self._on_action_changed()

        else:
            # 未知类型：只允许改 label 和步骤
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

    # ---------- 模式 / 轨道列表 ----------

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

    def _rebuild_tracks_for_current_mode(self) -> None:
        """
        根据当前选中的目标模式，重建目标轨道下拉框。
        """
        self._cmb_target_track.clear()
        data = self._cmb_target_mode.currentData()
        mid = data if isinstance(data, str) else ""
        if not mid:
            # 没有模式，禁用
            self._cmb_target_track.addItem("（无轨道）", userData="")
            self._cmb_target_track.setEnabled(False)
            return

        mode = None
        for m in self._preset.modes or []:
            if m.id == mid:
                mode = m
                break

        if mode is None or not mode.tracks:
            self._cmb_target_track.addItem("（无轨道）", userData="")
            self._cmb_target_track.setEnabled(False)
            return

        self._cmb_target_track.setEnabled(True)
        for t in mode.tracks:
            text = t.name or "(未命名)"
            self._cmb_target_track.addItem(text, userData=t.id or "")

    # ---------- 动作切换：启用/禁用相关控件 ----------

    def _on_action_changed(self) -> None:
        data = self._cmb_action.currentData()
        act = (data or "switch_mode").strip().lower()

        if act == "switch_mode":
            # 只需要目标模式
            self._cmb_target_mode.setEnabled(True)
            self._cmb_target_track.setEnabled(False)
            self._spin_target_node.setEnabled(False)
        elif act == "jump_track":
            # 需要模式 + 轨道
            self._cmb_target_mode.setEnabled(True)
            self._cmb_target_track.setEnabled(True)
            self._spin_target_node.setEnabled(False)
        elif act == "jump_node":
            # 只需要节点索引
            self._cmb_target_mode.setEnabled(False)
            self._cmb_target_track.setEnabled(False)
            self._spin_target_node.setEnabled(True)
        elif act == "end":
            # 结束执行：不需要任何目标字段
            self._cmb_target_mode.setEnabled(False)
            self._cmb_target_track.setEnabled(False)
            self._spin_target_node.setEnabled(False)
        else:
            # 未知动作，全部禁用
            self._cmb_target_mode.setEnabled(False)
            self._cmb_target_track.setEnabled(False)
            self._spin_target_node.setEnabled(False)

    def _on_target_mode_changed(self) -> None:
        """
        目标模式改变时，重建轨道列表（供 jump_track 使用）。
        """
        self._rebuild_tracks_for_current_mode()

    # ---------- 确认 ----------

    def _on_ok(self) -> None:
        n = self._node

        label = (self._edit_label.text() or "").strip()

        # 通用：写回步骤字段
        try:
            s = max(0, int(self._spin_step.value()))
            o = max(0, int(self._spin_order.value()))
            if hasattr(n, "step_index"):
                setattr(n, "step_index", s)
            if hasattr(n, "order_in_step"):
                setattr(n, "order_in_step", o)
        except Exception:
            pass

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
            act = act.strip().lower()
            n.action = act

            # 目标字段重置
            n.target_mode_id = None
            n.target_track_id = None
            n.target_node_index = None

            if act == "switch_mode":
                # 只需要目标模式
                if self._cmb_target_mode.count() == 0 or not self._cmb_target_mode.isEnabled():
                    QMessageBox.warning(self, "错误", "当前没有可用模式，请先新增模式。")
                    return
                mid = self._cmb_target_mode.currentData()
                if not isinstance(mid, str) or not mid.strip():
                    QMessageBox.warning(self, "错误", "请选择一个目标模式。")
                    return
                n.target_mode_id = mid.strip()

            elif act == "jump_track":
                # 需要模式 + 轨道
                if self._cmb_target_mode.count() == 0 or not self._cmb_target_mode.isEnabled():
                    QMessageBox.warning(self, "错误", "当前没有可用模式，请先新增模式。")
                    return
                mid = self._cmb_target_mode.currentData()
                if not isinstance(mid, str) or not mid.strip():
                    QMessageBox.warning(self, "错误", "请选择一个目标模式。")
                    return
                n.target_mode_id = mid.strip()

                if self._cmb_target_track.count() == 0 or not self._cmb_target_track.isEnabled():
                    QMessageBox.warning(self, "错误", "当前模式下没有轨道，请先新增轨道。")
                    return
                tid = self._cmb_target_track.currentData()
                if not isinstance(tid, str) or not tid.strip():
                    QMessageBox.warning(self, "错误", "请选择一个目标轨道。")
                    return
                n.target_track_id = tid.strip()

            elif act == "jump_node":
                # 当前轨道内跳转到指定索引
                idx = int(self._spin_target_node.value())
                if idx < 0:
                    idx = 0
                n.target_node_index = idx

            elif act == "end":
                # 结束执行：不需要任何目标字段
                pass

            else:
                # 未知动作，不做额外处理
                pass

        else:
            # 通用节点：只更新 label 和步骤
            if hasattr(n, "label"):
                setattr(n, "label", label or getattr(n, "label", "") or "")

        self.accept()
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
            act = act.strip().lower()
            n.action = act

            # 目标字段重置
            n.target_mode_id = None
            n.target_track_id = None
            n.target_node_index = None

            if act == "switch_mode":
                # 只需要目标模式
                if self._cmb_target_mode.count() == 0 or not self._cmb_target_mode.isEnabled():
                    QMessageBox.warning(self, "错误", "当前没有可用模式，请先新增模式。")
                    return
                mid = self._cmb_target_mode.currentData()
                if not isinstance(mid, str) or not mid.strip():
                    QMessageBox.warning(self, "错误", "请选择一个目标模式。")
                    return
                n.target_mode_id = mid.strip()

            elif act == "jump_track":
                # 需要模式 + 轨道
                if self._cmb_target_mode.count() == 0 or not self._cmb_target_mode.isEnabled():
                    QMessageBox.warning(self, "错误", "当前没有可用模式，请先新增模式。")
                    return
                mid = self._cmb_target_mode.currentData()
                if not isinstance(mid, str) or not mid.strip():
                    QMessageBox.warning(self, "错误", "请选择一个目标模式。")
                    return
                n.target_mode_id = mid.strip()

                if self._cmb_target_track.count() == 0 or not self._cmb_target_track.isEnabled():
                    QMessageBox.warning(self, "错误", "当前模式下没有轨道，请先新增轨道。")
                    return
                tid = self._cmb_target_track.currentData()
                if not isinstance(tid, str) or not tid.strip():
                    QMessageBox.warning(self, "错误", "请选择一个目标轨道。")
                    return
                n.target_track_id = tid.strip()

            elif act == "jump_node":
                # 当前轨道内跳转到指定索引
                idx = int(self._spin_target_node.value())
                if idx < 0:
                    idx = 0
                n.target_node_index = idx

            elif act == "end":
                # 结束执行：不需要任何目标字段
                pass

            else:
                # 未知动作，不做额外处理
                pass

        else:
            # 通用节点：只更新 label
            if hasattr(n, "label"):
                setattr(n, "label", label)

        self.accept()