from __future__ import annotations

import random
from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.app_state import AppState


class AppStateRepo:
    """
    Manages app_data/app_state.json (global, not profile-scoped).
    Responsible for persisting worker_id (Snowflake worker id) and last_profile.
    """

    def __init__(self, app_data_dir: Path) -> None:
        self._app_data_dir = app_data_dir
        ensure_dir(self._app_data_dir)

    @property
    def path(self) -> Path:
        return self._app_data_dir / "app_state.json"

    def load_or_create(self) -> AppState:
        data = read_json(self.path, default={})
        state = AppState.from_dict(data)

        changed = False

        # First-run: generate worker_id if missing/zero (you can allow 0 as valid,
        # but using "0 means unset" keeps it simple for now).
        if "worker_id" not in data or state.worker_id == 0:
            state.worker_id = self._gen_worker_id()
            changed = True

        # Ensure schema_version exists
        if "schema_version" not in data:
            state.schema_version = 1
            changed = True

        # Ensure file exists on disk
        if not self.path.exists():
            changed = True

        if changed:
            self.save(state)

        return state

    def save(self, state: AppState) -> None:
        atomic_write_json(self.path, state.to_dict(), backup=True)

    def _gen_worker_id(self) -> int:
        # 10-bit worker id: 0..1023
        # Use SystemRandom for better randomness.
        rng = random.SystemRandom()
        return rng.randrange(0, 1024)