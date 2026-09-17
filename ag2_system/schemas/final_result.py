from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ManyAgentFinalResult:
    case_id: str
    case_url: str
    stage: str
    case_name: str
    presentation: str
    most_likely_diagnosis: str
    differential_diagnoses: List[str] = field(default_factory=list)
    recommended_tests: List[str] = field(default_factory=list)
    areas_of_disagreement: List[str] = field(default_factory=list)
    committee_summaries: List[Dict[str, Any]] = field(default_factory=list)
    routing_trace: List[Dict[str, Any]] = field(default_factory=list)
    total_cost: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

