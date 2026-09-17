from __future__ import annotations

from typing import Dict, List

from ag2_system.agents.committee_members import CommitteeMember
from ag2_system.orchestration.ag2_native import native_available, run_committee_nested_chat_native
from ag2_system.schemas.committee_summary import CommitteeSummary


def run_activated_committee(
    department: Dict,
    presentation: str,
    *,
    model_name: str,
    model_provider: str,
    member_model_name: str,
    member_model_provider: str,
    use_native_ag2: bool,
    monitoring,
    enforce_all_members_first_round: bool,
    max_rounds: int,
    internal_discussion_rounds_per_member: int = 1,
) -> CommitteeSummary:
    if use_native_ag2 and native_available():
        summary = run_committee_nested_chat_native(
            department=department,
            presentation=presentation,
            chair_model_name=model_name,
            chair_model_provider=model_provider,
            member_model_name=member_model_name,
            member_model_provider=member_model_provider,
            max_rounds=max_rounds,
            internal_discussion_rounds_per_member=internal_discussion_rounds_per_member,
            monitoring=monitoring,
        )
        return CommitteeSummary(**{k: v for k, v in summary.items() if k in CommitteeSummary.__dataclass_fields__})

    members = [
        CommitteeMember(department["name"], role_prompt, idx + 1)
        for idx, role_prompt in enumerate(department.get("member_role_prompts", []))
    ]
    if not members:
        members = [CommitteeMember(department["name"], "general member", 1)]

    first_round_messages: List[str] = []
    if enforce_all_members_first_round:
        discussion_rounds = max(1, int(internal_discussion_rounds_per_member))
        for round_idx in range(discussion_rounds):
            for member in members:
                content = member.speak(presentation)
                first_round_messages.append(content)
                monitoring.log_event(
                    stage="committee_internal_round_robin",
                    sender=member.name,
                    receiver=f"{department['name']}::committee",
                    committee_name=department["name"],
                    message_type="member_statement",
                    short_content_summary=content[:160],
                    context_snapshot={
                        "committee": department["name"],
                        "discussion_round": round_idx + 1,
                        "rounds_per_member": discussion_rounds,
                        "speaker_role": member.role_prompt,
                    },
                    full_content=content,
                )

    for _ in range(max(0, max_rounds - 1)):
        # Deterministic placeholder for later AG2 DefaultPattern/AutoPattern rounds.
        pass

    configured_directions = department.get("default_diagnostic_directions", [])
    if isinstance(configured_directions, list) and configured_directions:
        directions = [str(x) for x in configured_directions if str(x).strip()][:2]
    else:
        directions = ["department-relevant disorder"]

    return CommitteeSummary(
        committee_name=department["name"],
        top_hypotheses=[],
        supporting_evidence=first_round_messages[:3] + [f"Diagnostic directions considered: {', '.join(directions)}"],
        missing_information=["additional targeted evidence needed"],
        recommended_tests=[f"{department['name']} targeted confirmatory test"],
        confidence=0.65 if len(members) < 3 else 0.78,
        minority_opinions=["alternative etiology remains possible"],
        activation_reason=f"Activated by routing policy for {department['name']}.",
    )
