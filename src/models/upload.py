from pydantic import BaseModel


class UploadResponse(BaseModel):
    status: str
    chunks: int
    filename: str
    type: str
