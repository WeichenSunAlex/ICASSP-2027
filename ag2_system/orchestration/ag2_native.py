from __future__ import annotations

from dataclasses import dataclass
import inspect
import json
import os
import re
from typing import Any, Dict, List, Optional


@dataclass
class NativeAG2Handles:
    ConversableAgent: Any
    RoundRobinPattern: Any
    DefaultPattern: Any
    AutoPattern: Any
    Handoffs: Any
    OnCondition: Any
    OnContextCondition: Any
    FunctionTarget: Any
    StringLLMCondition: Any
    StringContextCondition: Any
    initiate_group_chat: Any


def try_import_native_ag2() -> Optional[NativeAG2Handles]:
    try:
        from autogen import ConversableAgent
        try:
            from autogen.agentchat import initiate_group_chat
        except Exception:
            from autogen.agentchat.group import initiate_group_chat
        from autogen.agentchat.group.handoffs import Handoffs
        from autogen.agentchat.group.patterns import AutoPattern, DefaultPattern, RoundRobinPattern
        from autogen.agentchat.group.context_condition import StringContextCondition
        from autogen.agentchat.group.llm_condition import StringLLMCondition
        try:
            from autogen import OnCondition, OnContextCondition
        except Exception:
            from autogen.agentchat.group import OnCondition, OnContextCondition
        try:
            from autogen import FunctionTarget
        except Exception:
            try:
                from autogen.agentchat.group import FunctionTarget
            except Exception:
                FunctionTarget = None
    except Exception:
        return None

    return NativeAG2Handles(
        ConversableAgent=ConversableAgent,
        RoundRobinPattern=RoundRobinPattern,
        DefaultPattern=DefaultPattern,
        AutoPattern=AutoPattern,
        Handoffs=Handoffs,
        OnCondition=OnCondition,
        OnContextCondition=OnContextCondition,
        FunctionTarget=FunctionTarget,
        StringLLMCondition=StringLLMCondition,
        StringContextCondition=StringContextCondition,
        initiate_group_chat=initiate_group_chat,
    )


def native_available() -> bool:
    return try_import_native_ag2() is not None


def build_llm_config(model_name: str, model_provider: str) -> Dict[str, Any]:
    """Build one AG2 config entry without putting secrets in project files."""
    provider = str(model_provider or "openai").strip().lower()
    entry: Dict[str, Any] = {"model": str(model_name), "api_type": provider}
    provider_prefix = provider.upper().replace("-", "_")
    api_key = (
        os.environ.get("AG2_API_KEY")
        or os.environ.get(f"{provider_prefix}_API_KEY")
        or (os.environ.get("OPENAI_API_KEY") if provider == "openai" else None)
    )
    base_url = (
        os.environ.get("AG2_BASE_URL")
        or os.environ.get(f"{provider_prefix}_BASE_URL")
        or (os.environ.get("OPENAI_BASE_URL") if provider == "openai" else None)
    )
    if api_key:
        entry["api_key"] = api_key
    if base_url:
        entry["base_url"] = base_url
    return {"config_list": [entry]}


def _safe_initiate_group_chat(initiate_fn, **kwargs):
    sig = inspect.signature(initiate_fn)
    supported = set(sig.parameters.keys())
    call_kwargs = {k: v for k, v in kwargs.items() if k in supported}
    return initiate_fn(**call_kwargs)


def committee_round_robin_max_rounds(member_count: int, rounds_per_member: int) -> int:
    member_count = max(1, int(member_count))
    rounds_per_member = max(1, int(rounds_per_member))
    # AG2 counts the initial user task message as one chat round. In native
    # RoundRobinPattern, the user proxy can also receive a handoff between full
    # member cycles, even when it has no content; reserve those separator rounds
    # so the final member in later cycles is not truncated.
    return 1 + (member_count * rounds_per_member) + (rounds_per_member - 1)


def _log_native_committee_history(
    *,
    monitoring: Any,
    department_name: str,
    history: List[Dict[str, Any]],
    stage: str,
    message_type: str,
    speaker_roles: Dict[str, str] | None = None,
) -> None:
    if monitoring is None:
        return
    speaker_roles = speaker_roles or {}
    chair_name = f"{department_name}::chair"
    committee_name = f"{department_name}::committee"
    for msg in history:
        sender = str(msg.get("name", "")).strip()
        content = str(msg.get("content", "")).strip()
        if not sender or not content:
            continue
        if "::member_" in sender:
            receiver = committee_name
        elif sender == chair_name:
            receiver = committee_name
        elif sender == f"{department_name}::chair_summarizer":
            receiver = committee_name
        elif sender in {"committee_user", "committee_user2", "committee_summary_user"}:
            receiver = committee_name
        else:
            receiver = committee_name
        speaker_role = str(speaker_roles.get(sender, "")).strip()
        monitoring.log_event(
            stage=stage,
            sender=sender,
            receiver=receiver,
            committee_name=department_name,
            message_type=message_type,
            short_content_summary=content[:160],
            context_snapshot={
                "committee": department_name,
                "native_ag2": True,
                "internal_committee_discussion": True,
                "speaker_role": speaker_role,
            },
            full_content=content,
        )


