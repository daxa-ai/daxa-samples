"""Safe MCP utilities: LangGraph orchestration with multiple MCP servers using SafeInfer LLM."""
import asyncio
import os
import logging
from typing import Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

_env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_env_path)

from utils import API_BASE_URL, API_KEY, MODEL, X_PEBBLO_USER, X_PEBBLO_USER_GROUPS

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Per-server Pebblo API key defaults (each server has its own key)
ATLASSIAN_API_KEY = os.getenv("ATLASSIAN_API_KEY", "").strip() or None
CUSTOMER_BILLING_API_KEY = os.getenv("CUSTOMER_BILLING_API_KEY", "").strip() or None
ATLASSIAN_MCP_URL = os.getenv("ATLASSIAN_MCP_URL", "").strip() or None
ATLASSIAN_API_KEY = os.getenv("ATLASSIAN_API_KEY", "").strip() or None
CUSTOMER_BILLING_MCP_URL = os.getenv("CUSTOMER_BILLING_MCP_URL", "").strip() or None

# Atlassian Docker — no OAuth, Pebblo key only (via Proxima, streamable_http)
ATLASSIAN_DOCKER_MCP_URL = os.getenv("ATLASSIAN_DOCKER_MCP_URL", "").strip() or None
ATLASSIAN_DOCKER_API_KEY = os.getenv("ATLASSIAN_DOCKER_API_KEY", "").strip() or None

# Direct Agent — upstream URLs (no Proxima gateway)
DIRECT_ATLASSIAN_MCP_URL = os.getenv("DIRECT_ATLASSIAN_MCP_URL", "").strip() or None
DIRECT_CUSTOMER_BILLING_MCP_URL = os.getenv("DIRECT_CUSTOMER_BILLING_MCP_URL", "").strip() or None

# Feature flags — control sidebar visibility
SHOW_ATLASSIAN_OAUTH = os.getenv("ATLASSIAN_OAUTH", "false").strip().lower() == "true"
SHOW_ATLASSIAN_DOCKER = os.getenv("ATLASSIAN_DOCKER", "false").strip().lower() == "true"
SHOW_CUSTOMER_BILLING = os.getenv("CUSTOMER_BILLING", "false").strip().lower() == "true"


def _pebblo_mcp_headers(
    pebblo_user: Optional[str] = None,
    pebblo_user_groups: Optional[str] = None,
) -> Dict[str, str]:
    """Pebblo gateway user/group headers for MCP requests.

    Does NOT set x-pebblo-auth — that is always per-server (set in build_mcp_servers
    via the server-specific API key). Only x-pebblo-users and x-pebblo-user-groups
    are set here as they are shared across all servers for a given request.
    """
    headers: Dict[str, str] = {}
    user = (pebblo_user or X_PEBBLO_USER or "").strip()
    if user:
        headers["x-pebblo-users"] = user
    groups = (pebblo_user_groups or X_PEBBLO_USER_GROUPS or "").strip()
    if groups:
        headers["x-pebblo-user-groups"] = groups
    return headers


def build_mcp_servers(
    atlassian_url: Optional[str] = None,
    atlassian_api_key: Optional[str] = None,
    atlassian_docker_url: Optional[str] = None,
    atlassian_docker_api_key: Optional[str] = None,
    billing_url: Optional[str] = None,
    billing_api_key: Optional[str] = None,
    pebblo_user: Optional[str] = None,
    pebblo_user_groups: Optional[str] = None,
    atlassian_token: Optional[str] = None,
) -> Dict[str, dict]:
    """Build MultiServerMCPClient-compatible server config dict.

    Atlassian route through the Pebblo gateway — authenticated via
    x-pebblo-auth / x-pebblo-users / x-pebblo-user-groups headers.
    When an OAuth access token is available for a service it is also sent as
    Authorization: Bearer <token> so the upstream provider can verify the user.
    Customer Billing connects directly with no auth headers.
    A server is omitted when its URL is empty.
    """
    servers: Dict[str, dict] = {}
    pebblo_headers = _pebblo_mcp_headers(pebblo_user, pebblo_user_groups)

    def _headers_for(server_key: Optional[str], oauth_token: Optional[str] = None) -> Dict[str, str]:
        """Build headers for one server: use its own API key if provided, else the global one."""
        h = dict(pebblo_headers)
        key = (server_key or "").strip()
        if key:
            # Accept bare key or already-prefixed "Bearer ..."
            h["x-pebblo-auth"] = key if key.lower().startswith("bearer ") else f"Bearer {key}"
        if oauth_token:
            h["Authorization"] = f"Bearer {oauth_token}"
        return h

    # Atlassian — SSE transport (upstream is https://mcp.atlassian.com/v1/sse)
    a_url = (atlassian_url or ATLASSIAN_MCP_URL or "").strip()
    if a_url:
        servers["atlassian"] = {
            "url": a_url,
            "transport": "sse",
            "headers": _headers_for(atlassian_api_key or ATLASSIAN_API_KEY, atlassian_token),
        }

    # Atlassian Docker — no OAuth, Pebblo key only, streamable_http
    ad_url = (atlassian_docker_url or ATLASSIAN_DOCKER_MCP_URL or "").strip()
    if ad_url:
        servers["atlassian-docker"] = {
            "url": ad_url,
            "transport": "streamable_http",
            "headers": _headers_for(atlassian_docker_api_key or ATLASSIAN_DOCKER_API_KEY),
        }

    # Customer Billing — per-server key (no OAuth needed)
    b_url = (billing_url or CUSTOMER_BILLING_MCP_URL or "").strip()
    if b_url:
        servers["customer-billing"] = {
            "url": b_url,
            "transport": "streamable_http",
            "headers": _headers_for(billing_api_key or CUSTOMER_BILLING_API_KEY),
        }

    return servers


