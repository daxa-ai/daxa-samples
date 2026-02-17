"""Test environment: open via URL path /test. API type, stream, and model are selectable."""
import json
import time

import streamlit as st

from utils import (
    API_KEY,
    CUSTOM_CSS,
    FOOTER_HTML,
    MAIN_HEADER_HTML,
    SELECTED_MODEL,
    USER_EMAIL,
    USER_TEAM,
    call_llm,
    display_chat_message,
    get_available_models,
    get_welcome_html,
    test_api_connection,
)


@st.cache_data(ttl=300)
def fetch_models() -> tuple:
    """Fetch available models (cached 5 min). Returns (model_names, default_model_name)."""
    try:
        return get_available_models()
    except Exception:
        return [], ""


st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

if "test_chat_history" not in st.session_state:
    st.session_state.test_chat_history = []

# Sidebar: Test Settings (dropdowns) at top, then API Status, Chat Management, Statistics
with st.sidebar:
    st.subheader("⚙️ Test Settings")
    api_type = st.selectbox("API Type", ["completions", "responses"], key="api_type")
    stream_option = st.selectbox("Stream", [True, False], key="stream_option")
    try:
        model_names, default_model = fetch_models()
    except Exception:
        model_names = []
        default_model = ""
    if not model_names:
        st.warning("Could not load models. Check API and env.")
        selected_model = st.text_input("Model (fallback)", value="", key="model_fallback")
    else:
        default_idx = (
            model_names.index(default_model) if default_model in model_names else 0
        )
        selected_model = st.selectbox(
            "Model",
            model_names,
            index=default_idx,
            key="model_select",
        )
    if st.button("Refresh models", key="refresh_models"):
        fetch_models.clear()
        st.rerun()
    st.markdown("---")

    st.subheader("🔗 API Status")
    if st.button("Test API Connection", key="test_api_btn"):
        with st.spinner("Testing connection..."):
            result = test_api_connection()
            if result["status"] == "success":
                st.success(result["message"])
            else:
                st.error(result["message"])

    st.subheader("💬 Chat Management")
    if st.button("Clear Chat History", key="test_clear"):
        st.session_state.test_chat_history = []
        st.rerun()

    if st.session_state.test_chat_history:
        chat_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": selected_model,
            "api_type": api_type,
            "stream": stream_option,
            "conversation": st.session_state.test_chat_history,
        }
        st.download_button(
            label="📥 Export Chat",
            data=json.dumps(chat_data, indent=2),
            file_name=f"finance_test_{time.strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            key="test_export",
        )

    st.subheader("📊 Statistics")
    st.metric("Messages", len(st.session_state.test_chat_history))
    st.markdown(
        f"""
<div style="font-size:0.8rem;">
    API: <b>{api_type}</b> | Stream: <b>{stream_option}</b><br>
    Model: <b>{selected_model if model_names else (selected_model or '(none)')}</b>
</div>
""",
        unsafe_allow_html=True,
    )

# Main: header and chat only
st.markdown(MAIN_HEADER_HTML, unsafe_allow_html=True)
st.markdown(get_welcome_html(USER_EMAIL, USER_TEAM), unsafe_allow_html=True)
st.subheader("💬 Chat Interface (Test)")

for message in st.session_state.test_chat_history:
    display_chat_message(
        role=message["role"],
        content=message["content"],
        model=message.get("model", ""),
        timestamp=message.get("timestamp", ""),
    )

user_input = st.text_area(
    "Type your message here:",
    height=100,
    placeholder="Ask me anything (Test mode).",
    key="test_user_input",
)

col1, col2 = st.columns([1, 4])
with col1:
    send_button = st.button("🚀 Send", type="primary", key="test_send")

if send_button and user_input.strip():
    model = (
        selected_model
        if model_names
        else st.session_state.get("model_fallback", "")
    )
    if not model:
        st.error("Select or enter a model first.")
    else:
        st.session_state.test_chat_history.append({
            "role": "user",
            "content": user_input,
            "timestamp": time.strftime("%H:%M:%S"),
        })
        display_chat_message("user", user_input)

        with st.spinner("🤖 AI is thinking..."):
            result = call_llm(
                api_type=api_type,
                model=model,
                stream=stream_option,
                message=user_input,
                api_key=API_KEY,
            )

        if result["status"] == "success":
            if stream_option and result.get("stream_gen"):
                stream_placeholder = st.empty()
                full_content = stream_placeholder.write_stream(result["stream_gen"])
                st.session_state.test_chat_history.append({
                    "role": "assistant",
                    "content": full_content,
                    "model": model,
                    "timestamp": time.strftime("%H:%M:%S"),
                })
            else:
                response = result.get("data", "")
                st.session_state.test_chat_history.append({
                    "role": "assistant",
                    "content": response,
                    "model": model,
                    "timestamp": time.strftime("%H:%M:%S"),
                })
                display_chat_message(
                    "assistant",
                    response,
                    model,
                    time.strftime("%H:%M:%S"),
                )
        else:
            error_message = f"❌ Error: {result.get('message', 'Unknown error')}"
            st.error(error_message)
            st.session_state.test_chat_history.append({
                "role": "assistant",
                "content": error_message,
                "timestamp": time.strftime("%H:%M:%S"),
            })
        st.rerun()

st.markdown("---")
st.markdown(FOOTER_HTML, unsafe_allow_html=True)
