import streamlit as st
import asyncio
import os
from main import stream_query_steps, process_query

# Page configuration
st.set_page_config(
    page_title="Atlassian Agent",
    page_icon="🔧",
    layout="wide"
)

# Title
st.title("Atlassian Agent")

# Initialize session state for storing responses
if 'responses' not in st.session_state:
    st.session_state.responses = []

if 'tools_used' not in st.session_state:
    st.session_state.tools_used = []

async def run_streaming_query(user_input: str):
    """Run the streaming query and update Streamlit UI in real-time"""
    try:
        # Initialize response tracking
        current_response = ""
        tools_used = []
        intermediate_steps = []
        steps_container = st.empty()
        tools_displayed = False
        
        # Stream the query steps
        async for step_message in stream_query_steps(user_input):
            # Display the step message as plain text
            if step_message.startswith("Final answer"):
                # Extract the actual answer and display with header
                current_response = step_message.replace("Final answer: ", "")
                # Display all intermediate steps first
                if intermediate_steps:
                    steps_container.markdown("<br>".join([f"<small>{step}</small>" for step in intermediate_steps]), unsafe_allow_html=True)
                
                # Display tools used before final answer
                if tools_used and not tools_displayed:
                    st.markdown("<hr style='margin-top:5px; margin-bottom:5px;'>", unsafe_allow_html=True)
                    # st.markdown("---")  # Horizontal line above
                    st.subheader("Tools Used:")
                    for tool in tools_used:
                        st.markdown(f"• <span style='color: #3DC667; background-color: #1e1e1e; padding: 2px 6px; border-radius: 4px;'>{tool}</span>", unsafe_allow_html=True)
                    st.markdown("<hr style='margin-top:5px; margin-bottom:5px;'>", unsafe_allow_html=True)
                    # st.markdown("---")  # Horizontal line below
                    tools_displayed = True
                
                # Then display final answer
                st.subheader("Response:")
                st.markdown(current_response)
            elif step_message.startswith("Tools used"):
                # Extract tools for display
                tools_str = step_message.replace("Tools used: ", "")
                if tools_str != "No tools were used for this query":
                    tools_used = [tool.strip() for tool in tools_str.split(",")]
                else:
                    tools_used = []
            elif step_message.startswith("Error"):
                st.error("❌ " + step_message)
                current_response = step_message
            else:
                # Collect intermediate steps
                intermediate_steps.append(step_message)
                # Update the steps container with all collected steps
                steps_container.markdown("<br>".join([f"<small>{step}</small>" for step in intermediate_steps]), unsafe_allow_html=True)
                
                # Extract tool name for tracking if it's a tool selection
                if step_message.startswith("Selected tool"):
                    tool_name = step_message.replace("Selected tool: ", "")
                    if tool_name not in tools_used:
                        tools_used.append(tool_name)
            
        
        # Store the final response and tools used
        if current_response:
            st.session_state.responses.append(current_response)
            st.session_state.tools_used = tools_used
        
    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")
        st.session_state.responses.append(f"Error: {str(e)}")

def run_async_query(user_input: str):
    """Wrapper to run async query in Streamlit"""
    # Run the async function
    asyncio.run(run_streaming_query(user_input))

# User input section
st.subheader("Enter your query")
user_query = st.text_area(
    "Ask about Atlassian resources:",
    height=100,
    placeholder="e.g., What is the status of JIRA ticket ABC-9?"
)

# Submit button
if st.button("Submit Query", type="primary"):
    if user_query.strip():
        # Clear previous responses and containers
        st.session_state.responses = []
        st.session_state.tools_used = []
        
        # Process the query with streaming updates
        run_async_query(user_query)
    else:
        st.warning("Please enter a query.")

# Sidebar with information
with st.sidebar:
    st.header("About")
    st.write("""
    This app uses LangGraph to process queries about JIRA tickets, Confluence pages, and other Atlassian resources through the MCP (Model Context Protocol) server.
    
    **Features:**
    - Query JIRA, Confluence, and other Atlassian resources
    - Clean, parsed answers
    """)
    
    # Clear responses button
    if st.button("Clear Responses"):
        st.session_state.responses = []
        st.session_state.tools_used = []
        st.rerun() 