from __future__ import annotations

from typing import Dict, List

from ag2_system.utils.normalization import unique_keep_order


class Board:
    def __init__(self, model_cfg: Dict | None = None):
        self.model_cfg = model_cfg or {}

    def aggregate(self, committee_summaries: List[Dict]) -> Dict:
        hypotheses = unique_keep_order(
            h for s in committee_summaries for h in s.get("top_hypotheses", [])
        )
        tests = unique_keep_order(
            t for s in committee_summaries for t in s.get("recommended_tests", [])
        )
        disagreements = unique_keep_order(
            d for s in committee_summaries for d in s.get("minority_opinions", [])
        )
        avg_conf = (
            sum(float(s.get("confidence", 0.0)) for s in committee_summaries) / len(committee_summaries)
            if committee_summaries
            else 0.0
        )
        return {
            "activated_committees": [s.get("committee_name", "") for s in committee_summaries],
            "excluded_committees": [],
            "conflict_topics": disagreements,
            "confidence_estimates": avg_conf,
            "budget_remaining": None,
            "hypotheses": hypotheses,
            "recommended_tests": tests,
        }
