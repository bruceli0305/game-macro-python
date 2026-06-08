# core/logging_context.py
from __future__ import annotations

from contextvars import ContextVar
from contextlib import contextmanager
from uuid import uuid4

corr_id_var: ContextVar[str] = ContextVar("corr_id", default="-")
profile_var: ContextVar[str] = ContextVar("profile", default="-")
action_var: ContextVar[str] = ContextVar("action", default="-")

def new_corr_id() -> str:
    return uuid4().hex[:12]

@contextmanager
def log_context(*, corr_id: str | None = None, profile: str | None = None, action: str | None = None):
    tokens = []
    try:
        if corr_id is not None:
            tokens.append((corr_id_var, corr_id_var.set(corr_id)))
        if profile is not None:
            tokens.append((profile_var, profile_var.set(profile)))
        if action is not None:
            tokens.append((action_var, action_var.set(action)))
        yield
    finally:
        for var, tok in reversed(tokens):
            var.reset(tok)