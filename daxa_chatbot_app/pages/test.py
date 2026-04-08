"""Test environment: open via URL path /test.
Supports Safe Infer (API type, stream, model) and Safe MCP (MCP URL, model, user context).
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    API_KEY,
    CUSTOM_CSS,
    FOOTER_HTML,
    MAIN_HEADER_HTML,
    MODEL,
    USER_EMAIL,
    USER_TEAM,
    call_llm,
    display_chat_message,
    get_available_models,
    get_welcome_html,
    merge_env_model_into_model_list,
    test_api_connection,
)
from mcp_utils import (
    ATLASSIAN_MCP_URL,
    CUSTOMER_BILLING_MCP_URL,
    ATLASSIAN_API_KEY,
    CUSTOMER_BILLING_API_KEY,
    build_mcp_servers,
    stream_query_steps as mcp_stream_query_steps,
    _pebblo_mcp_headers,
)
from oauth_utils import (
    handle_oauth_callback,
    render_oauth_connect_button,
    get_token as get_oauth_token,
)


@st.cache_data(ttl=300)
def fetch_models(pebblo_user: str = None, pebblo_user_groups: str = None) -> tuple:
    try:
        return get_available_models(
            pebblo_user=pebblo_user or None,
            pebblo_user_groups=pebblo_user_groups or None,
        )
    except Exception:
        return [], ""


# ---------------------------------------------------------------------------
# Safe MCP helpers
# ---------------------------------------------------------------------------

async def _run_mcp_streaming(user_input, mcp_servers, pebblo_user, pebblo_user_groups):
    current_response = ""
    tools_used = []
    intermediate_steps = []
    steps_container = st.empty()
    tools_displayed = False

    async for step_message in mcp_stream_query_steps(
        user_input,
        mcp_servers=mcp_servers,
        pebblo_user=pebblo_user or None,
        pebblo_user_groups=pebblo_user_groups or None,
    ):
        if step_message.startswith("Final answer"):
            current_response = step_message.replace("Final answer: ", "")
            if intermediate_steps:
                steps_container.markdown(
                    "<br>".join([f"<small>{s}</small>" for s in intermediate_steps]),
                    unsafe_allow_html=True,
                )
            if tools_used and not tools_displayed:
                st.markdown("<hr style='margin-top:5px; margin-bottom:5px;'>", unsafe_allow_html=True)
                st.subheader("Tools Used:")
                for tool in tools_used:
                    st.markdown(
                        f"• <span style='color: #3DC667; background-color: #1e1e1e; "
                        f"padding: 2px 6px; border-radius: 4px;'>{tool}</span>",
                        unsafe_allow_html=True,
                    )
                st.markdown("<hr style='margin-top:5px; margin-bottom:5px;'>", unsafe_allow_html=True)
                tools_displayed = True
            st.subheader("Response:")
            st.markdown(current_response)
        elif step_message.startswith("Tools used"):
            tools_str = step_message.replace("Tools used: ", "")
            tools_used = (
                [t.strip() for t in tools_str.split(",")]
                if tools_str != "No tools were used for this query"
                else []
            )
        elif step_message.startswith("Error"):
            st.error("❌ " + step_message)
            current_response = step_message
        else:
            intermediate_steps.append(step_message)
            steps_container.markdown(
                "<br>".join([f"<small>{s}</small>" for s in intermediate_steps]),
                unsafe_allow_html=True,
            )
            if step_message.startswith("Selected tool"):
                tool_name = step_message.replace("Selected tool: ", "")
                if tool_name not in tools_used:
                    tools_used.append(tool_name)

    if current_response:
        st.session_state.mcp_test_responses.append(current_response)
        st.session_state.mcp_test_tools_used = tools_used


def run_mcp_query(user_input, mcp_servers, pebblo_user, pebblo_user_groups):
    asyncio.run(_run_mcp_streaming(user_input, mcp_servers, pebblo_user, pebblo_user_groups))


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# OAuth callback — must run before any UI is rendered
# ---------------------------------------------------------------------------
_TEST_REDIRECT_URI = os.getenv("DAXA_TEST_REDIRECT_URI", "http://localhost:8501/test")
handle_oauth_callback(_TEST_REDIRECT_URI)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

if "test_chat_history" not in st.session_state:
    st.session_state.test_chat_history = []
if "mcp_test_responses" not in st.session_state:
    st.session_state.mcp_test_responses = []
if "mcp_test_tools_used" not in st.session_state:
    st.session_state.mcp_test_tools_used = []

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("🔀 Mode")
    mode = st.radio(
        "Select API",
        ["Safe Infer", "Safe MCP"],
        key="test_mode",
        horizontal=True,
        label_visibility="collapsed",
    )

    st.markdown("---")

    if mode == "Safe Infer":
        st.subheader("⚙️ Test Settings")
        pebblo_user_override = st.text_input(
            "User (X_PEBBLO_USER)",
            value="",
            key="pebblo_user_override",
            placeholder="Leave empty to use env",
        )
        pebblo_user_groups_override = st.text_input(
            "User Groups (X_PEBBLO_USER_GROUPS)",
            value="",
            key="pebblo_user_groups_override",
            placeholder="Leave empty to use env",
        )
        api_type = st.selectbox("API Type", ["completions", "responses"], key="api_type")
        stream_option = st.selectbox("Stream", [True, False], key="stream_option")

        try:
            model_names, default_model = fetch_models(
                pebblo_user=pebblo_user_override.strip() or None,
                pebblo_user_groups=pebblo_user_groups_override.strip() or None,
            )
        except Exception:
            model_names, default_model = [], ""
        model_names = merge_env_model_into_model_list(model_names, MODEL)

        if not model_names:
            st.warning("Could not load models. Check API or enter a model ID below.")
            fallback_val = st.session_state.get("model_fallback", "") or MODEL
            selected_model = st.text_input("Model (fallback)", value=fallback_val, key="model_fallback")
        else:
            preferred = MODEL or default_model
            default_idx = model_names.index(preferred) if preferred in model_names else 0
            selected_model = st.selectbox("LLM Model", model_names, index=default_idx, key="model_select")

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
        user_display = pebblo_user_override.strip() if pebblo_user_override.strip() else "(from env)"
        groups_display = pebblo_user_groups_override.strip() if pebblo_user_groups_override.strip() else "(from env)"
        st.markdown(
            f"""
