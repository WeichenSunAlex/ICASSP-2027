from __future__ import annotations

from typing import Any, Dict, List

from ag2_system.orchestration.ag2_native import native_available, run_router_llm_decision_native


class TriageRouter:
    def __init__(self, model_cfg: Dict | None = None):
        self.model_cfg = model_cfg or {}

    def _rule_score(self, presentation: str, departments: List[Dict]) -> List[tuple[int, str]]:
        text = presentation.lower()
        scored = []
        for dep in departments:
            keywords = dep.get("routing", {}).get("keywords", [])
            score = int(dep.get("routing", {}).get("priority", 0))
            score += sum(1 for k in keywords if str(k).lower() in text)
            scored.append((score, dep["name"]))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored

    @staticmethod
    def _estimate_conflict_uncertainty(chair_briefs: List[Dict]) -> tuple[float, float]:
        if not chair_briefs:
            return 0.0, 1.0
        yes = sum(1 for b in chair_briefs if str(b.get("activation_recommendation", "")).lower() == "yes")
        no = len(chair_briefs) - yes
        conflict = min(1.0, abs(yes - no) / max(1, len(chair_briefs)))
        avg_rel = sum(float(b.get("relevance_score", 50)) for b in chair_briefs) / max(1, len(chair_briefs))
        uncertainty = max(0.0, min(1.0, 1.0 - (avg_rel / 100.0)))
        return conflict, uncertainty

    def _dynamic_k(self, *, min_k: int, max_k: int, uncertainty: float) -> int:
        lo = max(1, min_k)
        hi = max(lo, max_k)
        span = hi - lo
        return lo + int(round(span * max(0.0, min(1.0, uncertainty))))

    def decide_activation(
        self,
        presentation: str,
        departments: List[Dict],
        *,
        top_k: int,
        min_k: int,
        max_k: int,
        chair_briefs: List[Dict] | None = None,
        use_llm_router: bool = True,
        context_variables: Dict[str, Any] | None = None,
        monitoring: Any = None,
    ) -> Dict[str, Any]:
        briefs = chair_briefs or []
        scored = self._rule_score(presentation, departments)
        candidates = [d["name"] for d in departments]
        conflict, uncertainty = self._estimate_conflict_uncertainty(briefs)
        k = self._dynamic_k(min_k=min_k, max_k=max_k, uncertainty=uncertainty)
        if top_k > 0:
            k = min(k, max(1, top_k))
        rule_selected = [name for _score, name in scored[:k]]
        llm_selected: List[str] = []
        rejected: List[Dict[str, str]] = []
        routing_confidence = max(0.0, min(1.0, 1.0 - uncertainty))
        rationale = "rule-based fallback"
        if use_llm_router and native_available():
            provider = str(self.model_cfg.get("model_provider", "openai"))
            model = str(self.model_cfg.get("model_name", "deepseek-v4-flash"))
            router_input = {
                "presentation": presentation,
                "candidates": candidates,
                "chair_briefs": briefs,
                "constraints": {"min_k": max(1, min_k), "max_k": max(max_k, max(1, min_k)), "top_k_cap": top_k},
                "signals": {"conflict_level": conflict, "uncertainty_level": uncertainty},
            }
            try:
                out = run_router_llm_decision_native(
                    router_input=router_input,
                    model_name=model,
                    model_provider=provider,
                    context_variables=context_variables or {},
                    monitoring=monitoring,
                )
            except Exception:
                out = {}
            sel = out.get("selected_committees", [])
            if isinstance(sel, list):
                llm_selected = [str(x) for x in sel if str(x) in candidates]
            rej = out.get("rejected_committees", [])
            if isinstance(rej, list):
                for item in rej:
                    if isinstance(item, dict) and str(item.get("name", "")) in candidates:
                        rejected.append({"name": str(item.get("name")), "reason": str(item.get("reason", ""))})
            try:
                routing_confidence = float(out.get("routing_confidence", routing_confidence))
            except Exception:
                pass
            rationale = str(out.get("rationale", rationale))
        merged = []
        for name in llm_selected + rule_selected:
            if name not in merged:
                merged.append(name)
            if len(merged) >= k:
                break
        if not merged:
            merged = rule_selected[:k]
        selected_set = set(merged)
        if not rejected:
            rejected = [{"name": n, "reason": "lower priority under current evidence"} for n in candidates if n not in selected_set]
        return {
            "selected_committees": merged,
            "rejected_committees": rejected,
            "routing_confidence": max(0.0, min(1.0, routing_confidence)),
            "conflict_level": conflict,
            "uncertainty_level": uncertainty,
            "dynamic_k": k,
            "rationale": rationale,
            "decision_basis": "llm_structured_with_rule_fallback" if llm_selected else "rule_based",
        }

    def select_activated_committees(
        self,
        presentation: str,
        departments: List[Dict],
        *,
        top_k: int,
        chair_briefs: List[Dict] | None = None,
        use_llm_router: bool = True,
        context_variables: Dict[str, Any] | None = None,
        monitoring: Any = None,
    ) -> List[str]:
        decision = self.decide_activation(
            presentation,
            departments,
            top_k=top_k,
            min_k=max(1, top_k),
            max_k=max(1, top_k),
            chair_briefs=chair_briefs,
            use_llm_router=use_llm_router,
            context_variables=context_variables,
            monitoring=monitoring,
        )
        return list(decision.get("selected_committees", []))
