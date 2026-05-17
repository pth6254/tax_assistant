from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    name: str = "사용자"
