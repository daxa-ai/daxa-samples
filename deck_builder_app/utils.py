"""Shared utilities and config for Deck Builder app (Safe Infer + Insecure Inference)."""
import functools
import logging
import os
from typing import Any, Dict, List

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
X_PEBBLO_USER = os.getenv("X_PEBBLO_USER", None)
X_PEBBLO_USER_GROUPS = os.getenv("X_PEBBLO_USER_GROUPS", None)
MODEL = os.getenv("MODEL", "").strip()
PEBBLO_USERS_LIST = [u.strip() for u in os.getenv("PEBBLO_USERS", "").split(",") if u.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Gateway selection (Safe Infer mode)
#
# GATEWAY_TYPE picks which OpenAI-compatible gateway Safe Infer talks to:
#   daxa (default) — Daxa/Proxima SafeInfer at {PROXIMA_HOST}/safe_infer/llm/v1/
#   litellm        — a LiteLLM proxy at {LITELLM_BASE_URL}/v1
# Only the endpoints, auth and identity forwarding differ; the deck pipeline
# itself is gateway-agnostic (it just takes an OpenAI client + model name).
# ---------------------------------------------------------------------------

GATEWAY_DAXA = "daxa"
GATEWAY_LITELLM = "litellm"

GATEWAY_TYPE = os.getenv("GATEWAY_TYPE", GATEWAY_DAXA).strip().lower() or GATEWAY_DAXA
if GATEWAY_TYPE not in (GATEWAY_DAXA, GATEWAY_LITELLM):
    logger.warning("Unknown GATEWAY_TYPE=%r; falling back to %r", GATEWAY_TYPE, GATEWAY_DAXA)
    GATEWAY_TYPE = GATEWAY_DAXA

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://localhost:4000").strip()
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "").strip()
LITELLM_FORWARD_PEBBLO_HEADERS = _env_bool("LITELLM_FORWARD_PEBBLO_HEADERS", False)


def _litellm_root(url: str) -> str:
    """Normalize LITELLM_BASE_URL to the proxy root (no trailing '/' or '/v1')."""
    root = (url or "").rstrip("/")
    return root[: -len("/v1")] if root.endswith("/v1") else root


def _build_gateway_profile() -> Dict[str, Any]:
    """Endpoints, auth and identity behaviour for the configured GATEWAY_TYPE."""
    if GATEWAY_TYPE == GATEWAY_LITELLM:
        root = _litellm_root(LITELLM_BASE_URL)
        return {
            "type": GATEWAY_LITELLM,
            "label": "LiteLLM",
            "target": root,
            "chat_base_url": f"{root}/v1",
            "models_urls": [f"{root}/v1/models"],
            # /health/liveliness is LiteLLM's cheap, unauthenticated liveness probe;
            # /health would call every configured model, too slow for a button.
            "health_url": f"{root}/health/liveliness",
            "api_key": LITELLM_API_KEY,
            "send_pebblo_headers": LITELLM_FORWARD_PEBBLO_HEADERS,
            "send_user_field": True,
        }
    base = (API_BASE_URL or "").rstrip("/")
    return {
        "type": GATEWAY_DAXA,
        "label": "Daxa",
        "target": API_BASE_URL,
        "chat_base_url": RESPONSE_API_ENDPOINT,
        "models_urls": [f"{base}/safe_infer/llm/v1/models", f"{base}/llm/v1/models"],
        "health_url": f"{base}/safe_infer/healthz",
        "api_key": API_KEY,
        "send_pebblo_headers": True,
        "send_user_field": False,
    }


GATEWAY = _build_gateway_profile()
GATEWAY_LABEL = GATEWAY["label"]
GATEWAY_TARGET = GATEWAY["target"]


def _parse_user_groups_map(raw: str) -> dict:
    """Parse 'user1:group1,group2;user2:group3' into {user: 'group1,group2', ...}."""
    result = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if ":" not in entry:
            continue
        user, _, groups = entry.partition(":")
        user = user.strip()
        groups = groups.strip()
        if user:
            result[user] = groups
    return result


PEBBLO_USER_GROUPS_MAP: dict = _parse_user_groups_map(os.getenv("PEBBLO_USER_GROUPS_MAP", ""))

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
    /* Hide entire Streamlit sidebar nav (app name + page links) */
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
    <h1>📊 Deck Builder App</h1>
    <p>Upload a spreadsheet and describe the deck you want — get a slide-by-slide outline</p>
</div>
"""

FOOTER_HTML = f"""
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    <p>🛡️ Powered by SafeInfer LLM API ({GATEWAY_LABEL}) | Secure • Intelligent • Reliable</p>
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


def test_api_connection() -> Dict[str, Any]:
    """Test the configured gateway's health endpoint."""
    try:
        response = requests.get(GATEWAY["health_url"], timeout=5)
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
    role: str, content: str, model: str = "", user: str = "", timestamp: str = ""
) -> None:
    """Display a chat message with proper styling. Requires streamlit as st."""
    import streamlit as st

    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
    else:
        with st.chat_message("assistant"):
            st.markdown(content)
            display_user = format_display_name(user) if user else ""
            info_parts = [p for p in (
                f"Model: {model}" if model else "",
                f"User: {display_user}" if display_user else "",
                timestamp,
            ) if p]
            if info_parts:
                st.markdown(
                    f'<div class="model-info">{" | ".join(info_parts)}</div>',
                    unsafe_allow_html=True,
                )


def format_display_name(value: str) -> str:
    """Turn 'alice@daxa.ai' → 'Alice' or 'hr_group@daxa.ai' → 'Hr Group'."""
    if not value:
        return value
    local = value.split("@")[0] if "@" in value else value
    return local.replace("_", " ").replace("-", " ").replace(".", " ").title()


