# File: main.py
from pathlib import Path

import ttkbootstrap as tb  # 仍在 requirements 中，虽然此处未直接使用
import logging

from core.idgen.snowflake import SnowflakeGenerator
from core.profiles import ProfileManager
from core.repos.app_state_repo import AppStateRepo
from core.logging_setup import setup_logging
from ui.app_window import AppWindow


def main():
    app_data_dir = Path("app_data")

    log_rt = setup_logging(app_data_dir=app_data_dir, level="INFO", console=False)
    logging.getLogger(__name__).info("app starting")

    # global state
    app_state_repo = AppStateRepo(app_data_dir)
    app_state = app_state_repo.load_or_create()

    # id generator (snowflake)
    idgen = SnowflakeGenerator(worker_id=app_state.worker_id)

    # profiles
    pm = ProfileManager(
        app_data_dir=app_data_dir,
        app_state_repo=app_state_repo,
        app_state=app_state,
        idgen=idgen,
    )
    ctx = pm.open_last_or_fallback()

    # theme fallback
    themename = ctx.base.ui.theme or "darkly"
    try:
        app = AppWindow(
            themename=themename,
            profile_manager=pm,
            profile_ctx=ctx,
            app_state_repo=app_state_repo,
            app_state=app_state,
        )
    except Exception:
        # fallback to a known theme
        app = AppWindow(
            themename="darkly",
            profile_manager=pm,
            profile_ctx=ctx,
            app_state_repo=app_state_repo,
            app_state=app_state,
        )
    try:
        app.mainloop()
    finally:
        log_rt.stop()


if __name__ == "__main__":
    main()