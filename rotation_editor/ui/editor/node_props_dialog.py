from __future__ import annotations

from typing import Optional, List, Tuple

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

    - SkillNode:
        * 选择技能
        * label
        * 覆盖读条时间
        * 备注
    - GatewayNode:
        * label
        * action:
            - "switch_mode": 切换到目标模式第一条轨道
            - "jump_node" : 在当前作用域内跳到指定轨道+节点（下拉列表）
            - "end"      : 结束执行
        * 对应字段：
            - switch_mode: 只用 target_mode_id
            - jump_node  : 使用 target_track_id + target_node_index
            - end        : 不使用任何目标字段
    """

    def __init__(
        self,
        *,
        ctx: ProfileContext,
        preset: RotationPreset,
        node: object,
        mode_id: Optional[str],
        track_id: Optional[str],
        notify: UiNotify,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑节点属性")
        self.resize(520, 400)

        self._ctx = ctx
        self._preset = preset
        self._node = node
        self._mode_id = (mode_id or "").strip() or None   # None 表示全局轨道
        self._track_id = (track_id or "").strip() or None
        self._notify = notify

        # 供 jump_node 使用的轨道+节点列表缓存
        self._jump_tracks: List[Tuple[str, str]] = []   # (track_id, track_name)
        self._jump_nodes: List[Tuple[str, str]] = []    # (node_id, node_label) 按当前选中轨道

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

        # 动作
        row_action = QHBoxLayout()
        row_action.addWidget(QLabel("动作(action):", self._panel_gw))
        self._cmb_action = QComboBox(self._panel_gw)
        self._cmb_action.addItem("切换模式 (switch_mode)", userData="switch_mode")
        self._cmb_action.addItem("跳转节点 (jump_node)", userData="jump_node")
        self._cmb_action.addItem("结束执行 (end)", userData="end")
        row_action.addWidget(self._cmb_action, 1)
        gw_layout.addLayout(row_action)

        # 目标模式（仅 switch_mode 用）
        row_target_mode = QHBoxLayout()
        self._lbl_target_mode = QLabel("目标模式:", self._panel_gw)
        row_target_mode.addWidget(self._lbl_target_mode)
        self._cmb_target_mode = QComboBox(self._panel_gw)
        row_target_mode.addWidget(self._cmb_target_mode, 1)
        gw_layout.addLayout(row_target_mode)

        # 目标轨道（仅 jump_node 用）
        row_target_track = QHBoxLayout()
        self._lbl_target_track = QLabel("目标轨道:", self._panel_gw)
        row_target_track.addWidget(self._lbl_target_track)
        self._cmb_target_track = QComboBox(self._panel_gw)
        row_target_track.addWidget(self._cmb_target_track, 1)
        gw_layout.addLayout(row_target_track)

        # 目标节点（仅 jump_node 用）
        row_target_node = QHBoxLayout()
        self._lbl_target_node = QLabel("目标节点:", self._panel_gw)
        row_target_node.addWidget(self._lbl_target_node)
        self._cmb_target_node = QComboBox(self._panel_gw)
        row_target_node.addWidget(self._cmb_target_node, 1)
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
        self._cmb_target_track.currentIndexChanged.connect(self._on_target_track_changed)

    # ---------- 加载节点 ----------

    def _load_from_node(self) -> None:
        n = self._node

        if isinstance(n, SkillNode):
            self._lbl_type.setText("节点类型：技能节点 (SkillNode)")
            self._panel_skill.setVisible(True)
            self._panel_gw.setVisible(False)
            self._load_skills()

            self._edit_label.setText(n.label or "")

            sid = n.skill_id or ""
            idx = 0
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
            if act not in ("switch_mode", "jump_node", "end"):
                act = "switch_mode"
            idx_act = 0
            for i in range(self._cmb_action.count()):
                data = self._cmb_action.itemData(i)
                if isinstance(data, str) and data == act:
                    idx_act = i
                    break
            self._cmb_action.setCurrentIndex(idx_act)

            # 模式列表（switch_mode 用）
            self._load_modes()

            tm = n.target_mode_id or ""
            idx_mode = 0
            if tm:
                for i in range(self._cmb_target_mode.count()):
                    data = self._cmb_target_mode.itemData(i)
                    if isinstance(data, str) and data == tm:
                        idx_mode = i
                        break
            self._cmb_target_mode.setCurrentIndex(idx_mode)

            # jump_node 用轨道+节点列表
            self._rebuild_jump_tracks()
            self._rebuild_jump_nodes()

            # 选中 jump_node 目标
            if act == "jump_node":
                # 轨道
                tgt_tid = n.target_track_id or ""
                if not tgt_tid:
                    tgt_tid = self._track_id or ""
                if self._cmb_target_track.count() > 0:
                    sel_idx = 0
                    for i in range(self._cmb_target_track.count()):
                        data = self._cmb_target_track.itemData(i)
                        if isinstance(data, str) and data == tgt_tid:
                            sel_idx = i
                            break
                    self._cmb_target_track.setCurrentIndex(sel_idx)
                    # 更新节点列表后再选节点
                    self._rebuild_jump_nodes()

                # 节点
                tgt_idx = int(n.target_node_index or 0)
                for i in range(self._cmb_target_node.count()):
                    data = self._cmb_target_node.itemData(i)
                    if isinstance(data, int) and data == tgt_idx:
                        self._cmb_target_node.setCurrentIndex(i)
                        break

            # 根据动作调整可见性
            self._on_action_changed()

        else:
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

    # ---------- 模式 / 轨道 / 节点列表 ----------

    def _load_modes(self) -> None:
        """
        用于 switch_mode：列出所有模式。
        """
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

    def _rebuild_jump_tracks(self) -> None:
        """
        针对 jump_node：构建“当前作用域”内的轨道列表：
        - 若 _mode_id 非空 => 当前模式下的所有轨道
        - 若 _mode_id 为空 => 全局轨道列表
        """
        self._cmb_target_track.clear()
        self._jump_tracks = []

        if self._mode_id:
            # 模式轨道
            mode = None
            for m in self._preset.modes or []:
                if m.id == self._mode_id:
                    mode = m
                    break
            if mode is None or not mode.tracks:
                self._cmb_target_track.addItem("（无轨道）", userData="")
                self._cmb_target_track.setEnabled(False)
                return
            self._cmb_target_track.setEnabled(True)
            for t in mode.tracks or []:
                tid = t.id or ""
                name = t.name or "(未命名轨道)"
                text = f"{name}"
                self._cmb_target_track.addItem(text, userData=tid)
                self._jump_tracks.append((tid, name))
        else:
            # 全局轨道
            gtracks: List[Track] = list(self._preset.global_tracks or [])
            if not gtracks:
                self._cmb_target_track.addItem("（无轨道）", userData="")
                self._cmb_target_track.setEnabled(False)
                return
            self._cmb_target_track.setEnabled(True)
            for t in gtracks:
                tid = t.id or ""
                name = t.name or "(未命名轨道)"
                text = f"{name}"
                self._cmb_target_track.addItem(text, userData=tid)
                self._jump_tracks.append((tid, name))

    def _find_track_by_id(self, tid: str) -> Optional[Track]:
        tid = (tid or "").strip()
        if not tid:
            return None
        if self._mode_id:
            for m in self._preset.modes or []:
                if m.id == self._mode_id:
                    for t in m.tracks or []:
                        if t.id == tid:
                            return t
        else:
            for t in self._preset.global_tracks or []:
                if t.id == tid:
                    return t
        return None

    def _rebuild_jump_nodes(self) -> None:
        """
        针对 jump_node：构建当前选中轨道下的节点列表。
        """
        self._cmb_target_node.clear()
        self._jump_nodes = []

        data = self._cmb_target_track.currentData()
        tid = data if isinstance(data, str) else ""
        t = self._find_track_by_id(tid)
        if t is None or not t.nodes:
            self._cmb_target_node.addItem("（无可用节点）", userData=-1)
            self._cmb_target_node.setEnabled(False)
            return

        self._cmb_target_node.setEnabled(True)
        for idx, n in enumerate(t.nodes):
            label = getattr(n, "label", "") or getattr(n, "kind", "") or f"节点{idx}"
            text = f"{idx}: {label}"
            self._cmb_target_node.addItem(text, userData=idx)
            self._jump_nodes.append((getattr(n, "id", ""), label))

    # ---------- 动作切换 ----------

    def _on_action_changed(self) -> None:
        data = self._cmb_action.currentData()
        act = (data or "switch_mode").strip().lower()

        show_mode = False
        show_track = False
        show_node = False

        if act == "switch_mode":
            show_mode = True
        elif act == "jump_node":
            show_track = True
            show_node = True
        elif act == "end":
            pass
        else:
            pass

        self._lbl_target_mode.setVisible(show_mode)
        self._cmb_target_mode.setVisible(show_mode)
        self._cmb_target_mode.setEnabled(show_mode)

        self._lbl_target_track.setVisible(show_track)
        self._cmb_target_track.setVisible(show_track)
        self._cmb_target_track.setEnabled(show_track)

        self._lbl_target_node.setVisible(show_node)
        self._cmb_target_node.setVisible(show_node)
        self._cmb_target_node.setEnabled(show_node)

    def _on_target_mode_changed(self) -> None:
        # 目前仅 switch_mode 使用目标模式
        pass

    def _on_target_track_changed(self) -> None:
        # 轨道改变时，刷新该轨道下的节点列表
        self._rebuild_jump_nodes()

    # ---------- 确认 ----------

    def _on_ok(self) -> None:
        n = self._node
        label = (self._edit_label.text() or "").strip()

        if isinstance(n, SkillNode):
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
            n.label = label or n.label or "Gateway"

            act = self._cmb_action.currentData()
            if not isinstance(act, str) or not act.strip():
                act = "switch_mode"
            act = act.strip().lower()
            n.action = act

            # 重置目标字段
            n.target_mode_id = None
            n.target_track_id = None
            n.target_node_index = None

            if act == "switch_mode":
                if self._cmb_target_mode.count() == 0 or not self._cmb_target_mode.isEnabled():
                    QMessageBox.warning(self, "错误", "当前没有可用模式，请先新增模式。")
                    return
                mid = self._cmb_target_mode.currentData()
                if not isinstance(mid, str) or not mid.strip():
                    QMessageBox.warning(self, "错误", "请选择一个目标模式。")
                    return
                n.target_mode_id = mid.strip()

            elif act == "jump_node":
                # 目标轨道
                if self._cmb_target_track.count() == 0 or not self._cmb_target_track.isEnabled():
                    QMessageBox.warning(self, "错误", "当前作用域下没有可用轨道。")
                    return
                tid = self._cmb_target_track.currentData()
                if not isinstance(tid, str) or not tid.strip():
                    QMessageBox.warning(self, "错误", "请选择一个目标轨道。")
                    return
                n.target_track_id = tid.strip()

                # 目标节点索引
                if self._cmb_target_node.count() == 0 or not self._cmb_target_node.isEnabled():
                    QMessageBox.warning(self, "错误", "目标轨道下没有可用节点。")
                    return
                idx_data = self._cmb_target_node.currentData()
                try:
                    idx = int(idx_data)
                except Exception:
                    idx = 0
                if idx < 0:
                    idx = 0
                n.target_node_index = idx

                # mode_id 不跨模式：保持 None(全局) 或 当前模式
                n.target_mode_id = self._mode_id

            elif act == "end":
                # 结束执行：不需要任何目标字段
                pass

            else:
                pass

        else:
            if hasattr(n, "label"):
                setattr(n, "label", label or getattr(n, "label", "") or "")

        self.accept()