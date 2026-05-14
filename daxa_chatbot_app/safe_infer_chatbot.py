import ast
import asyncio
import json
import logging
import os
import time
from typing import Generator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

import httpx
import streamlit as st
import trafilatura
from langchain_community.agent_toolkits import FileManagementToolkit
from openai import OpenAI

MAX_FETCH_CHARS = 8000
MAX_FILE_CHARS = 8000

log = logging.getLogger("safe_infer.tools")

# ---------------------------------------------------------------------------
# File Search configuration (read from env at import time)
# ---------------------------------------------------------------------------

_APP_DIR = os.path.dirname(__file__)

_raw_root = os.getenv("FILE_SEARCH_ROOT_DIR", "").strip() or "static"
FILE_SEARCH_ROOT_DIR = _raw_root if os.path.isabs(_raw_root) else os.path.join(_APP_DIR, _raw_root)

# DOC_ACCESS_ALLOWED: Python dict literal mapping filename → list of allowed groups.
# Files not present as keys are open to all users.
_raw_access = os.getenv("DOC_ACCESS_ALLOWED", "").strip()
try:
    _DOC_ACCESS_ALLOWED: dict = ast.literal_eval(_raw_access) if _raw_access else {}
    if not isinstance(_DOC_ACCESS_ALLOWED, dict):
        _DOC_ACCESS_ALLOWED = {}
except Exception as _e:
    log.warning("[file-perms] could not parse DOC_ACCESS_ALLOWED: %s", _e)
    _DOC_ACCESS_ALLOWED = {}

_FILE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full text content of a file in the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to the file to read.",
                    }
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_search",
            "description": "Search for files matching a glob pattern (e.g. '*.py', '**/*.txt') in the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match file names against.",
                    }
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": (
                "List files and directories at a path inside the repository. "
                "Use this to explore available files before reading them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {
                        "type": "string",
                        "description": "Relative sub-directory to list. Omit or use '.' for root.",
                    }
                },
                "required": [],
            },
        },
    },
]

_lc_file_tools_cache: dict = {}


def _get_lc_file_tools() -> dict:
    """Lazily build and cache the read-only LangChain file management tools."""
    global _lc_file_tools_cache
    if not _lc_file_tools_cache:
        toolkit = FileManagementToolkit(
            root_dir=FILE_SEARCH_ROOT_DIR,
            selected_tools=["read_file", "list_directory", "file_search"],
        )
        _lc_file_tools_cache = {t.name: t for t in toolkit.get_tools()}
        log.info("[file-tools] initialized with root_dir=%s tools=%s",
                 FILE_SEARCH_ROOT_DIR, list(_lc_file_tools_cache))
    return _lc_file_tools_cache


def _is_file_readable(file_path: str, pebblo_user_groups: str) -> bool:
    """Return True if the user may read file_path.

    Checks against DOC_ACCESS_ALLOWED (filename → list of allowed groups).
    Files not present as keys are open to all users.
    """
    if not _DOC_ACCESS_ALLOWED:
        return True
    fname = os.path.basename(file_path.strip())
    if fname not in _DOC_ACCESS_ALLOWED:
        return True  # not restricted → open to all
    allowed = set(_DOC_ACCESS_ALLOWED[fname])
    user_groups = {g.strip() for g in (pebblo_user_groups or "").split(",") if g.strip()}
    return bool(user_groups & allowed)


def _list_docs() -> list:
    """Return [(filename, full_path), ...] for all non-hidden files in FILE_SEARCH_ROOT_DIR."""
    if not os.path.isdir(FILE_SEARCH_ROOT_DIR):
        return []
    return [
        (fname, os.path.join(FILE_SEARCH_ROOT_DIR, fname))
        for fname in sorted(os.listdir(FILE_SEARCH_ROOT_DIR))
        if not fname.startswith(".") and os.path.isfile(os.path.join(FILE_SEARCH_ROOT_DIR, fname))
    ]


def _doc_title(fpath: str) -> str:
    """Return the first non-empty heading or line from a file as its title hint."""
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip().lstrip("#").strip()
                if line:
                    return line
    except Exception:
        pass
    return ""


def _render_citations(cited_files: list) -> str:
    """Return an HTML string with clickable source links for the given filenames."""
    links = " &nbsp;|&nbsp; ".join(
        f'<a href="/app/static/{fname}" target="_blank" style="text-decoration:none;">📄 {fname}</a>'
        for fname in cited_files
    )
    return (
        f"<div style='margin-top:8px;font-size:0.82rem;color:#666;'>"
        f"<b>Sources:</b> {links}</div>"
    )


