from openai import OpenAI
from app.core.config import settings
from app.prompts.system_prompt import get_system_prompt

from app.services.mock_service import (
    get_total_sales,
    get_sales_by_region,
    get_total_leads
)

client = OpenAI(api_key=settings.OPENAI_API_KEY)


# -----------------------------
# 1. AI INTENT DETECTION
# -----------------------------
def detect_intent_with_ai(role: str, query: str):
    prompt = f"""
You are an ERP intent classifier.

User role: {role}

Classify the user query into ONLY ONE intent:

AVAILABLE INTENTS:
- total_sales
- sales_by_region
- total_leads
- unknown

RULES:
- Return ONLY the intent name
- No explanation
- No extra text
- No punctuation

User Query: {query}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a strict ERP intent classification system."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    return response.choices[0].message.content.strip()


# -----------------------------
# 2. TOOL EXECUTION LAYER
# -----------------------------
def execute_tool(intent: str):
    if intent == "total_sales":
        return f"Total sales: {get_total_sales()}"

    elif intent == "sales_by_region":
        return get_sales_by_region()

    elif intent == "total_leads":
        return f"Total leads generated: {get_total_leads()}"

    return None


# -----------------------------
# 3. MAIN AI SERVICE FUNCTION
# -----------------------------
def generate_response(role: str, query: str):

    # STEP 1: AI decides intent
    intent = detect_intent_with_ai(role, query)

    # STEP 2: Execute ERP tool if applicable
    tool_result = execute_tool(intent)

    if tool_result is not None:
        return {
            "intent": intent,
            "response": tool_result
        }

    # STEP 3: fallback to general AI response
    system_prompt = get_system_prompt(role)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": query
            }
        ],
        temperature=0.3
    )

    return {
        "intent": "general",
        "response": response.choices[0].message.content
    }