# qtui/nav_panel.py
from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
    QSizePolicy,
    QStyle,
)

from qtui.icons import load_icon


class NavPanel(QWidget):
    """
    左侧导航面板：
    - 顶部应用标题
    - Profile 区：下拉选择 + 新建/复制/重命名/删除 按钮（带图标）
    - 页面导航按钮：基础配置 / 技能配置 / 取色点位配置（带图标）

    信号：
    - profile_selected(str)  : 用户从下拉框选择了某个 profile
    - profile_action(str)    : "new" | "copy" | "rename" | "delete"
    - page_selected(str)     : "base" | "skills" | "points"
    """

    profile_selected = Signal(str)
    profile_action = Signal(str)
    page_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setMinimumWidth(220)
        self.setMaximumWidth(320)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        style = self.style()

        # ---- 标题 ----
        title = QLabel("Game Macro", self)
        font = title.font()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        # ---- 分组辅助函数 ----
        def add_group_header(text: str) -> None:
            lbl = QLabel(text, self)
            f = lbl.font()
            f.setPointSize(10)
            f.setBold(True)
            lbl.setFont(f)
            layout.addWidget(lbl)

            line = QFrame(self)
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            layout.addWidget(line)

        # -------- Profile 组 --------
        add_group_header("Profile")

        self._combo = QComboBox(self)
        layout.addWidget(self._combo)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        icon_new = load_icon("add", style, QStyle.StandardPixmap.SP_FileIcon)
        icon_copy = load_icon("copy", style, QStyle.StandardPixmap.SP_DirLinkIcon)
        icon_rename = load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogDetailedView)
        icon_delete = load_icon("delete", style, QStyle.StandardPixmap.SP_TrashIcon)

        btn_new = QPushButton("新建", self)
        btn_new.setIcon(icon_new)
        btn_new.clicked.connect(lambda: self.profile_action.emit("new"))
        btn_row.addWidget(btn_new)

        btn_copy = QPushButton("复制", self)
        btn_copy.setIcon(icon_copy)
        btn_copy.clicked.connect(lambda: self.profile_action.emit("copy"))
        btn_row.addWidget(btn_copy)

        btn_rename = QPushButton("重命名", self)
        btn_rename.setIcon(icon_rename)
        btn_rename.clicked.connect(lambda: self.profile_action.emit("rename"))
        btn_row.addWidget(btn_rename)

        btn_delete = QPushButton("删除", self)
        btn_delete.setIcon(icon_delete)
        btn_delete.clicked.connect(lambda: self.profile_action.emit("delete"))
        btn_row.addWidget(btn_delete)

        layout.addLayout(btn_row)

        # -------- 导航组：配置 --------
        add_group_header("配置")

        icon_base = load_icon("settings", style, QStyle.StandardPixmap.SP_FileDialogContentsView)
        icon_skill = load_icon("skill", style, QStyle.StandardPixmap.SP_ComputerIcon)
        icon_point = load_icon("point", style, QStyle.StandardPixmap.SP_DriveHDIcon)

        self._btn_base = QPushButton("基础配置", self)
        self._btn_base.setIcon(icon_base)
        self._btn_base.setCheckable(True)
        self._btn_base.clicked.connect(lambda: self.page_selected.emit("base"))
        layout.addWidget(self._btn_base)

        self._btn_skills = QPushButton("技能配置", self)
        self._btn_skills.setIcon(icon_skill)
        self._btn_skills.setCheckable(True)
        self._btn_skills.clicked.connect(lambda: self.page_selected.emit("skills"))
        layout.addWidget(self._btn_skills)

        self._btn_points = QPushButton("取色点位配置", self)
        self._btn_points.setIcon(icon_point)
        self._btn_points.setCheckable(True)
        self._btn_points.clicked.connect(lambda: self.page_selected.emit("points"))
        layout.addWidget(self._btn_points)

        layout.addStretch(1)

        # 底部提示
        hint = QLabel("Phase 1：配置管理", self)
        hint.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(hint)

        # 连接 profile 下拉变化
        self._combo.currentTextChanged.connect(self._on_profile_changed)

        # 默认选中“基础配置”按钮
        self.set_active_page("base")

    # ---------- 对外接口 ----------

    def set_profiles(self, names: List[str], current: str) -> None:
        """
        更新 Profile 下拉列表，并尝试选中 current。
        """
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(names)
        if current and current in names:
            self._combo.setCurrentText(current)
        elif names:
            self._combo.setCurrentIndex(0)
        self._combo.blockSignals(False)

    def current_profile(self) -> str:
        return (self._combo.currentText() or "").strip()

    def set_active_page(self, key: str) -> None:
        """
        更新左侧导航按钮的选中状态。
        """
        self._btn_base.setChecked(key == "base")
        self._btn_skills.setChecked(key == "skills")
        self._btn_points.setChecked(key == "points")

    # ---------- 内部回调 ----------

    def _on_profile_changed(self, text: str) -> None:
        name = (text or "").strip()
        if name:
            self.profile_selected.emit(name)