import json
import time
from typing import Dict, Any

import streamlit as st
from openai import OpenAI

from utils import (
    API_KEY,
    CUSTOM_CSS,
    FOOTER_HTML,
    MAIN_HEADER_HTML,
    MODEL_NAME,
    RESPONSE_API_ENDPOINT,
    SELECTED_MODEL,
    X_PEBBLO_USER,
    display_chat_message,
    get_welcome_html,
    load_prompts_from_yaml,
    test_api_connection,
)

# Page configuration
st.set_page_config(
    page_title="Finance Ops Chatbot",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Load language-based prompts from YAML (prompts.yaml)
LANGUAGE_PROMPTS = load_prompts_from_yaml()
DEFAULT_LANGUAGE = "en" if "en" in LANGUAGE_PROMPTS else (list(LANGUAGE_PROMPTS.keys())[0] if LANGUAGE_PROMPTS else "en")

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "selected_model" not in st.session_state:
    st.session_state.selected_model = SELECTED_MODEL
if "api_key" not in st.session_state:
    st.session_state.api_key = API_KEY
if "model_name" not in st.session_state:
    st.session_state.model_name = MODEL_NAME
if "prompt_language" not in st.session_state:
    st.session_state.prompt_language = DEFAULT_LANGUAGE


def call_open_ai(message: str, model: str, api_key: str = "") -> Dict[str, Any]:
    """Call OpenAI-compatible completions API (non-streaming) for Demo."""
    try:
        default_headers = {"X-PEBBLO-USER": X_PEBBLO_USER} if X_PEBBLO_USER else None
        client = OpenAI(
            base_url=RESPONSE_API_ENDPOINT,
            api_key=api_key,
            default_headers=default_headers,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": message}],
        )
        return {"status": "success", "data": response.choices[0].message.content}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}


# Main header
st.markdown(MAIN_HEADER_HTML, unsafe_allow_html=True)

# Sidebar configuration
with st.sidebar:
    st.subheader("🔗 API Status")
    if st.button("Test API Connection"):
        with st.spinner("Testing connection..."):
            result = test_api_connection()
            if result["status"] == "success":
                st.success(result["message"])
            else:
                st.error(result["message"])

    st.subheader("💬 Chat Management")
    if st.button("Clear Chat History"):
        st.session_state.chat_history = []
        if "user_input" in st.session_state:
            st.session_state.user_input = ""
        st.rerun()

    st.subheader("🌐 Prompt language")
    lang_options = list(LANGUAGE_PROMPTS.keys()) if LANGUAGE_PROMPTS else [DEFAULT_LANGUAGE]
    try:
        lang_index = lang_options.index(st.session_state.prompt_language)
    except ValueError:
        lang_index = 0
        st.session_state.prompt_language = lang_options[0] if lang_options else DEFAULT_LANGUAGE
    selected_lang = st.selectbox(
        "Language",
        options=lang_options,
        index=lang_index,
        key="prompt_language_select",
        label_visibility="collapsed",
    )
    st.session_state.prompt_language = selected_lang

    st.subheader("📝 Sample Prompts")
    prompts_for_lang = LANGUAGE_PROMPTS.get(selected_lang, [])
    for i, prompt in enumerate(prompts_for_lang):
        label = prompt.get("label", "")
        copyable_text = prompt.get("copyable", "")
        st.markdown('<span class="prompt-use-btn-marker"></span>', unsafe_allow_html=True)
        col_cap, col_btn = st.columns([3, 1])
        with col_cap:
            st.caption(f"**{label}**")
        with col_btn:
            if st.button("→", key=f"use_prompt_{selected_lang}_{i}", help="Copy to message box"):
                st.session_state.user_input = copyable_text
                st.rerun()
        st.text_area(
            "Prompt",
            value=copyable_text,
            height=min(120, 60 + copyable_text.count("\n") * 24),
            disabled=True,
            key=f"sidebar_prompt_{selected_lang}_{i}",
            label_visibility="collapsed",
        )

    if st.session_state.chat_history:
        chat_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": st.session_state.selected_model,
            "conversation": st.session_state.chat_history,
        }
        st.download_button(
            label="📥 Export Chat",
            data=json.dumps(chat_data, indent=2),
            file_name=f"finance_chatbot_{time.strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )

    st.subheader("📊 Statistics")
    st.metric("Messages", len(st.session_state.chat_history))
    st.markdown(
        f"""
<div style="font-size:0.8rem;">
    Current Model: <br><span style="font-size:1.2rem;"><b>{st.session_state.model_name}</b></span>
</div>
""",
        unsafe_allow_html=True,
    )

# Welcome message
st.markdown(get_welcome_html(), unsafe_allow_html=True)

# Main chat interface
st.subheader("💬 Chat Interface")

for message in st.session_state.chat_history:
    display_chat_message(
        role=message["role"],
        content=message["content"],
        model=message.get("model", ""),
        timestamp=message.get("timestamp", ""),
    )

user_input = st.text_area(
    "Type your message here:",
    height=100,
    placeholder="Ask me anything! I'm powered by SafeInfer LLM API.",
    key="user_input",
)

col1, col2 = st.columns([1, 4])
with col1:
    send_button = st.button("🚀 Send", type="primary")

if send_button and user_input.strip():
    st.session_state.chat_history.append({
        "role": "user",
        "content": user_input,
        "timestamp": time.strftime("%H:%M:%S"),
    })
    display_chat_message("user", user_input)

    with st.spinner("🤖 AI is thinking..."):
        model = SELECTED_MODEL
        result = call_open_ai(
            message=user_input,
            model=model,
            api_key=st.session_state.api_key,
        )

    if result["status"] == "success":
        response = result["data"]
        print(f"RESPONSE: {response}")
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response,
            "model": st.session_state.selected_model,
            "timestamp": time.strftime("%H:%M:%S"),
        })
        display_chat_message(
            "assistant",
            response,
            st.session_state.selected_model,
            time.strftime("%H:%M:%S"),
        )
        if isinstance(result.get("data"), dict) and "response" in result["data"]:
            response_data = result["data"]["response"]
            if isinstance(response_data, dict) and "classification" in response_data:
                with st.expander("🔍 Response Analysis"):
                    st.json(response_data["classification"])
    else:
        error_message = f"❌ Error: {result['message']}"
        st.error(error_message)
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": error_message,
            "timestamp": time.strftime("%H:%M:%S"),
        })

    st.rerun()

# Footer
st.markdown("---")
st.markdown(FOOTER_HTML, unsafe_allow_html=True)
