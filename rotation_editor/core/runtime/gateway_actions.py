from __future__ import annotations

from typing import Optional, Callable
import threading

from rotation_editor.core.models import GatewayNode
from rotation_editor.core.runtime.state import GlobalRuntime, ModeRuntime
from rotation_editor.core.runtime.clock import mono_ms


def _action(node: GatewayNode) -> str:
    return (node.action or "switch_mode").strip().lower() or "switch_mode"


def _to_int(v, default: int = 0) -> int:
    try:
        x = int(v)
    except Exception:
        return int(default)
    return x


def apply_gateway_global(
    *,
    node: GatewayNode,
    current_track_id: str,
    global_rt: GlobalRuntime,
    mode_rt: Optional[ModeRuntime],
    build_mode_rt: Callable[[str], Optional[ModeRuntime]],
    stop_evt: threading.Event,
    set_stop_reason: Callable[[str], None],
) -> Optional[ModeRuntime]:
    """
    全局域网关动作：
    - end
    - jump_node（当前全局轨道）
    - jump_track（仅全局 -> 全局；不跨模式）
    - switch_mode（切换到目标模式）
    """
    act = _action(node)
    tid = (current_track_id or "").strip()

    tr = global_rt.get_track(tid)
    st = global_rt.get_state(tid)
    if tr is None or st is None:
        return mode_rt

    if act == "end":
        set_stop_reason("gateway_end")
        stop_evt.set()
        st.next_time_ms = mono_ms() + 10
        return mode_rt

    if act == "jump_node":
        st.jump_to(tr, _to_int(node.target_node_index, 0))
        st.next_time_ms = mono_ms() + 10
        return mode_rt

    if act == "switch_mode":
        target_mode = (node.target_mode_id or "").strip()
        if target_mode:
            new_m = build_mode_rt(target_mode)
            if new_m is not None:
                mode_rt = new_m
        # 消费当前网关，防止反复触发
        st.advance(tr)
        st.next_time_ms = mono_ms() + 10
        return mode_rt

    if act == "jump_track":
        # 全局域不允许跨模式
        if (node.target_mode_id or "").strip():
            st.advance(tr)
            st.next_time_ms = mono_ms() + 10
            return mode_rt

        target_track = (node.target_track_id or "").strip()
        if target_track:
            tr2 = global_rt.get_track(target_track)
            st2 = global_rt.get_state(target_track)
            if tr2 is not None and st2 is not None and tr2.nodes:
                st2.jump_to(tr2, _to_int(node.target_node_index, 0))
                st2.next_time_ms = mono_ms() + 10

        # 当前网关也消费
        st.advance(tr)
        st.next_time_ms = mono_ms() + 10
        return mode_rt

    # 未支持：消费网关顺序前进
    st.advance(tr)
    st.next_time_ms = mono_ms() + 10
    return mode_rt


def apply_gateway_mode(
    *,
    node: GatewayNode,
    current_track_id: str,
    mode_rt: ModeRuntime,
    build_mode_rt: Callable[[str], Optional[ModeRuntime]],
    stop_evt: threading.Event,
    set_stop_reason: Callable[[str], None],
) -> Optional[ModeRuntime]:
    """
    模式域网关动作（与 UI 对齐）：
    - end
    - jump_node（当前轨道）
    - jump_track（同模式内跳到目标轨道；跨模式则 switch_mode）
    - switch_mode（切换到目标模式）
    """
    act = _action(node)
    tid = (current_track_id or "").strip()
    st = mode_rt.states.get(tid)
    tr = mode_rt.tracks_by_id.get(tid)
    if st is None or tr is None:
        return mode_rt

    if act == "end":
        set_stop_reason("gateway_end")
        stop_evt.set()
        st.next_time_ms = mono_ms() + 10
        return mode_rt

    if act == "jump_node":
        st.jump_to_node_index(_to_int(node.target_node_index, 0))
        mode_rt.maybe_backstep(tid)
        st.next_time_ms = mono_ms() + 10
        return mode_rt

    if act == "switch_mode":
        target_mode = (node.target_mode_id or "").strip()
        if not target_mode:
            # 无目标：消费网关
            st.advance()
            st.next_time_ms = mono_ms() + 10
            return mode_rt
        new_m = build_mode_rt(target_mode)
        if new_m is not None:
            return new_m
        # 无法切换：消费网关
        st.advance()
        st.next_time_ms = mono_ms() + 10
        return mode_rt

    if act == "jump_track":
        target_mode = (node.target_mode_id or "").strip()
        if target_mode and target_mode != mode_rt.mode_id:
            # 跨模式：语义清晰用 switch_mode
            new_m = build_mode_rt(target_mode)
            if new_m is not None:
                return new_m
            st.advance()
            st.next_time_ms = mono_ms() + 10
            return mode_rt

        target_track = (node.target_track_id or "").strip()
        if target_track and target_track in mode_rt.states:
            st2 = mode_rt.states.get(target_track)
            tr2 = mode_rt.tracks_by_id.get(target_track)
            if st2 is not None and tr2 is not None and tr2.nodes:
                st2.jump_to_node_index(_to_int(node.target_node_index, 0))
                st2.next_time_ms = mono_ms() + 10
                mode_rt.maybe_backstep(target_track)

        # 当前网关消费一次，避免反复触发
        st.advance()
        st.next_time_ms = mono_ms() + 10
        return mode_rt

    # 未支持：消费网关
    st.advance()
    st.next_time_ms = mono_ms() + 10
    return mode_rt