from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str | None = None
    role: str
    query: str


class ChatResponse(BaseModel):
    intent: str
    response: object