def build_direct_mcp_servers(
    atlassian_url: Optional[str] = None,
    atlassian_oauth_url: Optional[str] = None,
    atlassian_token: Optional[str] = None,
    billing_url: Optional[str] = None,
) -> Dict[str, dict]:
    """Build MCP server config for Direct Agent mode.

    No Pebblo headers at all (no x-pebblo-auth, no x-pebblo-users, no x-pebblo-user-groups).
    Only the OAuth Authorization header is sent where a token is available.
    """
    servers: Dict[str, dict] = {}

    # Atlassian Docker — no auth, streamable_http; falls back to DIRECT_ATLASSIAN_MCP_URL
    a_url = (atlassian_url or DIRECT_ATLASSIAN_MCP_URL or "").strip()
    if a_url:
        servers["atlassian"] = {
            "url": a_url,
            "transport": "streamable_http",
            "headers": {},
        }

    # Atlassian OAuth — SSE, OAuth Bearer token only
    ao_url = (atlassian_oauth_url or ATLASSIAN_MCP_URL or "").strip()
    if ao_url:
        headers: Dict[str, str] = {}
        if atlassian_token:
            headers["Authorization"] = f"Bearer {atlassian_token}"
        servers["atlassian-oauth"] = {
            "url": ao_url,
            "transport": "sse",
            "headers": headers,
        }

    # Customer Billing — no auth headers; falls back to DIRECT_CUSTOMER_BILLING_MCP_URL
    b_url = (billing_url or DIRECT_CUSTOMER_BILLING_MCP_URL or "").strip()
    if b_url:
        servers["customer-billing"] = {
            "url": b_url,
            "transport": "streamable_http",
            "headers": {},
        }

    return servers


def _get_chat_model() -> ChatOpenAI:
    """Build ChatOpenAI using OpenAI directly (same as atlassian_langgraph_app)."""
    return ChatOpenAI(model=MODEL or "gpt-4o-mini")


