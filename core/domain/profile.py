from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from core.models.meta import ProfileMeta
from core.models.base import BaseFile
from core.models.skill import SkillsFile
from core.models.point import PointsFile
from rotation_editor.core.models import RotationsFile
from core.io.json_store import now_iso_utc
from core.idgen.snowflake import SnowflakeGenerator


@dataclass
class Profile:
    """
    单个 profile 的完整聚合：
    - meta     : ProfileMeta（ID / 名称 / 创建时间等）
    - base     : BaseFile（基础配置）
    - skills   : SkillsFile（技能配置）
    - points   : PointsFile（取色点位）
    - rotations: RotationsFile（循环/轨道方案）
    """

    schema_version: int = 1
    meta: ProfileMeta = field(default_factory=ProfileMeta)
    base: BaseFile = field(default_factory=BaseFile)
    skills: SkillsFile = field(default_factory=SkillsFile)
    points: PointsFile = field(default_factory=PointsFile)
    rotations: RotationsFile = field(default_factory=RotationsFile)

    # ---------- 工厂方法 ----------

    @staticmethod
    def new(profile_name: str, idgen: SnowflakeGenerator) -> "Profile":
        """
        创建一个新的空 Profile 聚合：
        - 分配 profile_id
        - 填充 meta 的 created_at/updated_at
        - 其它部分使用各自的默认构造
        """
        now = now_iso_utc()
        meta = ProfileMeta(
            schema_version=1,
            profile_id=idgen.next_id(),
            profile_name=profile_name,
            created_at=now,
            updated_at=now,
            description="",
        )
        return Profile(
            schema_version=1,
            meta=meta,
            base=BaseFile(),
            skills=SkillsFile(),
            points=PointsFile(),
            rotations=RotationsFile(),
        )

    # ---------- 反序列化 ----------

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Profile":
        """
        从 dict 反序列化为 Profile 聚合。
        缺失字段走各自的 from_dict 默认行为。
        """
        return Profile(
            schema_version=int(d.get("schema_version", 1)),
            meta=ProfileMeta.from_dict(d.get("meta", {}) or {}),
            base=BaseFile.from_dict(d.get("base", {}) or {}),
            skills=SkillsFile.from_dict(d.get("skills", {}) or {}),
            points=PointsFile.from_dict(d.get("points", {}) or {}),
            rotations=RotationsFile.from_dict(d.get("rotations", {}) or {}),
        )

    # ---------- 序列化 ----------

    def to_dict(self) -> Dict[str, Any]:
        """
        将 Profile 聚合序列化为 dict，方便写入 JSON。
        """
        return {
            "schema_version": int(self.schema_version),
            "meta": self.meta.to_dict(),
            "base": self.base.to_dict(),
            "skills": self.skills.to_dict(),
            "points": self.points.to_dict(),
            "rotations": self.rotations.to_dict(),
        }