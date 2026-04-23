import streamlit as st
import requests

# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
API_URL = "http://localhost:8000/api/chat"

st.set_page_config(
    page_title="QueryBridge AI Assistant",
    page_icon="🤖",
    layout="wide"
)

# -------------------------------------------------------
# CUSTOM CSS
# -------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
        background-color: #0f1117;
        color: #e0e0e0;
    }

    .main { background-color: #0f1117; }

    .stApp { background-color: #0f1117; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }

    /* Role badge */
    .role-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        font-family: 'IBM Plex Mono', monospace;
        letter-spacing: 1px;
        text-transform: uppercase;
        margin-bottom: 16px;
    }
    .role-sales_manager { background: #1a3a2a; color: #3fb950; border: 1px solid #3fb950; }
    .role-secretary     { background: #1a2a3a; color: #58a6ff; border: 1px solid #58a6ff; }

    /* Chat messages */
    .msg-user {
        background: #1c2128;
        border: 1px solid #30363d;
        border-radius: 12px 12px 0 12px;
        padding: 12px 16px;
        margin: 8px 0;
        margin-left: 20%;
        font-size: 14px;
    }
    .msg-bot {
        background: #161b22;
        border: 1px solid #21262d;
        border-radius: 12px 12px 12px 0;
        padding: 12px 16px;
        margin: 8px 0;
        margin-right: 20%;
        font-size: 14px;
    }
    .msg-label {
        font-size: 10px;
        font-family: 'IBM Plex Mono', monospace;
        color: #8b949e;
        margin-bottom: 4px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .msg-type {
        font-size: 10px;
        font-family: 'IBM Plex Mono', monospace;
        color: #3fb950;
        float: right;
    }
    .msg-type-llm { color: #f0883e; }
    .msg-type-denied { color: #f85149; }

    /* SQL block */
    .sql-block {
        background: #0d1117;
        border: 1px solid #30363d;
        border-left: 3px solid #58a6ff;
        border-radius: 6px;
        padding: 10px 14px;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 12px;
        color: #79c0ff;
        margin-top: 8px;
        white-space: pre-wrap;
    }

    /* Input */
    .stTextInput > div > div > input {
        background-color: #161b22 !important;
        border: 1px solid #30363d !important;
        color: #e0e0e0 !important;
        border-radius: 8px !important;
        font-family: 'IBM Plex Sans', sans-serif !important;
    }

    /* Button */
    .stButton > button {
        background-color: #238636 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        width: 100% !important;
    }
    .stButton > button:hover {
        background-color: #2ea043 !important;
    }

    /* Select box */
    .stSelectbox > div > div {
        background-color: #161b22 !important;
        border: 1px solid #30363d !important;
        color: #e0e0e0 !important;
    }

    /* Header */
    .chat-header {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 22px;
        font-weight: 600;
        color: #e0e0e0;
        margin-bottom: 4px;
    }
    .chat-subheader {
        font-size: 13px;
        color: #8b949e;
        margin-bottom: 24px;
    }

    /* Divider */
    hr { border-color: #21262d; }
</style>
""", unsafe_allow_html=True)


# -------------------------------------------------------
# SIDEBAR — Settings
# -------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Session Config")
    st.markdown("---")

    user_id = st.text_input("User ID", value="user_001", placeholder="e.g. user_001")

    role = st.selectbox(
        "Role",
        options=["sales_manager", "secretary"],
        format_func=lambda x: "📊 Sales Manager" if x == "sales_manager" else "📋 Secretary"
    )

    show_sql = st.checkbox("Show generated SQL", value=True)
    show_raw = st.checkbox("Show raw data", value=False)

    st.markdown("---")

    # Role badge
    st.markdown(
        f'<div class="role-badge role-{role}">{role.replace("_", " ")}</div>',
        unsafe_allow_html=True
    )

    if role == "sales_manager":
        st.caption("✅ Full access to all tables")
    else:
        st.caption("✅ Access: APDSH only")

    st.markdown("---")

    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("**Debug Endpoints**")
    st.code("GET  /api/debug/schema", language="bash")
    st.code("POST /api/debug/sql", language="bash")


# -------------------------------------------------------
# MAIN CHAT
# -------------------------------------------------------
st.markdown('<div class="chat-header">🤖 SAMINC AI Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="chat-subheader">Ask anything about your ERP data</div>', unsafe_allow_html=True)

# Init chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f"""
        <div class="msg-user">
            <div class="msg-label">You</div>
            {msg["content"]}
        </div>
        """, unsafe_allow_html=True)
    else:
        type_class = f"msg-type-{msg.get('type', 'sql')}"
        type_label = msg.get("type", "sql").upper()
        st.markdown(f"""
        <div class="msg-bot">
            <div class="msg-label">AI Assistant <span class="msg-type {type_class}">[{type_label}]</span></div>
            {msg["content"]}
        </div>
        """, unsafe_allow_html=True)

        if show_sql and msg.get("sql"):
            st.markdown(f'<div class="sql-block">{msg["sql"]}</div>', unsafe_allow_html=True)

        if show_raw and msg.get("data"):
            with st.expander("Raw data"):
                st.json(msg["data"])


# -------------------------------------------------------
# INPUT
# -------------------------------------------------------
st.markdown("---")
col1, col2 = st.columns([5, 1])

with col1:
    query = st.text_input(
        "query",
        placeholder="Ask about your data... e.g. 'Show me all records from last month'",
        label_visibility="collapsed",
        key="query_input"
    )

with col2:
    send = st.button("Send →")

# -------------------------------------------------------
# SEND MESSAGE
# -------------------------------------------------------
if send and query.strip():
    # Add user message
    st.session_state.messages.append({
        "role": "user",
        "content": query
    })

    # Call API
    with st.spinner("Thinking..."):
        try:
            res = requests.post(API_URL, json={
                "user_id": user_id,
                "role": role,
                "query": query
            }, timeout=30)

            if res.status_code == 200:
                data = res.json()
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": data.get("response", "No response."),
                    "type": data.get("type", "llm"),
                    "sql": data.get("sql"),
                    "data": data.get("data"),
                })
            else:
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"❌ API error {res.status_code}: {res.text}",
                    "type": "error"
                })

        except requests.exceptions.ConnectionError:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "❌ Cannot connect to API. Make sure your FastAPI server is running on `localhost:8000`.",
                "type": "error"
            })
        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"❌ Unexpected error: {str(e)}",
                "type": "error"
            })

    st.rerun()