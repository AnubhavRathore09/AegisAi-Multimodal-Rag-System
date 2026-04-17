from groq import Groq
from langchain_groq import ChatGroq
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)

llm = ChatGroq(
    api_key=settings.GROQ_API_KEY,
    model=settings.GROQ_MODEL,
    temperature=settings.LLM_TEMPERATURE,
)

_client = Groq(api_key=settings.GROQ_API_KEY)

SYSTEM_PROMPT = """You are a friendly, helpful and polite AI assistant.

Rules:
- Always respond in a natural, human-like tone
- Be helpful and clear
- If unsure, say something helpful instead of "I don't know"
- Keep answers conversational and engaging
"""

def build_rag_prompt(query: str, context: str):
    return f"""
You are a helpful AI assistant.

Context:
{context}

User Question:
{query}

Answer clearly in a friendly tone.
"""

def get_llm_response(prompt: str, history: list[dict] | None = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        for m in history[-settings.MAX_HISTORY_MESSAGES:]:
            messages.append({
                "role": m["role"],
                "content": m["content"]
            })

    messages.append({
        "role": "user",
        "content": prompt
    })

    try:
        res = _client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=2048
        )

        answer = res.choices[0].message.content.strip()
        logger.info("LLM response generated")
        return answer

    except Exception as e:
        logger.error("LLM error: %s", str(e))
        return "Something went wrong. Please try again."

def analyze_image(base64_data: str, mime_type: str, question: str) -> str:
    try:
        res = _client.chat.completions.create(
            model=settings.VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_data}"
                            }
                        },
                        {
                            "type": "text",
                            "text": question or "Describe this image in a helpful way"
                        }
                    ]
                }
            ],
            max_tokens=1024
        )

        return res.choices[0].message.content.strip()

    except Exception as e:
        logger.warning("Vision error: %s", str(e))
        return "I couldn't analyze the image properly, but you can try again."

def get_streaming_response(prompt: str, history: list[dict] | None = None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        for m in history[-settings.MAX_HISTORY_MESSAGES:]:
            messages.append({
                "role": m["role"],
                "content": m["content"]
            })

    messages.append({
        "role": "user",
        "content": prompt
    })

    try:
        stream = _client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=2048,
            stream=True
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    except Exception as e:
        logger.error("Streaming error: %s", str(e))
        yield "Something went wrong while streaming response."
