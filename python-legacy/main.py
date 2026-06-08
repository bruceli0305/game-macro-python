# main_qt.py
from pathlib import Path
import os
import sys

from PySide6.QtWidgets import QApplication

from core.logging_setup import setup_logging
from core.idgen.snowflake import SnowflakeGenerator
from core.repos.app_state_repo import AppStateRepo
from core.profiles import ProfileManager
from qtui.main_window import MainWindow
from qtui.theme import apply_theme


def _resolve_app_data_dir() -> Path:
    """
    确定应用数据存储目录：
    - Windows: %LOCALAPPDATA%/GameMacro（或 ~/AppData/Local/GameMacro）
    - macOS:   ~/Library/Application Support/GameMacro
    - Linux:   ~/.local/share/GameMacro
    - 回退:    ~/GameMacro
    开发模式下若当前目录存在 app_data/，则继续使用相对路径（便于调试）。
    """
    # 开发模式检测：若脚本所在目录下有 app_data/，使用相对路径
    dev_dir = Path(__file__).resolve().parent / "app_data"
    if dev_dir.is_dir():
        return dev_dir

    try:
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path.home() / ".local" / "share"
        return base / "GameMacro"
    except Exception:
        return Path.home() / "GameMacro"


def main():
    app_data_dir = _resolve_app_data_dir()

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