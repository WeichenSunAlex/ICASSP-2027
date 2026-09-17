from __future__ import annotations

from typing import Any, Dict, List

from ag2_system.orchestration.ag2_native import native_available, run_final_judge_decision_native


class FinalJudge:
    def __init__(self, model_cfg: Dict | None = None):
        self.model_cfg = model_cfg or {}

    def decide(
        self,
        board_state: Dict,
        committee_summaries: List[Dict],
        *,
        case_id: str,
        stage: str,
        presentation: str,
        conflict_followup: Any = None,
        use_llm: bool = True,
        context_variables: Dict[str, Any] | None = None,
        monitoring: Any = None,
    ) -> Dict:
        if use_llm and native_available():
            provider = str(self.model_cfg.get("model_provider", "openai"))
            model = str(self.model_cfg.get("model_name", "deepseek-v4-flash"))
            try:
                out = run_final_judge_decision_native(
                    case_id=str(case_id),
                    stage=str(stage),
                    presentation=str(presentation),
                    board_summary=board_state,
                    committee_summaries=committee_summaries,
                    conflict_followup=conflict_followup,
                    model_name=model,
                    model_provider=provider,
                    context_variables=context_variables or {},
                    monitoring=monitoring,
                )
            except Exception:
                out = {}
            if isinstance(out, dict) and out.get("most_likely_diagnosis"):
                return {
                    "most_likely_diagnosis": str(out.get("most_likely_diagnosis", "")),
                    "differential_diagnoses": [str(x) for x in out.get("differential_diagnoses", [])][:6],
                    "recommended_tests": [str(x) for x in out.get("recommended_tests", [])],
                    "areas_of_disagreement": [str(x) for x in out.get("areas_of_disagreement", [])],
                    "committee_summaries": committee_summaries,
                    "decision_rationale": str(out.get("decision_rationale", "")),
                    "used_committees": [str(x) for x in out.get("used_committees", [])],
                    "overall_confidence": float(out.get("overall_confidence", 0.0)),
                }

        hypotheses = board_state.get("hypotheses", [])
        return {
            "most_likely_diagnosis": hypotheses[0] if hypotheses else "",
            "differential_diagnoses": hypotheses[1:6],
            "recommended_tests": board_state.get("recommended_tests", []) if stage == "initial" else [],
            "areas_of_disagreement": board_state.get("conflict_topics", []),
            "committee_summaries": committee_summaries,
            "decision_rationale": "Fallback deterministic adjudication from board aggregation.",
            "used_committees": [s.get("committee_name", "") for s in committee_summaries if s.get("committee_name")],
            "overall_confidence": float(board_state.get("confidence_estimates", 0.0)),
        }
