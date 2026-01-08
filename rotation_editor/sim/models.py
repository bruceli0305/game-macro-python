# rotation_editor/sim/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SkillSimState:
    """
    单个技能在推演过程中的状态：

    - next_available_ms : 下次可释放时间（冷却结束的绝对 ms）
    - metrics           : 各类计数指标，键与 StateStore 中的 SkillMetric 一致：
        * "success"
        * "attempt_started"
        * "key_sent_ok"
        * "cast_started"
        * "fail"
    """
    next_available_ms: int = 0
    metrics: Dict[str, int] = field(
        default_factory=lambda: {
            "success": 0,
            "attempt_started": 0,
            "key_sent_ok": 0,
            "cast_started": 0,
            "fail": 0,
        }
    )


@dataclass
class SimEvent:
    """
    推演结果中的单个事件（一次节点执行）：

    - index     : 事件序号（0,1,2,...）
    - t_ms      : 模拟时间（从 0 开始，单位 ms）
    - scope     : "global" | "mode"
    - mode_id   : 模式 ID（scope=global 时通常为空串）
    - track_id  : 轨道 ID
    - node_id   : 节点 ID
    - node_kind : "skill" | "gateway" | 其它
    - label     : 节点显示标签（技能名/自定义 label）
    - outcome   : 执行结果，例如：
        * "SUCCESS" / "SKIPPED_CD" / "GW_TAKEN" / "GW_COND_FALSE" / ...
    - reason    : 更具体的原因说明（如 "cd_not_ready" / "no_cast_start" 等）
    """
    index: int
    t_ms: int
    scope: str
    mode_id: str
    track_id: str
    node_id: str
    node_kind: str
    label: str
    outcome: str
    reason: str = ""


@dataclass
class SimConfig:
    """
    推演配置：

    - max_run_ms      : 最大模拟时长（毫秒），防止无限循环
    - max_exec_nodes  : 最大执行节点数，进一步限制推演规模

    后续可以扩展：
    - pixel_policy    : 在推演中如何处理 Pixel 原子（忽略/近似等）
    - ready_policy    : ready_expr 为 Unknown 时的处理方式
    等。
    """
    max_run_ms: int = 120_000
    max_exec_nodes: int = 500


@dataclass
class SimResult:
    """
    推演结果：

    - preset_id     : 所属 RotationPreset 的 ID
    - events        : 按时间顺序排列的 SimEvent 列表
    - final_time_ms : 推演结束时的模拟时间（ms）
    - final_metrics : 各技能的最终状态快照（冷却与指标），可用于统计/展示
    """
    preset_id: str
    events: List[SimEvent]
    final_time_ms: int
    final_metrics: Dict[str, SkillSimState]