async def setup_langgraph(
    mcp_servers: Dict[str, dict],
    pebblo_user: Optional[str] = None,
    pebblo_user_groups: Optional[str] = None,
):
    """Build and compile LangGraph bound to all provided MCP servers."""
    if not mcp_servers:
        raise ValueError(
            "No MCP servers configured. Provide at least one server URL."
        )

    # Try each server individually so a single failing server doesn't block the others
    all_tools = []
    for server_name, server_config in mcp_servers.items():
        try:
            client = MultiServerMCPClient({server_name: server_config})
            server_tools = await client.get_tools()
            logging.info("[MCP] %s: connected, %d tools: %s",
                         server_name, len(server_tools), [t.name for t in server_tools])
            all_tools.extend(server_tools)
        except Exception as exc:
            # Unwrap ExceptionGroup (Python 3.11+)
            inner = exc.exceptions[0] if hasattr(exc, "exceptions") else exc
            logging.warning("[MCP] %s: skipped — %s: %s",
                            server_name, type(inner).__name__, inner)

    tools = all_tools
    if not tools:
        raise ValueError("No tools available — all configured MCP servers failed to connect.")
    logging.info(f"Retrieved {len(tools)} tools from MCP servers: {[tool.name for tool in tools]}")
    tools_by_name = {tool.name: tool for tool in tools}
    chat_model = _get_chat_model()
    model_with_tools = chat_model.bind_tools(tools)

    async def async_tool_node(state: MessagesState):
        last_message = state["messages"][-1]
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {"messages": []}
        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]
            if tool_name in tools_by_name:
                result = await tools_by_name[tool_name].ainvoke(tool_args)
                tool_messages.append(
                    ToolMessage(
                        content=str(result),
                        name=tool_name,
                        tool_call_id=tool_call_id,
                    )
                )
        return {"messages": tool_messages}

    def should_continue(state: MessagesState):
        last_message = state["messages"][-1]
        has_calls = hasattr(last_message, "tool_calls") and bool(last_message.tool_calls)
        logging.info("[Graph] should_continue → %s (tool_calls=%s)",
                     "tools" if has_calls else "END",
                     [tc["name"] for tc in last_message.tool_calls] if has_calls else [])
        return "tools" if has_calls else END

    async def call_model(state: MessagesState):
        logging.info("[Graph] call_model: invoking LLM with %d messages", len(state["messages"]))
        response = await model_with_tools.ainvoke(state["messages"])
        logging.info("[Graph] call_model: response type=%s, tool_calls=%s",
                     type(response).__name__,
                     [tc["name"] for tc in response.tool_calls] if hasattr(response, "tool_calls") and response.tool_calls else [])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("call_model", call_model)
    builder.add_node("tools", async_tool_node)
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges("call_model", should_continue)
    builder.add_edge("tools", "call_model")
    return builder.compile()


def extract_final_answer(stream_result) -> str:
    try:
        if "call_model" in stream_result and "messages" in stream_result["call_model"]:
            for message in stream_result["call_model"]["messages"]:
                if isinstance(message, AIMessage) and message.content:
                    return message.content.strip()
        return "No final answer found"
    except Exception as e:
        return f"Error extracting answer: {str(e)}"


def extract_tool_calls_from_step(step, node_name: str) -> List[str]:
    if node_name in step and "messages" in step[node_name]:
        for message in step[node_name]["messages"]:
            if hasattr(message, "tool_calls") and message.tool_calls:
                return [tc["name"] for tc in message.tool_calls]
    return []


def extract_tools_used(all_steps) -> List[str]:
    tools_used = set()
    for step in all_steps:
        for node_name in step:
            if node_name == "call_model":
                tools_used.update(extract_tool_calls_from_step(step, node_name))
    return list(tools_used)


async def stream_query_steps(
    user_input: str,
    mcp_servers: Dict[str, dict],
    pebblo_user: Optional[str] = None,
    pebblo_user_groups: Optional[str] = None,
):
    """Async generator: yields status lines and final answer while running the graph."""
    try:
        graph = await setup_langgraph(mcp_servers, pebblo_user, pebblo_user_groups)
        inputs = {"messages": [HumanMessage(content=user_input)]}
        yield "Analyzing your query..."

        all_steps = []
        async for step in graph.astream(inputs, config={"recursion_limit": 10}):
            all_steps.append(step)
            for node_name in step:
                if node_name == "call_model":
                    tool_calls = extract_tool_calls_from_step(step, node_name)
                    for tool_name in tool_calls:
                        yield f"Selected tool: {tool_name}"
                elif node_name == "tools":
                    if len(all_steps) > 1:
                        prev_step = all_steps[-2]
                        tool_calls = extract_tool_calls_from_step(prev_step, "call_model")
                        for tool_name in tool_calls:
                            yield f"Received response from {tool_name}"
                            await asyncio.sleep(0.5)
                            yield "Processing response..."

        if all_steps:
            final_answer = extract_final_answer(all_steps[-1])
            yield f"Final answer: {final_answer}"
            tools_used = extract_tools_used(all_steps)
            if tools_used:
                yield f"Tools used: {', '.join(tools_used)}"
            else:
                yield "No tools were used for this query"
        else:
            yield "No response generated"
    except Exception as e:
        logger = logging.getLogger(__name__)
        # Unwrap Python 3.11+ ExceptionGroup (raised by asyncio.TaskGroup / anyio)
        if hasattr(e, "exceptions"):
            for sub in e.exceptions:
                logger.error("[MCP] sub-exception: %s: %s", type(sub).__name__, sub)
            first = e.exceptions[0]
            yield f"Error: {type(first).__name__}: {first}"
        else:
            logger.error("[MCP] error: %s: %s", type(e).__name__, e)
            yield f"Error: {type(e).__name__}: {e}"
