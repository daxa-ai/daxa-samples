"""Per-session environment configuration loaded from .env files via dotenv_values().

Unlike load_dotenv() — which writes to os.environ and is shared across all
Streamlit sessions in the same process — dotenv_values() reads into a plain
dict per call. Multiple concurrent sessions can therefore use different
environments simultaneously without interfering with each other.

Usage:
    Populate envs.json with a mapping of env-name -> .env file path:
        {"demo-1": ".env.demo-1", "demo-2": ".env.demo-2"}

    Set ?env=demo-1 in the browser URL. The app loads .env.demo-1 for that
    session. With no ?env= param, falls back to the default .env file.
"""
import json
import os
import re

from dotenv import dotenv_values

_APP_DIR = os.path.dirname(__file__)
_ENV_MAP_PATH = os.path.join(_APP_DIR, "envs.json")
_DEFAULT_ENV_FILE = os.path.join(_APP_DIR, ".env")
_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def _load_env_map() -> dict:
    """Read envs.json — maps env-name to .env file path. Returns {} if missing/corrupt."""
    if not os.path.isfile(_ENV_MAP_PATH):
        return {}
    try:
        with open(_ENV_MAP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_session_config() -> dict:
    """Return the env-var dict for the current Streamlit session.

    Reads ?env= from st.query_params, resolves the matching .env file via
    envs.json, and returns dotenv_values() for that file. Falls back to the
    default .env when the param is absent or not listed in envs.json.

    Never calls load_dotenv() — os.environ is never modified — so concurrent
    sessions on different environments do not interfere with each other.
    """
    import streamlit as st  # lazy: keeps this module importable outside Streamlit

    env_name = st.query_params.get("env", "").strip()
    env_file = _DEFAULT_ENV_FILE
    if env_name and _SAFE_NAME.match(env_name):
        env_map = _load_env_map()
        if env_name in env_map:
            candidate = env_map[env_name]
            if not os.path.isabs(candidate):
                candidate = os.path.join(_APP_DIR, candidate)
            if os.path.isfile(candidate):
                env_file = candidate
    return dict(dotenv_values(env_file))


# ---------------------------------------------------------------------------
# Typed accessors — each re-evaluates on every call (no caching)
# ---------------------------------------------------------------------------

def get_proxima_host() -> str:
    raw = get_session_config().get("PROXIMA_HOST", "http://localhost")
    return (raw or "http://localhost").rstrip("/")


def get_response_api_endpoint() -> str:
    return f"{get_proxima_host()}/safe_infer/llm/v1/"


def get_api_key() -> str:
    return get_session_config().get("PEBBLO_API_KEY", "")


def get_model() -> str:
    return (get_session_config().get("MODEL") or "").strip()


def get_pebblo_users_list() -> list:
    raw = get_session_config().get("PEBBLO_USERS", "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def get_pebblo_user_groups_map() -> dict:
    from utils import _parse_user_groups_map  # lazy import avoids circular dependency
    return _parse_user_groups_map(get_session_config().get("PEBBLO_USER_GROUPS_MAP", ""))


def get_env_name() -> str:
    return get_session_config().get("ENV_NAME", "").strip()


def get_debug_enabled() -> bool:
    return get_session_config().get("DEBUG", "false").strip().lower() == "true"


def list_available_envs() -> list:
    """Return sorted list of env names defined in envs.json."""
    return sorted(_load_env_map().keys())
