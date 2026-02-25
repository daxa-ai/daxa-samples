"""Shared utilities and config for SafeInfer chatbot app (Demo and Test)."""
import os
from typing import Any, Dict, Generator, List

import requests
import yaml
from openai import OpenAI

# Load .env from app directory if present (before reading any env vars)
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_env_path)

# API Configuration (from env)
API_KEY = os.getenv("PEBBLO_API_KEY", "")
API_BASE_URL = os.getenv("PROXIMA_HOST", "http://localhost")
USER_EMAIL = os.getenv("USER_EMAIL", "User")
USER_TEAM = os.getenv("USER_TEAM", "Finance Ops")
RESPONSE_API_ENDPOINT = f"{API_BASE_URL}/safe_infer/llm/v1/"
LLM_PROVIDER_API_ENDPOINT = f"{API_BASE_URL}/api/llm/provider"
SELECTED_MODEL = os.getenv("MODEL")
X_PEBBLO_USER = os.getenv("X_PEBBLO_USER", None)
MODEL_NAME = os.getenv("MODEL_NAME", SELECTED_MODEL)

CUSTOM_CSS = """
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .user-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    .bot-message {
        background-color: #f3e5f5;
        border-left: 4px solid #9c27b0;
    }
    .model-info {
        background-color: #fff3e0;
        padding: 0.5rem;
        border-radius: 5px;
        font-size: 0.8rem;
        color: #e65100;
    }
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.5rem 1rem;
    }
    .stButton > button:hover {
        background: linear-gradient(90deg, #5a6fd8 0%, #6a4190 100%);
    }
    /* Hide entire Streamlit sidebar nav (app name + page links); /test still works via URL */
    div[data-testid="stSidebarNav"] {
        display: none !important;
    }
    /* Sidebar sample prompt text areas: code-like appearance */
    [data-testid="stSidebar"] textarea[disabled] {
        font-family: ui-monospace, monospace !important;
        font-size: 0.85rem !important;
        background-color: #f6f8fa !important;
    }
    /* Smaller "Use" (→) button next to sample prompts */
    [data-testid="stSidebar"] .prompt-use-btn-marker { display: none; }
    [data-testid="stSidebar"] .prompt-use-btn-marker + div .stButton > button {
        min-height: 1.5rem !important;
        padding: 0.15rem 0.4rem !important;
        font-size: 0.875rem !important;
    }
</style>
"""

MAIN_HEADER_HTML = """
<div class="main-header">
    <h1>🛡️ Finance Ops Chatbot</h1>
    <p>Helpful assistant for Finance Ops team</p>
</div>
"""

FOOTER_HTML = """
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    <p>🛡️ Powered by SafeInfer LLM API | Secure • Intelligent • Reliable</p>
</div>
"""

_PROMPTS_PATH = os.path.join(os.path.dirname(__file__), "prompts.yaml")


def load_prompts_from_yaml(path: str = None) -> Dict[str, List[Dict[str, str]]]:
    """Load language-based prompts from a YAML file.

    YAML structure: top-level keys are language codes (e.g. en, ko); each value
    is a list of prompts with keys: label, full_text, copyable.

    Returns:
        Dict mapping language code -> list of {label, full_text, copyable}.
        Empty dict if file is missing or invalid.
    """
    path = path or _PROMPTS_PATH
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(lang): _normalize_prompt_list(prompts) for lang, prompts in data.items() if prompts}


def _normalize_prompt_list(prompts: Any) -> List[Dict[str, str]]:
    """Ensure each prompt has label, full_text, copyable (strings)."""
    result = []
    for p in prompts if isinstance(prompts, list) else []:
        if not isinstance(p, dict):
            continue
        label = p.get("label") or ""
        full_text = p.get("full_text") or ""
        copyable = p.get("copyable") or full_text
        result.append({"label": str(label), "full_text": str(full_text), "copyable": str(copyable)})
    return result


def test_api_connection(api_base_url: str = None) -> Dict[str, Any]:
    """Test the API connection."""
    base = api_base_url or API_BASE_URL
    try:
        response = requests.get(f"{base}/safe_infer/healthz", timeout=5)
        if response.status_code == 200:
            return {"status": "success", "message": "API is accessible"}
        return {"status": "error", "message": f"API returned status {response.status_code}"}
    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "message": "Cannot connect to API. Please ensure the service is running.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}


def display_chat_message(
    role: str, content: str, model: str = "", timestamp: str = ""
) -> None:
    """Display a chat message with proper styling. Requires streamlit as st."""
    import streamlit as st

    if role == "user":
        st.markdown(
            f"""
        <div class="chat-message user-message">
            <strong>👤 You:</strong><br>
            {content}
        </div>
        """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
        <div class="chat-message bot-message">
            <strong>🤖 AI Assistant:</strong><br>
            {content}
            <div class="model-info">
                Model: {model} | {timestamp}
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )


def get_welcome_html(user_email: str = None, user_team: str = None) -> str:
    """Return HTML for the welcome message."""
    email = user_email or USER_EMAIL
    team = user_team or USER_TEAM
    return f"""
<div class="chat-message bot-message">
    <strong>🤖 AI Assistant:</strong><br>
    Welcome {email}. {team} team!
</div>
"""


def get_available_models():
    """Fetch available models. Returns (model_names, default_model_name).
    Supports OpenAI-style /v1/models response: {object, data: [{id, ...}, ...]}.
    """
    try:
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {os.environ.get('PEBBLO_API_KEY')}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        url = f"{os.environ.get('PROXIMA_HOST')}/safe_infer/llm/v1/models"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        body = response.json()
        # OpenAI-style: {object: 'list', data: [{id: '...', ...}, ...]}
        if isinstance(body, dict) and "data" in body:
            models = body["data"] or []
            if not models:
                return [], ""
            # Preserve order, deduplicate by id
            model_names = list(dict.fromkeys(m["id"] for m in models if m.get("id")))
            default_model_name = model_names[0] if model_names else ""
            return model_names, default_model_name
        # Provider-list style: list of {default_model_name, is_default_provider}
        if isinstance(body, list):
            if len(body) == 0:
                return [], ""
            model_names = [m["default_model_name"] for m in body if m.get("default_model_name")]
            default = next(
                (m for m in body if m.get("is_default_provider")),
                body[0],
            )
            default_model_name = default.get("default_model_name", model_names[0] if model_names else "")
            return model_names, default_model_name
        return [], ""
    except Exception as e:
        print(f"Error getting available models: {e}")
        raise e


def _get_client(api_key: str = None):
    """Build OpenAI client with shared config."""
    key = api_key or API_KEY
    default_headers = {"X-PEBBLO-USER": X_PEBBLO_USER} if X_PEBBLO_USER else None
    return OpenAI(
        base_url=RESPONSE_API_ENDPOINT,
        api_key=key,
        default_headers=default_headers,
    )


def _extract_response_text(response) -> str:
    """Extract plain text from Responses API response object."""
    text = ""
    if hasattr(response, "output") and response.output:
        for item in response.output:
            if hasattr(item, "content") and item.content:
                for part in item.content:
                    if hasattr(part, "text"):
                        text += part.text
            if hasattr(item, "text"):
                text += item.text
    if not text and hasattr(response, "output_text"):
        text = getattr(response.output_text, "value", "") or str(response.output_text)
    return text or str(response)


def call_completions(
    message: str, model: str, stream: bool, api_key: str = ""
) -> Dict[str, Any]:
    """Call chat.completions API. Returns {status, data} or {status, stream_gen} for stream."""
    try:
        client = _get_client(api_key or API_KEY)
        if not stream:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": message}],
                stream=False,
            )
            content = response.choices[0].message.content or ""
            return {"status": "success", "data": content}
        # Streaming
        def gen() -> Generator[str, None, None]:
            stream_resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": message}],
                stream=True,
            )
            for chunk in stream_resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        return {"status": "success", "stream_gen": gen()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def call_responses(
    message: str, model: str, stream: bool, api_key: str = ""
) -> Dict[str, Any]:
    """Call responses API. Returns {status, data} or {status, stream_gen} for stream."""
    try:
        client = _get_client(api_key or API_KEY)
        if not stream:
            response = client.responses.create(
                model=model,
                input=message,
                stream=False,
            )
            text = _extract_response_text(response)
            return {"status": "success", "data": text}
        # Streaming
        def gen() -> Generator[str, None, None]:
            with client.responses.stream(model=model, input=message) as stream:
                for event in stream:
                    delta = getattr(event, "delta", None) or getattr(
                        event, "output_text_delta", None
                    )
                    if delta is not None:
                        chunk = getattr(delta, "text", None) or getattr(
                            delta, "content", None
                        )
                        if chunk:
                            yield chunk if isinstance(chunk, str) else str(chunk)

        return {"status": "success", "stream_gen": gen()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def call_llm(
    api_type: str,
    model: str,
    stream: bool,
    message: str,
    api_key: str = "",
) -> Dict[str, Any]:
    """Call OpenAI-compatible API using user-selected api_type, model, and stream.
    api_type: 'completions' or 'responses'
    Returns {status, data} or {status, stream_gen} for streaming.
    """
    if api_type == "responses":
        return call_responses(message, model, stream, api_key or API_KEY)
    return call_completions(message, model, stream, api_key or API_KEY)
