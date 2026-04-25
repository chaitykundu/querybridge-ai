import streamlit as st
import requests

# Your FastAPI endpoint
API_URL = "http://localhost:8004/chat"

st.set_page_config(page_title="AI Chatbot", layout="centered")

st.title("💬 AI Chatbot Tester")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "user_id" not in st.session_state:
    st.session_state.user_id = "001"  # fixed user for testing

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
user_input = st.chat_input("Ask something...")

if user_input:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    # Send request to FastAPI
    payload = {
        "user_id": st.session_state.user_id,
        "role": "user",
        "query": user_input
    }

    try:
        response = requests.post(API_URL, json=payload)
        data = response.json()

        bot_reply = data.get("response", "No response from server.")

    except Exception as e:
        bot_reply = f"Error connecting to API: {e}"

    # Show assistant message
    with st.chat_message("assistant"):
        st.markdown(bot_reply)

    # Save assistant response
    st.session_state.messages.append({"role": "assistant", "content": bot_reply})