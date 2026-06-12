import json
import time
from typing import Generator

import httpx
import streamlit as st
from openai import OpenAI

_attempt_counter = {"count": 0}


def _on_request(request):
    _attempt_counter["count"] += 1

from utils import (
    API_KEY,
    CUSTOM_CSS,
    FOOTER_HTML,
    MAIN_HEADER_HTML,
    MODEL,
    RESPONSE_API_ENDPOINT,
    X_PEBBLO_USER,
    X_PEBBLO_USER_GROUPS,
    display_chat_message,
    get_available_models,
    get_welcome_html,
    load_prompts_from_yaml,
    merge_env_model_into_model_list,
    test_api_connection,
)


@st.cache_data(ttl=300)
def fetch_models():
    """Fetch models from GET .../v1/models (cached 5 min). Returns (names, default_id)."""
    return get_available_models()

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
# Model: env MODEL is default; user can change via dropdown or manual entry
if "selected_model" not in st.session_state:
    st.session_state.selected_model = MODEL or ""
if "api_key" not in st.session_state:
    st.session_state.api_key = API_KEY
if "model_name" not in st.session_state:
    st.session_state.model_name = ""
if "prompt_language" not in st.session_state:
    st.session_state.prompt_language = DEFAULT_LANGUAGE


def stream_open_ai(message: str, model: str, api_key: str = ""):
    """Yield tokens from OpenAI-compatible completions API (streaming) for Demo."""
    default_headers = {}
    if X_PEBBLO_USER:
        default_headers["X-PEBBLO-USER"] = X_PEBBLO_USER
    if X_PEBBLO_USER_GROUPS:
        default_headers["X-PEBBLO-USER-GROUPS"] = X_PEBBLO_USER_GROUPS
    default_headers = default_headers or None

    http_client = httpx.Client(
        timeout=300,
        transport=httpx.HTTPTransport(retries=0),
        event_hooks={"request": [_on_request]},
    )
    client = OpenAI(
        base_url=RESPONSE_API_ENDPOINT,
        api_key=api_key,
        default_headers=default_headers,
        http_client=http_client,
        max_retries=0,
    )
    start_time = time.time()
    first_token_time = None
    with client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": message}],
        stream=True,
    ) as stream:
        for chunk in stream:
            if first_token_time is None:
                first_token_time = time.time() - start_time
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    # Store the time to first token in session state
    st.session_state.time_to_first_token = first_token_time


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

    st.subheader("🤖 Model")
    model_names, default_model = fetch_models()
    model_names = merge_env_model_into_model_list(model_names, MODEL)
    if model_names:
        try:
            current = (
                st.session_state.get("selected_model") or MODEL or default_model
            )
            if current not in model_names:
                current = default_model or model_names[0]
            idx = model_names.index(current) if current in model_names else 0
        except (ValueError, TypeError):
            idx = 0
        selected_model = st.selectbox(
            "LLM Model",
            model_names,
            index=idx,
            key="sidebar_model_select",
            label_visibility="collapsed",
        )
        st.session_state.selected_model = selected_model
        st.session_state.model_name = selected_model
    else:
        st.warning("Could not load models from API. Enter a model ID below.")
        fallback = st.session_state.get("selected_model") or MODEL or ""
        manual = st.text_input(
            "Model ID",
            value=fallback,
            key="sidebar_model_manual",
            placeholder="Enter model id",
        )
        if manual.strip():
            st.session_state.selected_model = manual.strip()
            st.session_state.model_name = manual.strip()
    if st.button("Refresh models", key="refresh_models_main"):
        fetch_models.clear()
        st.rerun()

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
        time_taken=message.get("time_taken"),
        time_to_first_token=message.get("time_to_first_token"),
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

    model = (st.session_state.get("selected_model") or "").strip()
    if not model:
        st.error("No model selected. Load models from API or enter a model ID.")
        st.stop()

    try:
        start_time = time.time()
        with st.chat_message("assistant"):
            response = st.write_stream(
                stream_open_ai(
                    message=user_input,
                    model=model,
                    api_key=st.session_state.api_key,
                )
            )
        end_time = time.time()
        time_taken = end_time - start_time
        time_to_first_token = getattr(st.session_state, 'time_to_first_token', None)
        print(f"RESPONSE: {response}")
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response,
            "model": st.session_state.selected_model,
            "timestamp": time.strftime("%H:%M:%S"),
            "time_taken": time_taken,
            "time_to_first_token": time_to_first_token,
        })
    except Exception as e:
        error_message = f"❌ Error: {str(e)}"
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