def _render_file_link(fname: str, fpath: str) -> None:
    """Render a sidebar link that opens the file in a new browser tab.

    Relies on Streamlit's static file serving (enableStaticServing = true).
    Files in FILE_SEARCH_ROOT_DIR (default: static/) are served at /app/static/<rel_path>.
    """
    rel = os.path.relpath(fpath, FILE_SEARCH_ROOT_DIR).replace(os.sep, "/")
    url = f"/app/static/{rel}"
    st.markdown(
        f'<a href="{url}" target="_blank" style="font-size:0.85rem;text-decoration:none;">📄 {fname}</a>',
        unsafe_allow_html=True,
    )


def _run_file_tool(tool_name: str, args: dict) -> str:
    """Execute a LangChain file tool and return its result (truncated if needed)."""
    try:
        tools = _get_lc_file_tools()
        tool = tools.get(tool_name)
        if not tool:
            return f"File tool '{tool_name}' is not available."
        result = tool.run(args)
        if not isinstance(result, str):
            result = str(result)
        if len(result) > MAX_FILE_CHARS:
            result = result[:MAX_FILE_CHARS] + "\n…[truncated]"
        log.info("[file-tools] %s returned %d chars", tool_name, len(result))
        return result
    except Exception as exc:
        log.warning("[file-tools] %s error: %s", tool_name, exc)
        return f"Error running '{tool_name}': {exc}"


