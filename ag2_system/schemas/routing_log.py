from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class RoutingLogEntry:
    sender: str
    selected_receiver: str
    reason: str
    decision_basis: str
    activated_committees: List[str] = field(default_factory=list)
    current_conflict_level: float = 0.0
    current_confidence_level: float = 0.0
    budget_remaining: float | None = None
    stage: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

