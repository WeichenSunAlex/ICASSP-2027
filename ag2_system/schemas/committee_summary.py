from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


@dataclass
class CommitteeSummary:
    committee_name: str
    top_hypotheses: List[str] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    recommended_tests: List[str] = field(default_factory=list)
    confidence: float = 0.0
    minority_opinions: List[str] = field(default_factory=list)
    activation_reason: str = ""

    def __post_init__(self) -> None:
        self.top_hypotheses = _as_list(self.top_hypotheses)
        self.supporting_evidence = _as_list(self.supporting_evidence)
        self.missing_information = _as_list(self.missing_information)
        self.recommended_tests = _as_list(self.recommended_tests)
        self.minority_opinions = _as_list(self.minority_opinions)
        self.confidence = max(0.0, min(1.0, float(self.confidence or 0.0)))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