def _fetch_web_page(url: str) -> str:
    """Local trafilatura-based web fetcher used as an OpenAI tool."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return f"Error: could not download {url}"
        text = trafilatura.extract(downloaded) or ""
        if not text.strip():
            return f"Error: no extractable text at {url}"
        if len(text) > MAX_FETCH_CHARS:
            text = text[:MAX_FETCH_CHARS] + "\n…[truncated]"
        log.info("[FETCH_WEB_PAGE] fetched %d chars from %s", len(text), url)
        log.info("[FETCH_WEB_PAGE] content preview: %s", text[:200].replace("\n", " "))
        return text
    except Exception as e:
        return f"Error fetching {url}: {e}"


_FETCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "fetch_web_page",
        "description": (
            "Fetch a web page by URL and return its main text content. "
            "Use this whenever the user mentions a URL or asks you to read, "
            "summarize, or quote a web page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute http(s) URL to fetch."}
            },
            "required": ["url"],
        },
    },
}

_attempt_counter = {"count": 0}


def _on_request(request):
    _attempt_counter["count"] += 1


from utils import (
    API_KEY,
    CUSTOM_CSS,
    FOOTER_HTML,
    MAIN_HEADER_HTML,
    MODEL,
    PEBBLO_USER_GROUPS_MAP,
    PEBBLO_USERS_LIST,
    RESPONSE_API_ENDPOINT,
    X_PEBBLO_USER,
    X_PEBBLO_USER_GROUPS,
    display_chat_message,
    format_display_name,
    get_available_models,
    get_welcome_html,
    load_prompts_from_yaml,
    merge_env_model_into_model_list,
    test_api_connection,
)
from mcp_utils import (
    ATLASSIAN_MCP_URL,
    ATLASSIAN_API_KEY,
    ATLASSIAN_DOCKER_MCP_URL,
    ATLASSIAN_DOCKER_API_KEY,
    CUSTOMER_BILLING_MCP_URL,
    CUSTOMER_BILLING_API_KEY,
    DIRECT_ATLASSIAN_MCP_URL,
    DIRECT_CUSTOMER_BILLING_MCP_URL,
    SHOW_ATLASSIAN_OAUTH,
    SHOW_ATLASSIAN_DOCKER,
    SHOW_CUSTOMER_BILLING,
    build_mcp_servers,
    build_direct_mcp_servers,
    stream_query_steps as mcp_stream_query_steps,
    _pebblo_mcp_headers,
)
from oauth_utils import (
    handle_oauth_callback,
    render_oauth_connect_button,
    get_token as get_oauth_token,
    is_connected as oauth_is_connected,
)


@st.cache_data(ttl=300)
def fetch_models():
    """Fetch models from GET .../v1/models (cached 5 min). Returns (names, default_id)."""
    return get_available_models()


# Page configuration
st.set_page_config(
    page_title="Customer Support Chatbot",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# OAuth callback — must run before any UI is rendered
# ---------------------------------------------------------------------------
_MAIN_REDIRECT_URI = os.getenv("DAXA_REDIRECT_URI", "http://localhost:8501")
handle_oauth_callback(_MAIN_REDIRECT_URI)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Load language-based prompts from YAML (prompts.yaml)
LANGUAGE_PROMPTS = load_prompts_from_yaml()
DEFAULT_LANGUAGE = "en" if "en" in LANGUAGE_PROMPTS else (list(LANGUAGE_PROMPTS.keys())[0] if LANGUAGE_PROMPTS else "en")

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "direct_chat_history" not in st.session_state:
    st.session_state.direct_chat_history = []
if "direct_mcp_responses" not in st.session_state:
    st.session_state.direct_mcp_responses = []
if "direct_mcp_tools_used" not in st.session_state:
    st.session_state.direct_mcp_tools_used = []
if "selected_model" not in st.session_state:
    st.session_state.selected_model = MODEL or ""
if "api_key" not in st.session_state:
    st.session_state.api_key = API_KEY
if "model_name" not in st.session_state:
    st.session_state.model_name = ""
if "prompt_language" not in st.session_state:
    st.session_state.prompt_language = DEFAULT_LANGUAGE
if "mcp_responses" not in st.session_state:
    st.session_state.mcp_responses = []
if "mcp_tools_used" not in st.session_state:
    st.session_state.mcp_tools_used = []
if "selected_pebblo_user" not in st.session_state:
    st.session_state.selected_pebblo_user = PEBBLO_USERS_LIST[0] if PEBBLO_USERS_LIST else (X_PEBBLO_USER or "")


# ---------------------------------------------------------------------------
# Safe Infer helpers
# ---------------------------------------------------------------------------

_FILE_TOOL_NAMES = {"list_directory", "read_file", "file_search"}


_FAILED_RESULT_PREFIXES = (
    "No files found",
    "Error",
    "Access denied",
    "not available",
    "Unknown tool",
)


def _is_useful_tool_result(result: str) -> bool:
    """Return False for empty results or known failure messages."""
    stripped = result.strip()
    if not stripped:
        return False
    return not any(stripped.startswith(p) for p in _FAILED_RESULT_PREFIXES)


def _execute_tool_call(tc, pebblo_user_groups: str) -> str:
    """Execute a single tool call and return the result string."""
    try:
        args = json.loads(tc.function.arguments or "{}")
    except json.JSONDecodeError:
        args = {}
    name = tc.function.name
    log.info("[tool-loop] invoking %s args=%s", name, args)

    if name == "fetch_web_page":
        result = _fetch_web_page(args.get("url", ""))
    elif name == "read_file":
        file_path = args.get("file_path", "")
        if not _is_file_readable(file_path, pebblo_user_groups):
            log.warning("[file-perms] access denied: user_groups=%s file=%s",
                        pebblo_user_groups, file_path)
            result = f"Access denied: your group does not have permission to read '{file_path}'."
        else:
            result = _run_file_tool(name, args)
    elif name in _FILE_TOOL_NAMES:
        result = _run_file_tool(name, args)
    else:
        result = f"Unknown tool: {name}"

    log.info("[tool-loop] %s returned %d chars", name, len(result))
    return result


def _stream_message(client: OpenAI, model: str, message: str, pebblo_user_groups: str = ""):
    """Multi-turn tool loop: chain all tool calls across rounds, collect every result
    into result_blocks, then inject them all into an augmented prompt and stream the
    final answer.

    Allows chained calls like file_search → read_file in a single user turn.
    read_file enforces per-file group permissions from DOC_ACCESS_ALLOWED.
    """
    # Only expose fetch_web_page when the message contains a URL
    has_url = "http://" in message or "https://" in message
    tools = _FILE_TOOL_SCHEMAS + ([_FETCH_TOOL_SCHEMA] if has_url else [])
    available_files = [fname for fname, _ in _list_docs()]
    # system_content = (
    #     f"Available local files: {', '.join(available_files)}. "
    #     "If the user's question relates to any of these files, use read_file to read the relevant file first. "
    #     "If the answer is not found in the local files or the question is unrelated to them, answer directly from your own knowledge."
    #     if available_files
    #     else "No local files are currently available. Answer directly from your own knowledge."
    # )
    system_content = f"""
        You are a helpful AI assistant.

        Available local files:
        {chr(10).join(f'- {fname}: "{_doc_title(fpath)}"' for fname, fpath in _list_docs()) if available_files else 'No local files are currently available.'}

        General behavior rules:

        1. First determine whether the user's request requires using any available tool.
        2. Use tools ONLY when they are clearly relevant and necessary.
        3. If no available tool is useful for answering the request, answer directly using your own knowledge.
        4. Do NOT force tool usage.
        5. If local files are available and the user asks about file contents, summaries, searches, analysis, extraction, or comparisons, use the read_file tool directly with the exact filename.
        6. If the request can be answered without reading files, do not use read_file.
        7. Prefer concise and efficient tool usage.
        8. After using a tool, provide a natural language answer based on the tool output.
        9. If a requested action cannot be completed with available tools, clearly say so and provide the best possible direct response.

        Important:
        - Tool availability does NOT mean the tool must be used.
        - Always choose the simplest correct path:
        - Tool if needed
        - Direct LLM response otherwise
    """.strip()
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message},
    ]
    log.info("[tool-loop] model=%s base_url=%s tools=%s",
             model, getattr(client, "base_url", "?"),
             [t["function"]["name"] for t in tools])

    result_blocks = []
    cited_files: list = []
    _MAX_ROUNDS = 5

    for round_num in range(_MAX_ROUNDS):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
        )
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        log.info("[tool-loop] round=%d finish_reason=%s tool_calls=%s",
                 round_num, resp.choices[0].finish_reason,
                 [tc.function.name for tc in tool_calls])

        if not tool_calls:
            if round_num == 0:
                log.info("[tool-loop] no tool calls → direct answer")
                yield msg.content or ""
                return
            break

        # Append assistant turn so the next round has full context
        messages.append(msg)

        for tc in tool_calls:
            result = _execute_tool_call(tc, pebblo_user_groups)
            # Keep conversation history for chaining regardless of outcome
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
            # Only accumulate meaningful results in result_blocks (skip failures/empty)
            if _is_useful_tool_result(result):
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                label = args.get("url") or args.get("file_path") or args.get("pattern") or tc.function.name
                result_blocks.append(
                    f"--- Tool result: {tc.function.name}({label}) ---\n{result}\n--- End of result ---"
                )
                if tc.function.name == "read_file":
                    fp = args.get("file_path", "")
                    if fp:
                        fname = os.path.basename(fp.strip("/\\"))
                        if fname and fname not in cited_files:
                            cited_files.append(fname)
            else:
                log.info("[tool-loop] skipping empty/failed result for %s", tc.function.name)

        # If we already have useful results, skip asking the LLM for more tools —
        # go straight to the final streaming call to save an extra round-trip.
        # Only continue the loop when results are still empty (e.g. file_search
        # returned nothing and the LLM should try a different tool).
        if result_blocks:
            break

    # Persist cited files so the UI can render clickable source links after streaming
    if cited_files:
        st.session_state["_cited_files"] = cited_files

    # Inject all collected tool results into the augmented prompt and stream
    injected = "\n\n".join(result_blocks)
    augmented = f"{injected}\n\nUsing the above content, answer the following:\n{message}"
    log.info("[tool-loop] augmented prompt length: %d chars, blocks: %d, cited: %s",
             len(augmented), len(result_blocks), cited_files)

    with client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": augmented}],
        stream=True,
    ) as stream:
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


def stream_open_ai(message: str, model: str, api_key: str = "", pebblo_user: str = "", pebblo_user_groups: str = ""):
    """Yield tokens from OpenAI-compatible completions API (streaming).

    fetch_web_page and file search tools are always offered to the LLM.
    Per-file group restrictions are enforced at execution time via DOC_ACCESS_ALLOWED.
    """
    default_headers = {}
    active_user = pebblo_user.strip() if pebblo_user and pebblo_user.strip() else X_PEBBLO_USER
    if active_user:
        default_headers["X-PEBBLO-USER"] = active_user
    active_groups = pebblo_user_groups.strip() if pebblo_user_groups and pebblo_user_groups.strip() else X_PEBBLO_USER_GROUPS
    if active_groups:
        default_headers["X-PEBBLO-USER-GROUPS"] = active_groups
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
    yield from _stream_message(client, model, message, pebblo_user_groups=active_groups or "")


# ---------------------------------------------------------------------------
# InSecure Infer helpers
# ---------------------------------------------------------------------------

def stream_direct_openai(message: str, model: str) -> Generator:
    """Yield tokens directly from OpenAI API using OPENAI_API_KEY (no gateway, no Pebblo headers)."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    http_client = httpx.Client(
        timeout=300,
        transport=httpx.HTTPTransport(retries=0),
        event_hooks={"request": [_on_request]},
    )
    client = OpenAI(
        api_key=api_key,
        http_client=http_client,
        max_retries=0,
    )
    yield from _stream_message(client, model, message, pebblo_user_groups="")


