from openai import OpenAI
from app.core.config import settings
from app.prompts.system_prompt import get_system_prompt

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def generate_response(role: str, query: str):
    system_prompt = get_system_prompt(role)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        temperature=0.3
    )

    return response.choices[0].message.content