"""Shared utilities and config for SafeInfer chatbot app (Demo and Test)."""
import logging
import os
from typing import Any, Dict, Generator, List

import httpx
import requests
import yaml
from openai import OpenAI

_attempt_counter = {"count": 0}


def _on_request(request):
    _attempt_counter["count"] += 1
    print(f"Attempt #{_attempt_counter['count']} -> {request.url}")

# Load .env from app directory if present (before reading any env vars)
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

# API Configuration (from env)
API_KEY = os.getenv("PEBBLO_API_KEY", "")
API_BASE_URL = os.getenv("PROXIMA_HOST", "http://localhost")
USER_EMAIL = os.getenv("USER_EMAIL", "User")
USER_TEAM = os.getenv("USER_TEAM", "Finance Ops")
RESPONSE_API_ENDPOINT = f"{API_BASE_URL}/safe_infer/llm/v1/"
LLM_PROVIDER_API_ENDPOINT = f"{API_BASE_URL}/api/llm/provider"
X_PEBBLO_USER = os.getenv("X_PEBBLO_USER", None)
X_PEBBLO_USER_GROUPS = os.getenv("X_PEBBLO_USER_GROUPS", None)
MODEL = os.getenv("MODEL", "").strip()

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


def _parse_models_response_body(body: Any) -> List[str]:
    """Extract ordered unique model id strings from a /v1/models-style JSON body."""
    # OpenAI-style: {object: 'list', data: [{id: '...', ...}, ...]}
    if isinstance(body, dict) and "data" in body:
        models = body["data"] or []
        if not models:
            return []
        return list(dict.fromkeys(m["id"] for m in models if m.get("id")))
    # Provider-list style: list of {default_model_name, is_default_provider}
    if isinstance(body, list):
        if len(body) == 0:
            return []
        return list(
            dict.fromkeys(m["default_model_name"] for m in body if m.get("default_model_name"))
        )
    return []


def _fetch_model_ids_from_url(url: str, headers: Dict[str, str]) -> List[str]:
    """GET a models URL; return id list or [] on HTTP error, empty body, or non-JSON."""
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.debug("Models request failed %s: %s", url, exc)
        return []

    text = (response.text or "").strip()
    if not text:
        logger.debug("Models response empty: %s", url)
        return []

    try:
        body = response.json()
    except ValueError:
        # HTML error page, plain text, or other non-JSON (common if path is missing)
        logger.debug(
            "Models response not JSON (status=%s): %s",
            response.status_code,
            url,
        )
        return []

    return _parse_models_response_body(body)


def _models_request_headers(
    api_key: str = None,
    pebblo_user: str = None,
    pebblo_user_groups: str = None,
) -> Dict[str, str]:
    key = api_key if api_key is not None else API_KEY
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {key}" if key else "",
    }
    header_user = (
        pebblo_user.strip() if (pebblo_user and pebblo_user.strip()) else X_PEBBLO_USER
    )
    if header_user:
        headers["X-PEBBLO-USER"] = header_user
    header_groups = (
        pebblo_user_groups.strip()
        if (pebblo_user_groups and pebblo_user_groups.strip())
        else X_PEBBLO_USER_GROUPS
    )
    if header_groups:
        headers["X-PEBBLO-USER-GROUPS"] = header_groups
    if not key:
        headers.pop("Authorization", None)
    return headers


def get_available_models(
    api_base_url: str = None,
    api_key: str = None,
    pebblo_user: str = None,
    pebblo_user_groups: str = None,
):
    """Fetch models from safe_infer and plain LLM endpoints, merged in order.

    Combines GET {base}/safe_infer/llm/v1/models and GET {base}/llm/v1/models,
    appending the second list after the first (deduplicated, order preserved).

    Returns (model_names, default_model_name).
    On total failure returns ([], "").
    pebblo_user / pebblo_user_groups: optional overrides for Pebblo headers.
    """
    base = (api_base_url or API_BASE_URL or "").rstrip("/")
    headers = _models_request_headers(api_key, pebblo_user, pebblo_user_groups)

    safe_infer_url = f"{base}/safe_infer/llm/v1/models"
    llm_v1_url = f"{base}/llm/v1/models"

    from_safe_infer = _fetch_model_ids_from_url(safe_infer_url, headers)
    from_llm_v1 = _fetch_model_ids_from_url(llm_v1_url, headers)

    merged = list(dict.fromkeys(from_safe_infer + from_llm_v1))
    if not merged:
        return [], ""

    default_model_name = merged[0]
    return merged, default_model_name


