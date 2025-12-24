from __future__ import annotations

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.constants import *


class NavFrame(tb.Frame):
    """
    Left navigation with groups + profile selector.

    Callbacks:
      - on_nav(page_key)
      - on_profile_select(profile_name)
      - on_profile_action(action: "new"|"copy"|"rename"|"delete")
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_nav,
        on_profile_select,
        on_profile_action,
    ) -> None:
        super().__init__(master, padding=(10, 10))
        self.configure(width=260)
        self.pack_propagate(False)

        self._on_nav = on_nav
        self._on_profile_select = on_profile_select
        self._on_profile_action = on_profile_action

        tb.Label(self, text="Game Macro", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 10))

        def group(title: str) -> None:
            tb.Label(self, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 6))
            tb.Separator(self).pack(fill=X, pady=(0, 8))

        # -------- Profile group --------
        group("Profile")

        self._var_profile = tk.StringVar(value="")
        self._cb_profile = tb.Combobox(self, textvariable=self._var_profile, values=[], state="readonly")
        self._cb_profile.pack(fill=X)
        self._cb_profile.bind("<<ComboboxSelected>>", self._on_profile_selected)

        # 2x2 grid buttons (auto-fit)
        btn_grid = tb.Frame(self)
        btn_grid.pack(fill=X, pady=(8, 0))

        btn_grid.columnconfigure(0, weight=1)
        btn_grid.columnconfigure(1, weight=1)

        tb.Button(btn_grid, text="新建", command=lambda: self._on_profile_action("new")).grid(
            row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6)
        )
        tb.Button(btn_grid, text="复制", command=lambda: self._on_profile_action("copy")).grid(
            row=0, column=1, sticky="ew", pady=(0, 6)
        )
        tb.Button(btn_grid, text="重命名", command=lambda: self._on_profile_action("rename")).grid(
            row=1, column=0, sticky="ew", padx=(0, 6)
        )
        tb.Button(btn_grid, text="删除", bootstyle=DANGER, command=lambda: self._on_profile_action("delete")).grid(
            row=1, column=1, sticky="ew"
        )

        # -------- Navigation groups --------
        btn_style = "secondary.TButton"

        group("配置")
        tb.Button(self, text="基础配置", style=btn_style, command=lambda: self._on_nav("base")).pack(fill=X, pady=4)

        group("数据")
        tb.Button(self, text="技能配置", style=btn_style, command=lambda: self._on_nav("skills")).pack(fill=X, pady=4)
        tb.Button(self, text="取色点位配置", style=btn_style, command=lambda: self._on_nav("points")).pack(fill=X, pady=4)

        tb.Separator(self).pack(fill=X, pady=12)
        tb.Label(self, text="Phase 1：配置管理", justify=LEFT).pack(anchor="w")

    def set_profiles(self, names: list[str], current: str) -> None:
        self._cb_profile.configure(values=names)
        if current in names:
            self._var_profile.set(current)
        elif names:
            self._var_profile.set(names[0])
        else:
            self._var_profile.set("")

    def get_current_profile(self) -> str:
        return self._var_profile.get().strip()

    def _on_profile_selected(self, _evt=None) -> None:
        name = self._var_profile.get().strip()
        if name:
            self._on_profile_select(name)