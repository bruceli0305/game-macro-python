from __future__ import annotations

import random
from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.migrations.app_state_json import migrate_app_state_json
from core.models.app_state import AppState


class AppStateRepo:
    """
    Manages app_data/app_state.json (global, not profile-scoped).
    Responsible for persisting worker_id (Snowflake worker id) and last_profile.

    Worker ID policy (FIXED):
    - 0 is VALID.
    - Only missing/invalid worker_id triggers generation.
    """

    def __init__(self, app_data_dir: Path) -> None:
        self._app_data_dir = app_data_dir
        ensure_dir(self._app_data_dir)

    @property
    def path(self) -> Path:
        return self._app_data_dir / "app_state.json"

    def load_or_create(self) -> AppState:
        existed = self.path.exists()
        data = read_json(self.path, default={})

        mig = migrate_app_state_json(data)
        data = mig.data

        state = AppState.from_dict(data)

        changed = bool(mig.changed)

        # First-run: generate worker_id ONLY if missing in JSON (0 is valid)
        if "worker_id" not in data:
            state.worker_id = self._gen_worker_id()
            changed = True

        # Ensure schema_version exists
        if "schema_version" not in data:
            state.schema_version = 1
            changed = True

        if (not existed) or changed:
            # backup only when migrating an existing file
            backup = bool(existed and mig.changed)
            self.save(state, backup=backup)

        return state

    def save(self, state: AppState, *, backup: bool = True) -> None:
        atomic_write_json(self.path, state.to_dict(), backup=backup)

    def _gen_worker_id(self) -> int:
        rng = random.SystemRandom()
        return rng.randrange(0, 1024)