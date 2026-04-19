from fastapi import APIRouter
from app.schemas.chat_schema import ChatRequest, ChatResponse
from app.services.ai_service import generate_response

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    ai_response = generate_response(request.role, request.query)
    
    return ChatResponse(response=ai_response)