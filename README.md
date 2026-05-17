# QueryBridge AI

uvicorn app.main:app --reload --port 8004
streamlit run streamlit_app.py

**QueryBridge AI** is an intelligent ERP query system that converts natural language into SQL queries and executes them across enterprise SQL Server databases using an AI-powered, schema-aware routing engine. For this I have used 300 sage database of 2023.

It supports both:
- Backend API (modular Python service architecture)
- Streamlit UI for real-time interaction

---

## Key Features

- 🧠 Natural Language to SQL generation using LLMs
- 🗂️ Schema-aware understanding (column role inference)
- 🔀 Intelligent ERP database routing
- 🧾 SQL validation and safety checks
- 📅 Temporal reasoning (e.g., "last year", "2023 sales")
- 🔐 Secure SQL Server execution using pyodbc
- 🖥️ Streamlit-based interactive UI
- 📦 Fully modular and scalable architecture

---

## System Architecture

User Query (Natural Language)
↓
API Layer (routes.py)
↓
AI Service (ai_service.py)
↓
Query Router (query_router.py)
↓
Schema Service (schema_service.py)
↓
SQL Validator (sql_validator.py)
↓
SQL Service (sql_service.py)
↓
Database Layer (repository.py)
↓
SQL Server Execution
↓
Response (API / Streamlit UI)

---

## Project Structure

QUERYBRIDGE-AI/
│
├── app/
│ ├── api/
│ │ └── routes.py # API endpoints
│ │
│ ├── core/
│ │ ├── config.py # Configuration & environment
│ │ └── security.py # Security utilities
│ │
│ ├── db/
│ │ ├── connection.py # SQL Server connection setup
│ │ └── repository.py # Query execution layer
│ │
│ ├── models/ # Data models (future expansion)
│ │
│ ├── prompts/
│ │ └── system_prompt.py # LLM system prompts
│ │
│ ├── schemas/
│ │ └── chat_schema.py # Request/response schemas
│ │
│ ├── services/
│ │ ├── ai_service.py # LLM-based SQL generation
│ │ ├── query_router.py # ERP database routing logic
│ │ ├── schema_service.py # Schema inference engine
│ │ ├── sql_service.py # SQL execution service
│ │ └── sql_validator.py # SQL safety validation
│ │
│ ├── main.py # Backend entry point
│
├── upload/ # File upload directory (optional)
├── streamlit_app.py # Streamlit frontend UI
├── .env # Environment variables
├── requirements.txt # Dependencies
├── .gitignore
└── README.md


## ⚙️ Installation

### 1. Clone the repository
```bash
git clone https://github.com/your-username/querybridge-ai.git
cd querybridge-ai

2. Create virtual environment

python -m venv env
env\Scripts\activate   # Windows
source env/bin/activate # Linux/Mac

3. Install dependencies

pip install -r requirements.txt

4. Environment Variables
Create a .env file in the root directory:

OPENAI_API_KEY=your_openai_api_key

DB_SERVER= ...
DB_NAME=SAMINC
DB_USER=pyuser
DB_PASSWORD=your_password

