from src.llms.groq_client import get_llm_response
from src.core.logger import get_logger

logger = get_logger(__name__)

def rewrite_query(query: str, history: list):
    try:
        prompt = f"""
Fix spelling mistakes in this query.

Query: {query}

Only return corrected query.

Examples:
narendar mudi -> narendra modi
elon mask -> elon musk
"""

        corrected = get_llm_response(prompt)

        if not corrected:
            return query

        corrected = corrected.strip()

        if len(corrected) < 3:
            return query

        return corrected

    except Exception as e:
        logger.error(f"Rewrite error: {str(e)}")
        return query
