from fastapi import APIRouter
from app.schemas.chat_schema import ChatRequest, ChatResponse
from app.services.ai_service import generate_response

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):

    result = generate_response(request.role, request.query)

    return ChatResponse(
        intent=result["intent"],
        response=result["response"]
    )