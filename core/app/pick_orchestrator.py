# File: core/app/pick_orchestrator.py
from __future__ import annotations


class PickOrchestrator:
    """
    Removed in Step 3-3-3-3-6.

    Pick is now applied by pages (SkillsPage / PointsPage) consuming PICK_CONFIRMED
    and calling services.*.apply_pick_cmd().
    """

    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError("PickOrchestrator has been removed. Use page-level PICK_CONFIRMED handling instead.")