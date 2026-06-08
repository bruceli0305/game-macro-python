from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from core.models.common import as_int, as_str


@dataclass
class ProfileMeta:
    schema_version: int = 1
    profile_id: str = ""          # snowflake id string
    profile_name: str = ""
    created_at: str = ""          # ISO string
    updated_at: str = ""          # ISO string
    description: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ProfileMeta":
        return ProfileMeta(
            schema_version=as_int(d.get("schema_version", 1), 1),
            profile_id=as_str(d.get("profile_id", "")),
            profile_name=as_str(d.get("profile_name", "")),
            created_at=as_str(d.get("created_at", "")),
            updated_at=as_str(d.get("updated_at", "")),
            description=as_str(d.get("description", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "description": self.description,
        }