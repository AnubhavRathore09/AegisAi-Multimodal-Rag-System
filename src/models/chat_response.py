from typing import List, Optional
from pydantic import BaseModel


class ChatResponse(BaseModel):
    response: str
    chat_id: str
    sources: List[str] = []
    route: Optional[str] = None