# ---------------------------------------------------------------------------
# Safe MCP helpers
# ---------------------------------------------------------------------------

async def _run_mcp_streaming(user_input: str, mcp_servers: dict, pebblo_user: str, pebblo_user_groups: str):
    """Run Safe MCP query with streaming status updates."""
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
        st.session_state.mcp_responses.append(current_response)
        st.session_state.mcp_tools_used = tools_used


def run_mcp_query(user_input: str, mcp_servers: dict, pebblo_user: str, pebblo_user_groups: str):
    asyncio.run(
        _run_mcp_streaming(user_input, mcp_servers, pebblo_user, pebblo_user_groups)
    )


# ---------------------------------------------------------------------------
# Main header
# ---------------------------------------------------------------------------

st.markdown(MAIN_HEADER_HTML, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helper: resolve groups for the currently selected Pebblo user
# ---------------------------------------------------------------------------

def _get_active_pebblo_groups() -> str:
    """Return user-groups string for the selected user, falling back to env default."""
    user = st.session_state.get("selected_pebblo_user", "")
    if user and PEBBLO_USER_GROUPS_MAP:
        mapped = PEBBLO_USER_GROUPS_MAP.get(user, "")
        if mapped:
            return mapped
    return X_PEBBLO_USER_GROUPS or ""


# ---------------------------------------------------------------------------
# Sidebar: mode selector first, then mode-specific controls
# ---------------------------------------------------------------------------

# Feature flags — control which mode tabs are visible
SHOW_SAFE_INFER      = os.getenv("SHOW_SAFE_INFER",      "true").strip().lower() == "true"
SHOW_INSECURE_INFER  = os.getenv("SHOW_INSECURE_INFER",  "true").strip().lower() == "true"
SHOW_SAFE_AGENT      = os.getenv("SHOW_SAFE_AGENT",      "true").strip().lower() == "true"
SHOW_INSECURE_AGENT  = os.getenv("SHOW_INSECURE_AGENT",  "true").strip().lower() == "true"

# Comma-separated ticket IDs to display in agent sidebars, e.g. "KAN-19,KAN-22,KAN-46"
_TICKET_LIST = [t.strip() for t in os.getenv("JIRA_TICKETS", "").split(",") if t.strip()]

_MODE_LABELS = {
    "Safe Infer":     "🟢 Safe Infer",
    "InSecure Infer": "🔴 Insecure Inference",
    "Safe Agent":     "🟢 Safe Agent",
    "InSecure Agent": "🔴 Insecure Agent",
}
_LABEL_TO_MODE = {v: k for k, v in _MODE_LABELS.items()}

# Display order: row1 = [Safe Infer, Insecure Inference], row2 = [Insecure Agent, Safe Agent]
# Each entry is only included when its feature flag is enabled.
_MODE_OPTIONS = [
    *(["🟢 Safe Infer"]          if SHOW_SAFE_INFER      else []),
    *(["🔴 Insecure Inference"]  if SHOW_INSECURE_INFER  else []),
    *(["🔴 Insecure Agent"]      if SHOW_INSECURE_AGENT   else []),
    *(["🟢 Safe Agent"]          if SHOW_SAFE_AGENT       else []),
]

# Default to the first available option
_DEFAULT_MODE = _MODE_OPTIONS[0] if _MODE_OPTIONS else "🟢 Safe Agent"

with st.sidebar:
    _raw_mode = st.segmented_control(
        "Mode",
        options=_MODE_OPTIONS,
        default=_DEFAULT_MODE,
        key="app_mode",
        label_visibility="collapsed",
    )
    mode = _LABEL_TO_MODE.get(_raw_mode, "Safe Agent")

    st.markdown("---")

    if PEBBLO_USERS_LIST and mode in ("Safe Infer", "Safe Agent"):
        st.subheader("👤 User")
        st.selectbox(
            "User",
            options=PEBBLO_USERS_LIST,
            format_func=format_display_name,
            key="selected_pebblo_user",
            label_visibility="collapsed",
        )
        st.markdown("---")

    if mode == "Safe Infer":
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
                current = st.session_state.get("selected_model") or MODEL or default_model
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

        # Documents section — list files from static/, clickable links open in new tab
        _docs = _list_docs()
        if _docs:
            st.subheader("📁 Documents")
            _current_groups = _get_active_pebblo_groups()
            for _fname, _fpath in _docs:
                if _is_file_readable(_fname, _current_groups):
                    _render_file_link(_fname, _fpath)
                else:
                    st.caption(f"🔒 {_fname}")
            st.markdown("---")

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

    elif mode == "InSecure Infer":
        st.subheader("🤖 Model")
        direct_model_val = st.session_state.get("direct_model") or MODEL or "gpt-5"
        st.text_input(
            "OpenAI Model ID",
            value=direct_model_val,
            key="direct_model",
            placeholder="e.g. gpt-5, gpt-5-mini, etc.",
        )
        st.caption("Calls **api.openai.com** directly using `OPENAI_API_KEY`. No SafeInfer gateway.")

        if st.session_state.direct_chat_history:
            chat_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model": st.session_state.get("direct_model", ""),
                "conversation": st.session_state.direct_chat_history,
            }
            st.download_button(
                label="📥 Export Chat",
                data=json.dumps(chat_data, indent=2),
                file_name=f"direct_infer_{time.strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                key="direct_export_btn",
            )
            if st.button("🗑️ Clear Chat", key="direct_clear_btn"):
                st.session_state.direct_chat_history = []
                st.rerun()

        st.subheader("📊 Statistics")
        st.metric("Messages", len(st.session_state.direct_chat_history))
        st.markdown(
            f"<div style='font-size:0.8rem;'>Model: <b>{st.session_state.get('direct_model') or MODEL or 'gpt-5'}</b></div>",
            unsafe_allow_html=True,
        )

    elif mode == "InSecure Agent":
        st.subheader("⚙️ MCP Servers")

        def _direct_server_expander(label, env_url, url_key, save_key):
            """URL-only expander for InSecure Agent (no Pebblo API key field)."""
            is_set = bool(st.session_state.get(url_key) or env_url)
            badge = "🟢" if is_set else "⚪"
            with st.expander(f"{label}  {badge}", expanded=False):
                st.text_input(
                    "MCP URL",
                    value=st.session_state.get(url_key) or env_url or "",
                    key=url_key,
                    placeholder=env_url,
                )
                if st.button("Save", key=save_key):
                    if (st.session_state.get(url_key) or "").strip():
                        st.toast(f"✅ {label} saved.", icon="💾")
                    else:
                        st.warning("Enter a URL first.")

        def _direct_pebblo_headers_for_oauth():
            # No Pebblo user headers in Direct mode — empty dict for OAuth probe
            return {}

        if SHOW_ATLASSIAN_OAUTH:
            _direct_server_expander(
                "Atlassian (OAuth)", ATLASSIAN_MCP_URL or "", "direct_atlassian_oauth_url", "direct_atlassian_oauth_save"
            )
            render_oauth_connect_button(
                "direct_atlassian", "Atlassian",
                mcp_url=st.session_state.get("direct_atlassian_oauth_url", "") or ATLASSIAN_MCP_URL or "",
                redirect_uri=_MAIN_REDIRECT_URI,
                button_key="direct_atlassian_oauth_btn",
                pebblo_headers=_direct_pebblo_headers_for_oauth(),
            )

        if SHOW_ATLASSIAN_DOCKER:
            _direct_server_expander(
                "Atlassian", DIRECT_ATLASSIAN_MCP_URL or "", "direct_atlassian_url", "direct_atlassian_save"
            )

        if SHOW_CUSTOMER_BILLING:
            _direct_server_expander(
                "Customer Billing", DIRECT_CUSTOMER_BILLING_MCP_URL or "", "direct_billing_url", "direct_billing_save"
            )

        st.markdown("---")
        if _TICKET_LIST:
            st.subheader("🎫 Recent Tickets")
            for _tid in _TICKET_LIST:
                st.markdown(f"- `{_tid}`")
            st.markdown("---")
        st.subheader("📝 Suggested Queries")
        _INSECURE_AGENT_PROMPTS = [
            ("Threat Protection",                   "Tell me details about KAN-19"),
            ("Data Privacy: Topics (Custom)",       "Tell me details about KAN-47."),
            ("Data Privacy: Entities (Redact)",     "Give me details of KAN-46"),
            ("Agent Access : Destructive Actions",  "Delete following jira ticket - KAN-25."),
            # ("Data Privacy: Topics (Health)",       "Tell me details about KAN-22"),
        ]
        for _lbl, _txt in _INSECURE_AGENT_PROMPTS:
            st.markdown('<span class="prompt-use-btn-marker"></span>', unsafe_allow_html=True)
            _c1, _c2 = st.columns([3, 1])
            with _c1:
                st.caption(f"**{_lbl}**")
            with _c2:
                if st.button("→", key=f"insecure_agent_prompt_{_lbl}", help="Use this prompt"):
                    st.session_state.direct_mcp_query_input = _txt
                    st.rerun()
            st.text_area(_lbl, value=_txt, height=68, disabled=True,
                         key=f"insecure_agent_prompt_ta_{_lbl}", label_visibility="collapsed")

        st.subheader("📊 Statistics")
        st.metric("Queries", len(st.session_state.get("direct_mcp_responses", [])))

    elif mode == "Safe Agent":
        st.subheader("⚙️ MCP Servers")

        def _server_expander(label, env_url, url_key, env_key, key_key, save_key):
            """Render URL + API key inputs for one MCP server. Returns (url, api_key)."""
            is_set = bool(st.session_state.get(url_key) or env_url)
            badge = "🟢" if is_set else "⚪"
            with st.expander(f"{label}  {badge}", expanded=False):
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
                pebblo_user=st.session_state.get("mcp_user_input") or None,
                pebblo_user_groups=st.session_state.get("mcp_groups_input") or None,
            )

        if SHOW_ATLASSIAN_OAUTH:
            _server_expander(
                "Atlassian (OAuth)", ATLASSIAN_MCP_URL or "", "atlassian_url",
                ATLASSIAN_API_KEY or "", "atlassian_api_key", "atlassian_save"
            )
            render_oauth_connect_button(
                "atlassian", "Atlassian",
                mcp_url=st.session_state.get("atlassian_url", "") or ATLASSIAN_MCP_URL or "",
                redirect_uri=_MAIN_REDIRECT_URI,
                button_key="atlassian_oauth_btn",
                pebblo_headers=_pebblo_headers_for_oauth(),
            )

        if SHOW_ATLASSIAN_DOCKER:
            _server_expander(
                "Atlassian", ATLASSIAN_DOCKER_MCP_URL or "", "atlassian_docker_url",
                ATLASSIAN_DOCKER_API_KEY or "", "atlassian_docker_api_key", "atlassian_docker_save"
            )

        if SHOW_CUSTOMER_BILLING:
            _server_expander(
                "Customer Billing", CUSTOMER_BILLING_MCP_URL or "", "billing_url",
                CUSTOMER_BILLING_API_KEY or "", "billing_api_key", "billing_save"
            )

        # st.markdown("---")
        # st.subheader("👤 User Context")
        # mcp_user_input = st.text_input(
        #     "User",
        #     key="mcp_user_input",
        #     placeholder="Leave empty to use env",
        # )
        # mcp_groups_input = st.text_input(
        #     "User Groups",
        #     key="mcp_groups_input",
        #     placeholder="Leave empty to use env",
        # )

        st.markdown("---")
        if _TICKET_LIST:
            st.subheader("🎫 Recent Tickets")
            for _tid in _TICKET_LIST:
                st.markdown(f"- `{_tid}`")
            st.markdown("---")
        st.subheader("📝 Suggested Queries")
        _AGENT_PROMPTS = [
            ("Threat Protection",                   "Tell me details about KAN-19"),
            ("Data Privacy: Topics (Custom)",       "Tell me details about KAN-47."),
            ("Data Privacy: Entities (Redact)",     "Give me details of KAN-46"),
            ("Agent Access : Destructive Actions",  "Delete following jira ticket - KAN-25."),
            # ("Data Privacy: Topics (Health)",       "Tell me details about KAN-22"),
        ]
        for _lbl, _txt in _AGENT_PROMPTS:
            st.markdown('<span class="prompt-use-btn-marker"></span>', unsafe_allow_html=True)
            _c1, _c2 = st.columns([3, 1])
            with _c1:
                st.caption(f"**{_lbl}**")
            with _c2:
                if st.button("→", key=f"safe_agent_prompt_{_lbl}", help="Use this prompt"):
                    st.session_state.mcp_query_input = _txt
                    st.rerun()
            st.text_area(_lbl, value=_txt, height=68, disabled=True,
                         key=f"safe_agent_prompt_ta_{_lbl}", label_visibility="collapsed")

        st.subheader("📊 Statistics")
        st.metric("Queries", len(st.session_state.mcp_responses))


