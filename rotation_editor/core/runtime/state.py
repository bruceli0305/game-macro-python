from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from rotation_editor.core.models import Track


# -----------------------------
# 全局轨道（环形、忽略 step）
# -----------------------------

@dataclass
class GlobalTrackState:
    track_id: str
    next_time_ms: int
    node_index: int = 0

    def advance(self, track: Track) -> None:
        if not track.nodes:
            self.node_index = 0
            return
        self.node_index += 1
        if self.node_index >= len(track.nodes):
            self.node_index = 0

    def jump_to(self, track: Track, node_index: int) -> None:
        if not track.nodes:
            self.node_index = 0
            return
        try:
            idx = int(node_index)
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(track.nodes):
            idx = 0
        self.node_index = idx


class GlobalRuntime:
    """
    全局域运行态：多条全局轨道并行调度（环形）。
    """
    def __init__(self, tracks: List[Track], *, now_ms: int) -> None:
        self.tracks_by_id: Dict[str, Track] = {}
        self.states: Dict[str, GlobalTrackState] = {}

        for t in tracks or []:
            tid = (t.id or "").strip()
            if not tid:
                continue
            if not t.nodes:
                continue
            self.tracks_by_id[tid] = t
            self.states[tid] = GlobalTrackState(track_id=tid, next_time_ms=int(now_ms), node_index=0)

    def has_tracks(self) -> bool:
        return bool(self.states)

    def all_next_times(self) -> List[int]:
        return [int(st.next_time_ms) for st in self.states.values()]

    def ready_candidates(self, now_ms: int) -> List[Tuple[int, str]]:
        out: List[Tuple[int, str]] = []
        for tid, st in self.states.items():
            if int(now_ms) >= int(st.next_time_ms):
                out.append((int(st.next_time_ms), tid))
        return out

    def get_track(self, track_id: str) -> Optional[Track]:
        return self.tracks_by_id.get((track_id or "").strip())

    def get_state(self, track_id: str) -> Optional[GlobalTrackState]:
        return self.states.get((track_id or "").strip())

    def remove_track(self, track_id: str) -> None:
        tid = (track_id or "").strip()
        self.states.pop(tid, None)
        self.tracks_by_id.pop(tid, None)


# -----------------------------
# 模式轨道（线性，cycle 结束后 reset）
# -----------------------------

def node_step(n) -> int:
    try:
        s = int(getattr(n, "step_index", 0) or 0)
    except Exception:
        s = 0
    return max(0, s)


def node_order_in_step(n) -> int:
    try:
        o = int(getattr(n, "order_in_step", 0) or 0)
    except Exception:
        o = 0
    return max(0, o)


@dataclass
class ModeTrackState:
    track_order: int
    track_id: str
    order: List[int]          # 节点索引序列（按 step/order/idx 排序）
    pos: int                  # 0..len(order)，pos==len(order) 表示 done
    next_time_ms: int

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

    def advance(self) -> None:
        if self.done():
            self.pos = len(self.order)
            return
        self.pos += 1
        if self.pos > len(self.order):
            self.pos = len(self.order)

    def reset(self) -> None:
        self.pos = 0

    def jump_to_node_index(self, node_index: int) -> None:
        if not self.order:
            self.pos = 0
            return
        try:
            idx = int(node_index)
        except Exception:
            idx = 0
        try:
            self.pos = self.order.index(idx)
        except ValueError:
            self.pos = 0


