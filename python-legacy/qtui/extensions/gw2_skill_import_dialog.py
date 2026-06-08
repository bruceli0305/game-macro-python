from __future__ import annotations

import json
import logging
from typing import Optional, Dict, Any, Iterable, Callable, Tuple, Set

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QComboBox,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QMessageBox,
)
from PySide6.QtCore import Qt

from core.profiles import ProfileContext
from core.app.services.app_services import AppServices
from core.models.skill import Skill
from qtui.icons import resource_path

log = logging.getLogger(__name__)

# 职业英文名 -> 中文名 映射
PROF_NAME_ZH: Dict[str, str] = {
    "Guardian": "守护者",
    "Warrior": "战士",
    "Engineer": "工程师",
    "Ranger": "游侠",
    "Thief": "潜行者",
    "Elementalist": "元素使",
    "Mesmer": "幻术师",
    "Necromancer": "死灵法师",
    "Revenant": "预言者",
}

# 武器英文名 -> 中文名 映射（可根据需要继续补充/调整）
WEAPON_NAME_ZH: Dict[str, str] = {
    "Axe": "斧",
    "Dagger": "匕首",
    "Mace": "钉锤",
    "Pistol": "手枪",
    "Scepter": "权杖",
    "Sword": "剑",
    "Focus": "聚能器",
    "Shield": "盾牌",
    "Torch": "火炬",
    "Warhorn": "战号",
    "Greatsword": "巨剑",
    "Hammer": "锤",
    "Longbow": "长弓",
    "Rifle": "步枪",
    "Shortbow": "短弓",
    "Staff": "法杖",
    "Spear": "长矛",
    "Trident": "三叉戟",
    "Harpoon Gun": "鱼叉枪",
    "Speargun": "鱼枪",
}

# 插槽英文名 -> 中文名 映射
SLOT_NAME_ZH: Dict[str, str] = {
    "Heal": "治疗",
    "Utility": "通用",
    "Elite": "精英",
    "Downed_1": "倒地1",
    "Downed_2": "倒地2",
    "Downed_3": "倒地3",
    "Downed_4": "倒地4",
    "Pet": "宠物技能",
    "Toolbelt": "工具带",
}


def prof_display_name(name: str) -> str:
    """
    将职业英文名映射为中文显示名；若无映射则原样返回。
    """
    n = (name or "").strip()
    return PROF_NAME_ZH.get(n, n)


def weapon_display_name(name: str) -> str:
    """
    将武器英文名映射为中文显示名；若无映射则原样返回。
    """
    n = (name or "").strip()
    return WEAPON_NAME_ZH.get(n, n)


def slot_display_name(name: str) -> str:
    """
    将插槽英文名映射为中文显示名；若无映射则按常见模式生成：
    - Weapon_1 -> 武器1
    - Profession_1 -> 职业技1
    - Downed_1 -> 倒地1
    否则原样返回。
    """
    n = (name or "").strip()
    if not n:
        return ""

    direct = SLOT_NAME_ZH.get(n)
    if direct:
        return direct

    lower = n.lower()
    # Weapon_1..Weapon_5
    if lower.startswith("weapon_"):
        try:
            num = n.split("_", 1)[1]
        except Exception:
            num = ""
        return f"武器{num}" if num else "武器技能"

    # Profession_1..Profession_*
    if lower.startswith("profession_"):
        try:
            num = n.split("_", 1)[1]
        except Exception:
            num = ""
        return f"职业技{num}" if num else "职业技能"

    # Downed_1..Downed_*
    if lower.startswith("downed_"):
        try:
            num = n.split("_", 1)[1]
        except Exception:
            num = ""
        return f"倒地{num}" if num else "倒地"

    return n


