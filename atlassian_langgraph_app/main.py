# Atlassian MCP LangGraph Example
import os
import asyncio
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

# Load environment variables from .env file
load_dotenv(override=True)

# Get environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL")

# Validate required environment variables
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")
if not MCP_SERVER_URL:
    raise ValueError("MCP_SERVER_URL environment variable is required")

# Load chat model
chat_model = ChatOpenAI(model="gpt-4o-mini")

async def setup_langgraph():
    """Setup and return the LangGraph with Atlassian MCP tools"""
    # Connect to Atlassian MCP server via Docker
    mcp_client = MultiServerMCPClient(
        {
            "mcp-atlassian": {
                "url": MCP_SERVER_URL,
                "transport": "streamable_http" 
            }
        }
    )

    # Get tools from the client
    tools = await mcp_client.get_tools()
    
    # Create a mapping of tool names to tools
    tools_by_name = {tool.name: tool for tool in tools}

    # Bind tools to model
    model_with_tools = chat_model.bind_tools(tools)

    # Define custom async tool node
    async def async_tool_node(state: MessagesState):
        messages = state["messages"]
        last_message = messages[-1]
        
        if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
            return {"messages": []}
        
        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]
            
            if tool_name in tools_by_name:
                # Call the async tool
                result = await tools_by_name[tool_name].ainvoke(tool_args)
                tool_message = ToolMessage(
                    content=str(result),
                    name=tool_name,
                    tool_call_id=tool_call_id
                )
                tool_messages.append(tool_message)
        
        return {"messages": tool_messages}

    # Define routing function
    def should_continue(state: MessagesState):
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return END

    # Define model function
    def call_model(state: MessagesState):
        messages = state["messages"]
        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    # Build the LangGraph
    builder = StateGraph(MessagesState)

    builder.add_node("call_model", call_model)
    builder.add_node("tools", async_tool_node)

    builder.add_edge(START, "call_model")
    builder.add_conditional_edges(
        "call_model",
        should_continue,
    )
    builder.add_edge("tools", "call_model")

    return builder.compile()

def extract_final_answer(stream_result):
    """Extract the final answer from the stream result"""
    try:
        # Get the last step which should contain the final AI message
        if 'call_model' in stream_result and 'messages' in stream_result['call_model']:
            messages = stream_result['call_model']['messages']
            for message in messages:
                if isinstance(message, AIMessage) and message.content:
                    return message.content.strip()
        return "No final answer found"
    except Exception as e:
        return f"Error extracting answer: {str(e)}"

async def process_query(user_input: str):
    """Process the user query through the LangGraph and return only the final answer"""
    try:
        # Setup the graph
        graph = await setup_langgraph()
        
        # Prepare inputs
        inputs = {"messages": [HumanMessage(content=user_input)]}
        
        # Collect all steps to find the final answer
        final_step = None
        async for step in graph.astream(inputs, config={"recursion_limit": 5}):
            final_step = step
        
        # Extract and return only the final answer
        if final_step:
            final_answer = extract_final_answer(final_step)
            return final_answer
        else:
            return "No response generated"
            
    except Exception as e:
        return f"Error: {str(e)}"