class ModeRuntime:
    """
    模式域运行态：多轨并行 + step 同步推进。
    """
    def __init__(self, mode_id: str, tracks: List[Track], *, now_ms: int) -> None:
        self.mode_id = (mode_id or "").strip()
        self.tracks_by_id: Dict[str, Track] = {}
        self.states: Dict[str, ModeTrackState] = {}
        self.current_step: int = 0

        # 建状态
        for t_order, t in enumerate(tracks or []):
            tid = (t.id or "").strip()
            if not tid:
                continue
            if not t.nodes:
                continue

            idxs = list(range(len(t.nodes)))
            idxs.sort(key=lambda i: (node_step(t.nodes[i]), node_order_in_step(t.nodes[i]), i))

            self.tracks_by_id[tid] = t
            self.states[tid] = ModeTrackState(
                track_order=int(t_order),
                track_id=tid,
                order=idxs,
                pos=0,
                next_time_ms=int(now_ms),
            )

        # 初始化 current_step 为当前节点最小 step
        self._reset_current_step_to_min()

    def has_tracks(self) -> bool:
        return bool(self.states)

    def all_done(self) -> bool:
        if not self.states:
            return True
        return all(st.done() for st in self.states.values())

    def _reset_current_step_to_min(self) -> None:
        min_step: Optional[int] = None
        for tid, st in self.states.items():
            tr = self.tracks_by_id.get(tid)
            if tr is None or not tr.nodes:
                continue
            ni = st.current_node_index()
            if ni < 0 or ni >= len(tr.nodes):
                continue
            s = node_step(tr.nodes[ni])
            min_step = s if min_step is None else min(min_step, s)
        self.current_step = int(min_step if min_step is not None else 0)

    def reset_cycle(self) -> None:
        for st in self.states.values():
            st.reset()
        self._reset_current_step_to_min()

    def ensure_step_runnable(self) -> None:
        """
        保证 current_step 至少有一个轨道的当前节点可执行。
        若所有轨道 done，则 reset 新一轮 cycle。
        """
        if not self.states:
            return

        if self.all_done():
            self.reset_cycle()
            return

        while True:
            any_in_step = False
            min_next: Optional[int] = None

            for tid, st in self.states.items():
                if st.done():
                    continue
                tr = self.tracks_by_id.get(tid)
                if tr is None or not tr.nodes:
                    continue
                ni = st.current_node_index()
                if ni < 0 or ni >= len(tr.nodes):
                    continue
                s = node_step(tr.nodes[ni])

                if s == self.current_step:
                    any_in_step = True
                min_next = s if min_next is None else min(min_next, s)

            if any_in_step:
                return

            if min_next is None or min_next == self.current_step:
                return

            self.current_step = int(min_next)

    def eligible_next_times(self) -> List[int]:
        """
        当前 step 下可执行轨道的 next_time 列表。
        """
        out: List[int] = []
        for tid, st in self.states.items():
            if st.done():
                continue
            tr = self.tracks_by_id.get(tid)
            if tr is None or not tr.nodes:
                continue
            ni = st.current_node_index()
            if ni < 0 or ni >= len(tr.nodes):
                continue
            if node_step(tr.nodes[ni]) == self.current_step:
                out.append(int(st.next_time_ms))
        return out

    def ready_candidates(self, now_ms: int) -> List[Tuple[int, str]]:
        """
        返回当前 step 下，到期可执行的 (next_time, track_id) 列表。
        """
        out: List[Tuple[int, str]] = []
        for tid, st in self.states.items():
            if st.done():
                continue
            tr = self.tracks_by_id.get(tid)
            if tr is None or not tr.nodes:
                continue
            ni = st.current_node_index()
            if ni < 0 or ni >= len(tr.nodes):
                continue
            if node_step(tr.nodes[ni]) != self.current_step:
                continue
            if int(now_ms) >= int(st.next_time_ms):
                out.append((int(st.next_time_ms), tid))
        return out

    def maybe_backstep(self, track_id: str) -> None:
        """
        若某轨道 jump 后导致当前节点 step 更小，允许回退 current_step。
        """
        tid = (track_id or "").strip()
        st = self.states.get(tid)
        tr = self.tracks_by_id.get(tid)
        if st is None or tr is None or not tr.nodes:
            return
        ni = st.current_node_index()
        if ni < 0 or ni >= len(tr.nodes):
            return
        s = node_step(tr.nodes[ni])
        if s < self.current_step:
            self.current_step = int(s)