from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.models.common import as_bool, as_dict, as_int, as_list, as_str, clamp_int


@dataclass
class ColorRGB:
    r: int = 0
    g: int = 0
    b: int = 0

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ColorRGB":
        d = as_dict(d)
        return ColorRGB(
            r=clamp_int(as_int(d.get("r", 0), 0), 0, 255),
            g=clamp_int(as_int(d.get("g", 0), 0), 0, 255),
            b=clamp_int(as_int(d.get("b", 0), 0), 0, 255),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"r": int(self.r), "g": int(self.g), "b": int(self.b)}


@dataclass
class SampleConfig:
    mode: str = "single"  # "single" | "mean_square" (future)
    radius: int = 0

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SampleConfig":
        d = as_dict(d)
        return SampleConfig(
            mode=as_str(d.get("mode", "single"), "single"),
            radius=clamp_int(as_int(d.get("radius", 0), 0), 0, 50),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"mode": self.mode, "radius": int(self.radius)}


@dataclass
class PixelSpec:
    """
    Pixel position is stored in virtual screen absolute coordinates (vx, vy).

    - vx/vy: OS virtual screen coordinates (can be negative on multi-monitor setups).
    - monitor: still kept as a hint / UI selection / policy (e.g. "primary", "monitor_2", "all").
    """
    monitor: str = "primary"
    vx: int = 0
    vy: int = 0
    color: ColorRGB = field(default_factory=ColorRGB)
    tolerance: int = 0
    sample: SampleConfig = field(default_factory=SampleConfig)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PixelSpec":
        d = as_dict(d)

        # Backward compatibility:
        # - new schema uses vx/vy
        # - older schema used x/y (relative coords), but repos will migrate those on load.
        vx_raw = d.get("vx", None)
        vy_raw = d.get("vy", None)
        if vx_raw is None:
            vx_raw = d.get("abs_x", d.get("x", 0))
        if vy_raw is None:
            vy_raw = d.get("abs_y", d.get("y", 0))

        return PixelSpec(
            monitor=as_str(d.get("monitor", "primary"), "primary"),
            vx=clamp_int(as_int(vx_raw, 0), -10**9, 10**9),
            vy=clamp_int(as_int(vy_raw, 0), -10**9, 10**9),
            color=ColorRGB.from_dict(d.get("color", {}) or {}),
            tolerance=clamp_int(as_int(d.get("tolerance", 0), 0), 0, 255),
            sample=SampleConfig.from_dict(d.get("sample", {}) or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "monitor": self.monitor,
            "vx": int(self.vx),
            "vy": int(self.vy),
            "color": self.color.to_dict(),
            "tolerance": int(self.tolerance),
            "sample": self.sample.to_dict(),
        }


@dataclass
class TriggerConfig:
    type: str = "key"  # "key" (一期先这样)
    key: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TriggerConfig":
        d = as_dict(d)
        return TriggerConfig(
            type=as_str(d.get("type", "key"), "key"),
            key=as_str(d.get("key", ""), ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "key": self.key}


@dataclass
class CastConfig:
    readbar_ms: int = 0
    cooldown_ms: int = 0  # 预留（与下面的 game 冷却不同，这里是本工具内部用）

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CastConfig":
        d = as_dict(d)
        return CastConfig(
            readbar_ms=clamp_int(as_int(d.get("readbar_ms", 0), 0), 0, 10**9),
            cooldown_ms=clamp_int(as_int(d.get("cooldown_ms", 0), 0), 0, 10**9),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"readbar_ms": int(self.readbar_ms), "cooldown_ms": int(self.cooldown_ms)}


@dataclass
class Skill:
    """
    单个技能配置：

    - id        : 本工具内部的 snowflake id
    - name      : 技能名称（你在本工具里看到/编辑的名字）
    - enabled   : 是否启用
    - trigger   : 触发键配置
    - cast      : 读条等时间参数
    - pixel     : 像素检测配置
    - note      : 备注（用户自定义）

    新增的一般游戏元数据（可从 GW2 技能 JSON 导入）：
    - game_id      : 游戏中的技能 ID（例如 5752），便于外部对照
    - game_desc    : 官方技能描述
    - icon_url     : 技能图标 URL（后续可用于列表/详情显示）
    - cooldown_ms  : 冷却时间（毫秒），从 JSON 的 Recharge(s) 转换而来
    - radius       : 技能半径（如有），从 Distance fact 中提取
    """
    id: str = ""          # snowflake id string（本工具内部）
    name: str = ""
    enabled: bool = True
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    cast: CastConfig = field(default_factory=CastConfig)
    pixel: PixelSpec = field(default_factory=PixelSpec)
    note: str = ""

    # 通用游戏元信息
    game_id: int = 0
    game_desc: str = ""
    icon_url: str = ""
    cooldown_ms: int = 0
    radius: int = 0

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Skill":
        d = as_dict(d)
        return Skill(
            id=as_str(d.get("id", "")),
            name=as_str(d.get("name", "")),
            enabled=as_bool(d.get("enabled", True), True),
            trigger=TriggerConfig.from_dict(d.get("trigger", {}) or {}),
            cast=CastConfig.from_dict(d.get("cast", {}) or {}),
            pixel=PixelSpec.from_dict(d.get("pixel", {}) or {}),
            note=as_str(d.get("note", "")),

            game_id=as_int(d.get("game_id", 0), 0),
            game_desc=as_str(d.get("game_desc", "")),
            icon_url=as_str(d.get("icon_url", "")),
            cooldown_ms=as_int(d.get("cooldown_ms", 0), 0),
            radius=as_int(d.get("radius", 0), 0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": bool(self.enabled),
            "trigger": self.trigger.to_dict(),
            "cast": self.cast.to_dict(),
            "pixel": self.pixel.to_dict(),
            "note": self.note,

            "game_id": int(self.game_id),
            "game_desc": self.game_desc,
            "icon_url": self.icon_url,
            "cooldown_ms": int(self.cooldown_ms),
            "radius": int(self.radius),
        }


@dataclass
class SkillsFile:
    schema_version: int = 2
    skills: List[Skill] = field(default_factory=list)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SkillsFile":
        d = as_dict(d)
        skills_raw = as_list(d.get("skills", []))
        skills: List[Skill] = []
        for item in skills_raw:
            if isinstance(item, dict):
                skills.append(Skill.from_dict(item))
        return SkillsFile(
            schema_version=as_int(d.get("schema_version", 2), 2),
            skills=skills,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "skills": [s.to_dict() for s in self.skills],
        }