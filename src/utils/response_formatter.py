def format_response(answer: str, citations: list, confidence: float):
    try:
        answer = answer.strip()

        if not answer:
            return {
                "answer": "I don't know",
                "citations": [],
                "confidence": 0.0
            }

        if citations:
            citation_text = "\n\nSources:\n"
            for c in citations:
                citation_text += f"[{c['id']}] {c['source']}\n"
            answer += citation_text

        if confidence >= 0.8:
            confidence_label = "High"
        elif confidence >= 0.5:
            confidence_label = "Medium"
        else:
            confidence_label = "Low"

        return {
            "answer": answer,
            "citations": citations,
            "confidence": confidence,
            "confidence_label": confidence_label
        }

    except Exception:
        return {
            "answer": "Error formatting response",
            "citations": [],
            "confidence": 0.0,
            "confidence_label": "Low"
        }
