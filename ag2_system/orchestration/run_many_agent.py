from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from ag2_system.core import CaseResult, ExperimentConfig
from ag2_system.orchestration.ag2_native import native_available
from ag2_system.orchestration.main_layer import run_main_layer
from ag2_system.orchestration.monitoring import MonitoringState
from ag2_system.schemas.final_result import ManyAgentFinalResult

ROLE_KEYS = ("triage_router", "department_chair", "committee_member", "board", "final_judge")


def _resolve_role_models(config: ExperimentConfig) -> Dict[str, Dict[str, str]]:
    raw = dict(config.heterogeneous_models or {})
    resolved: Dict[str, Dict[str, str]] = {}
    for role in ROLE_KEYS:
        value = raw.get(role, {})
        if isinstance(value, str):
            resolved[role] = {"model_provider": config.model_provider, "model_name": value}
        elif isinstance(value, dict):
            resolved[role] = {
                "model_provider": str(value.get("model_provider", config.model_provider)),
                "model_name": str(value.get("model_name", config.model_name)),
            }
        else:
            resolved[role] = {
                "model_provider": config.model_provider,
                "model_name": config.model_name,
            }
    return resolved


def load_department_config(path: str | Path) -> List[Dict[str, Any]]:
    import yaml

    with Path(path).open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    departments = data.get("departments", [])
    if not isinstance(departments, list):
        raise ValueError("departments must be a list")
    return [department for department in departments if department.get("enabled", True)]


def run_many_agent_case(case, config: ExperimentConfig) -> CaseResult:
    params = dict(config.many_agent or {})
    departments = load_department_config(
        params.get("departments_config", "ag2_system/configs/departments.yaml")
    )
    enabled = params.get("enabled_departments", [])
    if enabled:
        allowed = set(enabled)
        departments = [department for department in departments if department["name"] in allowed]

    presentation = case.initial_presentation if config.stage == "initial" else case.follow_up_presentation
    use_native_ag2 = bool(params.get("use_native_ag2", True))
    strict_native = bool(params.get("strict_native_ag2", True))
    if use_native_ag2 and strict_native and not config.mock and not native_available():
        raise RuntimeError("AG2 group chat APIs are unavailable. Install the pinned AG2 dependency.")
    if not config.mock and str(config.model_provider).lower() == "openai":
        if not (os.environ.get("AG2_API_KEY") or os.environ.get("OPENAI_API_KEY")):
            raise RuntimeError("Set AG2_API_KEY or OPENAI_API_KEY before a live run.")

    monitor = MonitoringState()
    role_models = _resolve_role_models(config)
    output = run_main_layer(
        case_id=str(case.case_url),
        stage=config.stage,
        presentation=presentation,
        departments=departments,
        cfg=params,
        role_models=role_models,
        mock=config.mock,
        monitoring=monitor,
    )

    canonical = ManyAgentFinalResult(
        case_id=str(case.case_url),
        case_url=str(case.case_url),
        stage=config.stage,
        case_name=case.case_name,
        presentation=presentation,
        most_likely_diagnosis=output["final"]["most_likely_diagnosis"],
        differential_diagnoses=output["final"]["differential_diagnoses"],
        recommended_tests=output["final"]["recommended_tests"],
        areas_of_disagreement=output["final"]["areas_of_disagreement"],
        committee_summaries=output["committee_summaries"],
        routing_trace=[item.to_dict() for item in monitor.routing],
        total_cost=0.0,
        metadata={
            "chair_briefs": output["chair_briefs"],
            "board_state": output["board_state"],
            "context_variables": output.get("context_variables", {}),
            "routing_decision": output.get("routing_decision", {}),
            "board_followup_rounds_used": output.get("board_followup_rounds_used", 0),
            "event_log": [item.to_dict() for item in monitor.events],
            "routing_log": [item.to_dict() for item in monitor.routing],
            "message_flow": [
                {
                    "round_id": item.round_id,
                    "stage": item.stage,
                    "sender": item.sender,
                    "receiver": item.receiver,
                    "full_content": item.full_content,
                }
                for item in monitor.events
            ],
            "activated_committees": output["activated_committees"],
            "non_activated_committees": [
                department["name"]
                for department in departments
                if department["name"] not in output["activated_committees"]
            ],
            "mode": "ag2_many_agent",
            "ag2_system": "hierarchical",
            "native_ag2_requested": use_native_ag2,
            "native_ag2_available": native_available(),
            "role_model_config": role_models,
            "baseline_source_commit": "01826c0",
            "node_pollution_enabled": False,
            "scheme_a": {
                "all_chairs_must_speak_once": bool(params.get("all_chairs_must_speak_once", True)),
                "all_activated_members_must_speak_once": bool(
                    params.get("all_activated_members_must_speak_once", True)
                ),
                "board_followup_max_rounds": int(params.get("board_followup_max_rounds", 0)),
                "internal_discussion_rounds_per_member": int(
                    params.get("internal_discussion_rounds_per_member", 1)
                ),
            },
        },
    )
    return CaseResult(
        case_type=case.case_type,
        case_url=case.case_url,
        case_name=case.case_name,
        stage=config.stage,
        presentation=presentation,
        most_likely_diagnosis=canonical.most_likely_diagnosis,
        differential_diagnoses=canonical.differential_diagnoses,
        recommended_tests=canonical.recommended_tests,
        areas_of_disagreement=canonical.areas_of_disagreement,
        total_cost=canonical.total_cost,
        metadata=canonical.metadata | {"canonical_result": canonical.to_dict()},
    )
