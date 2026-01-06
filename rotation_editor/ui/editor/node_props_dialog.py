from __future__ import annotations

import json
from typing import Optional, List, Tuple, Any, Dict

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
    QGroupBox,
)

from core.profiles import ProfileContext
from core.models.skill import Skill
from qtui.icons import load_icon
from qtui.notify import UiNotify
from rotation_editor.core.models import RotationPreset, SkillNode, GatewayNode, Mode, Track

from rotation_editor.ast import compile_expr_json


class NodePropertiesDialog(QDialog):
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
        self.resize(700, 760)

        self._ctx = ctx
        self._preset = preset
        self._node = node
        self._mode_id = (mode_id or "").strip() or None
        self._track_id = (track_id or "").strip() or None
        self._notify = notify

        self._build_ui()
        self._load_from_node()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._lbl_type = QLabel("", self)
        layout.addWidget(self._lbl_type)

        row_label = QHBoxLayout()
        row_label.addWidget(QLabel("显示标签(label):", self))
        self._edit_label = QLineEdit(self)
        row_label.addWidget(self._edit_label, 1)
        layout.addLayout(row_label)

        # Skill panel
        self._panel_skill = QWidget(self)
        skill_layout = QVBoxLayout(self._panel_skill)
        skill_layout.setContentsMargins(0, 0, 0, 0)
        skill_layout.setSpacing(6)

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
        self._txt_comment.setMinimumHeight(70)
        skill_layout.addWidget(self._txt_comment)

        self._grp_start = QGroupBox("开始信号 start_expr（可选，AST JSON）", self._panel_skill)
        g1 = QVBoxLayout(self._grp_start)
        g1.setContentsMargins(8, 8, 8, 8)
        g1.setSpacing(6)

        row_s1 = QHBoxLayout()
        self._lbl_start_check = QLabel("未校验", self._grp_start)
        row_s1.addWidget(self._lbl_start_check, 1)
        self._btn_check_start = QPushButton("校验", self._grp_start)
        self._btn_check_start.clicked.connect(self._on_check_start_expr)
        row_s1.addWidget(self._btn_check_start)
        g1.addLayout(row_s1)

        self._txt_start_expr = QPlainTextEdit(self._grp_start)
        self._txt_start_expr.setPlaceholderText("留空表示不设置（引擎使用默认开始信号）")
        self._txt_start_expr.setMinimumHeight(110)
        g1.addWidget(self._txt_start_expr)

        self._grp_complete = QGroupBox("完成信号 complete_expr（可选，AST JSON）", self._panel_skill)
        g2 = QVBoxLayout(self._grp_complete)
        g2.setContentsMargins(8, 8, 8, 8)
        g2.setSpacing(6)

        row_c1 = QHBoxLayout()
        self._lbl_complete_check = QLabel("未校验", self._grp_complete)
        row_c1.addWidget(self._lbl_complete_check, 1)
        self._btn_check_complete = QPushButton("校验", self._grp_complete)
        self._btn_check_complete.clicked.connect(self._on_check_complete_expr)
        row_c1.addWidget(self._btn_check_complete)
        g2.addLayout(row_c1)

        self._txt_complete_expr = QPlainTextEdit(self._grp_complete)
        self._txt_complete_expr.setPlaceholderText("留空表示不设置（由完成策略决定）")
        self._txt_complete_expr.setMinimumHeight(110)
        g2.addWidget(self._txt_complete_expr)

        skill_layout.addWidget(self._grp_start)
        skill_layout.addWidget(self._grp_complete)

        layout.addWidget(self._panel_skill)

        # Gateway panel
        self._panel_gw = QWidget(self)
        gw_layout = QVBoxLayout(self._panel_gw)
        gw_layout.setContentsMargins(0, 0, 0, 0)
        gw_layout.setSpacing(6)

        row_action = QHBoxLayout()
        row_action.addWidget(QLabel("动作(action):", self._panel_gw))
        self._cmb_action = QComboBox(self._panel_gw)
        self._cmb_action.addItem("切换模式 (switch_mode)", userData="switch_mode")
        self._cmb_action.addItem("跳转轨道 (jump_track)", userData="jump_track")
        self._cmb_action.addItem("跳转节点 (jump_node，仅当前轨道)", userData="jump_node")
        self._cmb_action.addItem("结束执行 (end)", userData="end")
        row_action.addWidget(self._cmb_action, 1)
        gw_layout.addLayout(row_action)

        row_target_mode = QHBoxLayout()
        self._lbl_target_mode = QLabel("目标模式:", self._panel_gw)
        row_target_mode.addWidget(self._lbl_target_mode)
        self._cmb_target_mode = QComboBox(self._panel_gw)
        row_target_mode.addWidget(self._cmb_target_mode, 1)
        gw_layout.addLayout(row_target_mode)

        row_target_track = QHBoxLayout()
        self._lbl_target_track = QLabel("目标轨道:", self._panel_gw)
        row_target_track.addWidget(self._lbl_target_track)
        self._cmb_target_track = QComboBox(self._panel_gw)
        row_target_track.addWidget(self._cmb_target_track, 1)
        gw_layout.addLayout(row_target_track)

        row_target_node = QHBoxLayout()
        self._lbl_target_node = QLabel("目标节点:", self._panel_gw)
        row_target_node.addWidget(self._lbl_target_node)
        self._cmb_target_node = QComboBox(self._panel_gw)
        row_target_node.addWidget(self._cmb_target_node, 1)
        gw_layout.addLayout(row_target_node)

        self._grp_gw_cond = QGroupBox("内联条件 condition_expr（可选，AST JSON；优先于引用条件）", self._panel_gw)
        cg = QVBoxLayout(self._grp_gw_cond)
        cg.setContentsMargins(8, 8, 8, 8)
        cg.setSpacing(6)

        row_gc = QHBoxLayout()
        self._lbl_gw_cond_check = QLabel("未校验", self._grp_gw_cond)
        row_gc.addWidget(self._lbl_gw_cond_check, 1)
        self._btn_check_gw_cond = QPushButton("校验", self._grp_gw_cond)
        self._btn_check_gw_cond.clicked.connect(self._on_check_gw_condition_expr)
        row_gc.addWidget(self._btn_check_gw_cond)
        cg.addLayout(row_gc)

        self._txt_gw_cond_expr = QPlainTextEdit(self._grp_gw_cond)
        self._txt_gw_cond_expr.setPlaceholderText(
            "留空表示不使用内联条件（将继续使用 condition_id 引用条件，如果有的话）。\n"
            "填写后保存会清空 condition_id，仅使用内联条件。"
        )
        self._txt_gw_cond_expr.setMinimumHeight(120)
        cg.addWidget(self._txt_gw_cond_expr)

        gw_layout.addWidget(self._grp_gw_cond)
        layout.addWidget(self._panel_gw)

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

        self._cmb_action.currentIndexChanged.connect(self._on_action_changed)
        self._cmb_target_mode.currentIndexChanged.connect(self._on_target_mode_changed)
        self._cmb_target_track.currentIndexChanged.connect(self._on_target_track_changed)

    # ---------- JSON helpers ----------

    def _pretty_json(self, obj: Any) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception:
            return ""

    def _parse_expr_text(self, text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        s = (text or "").strip()
        if not s:
            return None, ""
        try:
            obj = json.loads(s)
        except Exception as e:
            return None, f"JSON 解析失败：{e}"
        if not isinstance(obj, dict):
            return None, "表达式必须是 JSON 对象(dict)"
        if "type" not in obj:
            return None, "表达式缺少 type 字段"
        return obj, ""

    def _validate_expr_dict(self, expr: Dict[str, Any], *, path: str) -> Tuple[bool, str]:
        res = compile_expr_json(expr, ctx=self._ctx, path=path)
        if res.ok():
            return True, "校验通过"
        lines: List[str] = []
        for d in (res.diagnostics or [])[:80]:
            lines.append(f"- [{d.level}] [{d.code}] {d.path}: {d.message}" + (f" ({d.detail})" if d.detail else ""))
        if len(res.diagnostics or []) > 80:
            lines.append(f"... 还有 {len(res.diagnostics) - 80} 条")
        return False, "\n".join(lines) if lines else "校验失败"

    def _on_check_start_expr(self) -> None:
        expr, msg = self._parse_expr_text(self._txt_start_expr.toPlainText())
        if msg:
            QMessageBox.warning(self, "start_expr 无效", msg)
            self._lbl_start_check.setText("校验失败")
            self._lbl_start_check.setStyleSheet("color:#ff6b6b;")
            return
        if expr is None:
            self._lbl_start_check.setText("未设置（使用默认）")
            self._lbl_start_check.setStyleSheet("color:#6fdc6f;")
            return
        ok, detail = self._validate_expr_dict(expr, path="$.start_expr")
        if ok:
            self._lbl_start_check.setText("校验通过")
            self._lbl_start_check.setStyleSheet("color:#6fdc6f;")
        else:
            QMessageBox.warning(self, "start_expr 校验失败", detail)
            self._lbl_start_check.setText("校验失败（见弹窗）")
            self._lbl_start_check.setStyleSheet("color:#ff6b6b;")

    def _on_check_complete_expr(self) -> None:
        expr, msg = self._parse_expr_text(self._txt_complete_expr.toPlainText())
        if msg:
            QMessageBox.warning(self, "complete_expr 无效", msg)
            self._lbl_complete_check.setText("校验失败")
            self._lbl_complete_check.setStyleSheet("color:#ff6b6b;")
            return
        if expr is None:
            self._lbl_complete_check.setText("未设置（由策略决定）")
            self._lbl_complete_check.setStyleSheet("color:#6fdc6f;")
            return
        ok, detail = self._validate_expr_dict(expr, path="$.complete_expr")
        if ok:
            self._lbl_complete_check.setText("校验通过")
            self._lbl_complete_check.setStyleSheet("color:#6fdc6f;")
        else:
            QMessageBox.warning(self, "complete_expr 校验失败", detail)
            self._lbl_complete_check.setText("校验失败（见弹窗）")
            self._lbl_complete_check.setStyleSheet("color:#ff6b6b;")

    def _on_check_gw_condition_expr(self) -> None:
        expr, msg = self._parse_expr_text(self._txt_gw_cond_expr.toPlainText())
        if msg:
            QMessageBox.warning(self, "condition_expr 无效", msg)
            self._lbl_gw_cond_check.setText("校验失败")
            self._lbl_gw_cond_check.setStyleSheet("color:#ff6b6b;")
            return
        if expr is None:
            self._lbl_gw_cond_check.setText("未设置（使用 condition_id 引用）")
            self._lbl_gw_cond_check.setStyleSheet("color:#6fdc6f;")
            return
        ok, detail = self._validate_expr_dict(expr, path="$.condition_expr")
        if ok:
            self._lbl_gw_cond_check.setText("校验通过")
            self._lbl_gw_cond_check.setStyleSheet("color:#6fdc6f;")
        else:
            QMessageBox.warning(self, "condition_expr 校验失败", detail)
            self._lbl_gw_cond_check.setText("校验失败（见弹窗）")
            self._lbl_gw_cond_check.setStyleSheet("color:#ff6b6b;")

    # ---------- lists ----------

    def _load_skills(self) -> None:
        self._cmb_skill.clear()
        skills: List[Skill] = list(getattr(self._ctx.skills, "skills", []) or [])
        if not skills:
            self._cmb_skill.addItem("（无技能，请先在“技能配置”页面添加）", userData="")
            self._cmb_skill.setEnabled(False)
            return
        self._cmb_skill.setEnabled(True)
        for s in skills:
            self._cmb_skill.addItem(f"{s.name or '(未命名)'} [{(s.id or '')[-6:]}]", userData=s.id or "")

    def _load_modes(self) -> None:
        self._cmb_target_mode.clear()
        self._cmb_target_mode.addItem("（当前作用域）", userData="")
        for m in (self._preset.modes or []):
            self._cmb_target_mode.addItem(m.name or "(未命名)", userData=m.id or "")

    def _selected_target_mode_for_jump(self) -> str:
        data = self._cmb_target_mode.currentData()
        return data if isinstance(data, str) else ""

    def _find_track_by_id(self, tid: str, *, mode_override: Optional[str]) -> Optional[Track]:
        tid = (tid or "").strip()
        if not tid:
            return None
        if mode_override is None:
            return next((t for t in (self._preset.global_tracks or []) if (t.id or "").strip() == tid), None)
        m = next((m for m in (self._preset.modes or []) if (m.id or "").strip() == (mode_override or "").strip()), None)
        if m is None:
            return None
        return next((t for t in (m.tracks or []) if (t.id or "").strip() == tid), None)

    def _rebuild_jump_tracks(self) -> None:
        act = self._cmb_action.currentData()
        act = act.strip().lower() if isinstance(act, str) else "switch_mode"

        self._cmb_target_track.clear()

        mode_for_tracks: Optional[str] = None
        if act == "jump_track":
            tm = (self._selected_target_mode_for_jump() or "").strip()
            mode_for_tracks = tm if tm else self._mode_id
        elif act == "switch_mode":
            tm = self._cmb_target_mode.currentData()
            tm = tm if isinstance(tm, str) else ""
            mode_for_tracks = tm.strip() or None
        else:
            mode_for_tracks = self._mode_id

        tracks: List[Track] = []
        if mode_for_tracks is None:
            tracks = list(self._preset.global_tracks or [])
        else:
            m = next((m for m in (self._preset.modes or []) if (m.id or "").strip() == mode_for_tracks), None)
            tracks = list(m.tracks or []) if m is not None else []

        if not tracks:
            self._cmb_target_track.addItem("（无轨道）", userData="")
            self._cmb_target_track.setEnabled(False)
            return

        self._cmb_target_track.setEnabled(True)
        for t in tracks:
            tid = (t.id or "").strip()
            if tid:
                self._cmb_target_track.addItem(t.name or "(未命名轨道)", userData=tid)

    def _rebuild_jump_nodes(self) -> None:
        self._cmb_target_node.clear()

        act = self._cmb_action.currentData()
        act = act.strip().lower() if isinstance(act, str) else "switch_mode"

        if act == "jump_node":
            tid = self._track_id or ""
            mode_for_lookup = self._mode_id
        else:
            data = self._cmb_target_track.currentData()
            tid = data if isinstance(data, str) else ""
            if act == "jump_track":
                tm = (self._selected_target_mode_for_jump() or "").strip()
                mode_for_lookup = tm if tm else self._mode_id
            elif act == "switch_mode":
                tm = self._cmb_target_mode.currentData()
                tm = tm if isinstance(tm, str) else ""
                mode_for_lookup = tm.strip() or None
            else:
                mode_for_lookup = self._mode_id

        tr = self._find_track_by_id(tid, mode_override=mode_for_lookup)
        if tr is None or not tr.nodes:
            self._cmb_target_node.addItem("（无可用节点）", userData="")
            self._cmb_target_node.setEnabled(False)
            return

        self._cmb_target_node.setEnabled(True)
        for idx, nn in enumerate(tr.nodes):
            nid = (getattr(nn, "id", "") or "").strip()
            if not nid:
                continue
            label = getattr(nn, "label", "") or getattr(nn, "kind", "") or f"节点{idx}"
            self._cmb_target_node.addItem(f"{idx}: {label} [{nid[-6:]}]", userData=nid)

    def _on_action_changed(self) -> None:
        act = self._cmb_action.currentData()
        act = act.strip().lower() if isinstance(act, str) else "switch_mode"

        show_mode = act in ("switch_mode", "jump_track")
        show_track = act in ("switch_mode", "jump_track")
        show_node = act in ("switch_mode", "jump_track", "jump_node")

        if act == "switch_mode":
            self._lbl_target_mode.setText("目标模式(必选):")
        elif act == "jump_track":
            self._lbl_target_mode.setText("目标模式(可选):")

        self._lbl_target_mode.setVisible(show_mode)
        self._cmb_target_mode.setVisible(show_mode)
        self._lbl_target_track.setVisible(show_track)
        self._cmb_target_track.setVisible(show_track)
        self._lbl_target_node.setVisible(show_node)
        self._cmb_target_node.setVisible(show_node)

        if show_mode:
            self._load_modes()
        self._rebuild_jump_tracks()
        self._rebuild_jump_nodes()

    def _on_target_mode_changed(self) -> None:
        self._rebuild_jump_tracks()
        self._rebuild_jump_nodes()

    def _on_target_track_changed(self) -> None:
        self._rebuild_jump_nodes()

    # ---------- load node ----------

    def _load_from_node(self) -> None:
        n = self._node

        if isinstance(n, SkillNode):
            self._lbl_type.setText("节点类型：技能节点 (SkillNode)")
            self._panel_skill.setVisible(True)
            self._panel_gw.setVisible(False)
            self._load_skills()

            self._edit_label.setText(n.label or "")
            sid = (n.skill_id or "").strip()
            for i in range(self._cmb_skill.count()):
                if self._cmb_skill.itemData(i) == sid:
                    self._cmb_skill.setCurrentIndex(i)
                    break

            self._spin_cast.setValue(int(n.override_cast_ms) if (n.override_cast_ms or 0) > 0 else 0)
            self._txt_comment.setPlainText(n.comment or "")

            self._txt_start_expr.setPlainText(self._pretty_json(n.start_expr) if isinstance(n.start_expr, dict) else "")
            self._txt_complete_expr.setPlainText(self._pretty_json(n.complete_expr) if isinstance(n.complete_expr, dict) else "")

        elif isinstance(n, GatewayNode):
            self._lbl_type.setText("节点类型：网关节点 (GatewayNode)")
            self._panel_skill.setVisible(False)
            self._panel_gw.setVisible(True)

            self._edit_label.setText(n.label or "")

            act = (n.action or "switch_mode").strip().lower() or "switch_mode"
            for i in range(self._cmb_action.count()):
                if self._cmb_action.itemData(i) == act:
                    self._cmb_action.setCurrentIndex(i)
                    break

            self._on_action_changed()

            # restore target_mode
            tm = (n.target_mode_id or "").strip()
            for i in range(self._cmb_target_mode.count()):
                if self._cmb_target_mode.itemData(i) == tm:
                    self._cmb_target_mode.setCurrentIndex(i)
                    break

            self._rebuild_jump_tracks()
            self._rebuild_jump_nodes()

            # restore track/node
            tt = (n.target_track_id or "").strip()
            if tt:
                for i in range(self._cmb_target_track.count()):
                    if self._cmb_target_track.itemData(i) == tt:
                        self._cmb_target_track.setCurrentIndex(i)
                        break
                self._rebuild_jump_nodes()

            tn = (n.target_node_id or "").strip()
            if tn:
                for i in range(self._cmb_target_node.count()):
                    if self._cmb_target_node.itemData(i) == tn:
                        self._cmb_target_node.setCurrentIndex(i)
                        break

            ce = getattr(n, "condition_expr", None)
            self._txt_gw_cond_expr.setPlainText(self._pretty_json(ce) if isinstance(ce, dict) else "")

        else:
            self._lbl_type.setText("节点类型：未知")
            self._panel_skill.setVisible(False)
            self._panel_gw.setVisible(False)

    # ---------- OK ----------

    def _on_ok(self) -> None:
        n = self._node
        label = (self._edit_label.text() or "").strip()

        if isinstance(n, SkillNode):
            sid = self._cmb_skill.currentData()
            if not isinstance(sid, str) or not sid.strip():
                QMessageBox.warning(self, "错误", "请选择一个技能。")
                return
            n.skill_id = sid.strip()
            n.label = label or n.label or "Skill"

            cast = int(self._spin_cast.value())
            n.override_cast_ms = None if cast <= 0 else cast
            n.comment = self._txt_comment.toPlainText().rstrip("\n")

            se_dict, se_err = self._parse_expr_text(self._txt_start_expr.toPlainText())
            if se_err:
                QMessageBox.warning(self, "start_expr 无效", se_err)
                return
            if se_dict is not None:
                ok, detail = self._validate_expr_dict(se_dict, path="$.start_expr")
                if not ok:
                    QMessageBox.warning(self, "start_expr 校验失败", detail)
                    return

            ce_dict, ce_err = self._parse_expr_text(self._txt_complete_expr.toPlainText())
            if ce_err:
                QMessageBox.warning(self, "complete_expr 无效", ce_err)
                return
            if ce_dict is not None:
                ok, detail = self._validate_expr_dict(ce_dict, path="$.complete_expr")
                if not ok:
                    QMessageBox.warning(self, "complete_expr 校验失败", detail)
                    return

            n.start_expr = se_dict
            n.complete_expr = ce_dict
            self.accept()
            return

        if isinstance(n, GatewayNode):
            n.label = label or n.label or "Gateway"

            act = self._cmb_action.currentData()
            act = act.strip().lower() if isinstance(act, str) else "switch_mode"
            if act not in ("switch_mode", "jump_track", "jump_node", "end"):
                act = "switch_mode"
            n.action = act

            cond_dict, cond_err = self._parse_expr_text(self._txt_gw_cond_expr.toPlainText())
            if cond_err:
                QMessageBox.warning(self, "condition_expr 无效", cond_err)
                return
            if cond_dict is not None:
                ok, detail = self._validate_expr_dict(cond_dict, path="$.condition_expr")
                if not ok:
                    QMessageBox.warning(self, "condition_expr 校验失败", detail)
                    return
                n.condition_expr = cond_dict
                n.condition_id = None
            else:
                n.condition_expr = None

            # reset targets
            n.target_mode_id = None
            n.target_track_id = None
            n.target_node_id = None

            if act == "end":
                self.accept()
                return

            if act == "switch_mode":
                mid = self._cmb_target_mode.currentData()
                mid = mid if isinstance(mid, str) else ""
                mid = mid.strip()
                if not mid:
                    QMessageBox.warning(self, "错误", "switch_mode 必须选择一个目标模式。")
                    return
                n.target_mode_id = mid

                tid = self._cmb_target_track.currentData()
                tid = tid if isinstance(tid, str) else ""
                tid = tid.strip()
                nid = self._cmb_target_node.currentData()
                nid = nid if isinstance(nid, str) else ""
                nid = nid.strip()
                if tid and nid:
                    n.target_track_id = tid
                    n.target_node_id = nid
                self.accept()
                return

            if act == "jump_track":
                tm = self._cmb_target_mode.currentData()
                tm = tm if isinstance(tm, str) else ""
                tm = tm.strip()
                n.target_mode_id = tm or None

                tid = self._cmb_target_track.currentData()
                tid = tid if isinstance(tid, str) else ""
                tid = tid.strip()
                if not tid:
                    QMessageBox.warning(self, "错误", "jump_track 必须选择目标轨道。")
                    return
                n.target_track_id = tid

                nid = self._cmb_target_node.currentData()
                nid = nid if isinstance(nid, str) else ""
                nid = nid.strip()
                if not nid:
                    QMessageBox.warning(self, "错误", "jump_track 必须选择目标节点。")
                    return
                n.target_node_id = nid
                self.accept()
                return

            if act == "jump_node":
                nid = self._cmb_target_node.currentData()
                nid = nid if isinstance(nid, str) else ""
                nid = nid.strip()
                if not nid:
                    QMessageBox.warning(self, "错误", "jump_node 必须选择目标节点。")
                    return
                n.target_node_id = nid
                self.accept()
                return

            self.accept()
            return

        self.accept()