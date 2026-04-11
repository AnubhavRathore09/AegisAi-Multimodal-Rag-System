from __future__ import annotations

from app.services.llm_router import RouteDecision, llm_router


class QueryRouter:
    async def route(self, request, history_count: int = 0) -> RouteDecision:
        return await llm_router.classify(request, history_count)

    def heuristic_route(self, request, history_count: int = 0) -> RouteDecision:
        return llm_router.heuristic_route(request, history_count)


query_router = QueryRouter()