def _log_native_direct_chat_history(
    *,
    monitoring: Any,
    history: List[Dict[str, Any]],
    stage: str,
    message_type: str,
    user_agent_name: str,
    assistant_agent_name: str,
    committee_name: str | None = None,
    context_snapshot: Dict[str, Any] | None = None,
) -> None:
    if monitoring is None:
        return
    context_snapshot = dict(context_snapshot or {})
    for msg in history:
        sender = str(msg.get("name", "")).strip()
        content = str(msg.get("content", "")).strip()
        if not sender or not content:
            continue
        if sender == user_agent_name:
            receiver = assistant_agent_name
        elif sender == assistant_agent_name:
            receiver = user_agent_name
        else:
            receiver = assistant_agent_name
        monitoring.log_event(
            stage=stage,
            sender=sender,
            receiver=receiver,
            committee_name=committee_name or "",
            message_type=message_type,
            short_content_summary=content[:160],
            context_snapshot=context_snapshot
            | {
                "native_ag2": True,
                "raw_ag2_chat": True,
                "user_agent": user_agent_name,
                "assistant_agent": assistant_agent_name,
            },
            full_content=content,
        )


def _extract_json_object(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        out = json.loads(match.group(0))
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}

# def _extract_json_object(text: str) -> Dict[str, Any]:
#     """
#     Robustly extract the most relevant JSON object from LLM output.
#
#     Strategy:
#     1. Try parsing the whole text directly.
#     2. Try extracting fenced ```json ... ``` blocks.
#     3. Scan for every '{' position and use JSONDecoder.raw_decode()
#        to find valid JSON objects.
#     4. Return the last valid dict found, since LLMs often place the
#        final structured answer near the end.
#
#     Returns:
#         dict if a valid JSON object is found, else {}
#     """
#     if not text:
#         return {}
#
#     text = text.strip()
#     decoder = json.JSONDecoder()
#
#     # 1) Direct parse
#     try:
#         out = json.loads(text)
#         return out if isinstance(out, dict) else {}
#     except Exception:
#         pass
#
#     # 2) Parse fenced code blocks first
#     fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
#     for block in reversed(fenced_blocks):
#         block = block.strip()
#         try:
#             out = json.loads(block)
#             if isinstance(out, dict):
#                 return out
#         except Exception:
#             pass
#
#     # 3) Scan for valid JSON objects starting at each "{"
#     candidates = []
#     for match in re.finditer(r"\{", text):
#         start = match.start()
#         try:
#             obj, end = decoder.raw_decode(text[start:])
#             if isinstance(obj, dict):
#                 candidates.append(obj)
#         except Exception:
#             continue
#
#     if candidates:
#         return candidates[-1]
#
#     return {}


_PLACEHOLDER_PATTERNS = [
    re.compile(r"\bhypothesis\s*[a-z0-9]+\b", flags=re.IGNORECASE),
    re.compile(r"\bpossible\s+disease\b", flags=re.IGNORECASE),
    re.compile(r"\bcandidate\s*[a-z0-9]+\b", flags=re.IGNORECASE),
]