def merge_env_model_into_model_list(
    model_names: List[str],
    env_model: str,
) -> List[str]:
    """Include env MODEL in the dropdown when set; prepend if missing from the API list."""
    if not env_model:
        return list(model_names) if model_names else []
    ordered = list(dict.fromkeys(model_names)) if model_names else []
    if env_model in ordered:
        return ordered
    return [env_model] + ordered


def _get_client(
    api_key: str = None,
    pebblo_user: str = None,
    pebblo_user_groups: str = None,
):
    """Build OpenAI client with shared config.

    pebblo_user: if non-empty, use for X-PEBBLO-USER header; else use env X_PEBBLO_USER.
    pebblo_user_groups: if non-empty, use for X-PEBBLO-USER-GROUPS; else use env.
    """
    key = api_key or API_KEY
    default_headers = {}
    header_user = (
        pebblo_user.strip() if (pebblo_user and pebblo_user.strip()) else X_PEBBLO_USER
    )
    if header_user:
        default_headers["X-PEBBLO-USER"] = header_user
    header_groups = (
        pebblo_user_groups.strip()
        if (pebblo_user_groups and pebblo_user_groups.strip())
        else X_PEBBLO_USER_GROUPS
    )
    if header_groups:
        default_headers["X-PEBBLO-USER-GROUPS"] = header_groups
    default_headers = default_headers or None
    http_client = httpx.Client(
        timeout=300,
        transport=httpx.HTTPTransport(retries=0),
        event_hooks={"request": [_on_request]},
    )
    return OpenAI(
        base_url=RESPONSE_API_ENDPOINT,
        api_key=key,
        default_headers=default_headers,
        http_client=http_client,
        max_retries=0,
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
    message: str,
    model: str,
    stream: bool,
    api_key: str = "",
    pebblo_user: str = None,
    pebblo_user_groups: str = None,
) -> Dict[str, Any]:
    """Call chat.completions API. Returns {status, data} or {status, stream_gen} for stream."""
    try:
        client = _get_client(
            api_key or API_KEY,
            pebblo_user=pebblo_user,
            pebblo_user_groups=pebblo_user_groups,
        )
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
    message: str,
    model: str,
    stream: bool,
    api_key: str = "",
    pebblo_user: str = None,
    pebblo_user_groups: str = None,
) -> Dict[str, Any]:
    """Call responses API. Returns {status, data} or {status, stream_gen} for stream."""
    try:
        client = _get_client(
            api_key or API_KEY,
            pebblo_user=pebblo_user,
            pebblo_user_groups=pebblo_user_groups,
        )
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
    pebblo_user: str = None,
    pebblo_user_groups: str = None,
) -> Dict[str, Any]:
    """Call OpenAI-compatible API using user-selected api_type, model, and stream.
    api_type: 'completions' or 'responses'
    Returns {status, data} or {status, stream_gen} for streaming.
    pebblo_user: if non-empty, use for X-PEBBLO-USER header; else use env.
    pebblo_user_groups: if non-empty, use for X-PEBBLO-USER-GROUPS; else use env.
    """
    if api_type == "responses":
        return call_responses(
            message,
            model,
            stream,
            api_key or API_KEY,
            pebblo_user=pebblo_user,
            pebblo_user_groups=pebblo_user_groups,
        )
    return call_completions(
        message,
        model,
        stream,
        api_key or API_KEY,
        pebblo_user=pebblo_user,
        pebblo_user_groups=pebblo_user_groups,
    )
