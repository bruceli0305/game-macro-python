from __future__ import annotations

from typing import Any, Dict

from core.migrations.types import MigrationOutcome


LATEST_META_SCHEMA_VERSION = 1


def _as_int(v: Any, default: int) -> int:
    try:
        if v is None:
            return default
        if isinstance(v, bool):
            return int(v)
        return int(v)
    except Exception:
        return default


def migrate_meta_json(data: Dict[str, Any]) -> MigrationOutcome:
    """
    meta.json migrations
    Current latest: v1

    Policy:
    - Ensure root is dict
    - Ensure schema_version exists
    - Do not generate ids/timestamps here (MetaRepo will do that)
    """
    if not isinstance(data, dict):
        data = {}

    from_ver = _as_int(data.get("schema_version", 1), 1)
    changed = False

    if "schema_version" not in data or from_ver != LATEST_META_SCHEMA_VERSION:
        data["schema_version"] = LATEST_META_SCHEMA_VERSION
        changed = True

    return MigrationOutcome(
        data=data,
        changed=changed,
        from_version=from_ver,
        to_version=int(data.get("schema_version", LATEST_META_SCHEMA_VERSION)),
    )