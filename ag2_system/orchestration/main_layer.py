from __future__ import annotations

import json
from typing import Dict, List

from ag2_system.agents.board import Board
from ag2_system.agents.department_chairs import DepartmentChair
from ag2_system.agents.final_judge import FinalJudge
from ag2_system.agents.triage_router import TriageRouter
from ag2_system.orchestration.ag2_native import (
    native_available,
    run_chair_briefing_round_robin_native,
)
from ag2_system.orchestration.committee_layer import run_activated_committee
from ag2_system.orchestration.routing import route_many_to_one, route_one_to_many_sequential


def run_main_layer(
    *,
    case_id: str,
    stage: str,
    presentation: str,
    departments: List[Dict],
    cfg: Dict,
    role_models: Dict[str, Dict[str, str]],
    mock: bool,
    monitoring,
) -> Dict:
    context_variables = {
        "chair_briefs": [],
        "activated_committees": [],
        "conflict_topics": [],
        "budget_remaining": cfg.get("cost_budget"),
    }
    # Stage 1: all chairs must speak once (Scheme A)
    chair_briefs = []
    use_native_ag2 = bool(cfg.get("use_native_ag2", True)) and (not mock)
    if use_native_ag2 and native_available():
        chair_briefs = run_chair_briefing_round_robin_native(
            departments=departments,
            presentation=presentation,
            model_name=role_models["department_chair"]["model_name"],
            model_provider=role_models["department_chair"]["model_provider"],
            routing_mode=str(cfg.get("routing_mode", "deterministic")),
            monitoring=monitoring,
        )
        for brief in chair_briefs:
            monitoring.log_event(
                stage="chair_briefing_round_robin",
                sender=brief["speaker"],
                receiver="Board",
                committee_name=brief["department"],
                message_type="chair_briefing",
                short_content_summary=str(brief.get("content", ""))[:160],
                context_snapshot={"department": brief["department"], "native_ag2": True},
                full_content=str(brief.get("content", "")),
            )
    else:
        for dep in departments:
            chair = DepartmentChair(dep)
            brief = chair.briefing(presentation)
            chair_briefs.append(brief)
            monitoring.log_event(
                stage="chair_briefing_round_robin",
                sender=chair.name,
                receiver="Board",
                committee_name=dep["name"],
                message_type="chair_briefing",
                short_content_summary=brief["content"][:160],
                context_snapshot={"department": dep["name"], "native_ag2": False},
                full_content=brief["content"],
            )
    context_variables["chair_briefs"] = chair_briefs

    # Stage 2: activation with explicit router fan-out and many-to-one board collection
    router = TriageRouter(model_cfg=role_models["triage_router"])
    routing_decision = router.decide_activation(
        presentation,
        departments,
        top_k=int(cfg.get("top_k_committees", 4)),
        min_k=int(cfg.get("min_k_committees", 2)),
        max_k=int(cfg.get("max_k_committees", 5)),
        chair_briefs=chair_briefs,
        use_llm_router=bool(cfg.get("router_llm_enabled", True)) and (not mock),
        context_variables=context_variables,
        monitoring=monitoring,
    )
    activated = list(routing_decision.get("selected_committees", []))
    context_variables["routing_decision"] = routing_decision
    context_variables["activated_committees"] = activated
    fanout = route_one_to_many_sequential("TriageRouter", [d["name"] for d in departments], {"case": "screen"})
    for sender, receiver, _payload in fanout:
        monitoring.log_routing(
            sender=sender,
            selected_receiver=receiver,
            reason=str(routing_decision.get("rationale", "router decision")),
            decision_basis=str(routing_decision.get("decision_basis", "router")),
            activated_committees=activated,
            current_conflict_level=float(routing_decision.get("conflict_level", 0.0)),
            current_confidence_level=float(routing_decision.get("routing_confidence", 0.0)),
            budget_remaining=cfg.get("cost_budget"),
            stage="chair_briefing_round_robin",
        )
    for item in routing_decision.get("rejected_committees", []):
        monitoring.log_routing(
            sender="TriageRouter",
            selected_receiver=str(item.get("name", "")),
            reason=f"rejected: {str(item.get('reason', ''))}",
            decision_basis="router_rejection_record",
            activated_committees=activated,
            current_conflict_level=float(routing_decision.get("conflict_level", 0.0)),
            current_confidence_level=float(routing_decision.get("routing_confidence", 0.0)),
            budget_remaining=cfg.get("cost_budget"),
            stage="router_rejections",
        )

    # Stage 3: only activated committees deep discuss
    summaries = []
    for dep in departments:
        if dep["name"] not in activated:
            continue
        summary = run_activated_committee(
            dep,
            presentation,
            model_name=role_models["department_chair"]["model_name"],
            model_provider=role_models["department_chair"]["model_provider"],
            member_model_name=role_models["committee_member"]["model_name"],
            member_model_provider=role_models["committee_member"]["model_provider"],
            use_native_ag2=use_native_ag2,
            monitoring=monitoring,
            enforce_all_members_first_round=bool(cfg.get("all_activated_members_must_speak_once", True)),
            max_rounds=int(cfg.get("max_rounds_per_committee", 2)),
            internal_discussion_rounds_per_member=int(
                cfg.get("internal_discussion_rounds_per_member", 1)
            ),
        )
        summaries.append(summary.to_dict())
        summary_content = json.dumps(summary.to_dict(), ensure_ascii=True)
        monitoring.log_event(
            stage="committee_summary_upward",
            sender=f"{dep['name']}::chair",
            receiver="Board",
            committee_name=dep["name"],
            message_type="committee_summary",
            short_content_summary="structured summary emitted",
            context_snapshot={"activated_committees": activated},
            full_content=summary_content,
        )

    board = Board(model_cfg=role_models["board"])
    board_state = board.aggregate(summaries)
    context_variables["conflict_topics"] = list(board_state.get("conflict_topics", []))

    followup_k = int(cfg.get("board_followup_max_rounds", 0))
    round_idx = 0
    while board_state.get("conflict_topics") and round_idx < followup_k:
        round_idx += 1
        for dep_name in list(board_state.get("activated_committees", [])):
            monitoring.log_event(
                stage="board_followup_round",
                sender="Board",
                receiver=f"{dep_name}::chair",
                committee_name=dep_name,
                message_type="followup_request",
                short_content_summary=f"resolve conflict round {round_idx}",
                context_snapshot={"round": round_idx, "conflicts": board_state.get("conflict_topics", [])},
                full_content=json.dumps(
                    {
                        "round": round_idx,
                        "request": "resolve conflict",
                        "conflicts": board_state.get("conflict_topics", []),
                    },
                    ensure_ascii=True,
                ),
            )
            monitoring.log_routing(
                sender="Board",
                selected_receiver=f"{dep_name}::chair",
                reason=f"conflict follow-up round {round_idx}",
                decision_basis="context_condition",
                activated_committees=activated,
                current_conflict_level=float(len(board_state.get("conflict_topics", []))),
                current_confidence_level=float(board_state.get("confidence_estimates", 0.0)),
                budget_remaining=cfg.get("cost_budget"),
                stage="board_followup_round",
            )
        # Deterministic decay for mock/control flow
        board_state["conflict_topics"] = board_state.get("conflict_topics", [])[1:]
        context_variables["conflict_topics"] = list(board_state.get("conflict_topics", []))

    many_to_one = route_many_to_one(
        [f"{s['committee_name']}::chair" for s in summaries],
        "Board",
        summaries,
    )
    for sender, receiver, _payload in many_to_one:
        monitoring.log_routing(
            sender=sender,
            selected_receiver=receiver,
            reason="committee summary aggregation",
            decision_basis="explicit_hardcoded_rule",
            activated_committees=activated,
            current_conflict_level=float(len(board_state.get("conflict_topics", []))),
            current_confidence_level=float(board_state.get("confidence_estimates", 0.0)),
            budget_remaining=cfg.get("cost_budget"),
            stage="board_aggregation",
        )

    judge = FinalJudge(model_cfg=role_models["final_judge"])
    final = judge.decide(
        board_state,
        summaries,
        case_id=case_id,
        stage=stage,
        presentation=presentation,
        conflict_followup={"remaining_conflicts": board_state.get("conflict_topics", [])},
        use_llm=bool(cfg.get("final_judge_llm_enabled", True)) and (not mock),
        context_variables=context_variables,
        monitoring=monitoring,
    )
    return {
        "final": final,
        "board_state": board_state,
        "activated_committees": activated,
        "chair_briefs": chair_briefs,
        "committee_summaries": summaries,
        "board_followup_rounds_used": round_idx,
        "context_variables": context_variables,
        "routing_decision": routing_decision,
    }