def get_welcome_html(user_email: str = None, user_team: str = None) -> str:
    """Return HTML for the welcome message."""
    raw_email = user_email or USER_EMAIL
    raw_team = user_team or USER_TEAM
    display_user = format_display_name(raw_email)
    display_team = format_display_name(raw_team)
    return f"""
<div class="chat-message bot-message" style="background-color:#f3e5f5;border-left:4px solid #9c27b0;padding:1rem;border-radius:10px;margin:0.5rem 0;">
    <strong>🤖 AI Assistant:</strong><br>
    Welcome {display_user}, {display_team} team!
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


def _resolve_pebblo_identity(pebblo_user: str = None, pebblo_user_groups: str = None) -> tuple:
    """(user, groups) from the given overrides, falling back to env X_PEBBLO_USER*."""
    user = pebblo_user.strip() if (pebblo_user and pebblo_user.strip()) else X_PEBBLO_USER
    groups = (
        pebblo_user_groups.strip()
        if (pebblo_user_groups and pebblo_user_groups.strip())
        else X_PEBBLO_USER_GROUPS
    )
    return user, groups


def _pebblo_headers(pebblo_user: str = None, pebblo_user_groups: str = None) -> Dict[str, str]:
    """X-PEBBLO-* headers, or {} when the configured gateway doesn't take them."""
    if not GATEWAY["send_pebblo_headers"]:
        return {}
    user, groups = _resolve_pebblo_identity(pebblo_user, pebblo_user_groups)
    headers = {}
    if user:
        headers["X-PEBBLO-USER"] = user
    if groups:
        headers["X-PEBBLO-USER-GROUPS"] = groups
    return headers


def _models_request_headers(
    api_key: str = None,
    pebblo_user: str = None,
    pebblo_user_groups: str = None,
) -> Dict[str, str]:
    key = api_key if api_key is not None else GATEWAY["api_key"]
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    headers.update(_pebblo_headers(pebblo_user, pebblo_user_groups))
    return headers


def get_available_models(
    api_key: str = None,
    pebblo_user: str = None,
    pebblo_user_groups: str = None,
):
    """Fetch models from the configured gateway's model-list URL(s), merged in order.

    Daxa: GET {base}/safe_infer/llm/v1/models then GET {base}/llm/v1/models.
    LiteLLM: GET {LITELLM_BASE_URL}/v1/models.
    Lists are appended in that order (deduplicated, order preserved).

    Returns (model_names, default_model_name).
    On total failure returns ([], "").
    pebblo_user / pebblo_user_groups: optional overrides for Pebblo headers.
    """
    headers = _models_request_headers(api_key, pebblo_user, pebblo_user_groups)
    fetched: List[str] = []
    for url in GATEWAY["models_urls"]:
        fetched += _fetch_model_ids_from_url(url, headers)

    merged = list(dict.fromkeys(fetched))
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


def _http_client() -> httpx.Client:
    """Shared no-retry httpx client with request-count logging, used by both LLM clients."""
    return httpx.Client(
        timeout=300,
        transport=httpx.HTTPTransport(retries=0),
        event_hooks={"request": [_on_request]},
    )


def get_llm_client(
    api_key: str = None,
    pebblo_user: str = None,
    pebblo_user_groups: str = None,
) -> OpenAI:
    """Build an OpenAI client routed through the configured Safe Infer gateway
    (GATEWAY_TYPE: Daxa/Proxima SafeInfer or LiteLLM).

    pebblo_user: if non-empty, use for X-PEBBLO-USER header; else use env X_PEBBLO_USER.
    pebblo_user_groups: if non-empty, use for X-PEBBLO-USER-GROUPS; else use env.
    Daxa always gets these headers; LiteLLM gets them only when
    LITELLM_FORWARD_PEBBLO_HEADERS=true, and instead gets the user as the
    OpenAI `user` field on every chat completion.
    """
    key = api_key or GATEWAY["api_key"]
    client = OpenAI(
        base_url=GATEWAY["chat_base_url"],
        api_key=key,
        default_headers=_pebblo_headers(pebblo_user, pebblo_user_groups) or None,
        http_client=_http_client(),
        max_retries=0,
    )
    end_user, _ = _resolve_pebblo_identity(pebblo_user, pebblo_user_groups)
    if GATEWAY["send_user_field"] and end_user:
        # The SDK has no per-client default body, so bind `user` onto this
        # client's completions.create — callers stay gateway-agnostic.
        completions = client.chat.completions
        completions.create = functools.partial(completions.create, user=end_user)
    return client


def is_blocked_error(status_code: int, message: str = "") -> bool:
    """True if an API error means the gateway blocked the content.

    Daxa SafeInfer blocks with HTTP 403. LiteLLM guardrails usually reject with
    HTTP 400 and an error body mentioning the guardrail, so treat that as a
    block too when GATEWAY_TYPE=litellm.
    """
    if status_code == 403:
        return True
    return (
        GATEWAY["type"] == GATEWAY_LITELLM
        and status_code == 400
        and "guardrail" in (message or "").lower()
    )


def get_direct_llm_client(api_key: str = None) -> OpenAI:
    """Build an OpenAI client that calls the model directly (no Daxa gateway, no Pebblo headers).

    Uses OPENAI_API_KEY from env unless api_key is given. No base_url override —
    the SDK defaults to https://api.openai.com/v1.
    """
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    return OpenAI(
        api_key=key,
        http_client=_http_client(),
        max_retries=0,
    )
