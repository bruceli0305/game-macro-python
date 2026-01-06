from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.pick.scanner import CapturePlan
from rotation_editor.ast import ProbeRequirements

from rotation_editor.runtime.state.store import StateStore
from rotation_editor.runtime.capture.manager import CaptureEventSink


@dataclass
class StateStoreCaptureSink(CaptureEventSink):
    """
    CaptureManager -> StateStore 的事件适配器：
    - plan 更新：记录 CAPTURE_PLAN_UPDATED
    - capture ok：记录 CAPTURE_OK（带 snapshot_age_ms）
    - capture error：记录 CAPTURE_ERROR（带 error/detail）
    """
    store: StateStore

    def on_plan_updated(self, probes: ProbeRequirements, plan: CapturePlan) -> None:
        extra: Dict[str, Any] = {
            "probe_point_ids": sorted(list(probes.point_ids or [])),
            "probe_skill_pixel_ids": sorted(list(probes.skill_pixel_ids or [])),
            "probe_skill_metric_ids": sorted(list(probes.skill_metric_ids or [])),
            "monitor_count": int(len(getattr(plan, "plans", {}) or {})),
        }
        self.store.capture_plan_updated(message="capture_plan_updated", extra=extra)

    def on_capture_ok(self, snapshot_age_ms: int) -> None:
        self.store.capture_ok(int(snapshot_age_ms))

    def on_capture_error(self, error: str, detail: str) -> None:
        self.store.capture_error(error=str(error or "capture_error"), detail=str(detail or ""))