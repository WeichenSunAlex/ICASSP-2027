from __future__ import annotations

from typing import Dict, List, Tuple


def route_one_to_one(sender: str, receiver: str, payload: Dict) -> Tuple[str, str, Dict]:
    return sender, receiver, payload


def route_many_to_one(senders: List[str], receiver: str, payloads: List[Dict]) -> List[Tuple[str, str, Dict]]:
    return [(sender, receiver, payload) for sender, payload in zip(senders, payloads)]


def route_one_to_many_sequential(sender: str, receivers: List[str], payload: Dict) -> List[Tuple[str, str, Dict]]:
    return [(sender, receiver, dict(payload)) for receiver in receivers]


def route_context_dependent(
    sender: str,
    candidates: List[str],
    context: Dict,
    default_receiver: str,
) -> Tuple[str, str, Dict]:
    activated = context.get("activated_committees", [])
    for candidate in candidates:
        if candidate in activated:
            return sender, candidate, {"context": context}
    return sender, default_receiver, {"context": context}