<div style="font-size:0.8rem;">
    API: <b>{api_type}</b> | Stream: <b>{stream_option}</b><br>
    Model: <b>{selected_model if model_names else (selected_model or '(none)')}</b><br>
    User: <b>{user_display}</b><br>
    Groups: <b>{groups_display}</b>
</div>
""",
            unsafe_allow_html=True,
        )

    else:  # Safe MCP
        st.subheader("⚙️ MCP Servers")

        def _server_expander(label, env_url, url_key, env_key, key_key, save_key):
            """Render URL + API key inputs for one MCP server. Returns (url, api_key)."""
            is_set = bool(st.session_state.get(url_key) or env_url)
            badge = "🟢" if is_set else "⚪"
            with st.expander(f"{label}  {badge}", expanded=is_set):
                url = st.text_input(
                    "MCP URL",
                    value=st.session_state.get(url_key) or env_url or "",
                    key=url_key,
                    placeholder=env_url,
                )
                api_key = st.text_input(
                    "Pebblo API Key",
                    value=st.session_state.get(key_key) or env_key or "",
                    key=key_key,
                    type="password",
                    placeholder=env_key,
                )
                if st.button("Save", key=save_key):
                    if (st.session_state.get(url_key) or "").strip():
                        st.toast(f"✅ {label} saved.", icon="💾")
                    else:
                        st.warning("Enter a URL first.")
            return url, api_key

        def _pebblo_headers_for_oauth():
            return _pebblo_mcp_headers(
                pebblo_user=st.session_state.get("mcp_test_user") or None,
                pebblo_user_groups=st.session_state.get("mcp_test_groups") or None,
            )

        atlassian_url, atlassian_api_key = _server_expander(
            "Atlassian", ATLASSIAN_MCP_URL or "", "t_atlassian_url",
            ATLASSIAN_API_KEY or "", "t_atlassian_api_key", "t_atlassian_save"
        )
        render_oauth_connect_button(
            "atlassian", "Atlassian",
            mcp_url=st.session_state.get("t_atlassian_url", "") or ATLASSIAN_MCP_URL or "",
            redirect_uri=_TEST_REDIRECT_URI,
            button_key="t_atlassian_oauth_btn",
            pebblo_headers=_pebblo_headers_for_oauth(),
        )

        billing_url, billing_api_key = _server_expander(
            "Customer Billing", CUSTOMER_BILLING_MCP_URL or "", "t_billing_url",
            CUSTOMER_BILLING_API_KEY or "", "t_billing_api_key", "t_billing_save"
        )

        st.markdown("---")
        st.subheader("👤 User Context")
        mcp_user_input = st.text_input(
            "x-pebblo-users",
            value="",
            key="mcp_test_user",
            placeholder="Leave empty to use env",
        )
        mcp_groups_input = st.text_input(
            "x-pebblo-user-groups",
            value="",
            key="mcp_test_groups",
            placeholder="Leave empty to use env",
        )

        st.subheader("📊 Statistics")
        st.metric("Queries", len(st.session_state.mcp_test_responses))
        mcp_user_display = mcp_user_input.strip() if mcp_user_input.strip() else "(from env)"
        mcp_groups_display = mcp_groups_input.strip() if mcp_groups_input.strip() else "(from env)"
        st.markdown(
            f"""
