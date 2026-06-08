# core/logging_setup.py
from __future__ import annotations

import logging
import logging.config
import logging.handlers
import queue
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from core.io.json_store import ensure_dir
from core.logging_context import corr_id_var, profile_var, action_var

class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # 注入上下文字段；保证 formatter 里引用时永远存在
        record.corr_id = corr_id_var.get()
        record.profile = profile_var.get()
        record.action = action_var.get()
        return True

@dataclass
class LoggingRuntime:
    listener: logging.handlers.QueueListener

    def stop(self) -> None:
        try:
            self.listener.stop()
        except Exception:
            pass

def setup_logging(
    *,
    app_data_dir: Path,
    level: str = "INFO",
    keep_days_app: int = 14,
    keep_days_error: int = 30,
    console: bool = False,
) -> LoggingRuntime:
    logs_dir = app_data_dir / "logs"
    ensure_dir(logs_dir)

    log_q: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=20_000)

    # 统一格式：UTC 时间建议用 time.gmtime 但 logging 默认本地时区；
    # 这里先用 asctime（本地）也可接受，后续可切 UTC formatter。
    fmt = (
        "%(asctime)s %(levelname)s "
        "[pid=%(process)d tid=%(thread)d] "
        "%(name)s:%(funcName)s:%(lineno)d "
        "corr=%(corr_id)s profile=%(profile)s action=%(action)s - %(message)s"
    )

    formatter = logging.Formatter(fmt=fmt)

    # 真正写文件的 handlers（只在 listener 线程执行）
    app_fh = logging.handlers.TimedRotatingFileHandler(
        filename=str(logs_dir / "app.log"),
        when="midnight",
        backupCount=int(keep_days_app),
        encoding="utf-8",
        utc=False,  # 需要 UTC 可改 True（Python 3.9+ 支持 utc 参数）
    )
    app_fh.setLevel(logging.INFO)
    app_fh.setFormatter(formatter)
    app_fh.addFilter(ContextFilter())

    err_fh = logging.handlers.TimedRotatingFileHandler(
        filename=str(logs_dir / "error.log"),
        when="midnight",
        backupCount=int(keep_days_error),
        encoding="utf-8",
        utc=False,
    )
    err_fh.setLevel(logging.ERROR)
    err_fh.setFormatter(formatter)
    err_fh.addFilter(ContextFilter())

    handlers: list[logging.Handler] = [app_fh, err_fh]

    if console:
        ch = logging.StreamHandler(stream=sys.stderr)
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        ch.addFilter(ContextFilter())
        handlers.append(ch)

    # root logger 只挂 QueueHandler，避免多线程直接写文件
    qh = logging.handlers.QueueHandler(log_q)
    qh.setLevel(logging.DEBUG)
    qh.addFilter(ContextFilter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(qh)

    # listener 线程负责把队列记录写入文件/console
    listener = logging.handlers.QueueListener(
        log_q,
        *handlers,
        respect_handler_level=True,
    )
    listener.start()

    _install_global_exception_hooks()

    logging.getLogger(__name__).info(
        "logging initialized",
        extra={"action": "boot"},
    )

    return LoggingRuntime(listener=listener)

def _install_global_exception_hooks() -> None:
    log = logging.getLogger("unhandled")

    def excepthook(exc_type, exc, tb):
        log.critical("unhandled exception (main thread)", exc_info=(exc_type, exc, tb))

    sys.excepthook = excepthook

    # Python 3.8+：线程未捕获异常钩子
    # https://docs.python.org/3/library/threading.html#threading.excepthook
    def th_excepthook(args: threading.ExceptHookArgs):
        log.critical(
            "unhandled exception (thread)",
            extra={"action": "thread_excepthook"},
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    try:
        threading.excepthook = th_excepthook  # type: ignore[attr-defined]
    except Exception:
        pass