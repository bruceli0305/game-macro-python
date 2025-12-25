from __future__ import annotations

from typing import Any, Dict

from core.migrations.types import MigrationOutcome


LATEST_BASE_SCHEMA_VERSION = 1


def _as_int(v: Any, default: int) -> int:
    try:
        if v is None:
            return default
        if isinstance(v, bool):
            return int(v)
        return int(v)
    except Exception:
        return default


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def migrate_base_json(data: Dict[str, Any]) -> MigrationOutcome:
    """
    base.json migrations
    Current latest: v1

    Policy:
    - Ensure root is dict
    - Ensure schema_version exists and is int
    - Ensure major sections exist and are dicts (ui/capture/hotkeys/pick/io)
    """
    if not isinstance(data, dict):
        data = {}

    from_ver = _as_int(data.get("schema_version", 1), 1)
    changed = False

    # normalize schema_version
    if "schema_version" not in data or from_ver != LATEST_BASE_SCHEMA_VERSION:
        data["schema_version"] = LATEST_BASE_SCHEMA_VERSION
        changed = True

    # normalize sections to dict
    for k in ("ui", "capture", "hotkeys", "pick", "io"):
        if k not in data or not isinstance(data.get(k), dict):
            data[k] = _as_dict(data.get(k))
            changed = True

    # pick.avoidance as dict
    pick = _as_dict(data.get("pick"))
    if "avoidance" not in pick or not isinstance(pick.get("avoidance"), dict):
        pick["avoidance"] = _as_dict(pick.get("avoidance"))
        data["pick"] = pick
        changed = True

    return MigrationOutcome(
        data=data,
        changed=changed,
        from_version=from_ver,
        to_version=int(data.get("schema_version", LATEST_BASE_SCHEMA_VERSION)),
    )