<div style="font-size:0.8rem;">
    User: <b>{mcp_user_display}</b><br>
    Groups: <b>{mcp_groups_display}</b>
</div>
""",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

st.markdown(MAIN_HEADER_HTML, unsafe_allow_html=True)
st.markdown(get_welcome_html(USER_EMAIL, USER_TEAM), unsafe_allow_html=True)

if mode == "Safe Infer":
    st.subheader("💬 Chat Interface (Safe Infer — Test)")

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
        placeholder="Ask me anything (Safe Infer Test mode).",
        key="test_user_input",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        send_button = st.button("🚀 Send", type="primary", key="test_send")

    if send_button and user_input.strip():
        model = selected_model if model_names else st.session_state.get("model_fallback", "")
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
                    pebblo_user=pebblo_user_override.strip() or None,
                    pebblo_user_groups=pebblo_user_groups_override.strip() or None,
                )

            if result["status"] == "success":
                if stream_option and result.get("stream_gen"):
                    full_content = st.empty().write_stream(result["stream_gen"])
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
                    display_chat_message("assistant", response, model, time.strftime("%H:%M:%S"))
            else:
                error_message = f"❌ Error: {result.get('message', 'Unknown error')}"
                st.error(error_message)
                st.session_state.test_chat_history.append({
                    "role": "assistant",
                    "content": error_message,
                    "timestamp": time.strftime("%H:%M:%S"),
                })
            st.rerun()

else:  # Safe MCP
    st.subheader("🔧 Safe MCP Chat Interface (Test)")
    st.caption(
        "Queries are handled by a LangGraph agent across all configured MCP servers. "
        "The LLM is routed through SafeInfer. Configure servers in the sidebar."
    )

    mcp_query = st.text_area(
        "Enter your query:",
        height=100,
        placeholder="e.g., What is the status of ticket ABC-123?",
        key="mcp_test_query_input",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        mcp_send = st.button("🚀 Send", type="primary", key="mcp_test_send")

    if mcp_send and mcp_query.strip():
        mcp_servers = build_mcp_servers(
            atlassian_url=st.session_state.get("t_atlassian_url", ""),
            atlassian_api_key=st.session_state.get("t_atlassian_api_key", ""),
            billing_url=st.session_state.get("t_billing_url", ""),
            billing_api_key=st.session_state.get("t_billing_api_key", ""),
            pebblo_user=st.session_state.get("mcp_test_user", ""),
            pebblo_user_groups=st.session_state.get("mcp_test_groups", ""),
            atlassian_token=get_oauth_token("atlassian"),
        )
        if not mcp_servers:
            st.error("Configure at least one MCP server URL in the sidebar.")
        else:
            st.session_state.mcp_test_responses = []
            st.session_state.mcp_test_tools_used = []
            run_mcp_query(
                user_input=mcp_query,
                mcp_servers=mcp_servers,
                pebblo_user=mcp_user_input.strip(),
                pebblo_user_groups=mcp_groups_input.strip(),
            )

st.markdown("---")
st.markdown(FOOTER_HTML, unsafe_allow_html=True)
