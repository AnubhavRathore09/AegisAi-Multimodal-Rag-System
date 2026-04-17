def route_query(query: str):

    q = query.lower()

    if "image" in q or "photo" in q or "picture" in q:
        return "IMAGE"

    if len(q.split()) <= 2:
        return "LLM"

    if any(word in q for word in ["explain", "document", "pdf", "file", "context"]):
        return "RAG"

    return "RAG"
