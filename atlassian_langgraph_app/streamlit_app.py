import streamlit as st
import asyncio
import os
from main import process_query

# Page configuration
st.set_page_config(
    page_title="Ask Atlassian (via LangGraph)",
    page_icon="🔧",
    layout="wide"
)

# Title
st.title("Ask Atlassian (via LangGraph)")

# Initialize session state for storing responses
if 'responses' not in st.session_state:
    st.session_state.responses = []

def run_async_query(user_input: str):
    """Wrapper to run async query in Streamlit"""
    async def async_wrapper():
        try:
            final_answer = await process_query(user_input)
            st.session_state.responses.append(final_answer)
            st.rerun()
        except Exception as e:
            st.session_state.responses.append(f"Error: {str(e)}")
            st.rerun()
    
    # Run the async function
    asyncio.run(async_wrapper())

# User input section
st.subheader("Enter your query")
user_query = st.text_area(
    "Ask about JIRA tickets, Confluence pages, or other Atlassian resources:",
    height=100,
    placeholder="e.g., What is the status of JIRA ticket ABC-9?"
)

# Submit button
if st.button("Submit Query", type="primary"):
    if user_query.strip():
        # Clear previous responses
        st.session_state.responses = []
        
        # Show spinner while processing
        with st.spinner("Processing your query..."):
            try:
                # Process the query
                run_async_query(user_query)
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
    else:
        st.warning("Please enter a query.")

# Display responses
if st.session_state.responses:
    st.subheader("Answer")
    
    # Display the final answer
    for response in st.session_state.responses:
        st.markdown(response)

# Sidebar with information
with st.sidebar:
    st.header("About")
    st.write("""
    This app uses LangGraph to process queries about Atlassian resources 
    (JIRA, Confluence, etc.) through the MCP (Model Context Protocol) server.
    
    **Features:**
    - Query JIRA tickets
    - Search Confluence pages
    - Get project information
    - Clean, parsed answers
    """)
    
    st.header("Requirements")
    st.write("""
    - Atlassian MCP server running 
    - OpenAI API key configured
    - Docker container for MCP server
    """)
    
    # Clear responses button
    if st.button("Clear Responses"):
        st.session_state.responses = []
        st.rerun() 