# ---------------------------------------------------------------------------
# Main content area
# ---------------------------------------------------------------------------

_welcome_user = st.session_state.get("selected_pebblo_user", "") or None
_welcome_group = (_get_active_pebblo_groups().split(",")[0].strip()) or None
st.markdown(get_welcome_html(user_email=_welcome_user, user_team=_welcome_group), unsafe_allow_html=True)

if mode == "Safe Infer":
    for message in st.session_state.chat_history:
        display_chat_message(
            role=message["role"],
            content=message["content"],
            model=message.get("model", ""),
            timestamp=message.get("timestamp", ""),
        )
        if message["role"] == "assistant" and message.get("cited_files"):
            st.markdown(_render_citations(message["cited_files"]), unsafe_allow_html=True)

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
            with st.chat_message("assistant"):
                response = st.write_stream(
                    stream_open_ai(
                        message=user_input,
                        model=model,
                        api_key=st.session_state.api_key,
                        pebblo_user=st.session_state.get("selected_pebblo_user", ""),
                        pebblo_user_groups=_get_active_pebblo_groups(),
                    )
                )
            _cited = st.session_state.pop("_cited_files", [])
            if _cited:
                st.markdown(_render_citations(_cited), unsafe_allow_html=True)
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": response,
                "model": st.session_state.selected_model,
                "timestamp": time.strftime("%H:%M:%S"),
                "cited_files": _cited,
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