class Gw2SkillImportDialog(QDialog):
    """
    GW2 技能导入插件：

    - 从 assets/json/gw2/skills_all.json / professions_all.json 读取数据
    - 过滤条件：职业 + 技能类型 + 武器 + 文本搜索（都有“全部”选项，可组合过滤）
    - 列表展示：ID / 名称 / 职业 / 槽位 / 冷却(s) / 描述摘要
    - 支持多选 & 批量导入到当前 Profile 的技能列表（仅填充通用字段）

    通用字段映射：
    - Skill.name        <- GW2 name
    - Skill.game_id     <- GW2 id
    - Skill.game_desc   <- GW2 description
    - Skill.icon_url    <- GW2 icon
    - Skill.cooldown_ms <- facts 中 Recharge(value 秒) * 1000
    - Skill.radius      <- facts 中 Distance(distance)
    """

    def __init__(
        self,
        *,
        parent: Optional[QWidget] = None,
        ctx: ProfileContext,
        services: AppServices,
        on_imported: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)

        self._ctx = ctx
        self._services = services
        self._on_imported = on_imported or (lambda: None)

        self.setWindowTitle("GW2 技能导入（插件）")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(640)

        # 数据容器
        self._skills: list[Dict[str, Any]] = []
        self._skills_by_id: Dict[str, Dict[str, Any]] = {}
        self._professions: Dict[str, Any] = {}
        # (profession_en, weapon_name) -> set(skill_id_str)
        self._weapon_skills: Dict[Tuple[str, str], Set[str]] = {}

        self._build_ui()
        self._load_data()
        self._refresh_professions()
        self._refresh_weapons_for_prof()  # 默认职业=全部 -> 只有“全部武器”
        self._update_weapon_visibility()
        self._refresh_tree()

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 顶部：当前 Profile 信息
        lbl_profile = QLabel(
            f"当前 Profile: {self._ctx.profile_name}  "
            f"(当前 profile 中技能数量: {len(self._ctx.profile.skills.skills)})",
            self,
        )
        root.addWidget(lbl_profile)

        # 过滤区
        row_filter = QHBoxLayout()
        row_filter.setSpacing(8)

        # 职业
        row_filter.addWidget(QLabel("职业:", self))
        self._cmb_prof = QComboBox(self)
        row_filter.addWidget(self._cmb_prof)

        # 技能类型
        row_filter.addWidget(QLabel("技能类型:", self))
        self._cmb_type = QComboBox(self)
        self._cmb_type.addItem("全部类型", userData=None)
        self._cmb_type.addItem("武器技能", userData="weapon")
        self._cmb_type.addItem("治疗技能(Heal)", userData="heal")
        self._cmb_type.addItem("通用技能(Utility)", userData="utility")
        self._cmb_type.addItem("精英技能(Elite)", userData="elite")
        self._cmb_type.addItem("职业技能(Profession)", userData="profession")
        self._cmb_type.addItem("其它", userData="other")
        row_filter.addWidget(self._cmb_type)

        # 武器（仅在“武器技能”类型时显示）
        self._lbl_weapon = QLabel("武器:", self)
        row_filter.addWidget(self._lbl_weapon)
        self._cmb_weapon = QComboBox(self)
        row_filter.addWidget(self._cmb_weapon)

        # 搜索
        row_filter.addWidget(QLabel("搜索:", self))
        self._edit_search = QLineEdit(self)
        self._edit_search.setPlaceholderText("按名称 / ID / 描述 搜索（模糊匹配）")
        row_filter.addWidget(self._edit_search, 1)

        btn_clear = QPushButton("清空搜索", self)
        btn_clear.clicked.connect(self._edit_search.clear)
        row_filter.addWidget(btn_clear)

        root.addLayout(row_filter)

        # 列表区
        self._tree = QTreeWidget(self)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeWidget.ExtendedSelection)   # 支持多选
        self._tree.setSelectionBehavior(QTreeWidget.SelectRows)

        headers = ["ID", "名称", "职业", "槽位", "冷却(s)", "描述"]
        self._tree.setHeaderLabels(headers)

        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 名称
        header.setSectionResizeMode(2, QHeaderView.Interactive)       # 职业，用户可调
        header.resizeSection(2, 90)                                   # 默认宽度适合单个职业名
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 槽位
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 冷却
        header.setSectionResizeMode(5, QHeaderView.Stretch)           # 描述撑满

        root.addWidget(self._tree, 1)

        # 底部状态 + 按钮
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._lbl_stats = QLabel("加载中...", self)
        bottom.addWidget(self._lbl_stats, 1)

        self._btn_import = QPushButton("导入选中技能到当前 Profile", self)
        self._btn_import.clicked.connect(self._on_import_clicked)
        bottom.addWidget(self._btn_import)

        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)

        root.addLayout(bottom)

        # 信号连接（过滤）
        self._cmb_prof.currentIndexChanged.connect(self._on_prof_changed)
        self._cmb_weapon.currentIndexChanged.connect(lambda _i: self._refresh_tree())
        self._cmb_type.currentIndexChanged.connect(self._on_type_changed)
        self._edit_search.textChanged.connect(lambda _t: self._refresh_tree())

    # ---------- UI 辅助 ----------

    def _update_weapon_visibility(self) -> None:
        """
        仅在技能类型 = 武器技能 时显示武器筛选。
        """
        idx_t = self._cmb_type.currentIndex()
        type_filter = self._cmb_type.itemData(idx_t) if idx_t >= 0 else None
        type_str = str(type_filter) if type_filter is not None else ""
        show = (type_str == "weapon")
        self._lbl_weapon.setVisible(show)
        self._cmb_weapon.setVisible(show)

    # ---------- 数据加载 ----------

    def _load_data(self) -> None:
        """
        从 assets/json/gw2/skills_all.json / professions_all.json 读取数据。
        """
        skills_path = resource_path("assets/json/gw2/skills_all.json")
        profs_path = resource_path("assets/json/gw2/professions_all.json")

        self._skills = []
        self._skills_by_id = {}
        self._professions = {}
        self._weapon_skills = {}

        # 读取 skills_all.json
        try:
            if not skills_path.is_file():
                raise FileNotFoundError(f"skills_all.json 不存在: {skills_path}")
            data = json.loads(skills_path.read_text(encoding="utf-8"))

            if isinstance(data, list):
                self._skills = [x for x in data if isinstance(x, dict)]
            elif isinstance(data, dict):
                if "skills" in data and isinstance(data["skills"], list):
                    self._skills = [x for x in data["skills"] if isinstance(x, dict)]
                else:
                    self._skills = [v for v in data.values() if isinstance(v, dict)]
            else:
                self._skills = []

            for s in self._skills:
                sid = s.get("id", None)
                if sid is None:
                    continue
                self._skills_by_id[str(sid)] = s

        except Exception as e:
            log.exception("加载 skills_all.json 失败")
            QMessageBox.critical(
                self,
                "错误",
                f"加载技能数据失败：{e}",
                QMessageBox.Ok,
            )
            self._skills = []
            self._skills_by_id = {}

        # 读取 professions_all.json
        try:
            if profs_path.is_file():
                pdata = json.loads(profs_path.read_text(encoding="utf-8"))
                if isinstance(pdata, dict):
                    self._professions = pdata
                else:
                    self._professions = {}
            else:
                self._professions = {}
        except Exception:
            log.exception("加载 professions_all.json 失败")
            self._professions = {}

        # 预构建 (profession, weapon) -> {skill_ids}
        self._weapon_skills.clear()
        for prof_en, pval in self._professions.items():
            try:
                wmap = pval.get("weapons", {}) or {}
                if not isinstance(wmap, dict):
                    continue
                for wname, wdata in wmap.items():
                    skills_arr = wdata.get("skills", []) or []
                    sids: Set[str] = set()
                    for sk in skills_arr:
                        if isinstance(sk, dict) and "id" in sk:
                            sids.add(str(sk["id"]))
                    if sids:
                        self._weapon_skills[(prof_en, wname)] = sids
            except Exception:
                log.exception("预构建 weapon_skills 失败：prof=%s", prof_en)

    # ---------- 过滤逻辑 ----------

    def _refresh_professions(self) -> None:
        """
        刷新职业下拉列表（显示中文名，内部用英文值过滤）。
        """
        self._cmb_prof.blockSignals(True)
        self._cmb_prof.clear()

        # 全部职业
        self._cmb_prof.addItem("全部职业", userData=None)

        prof_names_en: set[str] = set()

        # 优先使用 professions_all.json 的 key 列表（英文）
        for name in sorted(self._professions.keys()):
            if not name:
                continue
            prof_names_en.add(str(name))

        # 如果 professions_all.json 为空，则从 skills_all.json 中汇总 professions 字段
        if not prof_names_en:
            for s in self._skills:
                for p in s.get("professions", []) or []:
                    if isinstance(p, str) and p:
                        prof_names_en.add(p)

        for name_en in sorted(prof_names_en):
            disp = prof_display_name(name_en)
            self._cmb_prof.addItem(disp, userData=name_en)

        self._cmb_prof.blockSignals(False)

    def _refresh_weapons_for_prof(self) -> None:
        """
        根据当前职业刷新武器下拉列表。
        - 全部职业：只提供“全部武器”
        - 具体职业：从 professions_all.json 的 weapons 键加载（显示中文，内部用英文）
        """
        self._cmb_weapon.blockSignals(True)
        self._cmb_weapon.clear()

        idx = self._cmb_prof.currentIndex()
        prof_filter = self._cmb_prof.itemData(idx) if idx >= 0 else None
        prof_filter = str(prof_filter) if prof_filter is not None else ""

        self._cmb_weapon.addItem("全部武器", userData=None)
        if not prof_filter:
            self._cmb_weapon.blockSignals(False)
            return

        pval = self._professions.get(prof_filter, {}) or {}
        wmap = pval.get("weapons", {}) or {}
        if isinstance(wmap, dict):
            for wname in sorted(wmap.keys()):
                disp = weapon_display_name(str(wname))
                self._cmb_weapon.addItem(disp, userData=wname)

        self._cmb_weapon.blockSignals(False)

    def _on_prof_changed(self, _index: int) -> None:
        """
        职业变更时，刷新武器列表并刷新技能列表。
        """
        self._refresh_weapons_for_prof()
        self._refresh_tree()

    def _on_type_changed(self, _index: int) -> None:
        """
        技能类型变更时，更新武器控件可见性并刷新列表。
        """
        self._update_weapon_visibility()
        self._refresh_tree()

    def _iter_filtered_skills(self) -> Iterable[Dict[str, Any]]:
        """
        根据职业 / 技能类型 / 武器 / 搜索关键字过滤技能。
        """
        # 职业过滤（英文内部名）
        idx_p = self._cmb_prof.currentIndex()
        prof_filter = self._cmb_prof.itemData(idx_p) if idx_p >= 0 else None
        prof_filter = str(prof_filter) if prof_filter is not None else ""

        # 技能类型过滤
        idx_t = self._cmb_type.currentIndex()
        type_filter = self._cmb_type.itemData(idx_t) if idx_t >= 0 else None
        type_filter = str(type_filter) if type_filter is not None else ""

        # 武器过滤（英文 weapon 名，仅在 type=weapon 时生效）
        idx_w = self._cmb_weapon.currentIndex()
        weapon_filter = self._cmb_weapon.itemData(idx_w) if idx_w >= 0 else None
        weapon_filter = str(weapon_filter) if weapon_filter is not None else ""
        if type_filter != "weapon":
            # 非武器技能模式下忽略武器过滤
            weapon_filter = ""

        # 搜索关键字
        kw = (self._edit_search.text() or "").strip().lower()

        for s in self._skills:
            # profession 过滤：GW2 技能 JSON 的 professions 字段
            if prof_filter:
                s_profs = s.get("professions", []) or []
                if prof_filter not in s_profs:
                    continue

            # weapon 过滤：使用 professions_all.json 的 (profession, weapon) -> skill_ids 映射
            if prof_filter and weapon_filter:
                key = (prof_filter, weapon_filter)
                allowed_ids = self._weapon_skills.get(key)
                if not allowed_ids:
                    continue
                sid = s.get("id", None)
                if sid is None or str(sid) not in allowed_ids:
                    continue

            # 技能类型过滤
            if type_filter and not self._skill_matches_type_filter(s, type_filter):
                continue

            # 搜索过滤：name / id / description
            if kw:
                name = str(s.get("name", "") or "").lower()
                desc = str(s.get("description", "") or "").lower()
                sid = str(s.get("id", "") or "")
                if kw not in name and kw not in desc and kw not in sid.lower():
                    continue

            yield s

    def _skill_matches_type_filter(self, s: Dict[str, Any], kind: str) -> bool:
        """
        根据 kind 过滤技能类型。
        """
        t = (s.get("type") or "").strip().lower()
        slot = (s.get("slot") or "").strip().lower()

        if kind == "weapon":
            return slot.startswith("weapon_") or t == "weapon"
        if kind == "heal":
            return t == "heal" or slot == "heal"
        if kind == "utility":
            return t == "utility" or slot == "utility"
        if kind == "elite":
            return t == "elite" or slot == "elite"
        if kind == "profession":
            return t == "profession" or slot.startswith("profession_")
        if kind == "other":
            if t in ("weapon", "heal", "utility", "elite", "profession"):
                return False
            if slot.startswith("weapon_") or slot in ("heal", "utility", "elite") or slot.startswith("profession_"):
                return False
            return True
        return True

    # ---------- 列表刷新 ----------

    def _refresh_tree(self) -> None:
        """
        根据当前过滤条件刷新技能列表。
        """
        self._tree.clear()

        total = len(self._skills)
        filtered = 0

        for s in self._iter_filtered_skills():
            item = self._skill_to_item(s)
            if item is not None:
                self._tree.addTopLevelItem(item)
                filtered += 1

        self._lbl_stats.setText(f"总技能数: {total}    当前过滤后: {filtered}")

        # ID / 名称 / 槽位 / 冷却 列适当收紧，避免太宽
        try:
            self._tree.resizeColumnToContents(0)
            self._tree.resizeColumnToContents(1)
            self._tree.resizeColumnToContents(3)
            self._tree.resizeColumnToContents(4)
        except Exception:
            pass

    def _skill_to_item(self, s: Dict[str, Any]) -> Optional[QTreeWidgetItem]:
        try:
            sid = s.get("id", None)
            if sid is None:
                return None
            sid_str = str(sid)

            name = str(s.get("name", "") or "")

            # professions 中文回显
            profs = s.get("professions", []) or []
            prof_list: list[str] = []
            if isinstance(profs, list):
                for p in profs:
                    if not isinstance(p, str):
                        continue
                    prof_list.append(prof_display_name(p))
            else:
                if isinstance(profs, str) and profs:
                    prof_list.append(prof_display_name(profs))

            prof_txt = ", ".join(prof_list)

            # 插槽：内部仍用英文原值做过滤，这里只做中文显示
            raw_slot = str(s.get("slot", "") or "")
            slot_disp = slot_display_name(raw_slot)

            cd_s = self._extract_cooldown_s(s)
            cd_txt = f"{cd_s:.2f}" if cd_s is not None and cd_s > 0 else ""

            desc = str(s.get("description", "") or "")
            desc_short = self._shorten(desc, 80)

            cols = [sid_str, name, prof_txt, slot_disp, cd_txt, desc_short]
            item = QTreeWidgetItem(cols)
            item.setData(0, Qt.UserRole, sid_str)
            return item
        except Exception:
            log.exception("构造技能列表项失败")
            return None

    @staticmethod
    def _extract_cooldown_s(s: Dict[str, Any]) -> Optional[float]:
        """
        从技能 JSON 的 facts 中提取冷却时间（秒）。
        """
        facts = s.get("facts", []) or []
        if not isinstance(facts, list):
            return None
        cd: Optional[float] = None
        for f in facts:
            if not isinstance(f, dict):
                continue
            f_type = (f.get("type") or "").lower()
            if f_type == "recharge":
                val = f.get("value", None)
                try:
                    v = float(val)
                except Exception:
                    continue
                cd = v
                break
        return cd

    @staticmethod
    def _extract_radius(s: Dict[str, Any]) -> Optional[int]:
        """
        从技能 JSON 的 facts 中提取半径（Distance.distance）。
        """
        facts = s.get("facts", []) or []
        if not isinstance(facts, list):
            return None
        for f in facts:
            if not isinstance(f, dict):
                continue
            f_type = (f.get("type") or "").lower()
            if f_type == "distance":
                dist = f.get("distance", None)
                try:
                    return int(dist)
                except Exception:
                    return None
        return None

    @staticmethod
    def _shorten(text: str, limit: int) -> str:
        t = (text or "").strip()
        if len(t) <= limit:
            return t
        return t[: limit - 3] + "..."

    # ---------- 导入逻辑：多选 & 批量导入 ----------

    def _on_import_clicked(self) -> None:
        """
        将当前选中的 GW2 技能批量导入到当前 Profile 的 skills 列表中（仅通用字段）。
        """
        items = self._tree.selectedItems()
        if not items:
            QMessageBox.information(self, "提示", "请先在列表中选择一个或多个技能。", QMessageBox.Ok)
            return

        # 预先收集当前 profile 中已有的 game_id，避免重复导入
        existing_ids: Set[int] = set()
        try:
            for s in self._ctx.profile.skills.skills:
                try:
                    gid = int(getattr(s, "game_id", 0) or 0)
                    if gid:
                        existing_ids.add(gid)
                except Exception:
                    continue
        except Exception:
            log.exception("收集现有 game_id 失败")

        total_sel = len(items)
        imported = 0
        skipped_exists = 0
        errors = 0

        for item in items:
            sid = item.data(0, Qt.UserRole)
            sid_str = str(sid) if sid is not None else ""
            if not sid_str:
                errors += 1
                continue

            gw2 = self._skills_by_id.get(sid_str)
            if gw2 is None:
                errors += 1
                continue

            try:
                gw2_id = int(gw2.get("id", 0))
            except Exception:
                gw2_id = 0

            # 已存在相同 game_id -> 跳过
            if gw2_id and gw2_id in existing_ids:
                skipped_exists += 1
                continue

            try:
                new_skill = self._create_skill_from_gw2(gw2)
            except Exception:
                errors += 1
                log.exception("从 GW2 技能 JSON 创建 Skill 失败 (id=%s)", sid_str)
                continue

            # 追加到 profile
            try:
                self._ctx.profile.skills.skills.append(new_skill)
                imported += 1
                if gw2_id:
                    existing_ids.add(gw2_id)
            except Exception:
                errors += 1
                log.exception("将新 Skill 追加到 profile 失败 (id=%s)", new_skill.id)
                continue

        if imported > 0:
            # 标记 skills 为 dirty 并通知 UI
            try:
                self._services.skills.mark_dirty()
                self._services.notify_dirty()
            except Exception:
                log.exception("标记 skills 脏状态失败")

            # 通知外层（MainWindow）刷新 SkillsPage 列表
            try:
                self._on_imported()
            except Exception:
                log.exception("on_imported 回调执行失败")

        # 汇总提示
        parts = [
            f"本次共选择 {total_sel} 个技能：",
            f"  成功导入 {imported} 个。",
        ]
        if skipped_exists:
            parts.append(f"  {skipped_exists} 个按 game_id 判断已存在，已跳过。")
        if errors:
            parts.append(f"  {errors} 个导入失败（详见日志）。")

        QMessageBox.information(
            self,
            "导入结果",
            "\n".join(parts),
            QMessageBox.Ok,
        )

    def _create_skill_from_gw2(self, gw2: Dict[str, Any]) -> Skill:
        """
        从单条 GW2 技能 JSON 创建一个新的 Skill 实例（只填充通用字段）。
        """
        new_skill = Skill()

        try:
            new_skill.id = self._ctx.idgen.next_id()
        except Exception:
            sid = gw2.get("id", None)
            new_skill.id = f"gw2-{sid}" if sid is not None else "gw2-unknown"

        new_skill.enabled = True
        new_skill.name = str(gw2.get("name", "") or f"Skill_{gw2.get('id', '')}")

        try:
            new_skill.game_id = int(gw2.get("id", 0))
        except Exception:
            new_skill.game_id = 0

        new_skill.game_desc = str(gw2.get("description", "") or "")
        new_skill.icon_url = str(gw2.get("icon", "") or "")

        cd_s = self._extract_cooldown_s(gw2) or 0.0
        try:
            new_skill.cooldown_ms = int(cd_s * 1000)
        except Exception:
            new_skill.cooldown_ms = 0

        radius = self._extract_radius(gw2) or 0
        try:
            new_skill.radius = int(radius)
        except Exception:
            new_skill.radius = 0

        # 其他字段（trigger/pixel/note 等）保持默认值，由用户后续在技能配置页中完善
        return new_skill