def _is_placeholder_label(value: str, department: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    dep = str(department or "").strip().lower()
    low = text.lower()
    if dep and low in {dep, dep.replace("_", " ")}:
        return True
    if dep and f"{dep} hypothesis" in low:
        return True
    return any(p.search(text) for p in _PLACEHOLDER_PATTERNS)


def _normalize_concrete_hypotheses(hypotheses: Any, department: str) -> List[str]:
    if isinstance(hypotheses, list):
        items = [str(x).strip() for x in hypotheses if str(x).strip()]
    elif hypotheses is None:
        items = []
    else:
        text = str(hypotheses).strip()
        items = [text] if text else []
    cleaned = [x for x in items if not _is_placeholder_label(x, department)]
    return cleaned[:2]


def _normalize_committee_summary_payload(
    *,
    department: str,
    parsed: Dict[str, Any],
) -> Dict[str, Any]:
    top = _normalize_concrete_hypotheses(parsed.get("top_hypotheses", []), department)
    supporting = parsed.get("supporting_evidence", [])
    missing = parsed.get("missing_information", [])
    tests = parsed.get("recommended_tests", [])
    minority = parsed.get("minority_opinions", [])
    if not isinstance(supporting, list):
        supporting = [str(supporting)] if str(supporting).strip() else []
    if not isinstance(missing, list):
        missing = [str(missing)] if str(missing).strip() else []
    if not isinstance(tests, list):
        tests = [str(tests)] if str(tests).strip() else []
    if not isinstance(minority, list):
        minority = [str(minority)] if str(minority).strip() else []
    try:
        conf = float(parsed.get("confidence", 0.6))
    except Exception:
        conf = 0.6
    conf = max(0.0, min(1.0, conf))
    return {
        "committee_name": department,
        "top_hypotheses": [str(x) for x in top][:2],
        "supporting_evidence": [str(x) for x in supporting if str(x).strip()][:3],
        "missing_information": [str(x) for x in missing if str(x).strip()][:3],
        "recommended_tests": [str(x) for x in tests if str(x).strip()][:3],
        "confidence": conf,
        "minority_opinions": [str(x) for x in minority if str(x).strip()][:3],
        "activation_reason": str(
            parsed.get("activation_reason", f"Activated by routing policy for {department}.")
        ),
        "internal_transcript_hidden": True,
    }


def _normalize_chair_brief_payload(
    *,
    department: str,
    speaker: str,
    parsed: Dict[str, Any],
    raw_content: str,
) -> Dict[str, Any]:
    score_raw = str(parsed.get("relevance_score", "50"))
    score = int(score_raw) if score_raw.isdigit() else 50
    score = max(0, min(100, score))
    rec = str(parsed.get("activation_recommendation", "yes")).lower() in {"yes", "true", "1"}
    suspected = parsed.get("suspected_conditions", [])
    directions = parsed.get("diagnostic_directions", [])
    if not isinstance(suspected, list):
        suspected = [str(suspected)]
    if not isinstance(directions, list):
        directions = [str(directions)]
    suspected_clean = [str(x).strip() for x in suspected if str(x).strip()]
    suspected_clean = [x for x in suspected_clean if not _is_placeholder_label(x, department)]
    suspected_clean = suspected_clean[:2]
    directions_clean = [str(x).strip() for x in directions if str(x).strip()][:2]
    if not suspected_clean and not directions_clean:
        directions_clean = ["department-relevant disorder"]
    conf = parsed.get("confidence", 0.5)
    try:
        conf = float(conf)
    except Exception:
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    out = {
        "department": department,
        "speaker": speaker,
        "relevance_score": score,
        "activation_recommendation": "yes" if rec else "no",
        "key_evidence": parsed.get("key_evidence", []),
        "counter_evidence": parsed.get("counter_evidence", []),
        "missing_information": parsed.get("missing_information", []),
        "why_not_me": str(parsed.get("why_not_me", "")),
        "uncertainty": str(parsed.get("uncertainty", "")),
        "suspected_conditions": suspected_clean,
        "diagnostic_directions": directions_clean,
        "confidence": conf,
        "recommend_activate": rec,
    }
    out["content"] = json.dumps(
        {
            "department": out["department"],
            "relevance_score": out["relevance_score"],
            "activation_recommendation": out["activation_recommendation"],
            "key_evidence": out["key_evidence"],
            "counter_evidence": out["counter_evidence"],
            "missing_information": out["missing_information"],
            "why_not_me": out["why_not_me"],
            "uncertainty": out["uncertainty"],
            "suspected_conditions": out["suspected_conditions"],
            "diagnostic_directions": out["diagnostic_directions"],
            "confidence": out["confidence"],
        },
        ensure_ascii=True,
    )
    if not raw_content.strip():
        return out
    return out


def run_chair_briefing_round_robin_native(
    *,
    departments: List[Dict[str, Any]],
    presentation: str,
    model_name: str,
    model_provider: str,
    routing_mode: str = "deterministic",
    monitoring: Any = None,
) -> List[Dict[str, Any]]:
    del routing_mode
    ag2 = try_import_native_ag2()
    if ag2 is None:
        raise RuntimeError("AG2 native APIs unavailable in current environment.")

    llm_config = build_llm_config(model_name, model_provider)
    out = []
    for dep in departments:
        dep_system_prompt = str(dep.get("system_prompt", "")).strip()
        chair_constraints = (
            f"You are the chair of {dep['name']}.\n\n"
            "You are in the pre-routing screening stage of a hierarchical medical many-agent system.\n\n"
            f"Your task is NOT to perform a full diagnosis.\nYour task is to briefly assess whether this case should activate the {dep['name']} committee.\n\n"
            "Important rules:\n"
            "- Prefer concrete disease names when supported by the case.\n"
            "- If the evidence is not sufficient for a concrete disease name, do NOT invent placeholders such as \"hypothesis A\" or \"hypothesis B\".\n"
            "- If a concrete disease name is not justified, return an empty suspected_conditions list and use diagnostic_directions to describe relevant disease category directions.\n"
            "- Keep the output short, structured, and evidence-grounded.\n"
            "- Do not provide treatment or management advice.\n\n"
            "Return JSON only with fields:\n"
            "department,relevance_score,activation_recommendation,key_evidence,counter_evidence,"
            "missing_information,why_not_me,uncertainty,suspected_conditions,diagnostic_directions,confidence"
        )
        chair_system_message = (
            f"{dep_system_prompt}\n\n{chair_constraints}" if dep_system_prompt else chair_constraints
        )
        chair = ag2.ConversableAgent(
            name=f"{dep['name']}::chair",
            system_message=chair_system_message,
            llm_config=llm_config,
            human_input_mode="NEVER",
        )
        user = ag2.ConversableAgent(name=f"user::{dep['name']}", human_input_mode="NEVER")
        pattern = ag2.DefaultPattern(initial_agent=chair, agents=[chair], user_agent=user)
        msg = (
            f"Case presentation:\n{presentation}\n\n"
            f"Evaluate this case from the perspective of {dep['name']}.\n"
            f"Department role:\n{dep.get('chair_role_prompt', dep['name'])}\n\n"
            "Requirements:\n"
            "- relevance_score: integer 0-100\n"
            "- activation_recommendation: \"yes\" or \"no\"\n"
            "- key_evidence: up to 3 short items\n"
            "- counter_evidence: up to 2 short items\n"
            "- missing_information: up to 3 short items\n"
            "- why_not_me: one short sentence\n"
            "- uncertainty: one short sentence\n"
            "- suspected_conditions: up to 2 concrete disease names, only if justified\n"
            "- diagnostic_directions: up to 2 syndrome/category directions when concrete disease names are not justified\n"
            "- confidence: float between 0 and 1\n\n"
            "Do not use placeholders like hypothesis A/B, possible disease 1, candidate X.\n"
            "If you cannot justify a concrete disease, suspected_conditions must be [].\n"
            "Return JSON only."
        )
        result, _context, _last = _safe_initiate_group_chat(
            ag2.initiate_group_chat,
            pattern=pattern,
            messages=msg,
            max_rounds=2,
        )
        chat_history = getattr(result, "chat_history", [])
        _log_native_direct_chat_history(
            monitoring=monitoring,
            history=chat_history,
            stage="chair_briefing_raw_chat",
            message_type="chair_briefing_raw_chat",
            user_agent_name=f"user::{dep['name']}",
            assistant_agent_name=f"{dep['name']}::chair",
            committee_name=dep["name"],
            context_snapshot={"department": dep["name"]},
        )
        last_content = ""
        for m in reversed(chat_history):
            if str(m.get("name") or "") == f"{dep['name']}::chair":
                last_content = str(m.get("content") or "")
                break
        out.append({"department": dep["name"], "speaker": f"{dep['name']}::chair", "content": last_content})
    enriched = []
    for brief in out:
        parsed = _extract_json_object(str(brief.get("content", "")))
        enriched.append(
            _normalize_chair_brief_payload(
                department=str(brief["department"]),
                speaker=str(brief["speaker"]),
                parsed=parsed,
                raw_content=str(brief.get("content", "")),
            )
        )
    return enriched


def run_router_llm_decision_native(
    *,
    router_input: Dict[str, Any],
    model_name: str,
    model_provider: str,
    context_variables: Optional[Dict[str, Any]] = None,
    monitoring: Any = None,
) -> Dict[str, Any]:
    ag2 = try_import_native_ag2()
    if ag2 is None:
        raise RuntimeError("AG2 native APIs unavailable in current environment.")
    llm_config = build_llm_config(model_name, model_provider)
    router = ag2.ConversableAgent(
        name="TriageRouterLLM",
        system_message=(
            "You are a medical triage router. Read the structured router_input object and decide activation. "
            "Use case facts and chair screening briefs jointly. "
            "Balance supporting and counter-evidence, and prioritize committees that can resolve critical missing information. "
            "Return JSON only with keys: "
            "selected_committees(list), rejected_committees(list of {name,reason}), "
            "routing_confidence(0-1), rationale(string). "
            "selected_committees must be from candidates only and count must be within [min_k,max_k]."
        ),
        llm_config=llm_config,
        human_input_mode="NEVER",
    )
    user = ag2.ConversableAgent(name="router_user", human_input_mode="NEVER")
    message = json.dumps(router_input, ensure_ascii=True)
    pattern = ag2.DefaultPattern(initial_agent=router, agents=[router], user_agent=user)
    result, _context, _last = _safe_initiate_group_chat(
        ag2.initiate_group_chat,
        pattern=pattern,
        messages=message,
        max_rounds=2,
        context_variables=context_variables or {},
    )
    history = getattr(result, "chat_history", [])
    _log_native_direct_chat_history(
        monitoring=monitoring,
        history=history,
        stage="router_llm_raw_chat",
        message_type="router_llm_raw_chat",
        user_agent_name="router_user",
        assistant_agent_name="TriageRouterLLM",
        committee_name=None,
        context_snapshot={"router": True},
    )
    last_content = ""
    for msg in reversed(history):
        if str(msg.get("name", "")) == "TriageRouterLLM":
            last_content = str(msg.get("content", ""))
            break
    parsed = _extract_json_object(last_content)
    return parsed if isinstance(parsed, dict) else {}


def run_committee_nested_chat_native(
    *,
    department: Dict[str, Any],
    presentation: str,
    chair_model_name: str,
    chair_model_provider: str,
    member_model_name: str,
    member_model_provider: str,
    max_rounds: int,
    routing_mode: str = "deterministic",
    internal_discussion_rounds_per_member: int = 1,
    monitoring: Any = None,
) -> Dict[str, Any]:
    from autogen.agentchat.group import TerminateTarget
    ag2 = try_import_native_ag2()
    if ag2 is None:
        raise RuntimeError("AG2 native APIs unavailable in current environment.")

    member_llm_config = build_llm_config(member_model_name, member_model_provider)
    chair_llm_config = build_llm_config(chair_model_name, chair_model_provider)

    dep_name = department["name"]
    dep_system_prompt = str(department.get("system_prompt", "")).strip()
    roles = list(department.get("member_role_prompts", []) or ["general member"])

    def _member_system_message(role: str) -> str:
        role = str(role)
        member_prompt = (
            f"You are a committee member with role: {role} in the {dep_name} committee.\n"
            "This is an internal committee discussion, not the final diagnosis.\n"
            "Your job is to contribute one short, evidence-grounded diagnostic point from your role perspective.\n"
            "You should reason like a clinician in a multidisciplinary discussion: you may propose a diagnostic direction, "
            "support or refine a prior point, point out a limitation, or respectfully challenge earlier reasoning when the case evidence justifies it.\n"
            "Do not challenge for its own sake. Any agreement, disagreement, or revision must be grounded in the case facts.\n"
            "Prefer specific disease names only when the case evidence supports them.\n"
            "If specific disease names are not justified, use syndrome-level or category-level diagnostic directions instead.\n"
            "Do not invent fake disease labels or placeholders such as hypothesis A, hypothesis B, possible disease 1, or candidate X.\n"
            "Do not provide treatment, management, or prognosis.\n"
            "Keep your reply concise.\n"
            "Your reply should usually contain:\n"
            "1. one evidence-grounded observation,\n"
            "2. one suspected condition, diagnostic direction, refinement, or challenge,\n"
            "3. one uncertainty, limitation, or missing piece of evidence if relevant."
        )
        return f"{dep_system_prompt}\n\n{member_prompt}" if dep_system_prompt else member_prompt

    members = [
        ag2.ConversableAgent(
            name=f"{dep_name}::member_{idx + 1}",
            system_message=_member_system_message(role),
            llm_config=member_llm_config,
            human_input_mode="NEVER",
        )
        for idx, role in enumerate(roles)
    ]
    speaker_roles = {
        f"{dep_name}::member_{idx + 1}": str(role)
        for idx, role in enumerate(roles)
    }
    speaker_roles[f"{dep_name}::chair"] = "committee chair"
    speaker_roles[f"{dep_name}::chair_summarizer"] = "committee chair summarizer"
    speaker_roles["committee_user"] = "committee user prompt"
    speaker_roles["committee_user2"] = "committee follow-up user prompt"
    speaker_roles["committee_summary_user"] = "committee summary user prompt"

    chair = ag2.ConversableAgent(
        name=f"{dep_name}::chair",
        system_message=(
            f"You are the chair of the {dep_name} committee.\n"
            "Your role is to guide brief internal follow-up discussion and clarify disagreements.\n"
            "You are not the final judge.\n"
            "Prefer specific disease names only when supported by the case and committee discussion.\n"
            "If specific disease names are not justified, use syndrome-level or category-level directions instead.\n"
            "Do not use placeholders such as hypothesis A/B, candidate X, or possible disease 1.\n"
            "Keep your replies concise, evidence-grounded, and focused on diagnostic reasoning only."
        ),
        llm_config=chair_llm_config,
        human_input_mode="NEVER",
    )

    user = ag2.ConversableAgent(name="committee_user", human_input_mode="NEVER")
    discussion_rounds = max(1, int(internal_discussion_rounds_per_member))
    first_round_max_rounds = committee_round_robin_max_rounds(len(members), discussion_rounds)

    # Stage 1: every activated committee member speaks for the configured number of rounds.
    rr = ag2.RoundRobinPattern(
        initial_agent=members[0],
        agents=members,
        user_agent=user,
    )
    rr_result, context, last = _safe_initiate_group_chat(
        ag2.initiate_group_chat,
        pattern=rr,
        messages=(
            "Committee internal round-robin discussion.\n"
    f"Case presentation:\n{presentation}\n\n"
    f"Each member must speak {discussion_rounds} time(s) in round-robin order.\n"
    "In later turns, consider the prior committee messages and respond naturally as in a clinical discussion. "
    "You may add new evidence, agree with and strengthen a prior point, refine a diagnostic direction, "
    "point out uncertainty, ask for distinguishing data, or challenge/revise earlier reasoning when appropriate. "
    "Avoid repeating the same point without adding value.\n\n"
    "If you have spoken earlier, treat your prior messages as your own stated position. "
    "Do not repeat them verbatim; instead update, qualify, or add a new point based on the intervening discussion.\n\n"
    "All members should reason from their assigned role perspective, but they are not limited to only supporting prior opinions. "
    "Evidence-grounded disagreement is allowed and encouraged when it improves diagnostic reasoning.\n"
    "Each reply must be concise and grounded in the case presentation or prior committee messages.\n"
    "When proposing a specific disease, make sure the case evidence reasonably supports it. "
    "If a specific disease name is not justified, use a syndrome-level or category-level diagnostic direction instead.\n"
    "Do not use placeholders such as hypothesis A/B, possible disease 1, candidate X, or department-name-only labels.\n"
    "Do not invent unsupported diagnoses.\n"
    "Do not provide treatment or management advice."
        ),
        max_rounds=first_round_max_rounds,
    )

    # Stage 2: optional follow-up rounds.
    # Temporarily disabled: this second group chat needs a clearer continuation design
    # before it should run in production. In particular, it should explicitly carry
    # the first-round transcript into the follow-up prompt and avoid treating the
    # user proxy as a discussion participant.
    follow_history = []
    if False and max_rounds > first_round_max_rounds:
        extra_rounds = max_rounds - first_round_max_rounds

        # DefaultPattern without explicit handoffs can terminate early.
        # Use RoundRobin for deterministic follow-up, AutoPattern for dynamic follow-up.
        if routing_mode == "deterministic":
            follow = ag2.RoundRobinPattern(
                initial_agent=chair,
                agents=[chair] + members,
                user_agent=ag2.ConversableAgent(
                    name="committee_user2",
                    human_input_mode="NEVER",
                ),
            )
        else:
            follow = ag2.AutoPattern(
                initial_agent=last or chair,
                agents=members + [chair],
                user_agent=ag2.ConversableAgent(
                    name="committee_user2",
                    human_input_mode="NEVER",
                ),
            )

        follow_result, context, last = _safe_initiate_group_chat(
            ag2.initiate_group_chat,
            pattern=follow,
            messages=(
                "Committee follow-up round.\n"
                f"Case presentation:\n{presentation}\n\n"
                "Goal:\n"
                "- clarify disagreements,\n"
                "- refine the strongest disease candidates or diagnostic directions,\n"
                "- identify the most useful distinguishing tests,\n"
                "- highlight unresolved uncertainty.\n"
                "Do not use placeholders such as hypothesis A/B.\n"
                "Do not give treatment or management advice."
            ),
            max_rounds=extra_rounds,
            context_variables=context,
        )
        follow_history = getattr(follow_result, "chat_history", []) or []

    rr_history = getattr(rr_result, "chat_history", []) or []
    _log_native_committee_history(
        monitoring=monitoring,
        department_name=dep_name,
        history=rr_history,
        stage="committee_internal_round_robin",
        message_type="member_statement",
        speaker_roles=speaker_roles,
    )
    _log_native_committee_history(
        monitoring=monitoring,
        department_name=dep_name,
        history=follow_history,
        stage="committee_internal_followup",
        message_type="followup_statement",
        speaker_roles=speaker_roles,
    )

    # Build transcript digest for summarization
    transcript = []
    for msg in rr_history + follow_history:
        name = str(msg.get("name", "")).strip()
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        if "::member_" in name or name.endswith("::chair"):
            transcript.append(
                {
                    "speaker": name,
                    "content": content[:600],
                }
            )

    summary_agent = ag2.ConversableAgent(
        name=f"{dep_name}::chair_summarizer",
        system_message=(
            f"You are the chair summarizer of the {dep_name} committee.\n"
            "Your job is to summarize the internal committee discussion into a structured committee summary.\n"
            "Use only the case information and the committee transcript digest provided.\n"
            "Do not invent evidence that was not mentioned.\n"
            "You must return at least one top_hypothesis whenever the committee discussion contains any meaningful diagnostic signal.\n"
            "Prefer specific disease names when supported by the discussion and case evidence.\n"
            "If a specific disease name is not sufficiently justified, use the strongest syndrome-level or category-level diagnostic direction instead.\n"
            "Do not use placeholders such as hypothesis A, hypothesis B, possible disease 1, candidate X, or specialty-name-only labels.\n"
            "Every top_hypothesis must be supported by at least one item in supporting_evidence.\n"
            "recommended_tests must be diagnostically useful tests that help distinguish among the leading hypotheses.\n"
            "supporting_evidence must contain short evidence points derived from the case or committee discussion, not generic filler text.\n"
            "minority_opinions should include evidence-based alternative views only if they were raised in the discussion.\n"
            "confidence must be a numeric value between 0 and 1.\n"
            "Return JSON only with exactly these keys:\n"
            "top_hypotheses, supporting_evidence, missing_information, recommended_tests, confidence, minority_opinions, activation_reason."
        ),
        llm_config=chair_llm_config,
        human_input_mode="NEVER",
    )

    summary_agent.handoffs.set_after_work(TerminateTarget())

    sum_user = ag2.ConversableAgent(
        name="committee_summary_user",
        human_input_mode="NEVER",
    )

    sum_pattern = ag2.RoundRobinPattern(
        initial_agent=summary_agent,
        agents=[summary_agent],
        user_agent=sum_user,
        group_after_work=TerminateTarget(),
    )

    sum_msg = (
        f"Committee: {dep_name}\n"
        f"Case presentation:\n{presentation}\n\n"
        f"Committee transcript digest:\n{json.dumps(transcript, ensure_ascii=True)}\n\n"
        "Task:\n"
        "Summarize this committee discussion into the required committee summary JSON.\n"
        "Rules:\n"
        "- return at least one top_hypothesis if the transcript contains any meaningful diagnostic signal\n"
        "- prefer specific disease names when justified by the discussion and case evidence\n"
        "- if a specific disease name is not justified, return the strongest syndrome-level or category-level diagnostic direction instead\n"
        "- do not use placeholders such as hypothesis A/B, candidate X, or possible disease 1\n"
        "- every top_hypothesis must be supported by at least one supporting_evidence item\n"
        "- supporting_evidence must be concrete and non-generic\n"
        "- recommended_tests must be diagnostically useful and specific\n"
        "- minority_opinions should only be included if genuine disagreement appeared in the transcript\n"
        "- activation_reason should explain why this committee was relevant to this case\n"
        "Return JSON only."
    )

    sum_result, _sum_ctx, _sum_last = _safe_initiate_group_chat(
        ag2.initiate_group_chat,
        pattern=sum_pattern,
        messages=sum_msg,
        max_rounds=2,
        context_variables=context,
    )

    sum_history = getattr(sum_result, "chat_history", []) or []
    sum_content = ""
    for msg in reversed(sum_history):
        if str(msg.get("name", "")).strip() == f"{dep_name}::chair_summarizer":
            sum_content = str(msg.get("content", "")).strip()
            break
    _log_native_committee_history(
        monitoring=monitoring,
        department_name=dep_name,
        history=sum_history,
        stage="committee_internal_summary",
        message_type="committee_internal_summary",
        speaker_roles=speaker_roles,
    )

    # Retry once if the summary agent returned empty content.
    if not sum_content:
        sum_result2, _sum_ctx2, _sum_last2 = _safe_initiate_group_chat(
            ag2.initiate_group_chat,
            pattern=sum_pattern,
            messages=sum_msg + "\nReturn valid JSON only.",
            max_rounds=2,
            context_variables=context,
        )
        sum_history2 = getattr(sum_result2, "chat_history", []) or []
        for msg in reversed(sum_history2):
            if str(msg.get("name", "")).strip() == f"{dep_name}::chair_summarizer":
                sum_content = str(msg.get("content", "")).strip()
                break
        _log_native_committee_history(
            monitoring=monitoring,
            department_name=dep_name,
            history=sum_history2,
            stage="committee_internal_summary_retry",
            message_type="committee_internal_summary",
            speaker_roles=speaker_roles,
        )

    parsed = _extract_json_object(sum_content)
    if os.environ.get("DEBUG_SUMMARY_AGENT", "").strip().lower() in {"1", "true", "yes"}:
        print(f"[DEBUG_SUMMARY_AGENT] committee={dep_name}")
        print(f"[DEBUG_SUMMARY_AGENT] raw={sum_content}")
        print(
            "[DEBUG_SUMMARY_AGENT] parsed_ok="
            f"{bool(parsed)} keys={list(parsed.keys()) if isinstance(parsed, dict) else []}"
        )

    normalized = _normalize_committee_summary_payload(
        department=dep_name,
        parsed=parsed,
    )

    # Fallbacks
    if not normalized["top_hypotheses"]:
        default_dirs = department.get("default_diagnostic_directions", []) or []
        fallback_direction = None
        for item in default_dirs:
            item = str(item).strip()
            if item:
                fallback_direction = item
                break
        if not fallback_direction:
            fallback_direction = f"{dep_name.lower()}-relevant diagnostic direction"
        normalized["top_hypotheses"] = [fallback_direction]

    if not normalized["supporting_evidence"]:
        normalized["supporting_evidence"] = [
            "Committee discussion identified at least one department-relevant diagnostic signal, but the extracted evidence was underspecified."
        ]

    if not normalized["missing_information"]:
        normalized["missing_information"] = [
            f"{dep_name} targeted confirmatory data are still missing."
        ]

    if not normalized["recommended_tests"]:
        normalized["recommended_tests"] = []

    if not normalized["minority_opinions"]:
        normalized["minority_opinions"] = []

    return normalized


def run_final_judge_decision_native(
    *,
    case_id: str,
    stage: str,
    presentation: str,
    board_summary: Dict[str, Any],
    committee_summaries: List[Dict[str, Any]],
    conflict_followup: Any,
    model_name: str,
    model_provider: str,
    context_variables: Optional[Dict[str, Any]] = None,
    monitoring: Any = None,
) -> Dict[str, Any]:
    ag2 = try_import_native_ag2()
    if ag2 is None:
        raise RuntimeError("AG2 native APIs unavailable in current environment.")
    llm_config = build_llm_config(model_name, model_provider)
    judge = ag2.ConversableAgent(
        name="FinalJudgeLLM",
        system_message=(
            "You are the FinalJudge in a hierarchical medical many-agent diagnostic system."
            "You are a constrained adjudicator.\n"
            "Your job is to adjudicate among committee-supported hypotheses, not to generate an entirely new diagnostic pathway unsupported by the board or committee summaries.\n\n"
            "Your role is to make the final diagnostic decision for one case based only on:\n"
            "1. the case presentation,\n"
            "2. the Board summary,\n"
            "3. the structured summaries from activated committees,\n"
            "4. any explicit conflict follow-up notes if provided.\n\n"
            "You are NOT a free-form independent diagnostician.\n"
            "Do NOT ignore the committee and board outputs and restart the diagnosis from scratch.\n"
            "Do NOT use raw internal committee transcripts unless they are explicitly provided.\n"
            "Do NOT provide treatment, management, prognosis, or counseling.\n"
            "Focus only on diagnosis and diagnostically useful tests.\n\n"
            "Output format:\nReturn JSON only.\n"
            "Do not include markdown fences.\n"
            "Do not include any text outside the JSON."
        ),
        llm_config=llm_config,
        human_input_mode="NEVER",
    )
    user = ag2.ConversableAgent(name="final_judge_user", human_input_mode="NEVER")
    payload = {
        "case_id": case_id,
        "stage": stage,
        "presentation": presentation,
        "board_summary_json": board_summary,
        "committee_summaries_json": committee_summaries,
        "conflict_followup_json_or_null": conflict_followup,
    }
    message = (
        f"Case ID: {case_id}\n"
        f"Stage: {stage}\n\n"
        f"Case presentation:\n{presentation}\n\n"
        f"Board summary:\n{json.dumps(board_summary, ensure_ascii=True)}\n\n"
        f"Activated committee summaries:\n{json.dumps(committee_summaries, ensure_ascii=True)}\n\n"
        f"Conflict follow-up notes:\n{json.dumps(conflict_followup, ensure_ascii=True)}\n\n"
        "Task:\nUsing only the information above, produce the final diagnostic decision.\n\n"
        "Requirements:\n"
        "- Choose exactly one most_likely_diagnosis.\n"
        "- Provide 3 to 6 differential_diagnoses when possible.\n"
        "- If stage == \"initial\", provide targeted recommended_tests that would help distinguish among the leading hypotheses.\n"
        "- If stage == \"follow_up\", recommended_tests should usually be [] unless one final clarifying diagnostic test is strongly justified.\n"
        "- areas_of_disagreement should summarize genuine unresolved conflicts across committees, not repeat agreed points.\n"
        "- decision_rationale should be brief, evidence-based, and reflect the board + committee summaries rather than a fresh independent diagnosis.\n"
        "- used_committees should include only committees that materially influenced the final decision.\n"
        "- overall_confidence should be a float between 0 and 1.\n\n"
        "Return JSON only."
    )
    pattern = ag2.DefaultPattern(initial_agent=judge, agents=[judge], user_agent=user)
    result, _context, _last = _safe_initiate_group_chat(
        ag2.initiate_group_chat,
        pattern=pattern,
        messages=message,
        max_rounds=2,
        context_variables=(context_variables or {}) | {"final_judge_payload": payload},
    )
    history = getattr(result, "chat_history", [])
    _log_native_direct_chat_history(
        monitoring=monitoring,
        history=history,
        stage="final_judge_raw_chat",
        message_type="final_judge_raw_chat",
        user_agent_name="final_judge_user",
        assistant_agent_name="FinalJudgeLLM",
        committee_name=None,
        context_snapshot={"final_judge": True, "case_id": case_id, "case_stage": stage},
    )
    last_content = ""
    for msg in reversed(history):
        if str(msg.get("name", "")) == "FinalJudgeLLM":
            last_content = str(msg.get("content", ""))
            break
    parsed = _extract_json_object(last_content)
    return parsed if isinstance(parsed, dict) else {}
