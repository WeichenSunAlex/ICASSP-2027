from __future__ import annotations


class CommitteeMember:
    def __init__(self, committee_name: str, role_prompt: str, idx: int):
        self.committee_name = committee_name
        self.role_prompt = role_prompt
        self.name = f"{committee_name}::member_{idx}"

    def speak(self, presentation: str) -> str:
        return (
            f"{self.name}: role='{self.role_prompt}'. Evidence-focused screening only. "
            "Use concrete disease names only when clearly justified; otherwise provide syndrome/category direction. "
            "Do not use placeholders like hypothesis A/B or candidate X. "
            f"Case snippet: '{presentation[:80]}...'"
        )
