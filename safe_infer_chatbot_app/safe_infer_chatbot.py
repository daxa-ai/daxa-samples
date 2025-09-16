import os
import streamlit as st
import requests
import json
from typing import Dict, Any
import time

 

# Page configuration
st.set_page_config(
    page_title="Finance Ops Chatbot",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
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
</style>
""", unsafe_allow_html=True)

from utils import get_available_models

# API Configuration
API_KEY = os.getenv("PEBBLO_API_KEY", "")
API_BASE_URL = os.getenv("PROXIMA_HOST", "http://localhost")
USER_EMAIL = os.getenv("USER_EMAIL", "User")
USER_TEAM = os.getenv("USER_TEAM", "Finance Ops")
RESPONSE_API_ENDPOINT = f"{API_BASE_URL}/safe_infer/llm/v1/responses"
LLM_PROVIDER_API_ENDPOINT = f"{API_BASE_URL}/api/llm/provider"
AVAILABLE_MODELS, DEFAULT_MODEL = get_available_models()

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'selected_model' not in st.session_state:
    st.session_state.selected_model = DEFAULT_MODEL
if 'api_key' not in st.session_state:
    st.session_state.api_key = API_KEY

def test_api_connection() -> Dict[str, Any]:
    """Test the API connection"""
    try:
        response = requests.get(f"{API_BASE_URL}/safe_infer/healthz", timeout=5)
        if response.status_code == 200:
            return {"status": "success", "message": "API is accessible"}
        else:
            return {"status": "error", "message": f"API returned status {response.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "message": "Cannot connect to API. Please ensure the service is running."}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}

def call_safe_infer_api(message: str, model: str, api_key: str = "") -> Dict[str, Any]:
    """Call the SafeInfer API"""
    headers = {
        "Content-Type": "application/json"
    }
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "model": model,
        "input": message
    }
    
    try:
        response = requests.post(
            RESPONSE_API_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return {"status": "success", "data": response.json()}
        else:
            return {
                "status": "error", 
                "message": f"API Error {response.status_code}: {response.text}"
            }
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "Request timed out"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "message": "Cannot connect to API"}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}

def extract_response_content(api_response: Dict[str, Any]) -> str:
    """Extract the response content from the API response"""
    try:
        # Handle different response formats
        if 'response' in api_response:
            response_data = api_response['response']
            if isinstance(response_data, dict):
                if 'message' in response_data:
                    if isinstance(response_data['message'], str):
                        return response_data['message']
                    elif isinstance(response_data['message'], dict) and 'content' in response_data['message']:
                        return response_data['message']['content']
                elif 'content' in response_data:
                    return response_data['content']
            elif isinstance(response_data, str):
                return response_data
        
        # Check for direct content
        elif 'content' in api_response:
            return api_response['content']
        
        # Check for message field
        elif 'message' in api_response:
            if isinstance(api_response['message'], str):
                return api_response['message']
            elif isinstance(api_response['message'], dict) and 'content' in api_response['message']:
                return api_response['message']['content']
        
        # If none of the above, return the full response as JSON
        return json.dumps(api_response, indent=2)
        
    except Exception as e:
        return f"Error parsing response: {str(e)}"

def display_chat_message(role: str, content: str, model: str = "", timestamp: str = ""):
    """Display a chat message with proper styling"""
    if role == "user":
        st.markdown(f"""
        <div class="chat-message user-message">
            <strong>👤 You:</strong><br>
            {content}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="chat-message bot-message">
            <strong>🤖 AI Assistant:</strong><br>
            {content}
            <div class="model-info">
                Model: {model} | {timestamp}
            </div>
        </div>
        """, unsafe_allow_html=True)

# Main header
st.markdown("""
<div class="main-header">
    <h1>🛡️ Finance Ops Chatbot</h1>
    <p>Helpful assistant for Finance Ops team</p>
</div>
""", unsafe_allow_html=True)

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Model selection
    available_models = AVAILABLE_MODELS
    if available_models:
        st.subheader("🤖 Model Selection")
        selected_model = st.selectbox(
            "Choose a model:",
            available_models,
            index=available_models.index(st.session_state.selected_model)
        )
        st.session_state.selected_model = selected_model
    
    # API connection test
    st.subheader("🔗 API Status")
    if st.button("Test API Connection"):
        with st.spinner("Testing connection..."):
            result = test_api_connection()
            if result["status"] == "success":
                st.success(result["message"])
            else:
                st.error(result["message"])
    
    # Chat management
    st.subheader("💬 Chat Management")
    if st.button("Clear Chat History"):
        st.session_state.chat_history = []
        st.rerun()
    
    # Export chat
    if st.session_state.chat_history:
        chat_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": st.session_state.selected_model,
            "conversation": st.session_state.chat_history
        }
        st.download_button(
            label="📥 Export Chat",
            data=json.dumps(chat_data, indent=2),
            file_name=f"safe_infer_chat_{time.strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
    
    # Statistics
    st.subheader("📊 Statistics")
    st.metric("Messages", len(st.session_state.chat_history))
    st.metric("Current Model", st.session_state.selected_model)

# Welcome message
st.markdown(f"""
<div class="chat-message bot-message">
    <strong>🤖 AI Assistant:</strong><br>
    Welcome {USER_EMAIL}. {USER_TEAM} team!
</div>
""", unsafe_allow_html=True)


# Main chat interface
st.subheader("💬 Chat Interface")

# Display chat history
for message in st.session_state.chat_history:
    display_chat_message(
        role=message["role"],
        content=message["content"],
        model=message.get("model", ""),
        timestamp=message.get("timestamp", "")
    )

# User input
user_input = st.text_area(
    "Type your message here:",
    height=100,
    placeholder="Ask me anything! I'm powered by SafeInfer LLM API.",
    key="user_input"
)

# Send button
col1, col2 = st.columns([1, 4])
with col1:
    send_button = st.button("🚀 Send", type="primary")
with col2:
    regenerate_button = st.button("🔄 Regenerate Last Response")
    if regenerate_button and st.session_state.chat_history:
        # Remove the last bot response and regenerate
        while st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "assistant":
            st.session_state.chat_history.pop()
        if st.session_state.chat_history:
            # Store the last user message for regeneration
            last_user_message = st.session_state.chat_history[-1]["content"]
            # Process the regeneration
            if last_user_message.strip():
                # Add user message to history
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": last_user_message,
                    "timestamp": time.strftime("%H:%M:%S")
                })
                
                # Display user message
                display_chat_message("user", last_user_message)
                
                # Get AI response
                with st.spinner("🤖 AI is thinking..."):
                    result = call_safe_infer_api(
                        message=last_user_message,
                        model=st.session_state.selected_model,
                        api_key=st.session_state.api_key
                    )
                
                if result["status"] == "success":
                    # Extract response content
                    response_content = extract_response_content(result["data"])
                    
                    # Add bot response to history
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": response_content,
                        "model": st.session_state.selected_model,
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                    
                    # Display bot response
                    display_chat_message(
                        "assistant", 
                        response_content, 
                        st.session_state.selected_model,
                        time.strftime("%H:%M:%S")
                    )
                    
                    # Show classification info if available
                    if 'response' in result["data"] and isinstance(result["data"]["response"], dict):
                        response_data = result["data"]["response"]
                        if 'classification' in response_data:
                            classification = response_data['classification']
                            with st.expander("🔍 Response Analysis"):
                                st.json(classification)
                
                else:
                    error_message = f"❌ Error: {result['message']}"
                    st.error(error_message)
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": error_message,
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                
                st.rerun()

# Process user input
if send_button and user_input.strip():
    # Add user message to history
    st.session_state.chat_history.append({
        "role": "user",
        "content": user_input,
        "timestamp": time.strftime("%H:%M:%S")
    })
    
    # Display user message
    display_chat_message("user", user_input)
    
    # Get AI response
    with st.spinner("🤖 AI is thinking..."):
        result = call_safe_infer_api(
            message=user_input,
            model=st.session_state.selected_model,
            api_key=st.session_state.api_key
        )
    
    if result["status"] == "success":
        # Extract response content
        response_content = extract_response_content(result["data"])
        
        # Add bot response to history
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response_content,
            "model": st.session_state.selected_model,
            "timestamp": time.strftime("%H:%M:%S")
        })
        
        # Display bot response
        display_chat_message(
            "assistant", 
            response_content, 
            st.session_state.selected_model,
            time.strftime("%H:%M:%S")
        )
        
        # Show classification info if available
        if 'response' in result["data"] and isinstance(result["data"]["response"], dict):
            response_data = result["data"]["response"]
            if 'classification' in response_data:
                classification = response_data['classification']
                with st.expander("🔍 Response Analysis"):
                    st.json(classification)
    
    else:
        error_message = f"❌ Error: {result['message']}"
        st.error(error_message)
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": error_message,
            "timestamp": time.strftime("%H:%M:%S")
        })
    
    # Clear input and rerun to refresh the UI
    st.rerun()

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    <p>🛡️ Powered by SafeInfer LLM API | Secure • Intelligent • Reliable</p>
</div>
""", unsafe_allow_html=True)
