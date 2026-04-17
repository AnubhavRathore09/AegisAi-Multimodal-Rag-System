from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentPlan:
    route: str
    steps: list[str] = field(default_factory=list)
    use_memory: bool = False
    use_retrieval: bool = False
    use_multimodal: bool = False
    notes: list[str] = field(default_factory=list)


class QueryAgent:
    def build_plan(self, route: str, history_available: bool, has_attachments: bool, has_images: bool) -> AgentPlan:
        plan = AgentPlan(route=route)
        if route == "memory" and history_available:
            plan.use_memory = True
            plan.steps.extend(["read_memory", "answer"])
        elif route in {"rag", "multimodal", "search"}:
            plan.use_retrieval = True
            plan.steps.append("retrieve")
            if has_attachments or has_images or route == "multimodal":
                plan.use_multimodal = True
                plan.steps.append("extract_multimodal")
            if history_available:
                plan.use_memory = True
                plan.steps.append("read_memory")
            plan.steps.extend(["reason", "answer"])
        else:
            if history_available:
                plan.notes.append("memory available but not required")
            plan.steps.extend(["answer"])
        return plan

    def debug_payload(self, plan: AgentPlan) -> dict[str, Any]:
        return {
            "route": plan.route,
            "steps": list(plan.steps),
            "use_memory": plan.use_memory,
            "use_retrieval": plan.use_retrieval,
            "use_multimodal": plan.use_multimodal,
            "notes": list(plan.notes),
        }


query_agent = QueryAgent()
