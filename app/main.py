from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="ERP AI Chatbot")

app.include_router(router)