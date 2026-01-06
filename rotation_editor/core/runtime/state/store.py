from __future__ import annotations

import threading
import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal

from core.profiles import ProfileContext

from .events import EventBus, EngineEvent, AttemptEvent, CaptureEvent
from .metrics import SkillMetric


def mono_ms() -> int:
    return int(time.monotonic() * 1000)


AttemptStage = Literal[
    "IDLE",
    "READY_CHECK",
    "LOCK_WAIT",
    "PREPARING",
    "START_WAIT",
    "CASTING",
    "COMPLETE_WAIT",
    "SUCCESS",
    "FAILED",
    "STOPPED",
]


@dataclass
class EngineState:
    running: bool = False
    paused: bool = False
    preset_id: str = ""
    started_ms: int = 0
    stop_reason: str = ""
    last_error: str = ""
    last_error_detail: str = ""


@dataclass
class AttemptState:
    attempt_id: str
    skill_id: str
    node_id: str
    start_mode: str
    readbar_ms: int

    created_ms: int
    stage: AttemptStage = "PREPARING"
    stage_since_ms: int = 0

    retry_index: int = 0
    key_sent_ok: int = 0

    casting_ms: Optional[int] = None
    ended_ms: Optional[int] = None

    result: str = ""          # "success" | "failed" | "stopped" | ""
    fail_reason: str = ""

    events: List[AttemptEvent] = field(default_factory=list)

    def stage_age_ms(self, now_ms: Optional[int] = None) -> int:
        now = mono_ms() if now_ms is None else int(now_ms)
        s = int(self.stage_since_ms or 0)
        return max(0, now - s) if s > 0 else 0


@dataclass
class SkillAggregateState:
    skill_id: str

    node_exec: int = 0
    ready_false: int = 0
    skipped_disabled: int = 0
    skipped_lock_busy: int = 0

    attempt_started: int = 0
    key_sent_ok: int = 0
    cast_started: int = 0
    success: int = 0
    fail: int = 0
    fail_by_reason: Dict[str, int] = field(default_factory=dict)

    current_attempt_id: str = ""
    recent_attempt_ids: List[str] = field(default_factory=list)


