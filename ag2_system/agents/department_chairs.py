from __future__ import annotations

import json
from typing import Dict


class DepartmentChair:
    def __init__(self, department: Dict):
        self.department = department
        self.name = f"{department['name']}::chair"

    @staticmethod
    def _default_directions_for_department(dep: str) -> list[str]:
        dep_norm = dep.lower()
        mapping = {
            "genetics": ["chromosomal disorder", "congenital syndrome"],
            "neurology": ["neurodevelopmental disorder", "central nervous system disorder"],
            "infectious_disease": ["systemic infection", "congenital infection"],
            "hematology": ["hematologic disorder", "bone marrow disorder"],
            "endocrinology_metabolism": ["metabolic disorder", "inborn error of metabolism"],
        }
        return mapping.get(dep_norm, ["department-relevant disorder"])

    def briefing(self, presentation: str) -> Dict:
        dep = self.department["name"]
        text = presentation.lower()
        keywords = [str(k).lower() for k in self.department.get("routing", {}).get("keywords", [])]
        hits = [k for k in keywords if k in text]
        score = max(5, min(95, int(self.department.get("routing", {}).get("priority", 0)) * 10 + len(hits) * 12))
        recommend = score >= 45
        configured_directions = self.department.get("default_diagnostic_directions", [])
        if isinstance(configured_directions, list) and configured_directions:
            directions = [str(x) for x in configured_directions if str(x).strip()][:2]
        else:
            directions = self._default_directions_for_department(dep)[:2]
        payload = {
            "department": dep,
            "relevance_score": score,
            "activation_recommendation": "yes" if recommend else "no",
            "key_evidence": hits[:3],
            "counter_evidence": ["no decisive specialty-specific hallmark yet"],
            "missing_information": [f"{dep} targeted confirmatory data"],
            "why_not_me": "Current evidence is suggestive but not definitive for this specialty.",
            "uncertainty": "Fallback chair brief without LLM reasoning.",
            "suspected_conditions": [],
            "diagnostic_directions": directions,
            "confidence": 0.35,
        }
        return {
            "speaker": self.name,
            **payload,
            "recommend_activate": recommend,
            "content": json.dumps(payload, ensure_ascii=True),
        }
