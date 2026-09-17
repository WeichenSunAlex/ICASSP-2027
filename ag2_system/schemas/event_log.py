from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class EventLogEntry:
    round_id: int
    stage: str
    sender: str
    receiver: str
    committee_name: str
    message_type: str
    short_content_summary: str
    context_snapshot: Dict[str, Any]
    token_usage: float
    timestamp: str
    full_content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