elif mode == "InSecure Infer":
    for message in st.session_state.direct_chat_history:
        display_chat_message(
            role=message["role"],
            content=message["content"],
            model=message.get("model", ""),
            timestamp=message.get("timestamp", ""),
        )

    user_input_direct = st.text_area(
        "Type your message here:",
        height=100,
        placeholder="Ask me anything! Powered directly by OpenAI.",
        key="direct_user_input",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        direct_send = st.button("🚀 Send", type="primary", key="direct_send_btn")

    if direct_send and user_input_direct.strip():
        st.session_state.direct_chat_history.append({
            "role": "user",
            "content": user_input_direct,
            "timestamp": time.strftime("%H:%M:%S"),
        })
        display_chat_message("user", user_input_direct)

        direct_model = (st.session_state.get("direct_model") or MODEL or "gpt-5").strip()

        try:
            with st.chat_message("assistant"):
                response = st.write_stream(
                    stream_direct_openai(
                        message=user_input_direct,
                        model=direct_model,
                    )
                )
            st.session_state.direct_chat_history.append({
                "role": "assistant",
                "content": response,
                "model": direct_model,
                "timestamp": time.strftime("%H:%M:%S"),
            })
        except Exception as e:
            error_message = f"❌ Error: {str(e)}"
            st.error(error_message)
            st.session_state.direct_chat_history.append({
                "role": "assistant",
                "content": error_message,
                "timestamp": time.strftime("%H:%M:%S"),
            })

        st.rerun()

elif mode == "InSecure Agent":
    if "direct_mcp_responses" not in st.session_state:
        st.session_state.direct_mcp_responses = []
    if "direct_mcp_tools_used" not in st.session_state:
        st.session_state.direct_mcp_tools_used = []

    direct_mcp_query = st.text_area(
        "Enter your query:",
        height=100,
        placeholder="e.g., What is the status of ticket ABC-123?",
        key="direct_mcp_query_input",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        direct_mcp_send = st.button("🚀 Send", type="primary", key="direct_mcp_send_btn")

    if direct_mcp_send and direct_mcp_query.strip():
        direct_mcp_servers = build_direct_mcp_servers(
            atlassian_url=st.session_state.get("direct_atlassian_url", "") if SHOW_ATLASSIAN_DOCKER else "",
            atlassian_oauth_url=st.session_state.get("direct_atlassian_oauth_url", "") if SHOW_ATLASSIAN_OAUTH else "",
            atlassian_token=get_oauth_token("direct_atlassian") if SHOW_ATLASSIAN_OAUTH else None,
            billing_url=st.session_state.get("direct_billing_url", "") if SHOW_CUSTOMER_BILLING else "",
        )
        st.session_state.direct_mcp_responses = []
        st.session_state.direct_mcp_tools_used = []
        run_mcp_query(
            user_input=direct_mcp_query,
            mcp_servers=direct_mcp_servers,
            pebblo_user="",
            pebblo_user_groups="",
        )

elif mode == "Safe Agent":
    mcp_query = st.text_area(
        "Enter your query:",
        height=100,
        placeholder="e.g., What is the status of ticket ABC-123?",
        key="mcp_query_input",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        mcp_send = st.button("🚀 Send", type="primary", key="mcp_send_btn")

    if mcp_send and mcp_query.strip():
        _active_pebblo_user = st.session_state.get("selected_pebblo_user", "") or st.session_state.get("mcp_user_input", "")
        _active_pebblo_groups = _get_active_pebblo_groups()
        mcp_servers = build_mcp_servers(
            atlassian_url=st.session_state.get("atlassian_url", "") if SHOW_ATLASSIAN_OAUTH else "",
            atlassian_api_key=st.session_state.get("atlassian_api_key", "") if SHOW_ATLASSIAN_OAUTH else "",
            atlassian_docker_url=st.session_state.get("atlassian_docker_url", "") if SHOW_ATLASSIAN_DOCKER else "",
            atlassian_docker_api_key=st.session_state.get("atlassian_docker_api_key", "") if SHOW_ATLASSIAN_DOCKER else "",
            billing_url=st.session_state.get("billing_url", "") if SHOW_CUSTOMER_BILLING else "",
            billing_api_key=st.session_state.get("billing_api_key", "") if SHOW_CUSTOMER_BILLING else "",
            pebblo_user=_active_pebblo_user,
            pebblo_user_groups=_active_pebblo_groups,
            atlassian_token=get_oauth_token("atlassian") if SHOW_ATLASSIAN_OAUTH else None,
        )
        st.session_state.mcp_responses = []
        st.session_state.mcp_tools_used = []
        run_mcp_query(
            user_input=mcp_query,
            mcp_servers=mcp_servers,
            pebblo_user=_active_pebblo_user,
            pebblo_user_groups=_active_pebblo_groups,
        )

# Footer
st.markdown("---")
st.markdown(FOOTER_HTML, unsafe_allow_html=True)
