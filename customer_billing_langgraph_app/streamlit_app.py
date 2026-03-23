import streamlit as st
import asyncio
from main import stream_query_steps

st.set_page_config(
    page_title="Customer Billing (MCP)",
    page_icon="📄",
    layout="wide",
)

st.title("Customer Billing Assistant")

if "responses" not in st.session_state:
    st.session_state.responses = []

if "tools_used" not in st.session_state:
    st.session_state.tools_used = []


async def run_streaming_query(user_input: str):
    """Run the streaming query and update Streamlit UI in real-time."""
    try:
        current_response = ""
        tools_used = []
        intermediate_steps = []
        steps_container = st.empty()
        tools_displayed = False

        async for step_message in stream_query_steps(user_input):
            if step_message.startswith("Final answer"):
                current_response = step_message.replace("Final answer: ", "")
                if intermediate_steps:
                    steps_container.markdown(
                        "<br>".join([f"<small>{step}</small>" for step in intermediate_steps]),
                        unsafe_allow_html=True,
                    )
                if tools_used and not tools_displayed:
                    st.markdown("<hr style='margin-top:5px; margin-bottom:5px;'>", unsafe_allow_html=True)
                    st.subheader("Tools Used:")
                    for tool in tools_used:
                        st.markdown(
                            f"• <span style='color: #3DC667; background-color: #1e1e1e; padding: 2px 6px; border-radius: 4px;'>{tool}</span>",
                            unsafe_allow_html=True,
                        )
                    st.markdown("<hr style='margin-top:5px; margin-bottom:5px;'>", unsafe_allow_html=True)
                    tools_displayed = True
                st.subheader("Response:")
                st.markdown(current_response)
            elif step_message.startswith("Tools used"):
                tools_str = step_message.replace("Tools used: ", "")
                if tools_str != "No tools were used for this query":
                    tools_used = [tool.strip() for tool in tools_str.split(",")]
                else:
                    tools_used = []
            elif step_message.startswith("Error"):
                st.error("❌ " + step_message)
                current_response = step_message
            else:
                intermediate_steps.append(step_message)
                steps_container.markdown(
                    "<br>".join([f"<small>{step}</small>" for step in intermediate_steps]),
                    unsafe_allow_html=True,
                )
                if step_message.startswith("Selected tool"):
                    tool_name = step_message.replace("Selected tool: ", "")
                    if tool_name not in tools_used:
                        tools_used.append(tool_name)

        if current_response:
            st.session_state.responses.append(current_response)
            st.session_state.tools_used = tools_used
    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")
        st.session_state.responses.append(f"Error: {str(e)}")


def run_async_query(user_input: str):
    asyncio.run(run_streaming_query(user_input))


st.subheader("Enter your query")
user_query = st.text_area(
    "Ask about customer billing (invoices, balances, etc.):",
    height=100,
    placeholder="e.g., Summarize open invoices for account ACME-123",
)

if st.button("Submit Query", type="primary"):
    if user_query.strip():
        st.session_state.responses = []
        st.session_state.tools_used = []
        run_async_query(user_query)
    else:
        st.warning("Please enter a query.")

with st.sidebar:
    st.header("About")
    st.write(
        """
    This app uses LangGraph to answer questions about customer billing—such as invoices,
    balances, and account details—using a connected billing assistant (MCP).

    **Features:**
    - Ask in plain language; get clear, parsed answers
    - See which billing tools were used along the way
    """
    )
    if st.button("Clear Responses"):
        st.session_state.responses = []
        st.session_state.tools_used = []
        st.rerun()
