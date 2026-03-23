# Customer Billing MCP LangGraph Example (MCP server has no separate auth;
# Pebblo gateway uses x-pebblo-auth only.)
import os
import asyncio
from typing import Dict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

_env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_env_path, override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip() or None
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "").strip() or None
PEBBLO_API_KEY = os.getenv("PEBBLO_API_KEY", "").strip() or None
X_PEBBLO_USER = os.getenv("X_PEBBLO_USER")
X_PEBBLO_USER_GROUPS = os.getenv("X_PEBBLO_USER_GROUPS")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")
if not MCP_SERVER_URL:
    raise ValueError("MCP_SERVER_URL environment variable is required")
if not PEBBLO_API_KEY:
    raise ValueError("PEBBLO_API_KEY environment variable is required")


def _mcp_gateway_headers() -> Dict[str, str]:
    """Headers for Pebblo MCP gateway: x-pebblo-auth Bearer token; optional user context."""
    headers: Dict[str, str] = {"x-pebblo-auth": f"Bearer {PEBBLO_API_KEY}"}
    user = X_PEBBLO_USER.strip() if (X_PEBBLO_USER and X_PEBBLO_USER.strip()) else ""
    if user:
        headers["X-PEBBLO-USER"] = user
    groups = (
        X_PEBBLO_USER_GROUPS.strip()
        if (X_PEBBLO_USER_GROUPS and X_PEBBLO_USER_GROUPS.strip())
        else ""
    )
    if groups:
        headers["X-PEBBLO-USER-GROUPS"] = groups
    return headers

chat_model = ChatOpenAI(model="gpt-4o-mini")


async def setup_langgraph():
    """Build and compile LangGraph with Customer Billing MCP tools."""
    server_config = {
        "url": MCP_SERVER_URL,
        "transport": "streamable_http",
        "headers": _mcp_gateway_headers(),
    }

    mcp_client = MultiServerMCPClient({"customer-billing": server_config})
    tools = await mcp_client.get_tools()
    tools_by_name = {tool.name: tool for tool in tools}
    model_with_tools = chat_model.bind_tools(tools)

    async def async_tool_node(state: MessagesState):
        messages = state["messages"]
        last_message = messages[-1]

        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {"messages": []}

        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]

            if tool_name in tools_by_name:
                result = await tools_by_name[tool_name].ainvoke(tool_args)
                tool_message = ToolMessage(
                    content=str(result),
                    name=tool_name,
                    tool_call_id=tool_call_id,
                )
                tool_messages.append(tool_message)

        return {"messages": tool_messages}

    def should_continue(state: MessagesState):
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    def call_model(state: MessagesState):
        messages = state["messages"]
        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("call_model", call_model)
    builder.add_node("tools", async_tool_node)
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges("call_model", should_continue)
    builder.add_edge("tools", "call_model")
    return builder.compile()


def extract_final_answer(stream_result):
    """Extract the final answer from the stream result."""
    try:
        if "call_model" in stream_result and "messages" in stream_result["call_model"]:
            messages = stream_result["call_model"]["messages"]
            for message in messages:
                if isinstance(message, AIMessage) and message.content:
                    return message.content.strip()
        return "No final answer found"
    except Exception as e:
        return f"Error extracting answer: {str(e)}"


def extract_tool_calls_from_step(step, node_name):
    """Extract tool call names from a graph step for a node."""
    if node_name in step and "messages" in step[node_name]:
        messages = step[node_name]["messages"]
        for message in messages:
            if hasattr(message, "tool_calls") and message.tool_calls:
                return [tool_call["name"] for tool_call in message.tool_calls]
    return []


def extract_tools_used(stream_result):
    """Collect all tool names invoked during the run."""
    tools_used = set()
    for step in stream_result:
        for node_name in step:
            if node_name == "call_model":
                tools_used.update(extract_tool_calls_from_step(step, node_name))
    return list(tools_used)


async def stream_query_steps(user_input: str):
    """Stream status lines while the graph runs."""
    try:
        graph = await setup_langgraph()
        inputs = {"messages": [HumanMessage(content=user_input)]}
        yield "Analyzing your query..."

        all_steps = []
        async for step in graph.astream(inputs, config={"recursion_limit": 10}):
            all_steps.append(step)
            for node_name, node_data in step.items():
                if node_name == "call_model":
                    tool_calls = extract_tool_calls_from_step(step, node_name)
                    if tool_calls:
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
        yield f"Error: {str(e)}"


async def process_query(user_input: str):
    """Run the graph and return the final assistant text only."""
    try:
        graph = await setup_langgraph()
        inputs = {"messages": [HumanMessage(content=user_input)]}
        final_step = None
        async for step in graph.astream(inputs, config={"recursion_limit": 10}):
            final_step = step
        if final_step:
            return extract_final_answer(final_step)
        return "No response generated"
    except Exception as e:
        return f"Error: {str(e)}"
