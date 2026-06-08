# File: core/repos/app_state_repo.py
from __future__ import annotations

import random
from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from core.models.app_state import AppState


class AppStateRepo:
    """
    Manages app_data/app_state.json (global, not profile-scoped).

    Step 1 change:
    - migrations 已移除：不再做 schema 迁移
    - 只做最小可运行保障：worker_id 缺失/越界时生成
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

        state = AppState.from_dict(data)

        changed = False

        # worker_id: 0..1023
        if "worker_id" not in data:
            state.worker_id = self._gen_worker_id()
            changed = True
        else:
            try:
                wid = int(state.worker_id)
                if wid < 0 or wid > 1023:
                    state.worker_id = self._gen_worker_id()
                    changed = True
            except Exception:
                state.worker_id = self._gen_worker_id()
                changed = True

        # schema_version: 固定写 1（不做迁移，只保证字段存在）
        if "schema_version" not in data:
            state.schema_version = 1
            changed = True

        if (not existed) or changed:
            # 不考虑兼容：默认不备份；你也可以改成 backup=existed
            self.save(state, backup=False)

        return state

    def save(self, state: AppState, *, backup: bool = False) -> None:
        atomic_write_json(self.path, state.to_dict(), backup=backup)

    def _gen_worker_id(self) -> int:
        rng = random.SystemRandom()
        return int(rng.randrange(0, 1024))