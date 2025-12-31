# main_qt.py
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from core.logging_setup import setup_logging
from core.idgen.snowflake import SnowflakeGenerator
from core.repos.app_state_repo import AppStateRepo
from core.profiles import ProfileManager
from qtui.main_window import MainWindow
from qtui.theme import apply_theme

def main():
    app_data_dir = Path("app_data")

    # 日志
    log_rt = setup_logging(app_data_dir=app_data_dir, level="INFO", console=False)

    # 全局 app_state
    app_state_repo = AppStateRepo(app_data_dir)
    app_state = app_state_repo.load_or_create()

    # 雪花 ID
    idgen = SnowflakeGenerator(worker_id=app_state.worker_id)

    # Profile 管理
    pm = ProfileManager(
        app_data_dir=app_data_dir,
        app_state_repo=app_state_repo,
        app_state=app_state,
        idgen=idgen,
    )
    ctx = pm.open_last_or_fallback()

    # Qt 应用
    app = QApplication(sys.argv)

    theme_name = ctx.base.ui.theme or "darkly"  # 先记下来，后面再用主题系统
     # 先根据当前 profile 的配置应用主题
    apply_theme(app, theme_name)
    
    win = MainWindow(
        theme_name=theme_name,
        profile_manager=pm,
        profile_ctx=ctx,
        app_state_repo=app_state_repo,
        app_state=app_state,
    )
    win.show()

    try:
        app.exec()
    finally:
        log_rt.stop()


if __name__ == "__main__":
    main()