class StateStore:
    def __init__(
        self,
        *,
        max_recent_attempts_per_skill: int = 120,
        max_events_per_attempt: int = 200,
        bus: Optional[EventBus] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._bus = bus or EventBus()

        self._engine = EngineState()
        self._skills: Dict[str, SkillAggregateState] = {}
        self._attempts: Dict[str, AttemptState] = {}

        self._max_recent_attempts = int(max(10, max_recent_attempts_per_skill))
        self._max_events_per_attempt = int(max(50, max_events_per_attempt))

    @property
    def bus(self) -> EventBus:
        return self._bus

    def _publish(self, ev) -> None:
        try:
            self._bus.publish(ev)
        except Exception:
            pass

    # -------------------------
    # Engine state
    # -------------------------

    def engine_started(self, preset_id: str) -> None:
        now = mono_ms()
        with self._lock:
            self._engine.running = True
            self._engine.paused = False
            self._engine.preset_id = (preset_id or "")
            self._engine.started_ms = now
            self._engine.stop_reason = ""
            self._engine.last_error = ""
            self._engine.last_error_detail = ""
        self._publish(EngineEvent(t_ms=now, type="ENGINE_STARTED", preset_id=preset_id))

    def engine_stopping(self, reason: str) -> None:
        now = mono_ms()
        with self._lock:
            self._engine.stop_reason = (reason or "")
        self._publish(EngineEvent(t_ms=now, type="ENGINE_STOPPING", preset_id=self._engine.preset_id, reason=reason))

    def engine_stopped(self, reason: str) -> None:
        now = mono_ms()
        with self._lock:
            self._engine.running = False
            self._engine.paused = False
            self._engine.stop_reason = (reason or "")
        self._publish(EngineEvent(t_ms=now, type="ENGINE_STOPPED", preset_id=self._engine.preset_id, reason=reason))

    def engine_paused(self) -> None:
        now = mono_ms()
        with self._lock:
            self._engine.paused = True
        self._publish(EngineEvent(t_ms=now, type="ENGINE_PAUSED", preset_id=self._engine.preset_id))

    def engine_resumed(self) -> None:
        now = mono_ms()
        with self._lock:
            self._engine.paused = False
        self._publish(EngineEvent(t_ms=now, type="ENGINE_RESUMED", preset_id=self._engine.preset_id))

    def engine_error(self, msg: str, detail: str = "") -> None:
        now = mono_ms()
        with self._lock:
            self._engine.last_error = (msg or "")
            self._engine.last_error_detail = (detail or "")
        self._publish(EngineEvent(t_ms=now, type="ENGINE_ERROR", preset_id=self._engine.preset_id, message=msg, detail=detail))

    def get_engine_state(self) -> Dict[str, Any]:
        with self._lock:
            e = self._engine
            return {
                "running": bool(e.running),
                "paused": bool(e.paused),
                "preset_id": e.preset_id,
                "started_ms": int(e.started_ms),
                "stop_reason": e.stop_reason,
                "last_error": e.last_error,
                "last_error_detail": e.last_error_detail,
            }

    # -------------------------
    # Skill aggregates helpers
    # -------------------------

    def _ensure_skill(self, skill_id: str) -> SkillAggregateState:
        sid = (skill_id or "").strip()
        if sid not in self._skills:
            self._skills[sid] = SkillAggregateState(skill_id=sid)
        return self._skills[sid]

    # -------------------------
    # Poll layer marks
    # -------------------------

    def mark_node_exec(self, skill_id: str, *, node_id: str = "", attempt_id: str = "") -> None:
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure_skill(sid)
            st.node_exec += 1
        # 这里不强制写 attempt event（poll 频率高），由执行器自行决定是否写 START/COMPLETE_CHECK 等

    def mark_ready_false(self, skill_id: str, *, node_id: str = "", reason: str = "") -> None:
        now = mono_ms()
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure_skill(sid)
            st.ready_false += 1
        self._publish(AttemptEvent(
            t_ms=now,
            type="READY_CHECK",
            attempt_id="",
            skill_id=sid,
            node_id=node_id,
            message="ready_false",
            detail=reason,
        ))

    def mark_skipped_disabled(self, skill_id: str, *, node_id: str = "") -> None:
        now = mono_ms()
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure_skill(sid)
            st.skipped_disabled += 1
        self._publish(AttemptEvent(t_ms=now, type="SKIPPED_DISABLED", attempt_id="", skill_id=sid, node_id=node_id))

    def mark_skipped_lock_busy(self, skill_id: str, *, node_id: str = "") -> None:
        now = mono_ms()
        sid = (skill_id or "").strip()
        with self._lock:
            st = self._ensure_skill(sid)
            st.skipped_lock_busy += 1
        self._publish(AttemptEvent(t_ms=now, type="SKIPPED_LOCK_BUSY", attempt_id="", skill_id=sid, node_id=node_id))

    # -------------------------
    # Attempt lifecycle
    # -------------------------

    def begin_attempt(
        self,
        *,
        skill_id: str,
        node_id: str,
        start_mode: str,
        readbar_ms: int,
    ) -> str:
        now = mono_ms()
        sid = (skill_id or "").strip()
        aid = uuid.uuid4().hex

        at = AttemptState(
            attempt_id=aid,
            skill_id=sid,
            node_id=(node_id or ""),
            start_mode=(start_mode or ""),
            readbar_ms=int(readbar_ms),
            created_ms=now,
            stage="PREPARING",
            stage_since_ms=now,
        )

        ev = AttemptEvent(
            t_ms=now,
            type="ATTEMPT_BEGIN",
            attempt_id=aid,
            skill_id=sid,
            node_id=node_id or "",
            extra={"start_mode": start_mode, "readbar_ms": int(readbar_ms)},
        )

        with self._lock:
            self._attempts[aid] = at
            st = self._ensure_skill(sid)
            st.attempt_started += 1
            st.current_attempt_id = aid

            st.recent_attempt_ids.insert(0, aid)
            if len(st.recent_attempt_ids) > self._max_recent_attempts:
                del st.recent_attempt_ids[self._max_recent_attempts :]

            at.events.append(ev)
            self._trim_events_locked(at)

        self._publish(ev)
        return aid

    def append_attempt_event(
        self,
        attempt_id: str,
        *,
        type: str,
        message: str = "",
        detail: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        追加一个 attempt 事件（用于 START_CHECK / COMPLETE_CHECK / BASELINE_SAMPLED 等细粒度记录）。
        """
        aid = (attempt_id or "").strip()
        if not aid:
            return
        now = mono_ms()

        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return
            ev = AttemptEvent(
                t_ms=now,
                type=type,  # type: ignore[arg-type]
                attempt_id=aid,
                skill_id=at.skill_id,
                node_id=at.node_id,
                message=message,
                detail=detail,
                extra=extra or {},
            )
            at.events.append(ev)
            self._trim_events_locked(at)

        self._publish(ev)

    def set_stage(self, attempt_id: str, stage: AttemptStage, *, message: str = "", detail: str = "", extra: Optional[Dict[str, Any]] = None) -> None:
        now = mono_ms()
        aid = (attempt_id or "").strip()
        if not aid:
            return

        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return
            at.stage = stage
            at.stage_since_ms = now
            if stage == "CASTING":
                at.casting_ms = now

            ev_type = {
                "LOCK_WAIT": "LOCK_WAIT",
                "PREPARING": "ATTEMPT_BEGIN",
                "START_WAIT": "START_WAIT",
                "CASTING": "CASTING_BEGIN",
                "COMPLETE_WAIT": "COMPLETE_WAIT",
                "SUCCESS": "ATTEMPT_SUCCESS",
                "FAILED": "ATTEMPT_FAILED",
                "STOPPED": "ATTEMPT_STOPPED",
                "READY_CHECK": "READY_CHECK",
                "IDLE": "READY_CHECK",
            }.get(stage, "READY_CHECK")

            ev = AttemptEvent(
                t_ms=now,
                type=ev_type,  # type: ignore[arg-type]
                attempt_id=aid,
                skill_id=at.skill_id,
                node_id=at.node_id,
                message=message,
                detail=detail,
                extra=extra or {},
            )
            at.events.append(ev)
            self._trim_events_locked(at)

        self._publish(ev)

    def mark_key_sent_ok(self, attempt_id: str) -> None:
        now = mono_ms()
        aid = (attempt_id or "").strip()
        if not aid:
            return

        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return
            at.key_sent_ok += 1
            st = self._ensure_skill(at.skill_id)
            st.key_sent_ok += 1

            ev = AttemptEvent(t_ms=now, type="SEND_KEY_OK", attempt_id=aid, skill_id=at.skill_id, node_id=at.node_id)
            at.events.append(ev)
            self._trim_events_locked(at)

        self._publish(ev)

    def mark_key_sent_fail(self, attempt_id: str, reason: str) -> None:
        now = mono_ms()
        aid = (attempt_id or "").strip()
        if not aid:
            return

        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return
            ev = AttemptEvent(
                t_ms=now,
                type="SEND_KEY_FAIL",
                attempt_id=aid,
                skill_id=at.skill_id,
                node_id=at.node_id,
                detail=reason or "send_key_fail",
            )
            at.events.append(ev)
            self._trim_events_locked(at)

        self._publish(ev)

    def mark_cast_started(self, attempt_id: str, *, extra: Optional[Dict[str, Any]] = None) -> None:
        now = mono_ms()
        aid = (attempt_id or "").strip()
        if not aid:
            return
        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return
            at.stage = "CASTING"
            at.stage_since_ms = now
            at.casting_ms = now
            st = self._ensure_skill(at.skill_id)
            st.cast_started += 1

            ev = AttemptEvent(
                t_ms=now,
                type="CASTING_BEGIN",
                attempt_id=aid,
                skill_id=at.skill_id,
                node_id=at.node_id,
                extra=extra or {},
            )
            at.events.append(ev)
            self._trim_events_locked(at)

        self._publish(ev)

    def schedule_retry(self, attempt_id: str, *, retry_index: int, reason: str = "") -> None:
        now = mono_ms()
        aid = (attempt_id or "").strip()
        if not aid:
            return
        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return
            at.retry_index = int(max(0, retry_index))
            ev = AttemptEvent(
                t_ms=now,
                type="RETRY_SCHEDULED",
                attempt_id=aid,
                skill_id=at.skill_id,
                node_id=at.node_id,
                detail=reason,
                extra={"retry_index": at.retry_index},
            )
            at.events.append(ev)
            self._trim_events_locked(at)
        self._publish(ev)

    def finish_success(self, attempt_id: str) -> None:
        now = mono_ms()
        aid = (attempt_id or "").strip()
        if not aid:
            return
        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return
            at.stage = "SUCCESS"
            at.stage_since_ms = now
            at.ended_ms = now
            at.result = "success"
            at.fail_reason = ""

            st = self._ensure_skill(at.skill_id)
            st.success += 1
            if st.current_attempt_id == aid:
                st.current_attempt_id = ""

            ev = AttemptEvent(t_ms=now, type="ATTEMPT_SUCCESS", attempt_id=aid, skill_id=at.skill_id, node_id=at.node_id)
            at.events.append(ev)
            self._trim_events_locked(at)
        self._publish(ev)

    def finish_fail(self, attempt_id: str, reason: str) -> None:
        now = mono_ms()
        aid = (attempt_id or "").strip()
        if not aid:
            return
        r = (reason or "unknown").strip() or "unknown"

        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return
            at.stage = "FAILED"
            at.stage_since_ms = now
            at.ended_ms = now
            at.result = "failed"
            at.fail_reason = r

            st = self._ensure_skill(at.skill_id)
            st.fail += 1
            st.fail_by_reason[r] = st.fail_by_reason.get(r, 0) + 1
            if st.current_attempt_id == aid:
                st.current_attempt_id = ""

            ev = AttemptEvent(
                t_ms=now,
                type="ATTEMPT_FAILED",
                attempt_id=aid,
                skill_id=at.skill_id,
                node_id=at.node_id,
                detail=r,
            )
            at.events.append(ev)
            self._trim_events_locked(at)
        self._publish(ev)

    def finish_stopped(self, attempt_id: str, reason: str = "stopped") -> None:
        now = mono_ms()
        aid = (attempt_id or "").strip()
        if not aid:
            return
        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return
            at.stage = "STOPPED"
            at.stage_since_ms = now
            at.ended_ms = now
            at.result = "stopped"
            at.fail_reason = (reason or "stopped")

            st = self._ensure_skill(at.skill_id)
            if st.current_attempt_id == aid:
                st.current_attempt_id = ""

            ev = AttemptEvent(
                t_ms=now,
                type="ATTEMPT_STOPPED",
                attempt_id=aid,
                skill_id=at.skill_id,
                node_id=at.node_id,
                detail=at.fail_reason,
            )
            at.events.append(ev)
            self._trim_events_locked(at)
        self._publish(ev)

    def _trim_events_locked(self, at: AttemptState) -> None:
        if len(at.events) > self._max_events_per_attempt:
            del at.events[: len(at.events) - self._max_events_per_attempt]

    # -------------------------
    # Capture events
    # -------------------------

    def capture_plan_updated(self, *, message: str = "", extra: Optional[Dict[str, Any]] = None) -> None:
        now = mono_ms()
        self._publish(CaptureEvent(t_ms=now, type="CAPTURE_PLAN_UPDATED", message=message, extra=extra or {}))

    def capture_ok(self, snapshot_age_ms: int) -> None:
        now = mono_ms()
        self._publish(CaptureEvent(t_ms=now, type="CAPTURE_OK", extra={"snapshot_age_ms": int(snapshot_age_ms)}))

    def capture_error(self, error: str, detail: str = "") -> None:
        now = mono_ms()
        self._publish(CaptureEvent(t_ms=now, type="CAPTURE_ERROR", message=error, detail=detail))

    # -------------------------
    # MetricProvider API (for AST evaluator)
    # -------------------------

    def get_metric(self, skill_id: str, metric: SkillMetric) -> Optional[int]:
        sid = (skill_id or "").strip()
        if not sid:
            return None
        m = (metric or "").strip()
        with self._lock:
            st = self._skills.get(sid)
            if st is None:
                return 0
            if m == "success":
                return int(st.success)
            if m == "attempt_started":
                return int(st.attempt_started)
            if m == "key_sent_ok":
                return int(st.key_sent_ok)
            if m == "cast_started":
                return int(st.cast_started)
            if m == "fail":
                return int(st.fail)
        return None

    # -------------------------
    # Query APIs for UI
    # -------------------------

    def snapshot_skills(self, ctx: Optional[ProfileContext] = None, *, recent_limit: int = 25) -> List[Dict[str, Any]]:
        now = mono_ms()

        skills_name: Dict[str, str] = {}
        if ctx is not None:
            try:
                for s in (getattr(ctx.skills, "skills", []) or []):
                    sid = getattr(s, "id", "") or ""
                    if sid:
                        skills_name[sid] = getattr(s, "name", "") or ""
            except Exception:
                pass

        out: List[Dict[str, Any]] = []
        with self._lock:
            for sid, st in self._skills.items():
                cur_attempt_id = st.current_attempt_id
                at = self._attempts.get(cur_attempt_id) if cur_attempt_id else None

                state = "IDLE"
                state_since = 0
                fail_reason = ""
                retry_index = 0
                node_id = ""

                if at is not None:
                    state = at.stage
                    state_since = int(at.stage_since_ms or 0)
                    fail_reason = at.fail_reason or ""
                    retry_index = int(at.retry_index or 0)
                    node_id = at.node_id or ""

                state_age = (now - state_since) if state_since > 0 else 0

                recent_rows: List[Dict[str, Any]] = []
                recent_ids = st.recent_attempt_ids[: max(0, int(recent_limit))]
                for aid in recent_ids:
                    at2 = self._attempts.get(aid)
                    if at2 is None:
                        continue
                    dur = 0
                    if at2.ended_ms is not None:
                        dur = int(at2.ended_ms - at2.created_ms)
                    age = int(now - (at2.ended_ms or at2.created_ms))
                    recent_rows.append(
                        {
                            "attempt_id": at2.attempt_id,
                            "node_id": at2.node_id,
                            "mode": at2.start_mode,
                            "result": at2.result,
                            "reason": at2.fail_reason,
                            "retries": int(at2.retry_index),
                            "readbar_ms": int(at2.readbar_ms),
                            "duration_ms": int(dur),
                            "age_ms": int(age),
                        }
                    )

                out.append(
                    {
                        "skill_id": sid,
                        "skill_name": skills_name.get(sid, ""),
                        "state": state,
                        "state_age_ms": int(state_age),
                        "current_attempt_id": cur_attempt_id,
                        "current_node_id": node_id,
                        "retry_index": int(retry_index),
                        "fail_reason": fail_reason,
                        "node_exec": int(st.node_exec),
                        "ready_false": int(st.ready_false),
                        "skipped_lock": int(st.skipped_lock_busy),
                        "skipped_disabled": int(st.skipped_disabled),
                        "attempt_started": int(st.attempt_started),
                        "key_sent_ok": int(st.key_sent_ok),
                        "cast_started": int(st.cast_started),
                        "success": int(st.success),
                        "fail": int(st.fail),
                        "fail_by_reason": dict(st.fail_by_reason),
                        "recent_attempts": recent_rows,
                    }
                )

        out.sort(key=lambda d: ((d.get("skill_name") or ""), (d.get("skill_id") or "")))
        return out

    def get_attempt_timeline(self, attempt_id: str) -> List[Dict[str, Any]]:
        aid = (attempt_id or "").strip()
        if not aid:
            return []
        with self._lock:
            at = self._attempts.get(aid)
            if at is None:
                return []
            rows: List[Dict[str, Any]] = []
            for ev in at.events:
                rows.append(
                    {
                        "t_ms": int(ev.t_ms),
                        "type": ev.type,
                        "attempt_id": ev.attempt_id,
                        "skill_id": ev.skill_id,
                        "node_id": ev.node_id,
                        "message": ev.message,
                        "detail": ev.detail,
                        "extra": dict(ev.extra or {}),
                    }
                )
            return rows

    def get_recent_attempt_ids(self, skill_id: str, *, limit: int = 50) -> List[str]:
        sid = (skill_id or "").strip()
        if not sid:
            return []
        with self._lock:
            st = self._skills.get(sid)
            if st is None:
                return []
            return list(st.recent_attempt_ids[: max(0, int(limit))])