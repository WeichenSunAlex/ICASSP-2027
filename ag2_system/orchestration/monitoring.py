from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from ag2_system.schemas.event_log import EventLogEntry
from ag2_system.schemas.routing_log import RoutingLogEntry


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MonitoringState:
    def __init__(self) -> None:
        self.events: List[EventLogEntry] = []
        self.routing: List[RoutingLogEntry] = []
        self.round_id = 0

    def log_event(
        self,
        *,
        stage: str,
        sender: str,
        receiver: str,
        committee_name: str,
        message_type: str,
        short_content_summary: str,
        context_snapshot: Dict[str, Any],
        token_usage: float = 0.0,
        full_content: str = "",
    ) -> None:
        self.round_id += 1
        self.events.append(
            EventLogEntry(
                round_id=self.round_id,
                stage=stage,
                sender=sender,
                receiver=receiver,
                committee_name=committee_name,
                message_type=message_type,
                short_content_summary=short_content_summary,
                context_snapshot=context_snapshot,
                token_usage=token_usage,
                timestamp=utc_now(),
                full_content=full_content or short_content_summary,
            )
        )

    def log_routing(
        self,
        *,
        sender: str,
        selected_receiver: str,
        reason: str,
        decision_basis: str,
        activated_committees: List[str],
        current_conflict_level: float,
        current_confidence_level: float,
        budget_remaining: float | None,
        stage: str,
    ) -> None:
        self.routing.append(
            RoutingLogEntry(
                sender=sender,
                selected_receiver=selected_receiver,
                reason=reason,
                decision_basis=decision_basis,
                activated_committees=activated_committees,
                current_conflict_level=current_conflict_level,
                current_confidence_level=current_confidence_level,
                budget_remaining=budget_remaining,
                stage=stage,
                timestamp=utc_now(),
            )
        )
