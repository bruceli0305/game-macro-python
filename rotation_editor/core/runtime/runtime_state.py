from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from rotation_editor.core.models import RotationPreset, Track


def node_step(n) -> int:
    try:
        s = int(getattr(n, "step_index", 0) or 0)
    except Exception:
        s = 0
    return max(0, s)


def node_order(n) -> int:
    try:
        o = int(getattr(n, "order_in_step", 0) or 0)
    except Exception:
        o = 0
    return max(0, o)


@dataclass
class GlobalTrackRuntime:
    track: Track
    next_time_ms: int
    index: int = 0

    def current_node(self):
        if not self.track.nodes:
            return None
        if self.index < 0 or self.index >= len(self.track.nodes):
            self.index = 0
        return self.track.nodes[self.index]

    def current_node_index(self) -> int:
        if not self.track.nodes:
            return -1
        if self.index < 0 or self.index >= len(self.track.nodes):
            self.index = 0
        return int(self.index)

    def advance(self) -> None:
        if not self.track.nodes:
            self.index = 0
            return
        self.index += 1
        if self.index >= len(self.track.nodes):
            self.index = 0

    def jump_to_node_id(self, node_id: str) -> bool:
        nid = (node_id or "").strip()
        if not nid or not self.track.nodes:
            return False
        for i, n in enumerate(self.track.nodes):
            if (getattr(n, "id", "") or "") == nid:
                self.index = i
                return True
        return False


@dataclass
class ModeTrackRuntime:
    track: Track
    next_time_ms: int
    order: List[int]          # indices into track.nodes sorted by step/order/idx
    pos: int = 0              # 0..len(order) (==len means done)

    def done(self) -> bool:
        return (not self.order) or self.pos >= len(self.order)

    def current_node_index(self) -> int:
        if self.done():
            return -1
        if self.pos < 0:
            self.pos = 0
        if self.pos >= len(self.order):
            self.pos = len(self.order)
            return -1
        return int(self.order[self.pos])

    def current_node(self):
        idx = self.current_node_index()
        if idx < 0 or not self.track.nodes:
            return None
        if idx >= len(self.track.nodes):
            return None
        return self.track.nodes[idx]

    def current_step(self) -> int:
        n = self.current_node()
        if n is None:
            return 0
        return node_step(n)

    def advance(self) -> None:
        if self.done():
            self.pos = len(self.order)
            return
        self.pos += 1
        if self.pos > len(self.order):
            self.pos = len(self.order)

    def reset(self) -> None:
        self.pos = 0

    def jump_to_node_id(self, node_id: str) -> bool:
        nid = (node_id or "").strip()
        if not nid or not self.track.nodes or not self.order:
            return False
        # find physical index
        phys = -1
        for i, n in enumerate(self.track.nodes):
            if (getattr(n, "id", "") or "") == nid:
                phys = i
                break
        if phys < 0:
            return False
        try:
            self.pos = self.order.index(phys)
        except ValueError:
            self.pos = 0
        return True


@dataclass
class GlobalRuntimeState:
    tracks: Dict[str, GlobalTrackRuntime]

    def all_next_times(self) -> List[int]:
        return [int(rt.next_time_ms) for rt in self.tracks.values()]

    def ready_candidates(self, now_ms: int) -> List[Tuple[int, str]]:
        out: List[Tuple[int, str]] = []
        for tid, rt in self.tracks.items():
            if int(now_ms) >= int(rt.next_time_ms):
                out.append((int(rt.next_time_ms), tid))
        return out

    def get(self, track_id: str) -> Optional[GlobalTrackRuntime]:
        return self.tracks.get((track_id or "").strip())

    def remove(self, track_id: str) -> None:
        self.tracks.pop((track_id or "").strip(), None)


@dataclass
class ModeRuntimeState:
    mode_id: str
    tracks: Dict[str, ModeTrackRuntime]
    current_step: int = 0

    def has_tracks(self) -> bool:
        return bool(self.tracks)

    def all_done(self) -> bool:
        return all(rt.done() for rt in self.tracks.values()) if self.tracks else True

    def reset_cycle(self) -> None:
        for rt in self.tracks.values():
            rt.reset()
        self._reset_current_step_to_min()

    def _reset_current_step_to_min(self) -> None:
        min_step: Optional[int] = None
        for rt in self.tracks.values():
            if rt.done():
                continue
            s = rt.current_step()
            min_step = s if min_step is None else min(min_step, s)
        self.current_step = int(min_step if min_step is not None else 0)

    def ensure_step_runnable(self) -> None:
        """
        保证 current_step 下至少有一个未 done 的轨道其当前节点属于该 step；
        若所有 done，则 reset cycle。
        """
        if not self.tracks:
            return
        if self.all_done():
            self.reset_cycle()
            return

        while True:
            any_in_step = False
            min_next: Optional[int] = None

            for rt in self.tracks.values():
                if rt.done():
                    continue
                s = rt.current_step()
                if s == self.current_step:
                    any_in_step = True
                min_next = s if min_next is None else min(min_next, s)

            if any_in_step:
                return
            if min_next is None or min_next == self.current_step:
                return
            self.current_step = int(min_next)

    def eligible_next_times(self) -> List[int]:
        out: List[int] = []
        for rt in self.tracks.values():
            if rt.done():
                continue
            if rt.current_step() == self.current_step:
                out.append(int(rt.next_time_ms))
        return out

    def ready_candidates(self, now_ms: int) -> List[Tuple[int, str]]:
        out: List[Tuple[int, str]] = []
        for tid, rt in self.tracks.items():
            if rt.done():
                continue
            if rt.current_step() != self.current_step:
                continue
            if int(now_ms) >= int(rt.next_time_ms):
                out.append((int(rt.next_time_ms), tid))
        return out

    def maybe_backstep(self, track_id: str) -> None:
        rt = self.tracks.get((track_id or "").strip())
        if rt is None or rt.done():
            return
        s = rt.current_step()
        if s < self.current_step:
            self.current_step = int(s)


def build_global_runtime(preset: RotationPreset, *, now_ms: int) -> GlobalRuntimeState:
    tracks: Dict[str, GlobalTrackRuntime] = {}
    for t in preset.global_tracks or []:
        tid = (t.id or "").strip()
        if not tid or not t.nodes:
            continue
        tracks[tid] = GlobalTrackRuntime(track=t, next_time_ms=int(now_ms), index=0)
    return GlobalRuntimeState(tracks=tracks)


def build_mode_runtime(preset: RotationPreset, mode_id: str, *, now_ms: int) -> Optional[ModeRuntimeState]:
    mid = (mode_id or "").strip()
    if not mid:
        return None
    mode = next((m for m in (preset.modes or []) if (m.id or "").strip() == mid), None)
    if mode is None:
        return None

    tracks: Dict[str, ModeTrackRuntime] = {}
    for t in mode.tracks or []:
        tid = (t.id or "").strip()
        if not tid or not t.nodes:
            continue
        idxs = list(range(len(t.nodes)))
        idxs.sort(key=lambda i: (node_step(t.nodes[i]), node_order(t.nodes[i]), i))
        tracks[tid] = ModeTrackRuntime(track=t, next_time_ms=int(now_ms), order=idxs, pos=0)

    rt = ModeRuntimeState(mode_id=mid, tracks=tracks, current_step=0)
    rt._reset_current_step_to_min()
    return rt


def find_track_in_preset(preset: RotationPreset, *, scope: str, mode_id: str, track_id: str) -> Optional[Track]:
    tid = (track_id or "").strip()
    if not tid:
        return None
    sc = (scope or "global").strip().lower()
    if sc == "global":
        return next((t for t in (preset.global_tracks or []) if (t.id or "").strip() == tid), None)
    # mode
    mid = (mode_id or "").strip()
    mode = next((m for m in (preset.modes or []) if (m.id or "").strip() == mid), None)
    if mode is None:
        return None
    return next((t for t in (mode.tracks or []) if (t.id or "").strip() == tid), None)


def track_has_node(track: Track, node_id: str) -> bool:
    nid = (node_id or "").strip()
    if not nid or track is None:
        return False
    for n in (track.nodes or []):
        if (getattr(n, "id", "") or "") == nid:
            return True
    return False