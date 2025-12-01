import os
import streamlit as st
import requests
import json
from typing import Dict, Any
import time
from openai import OpenAI
from utils import get_available_models
 

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


# API Configuration
API_KEY = os.getenv("PEBBLO_API_KEY", "")
API_BASE_URL = os.getenv("PROXIMA_HOST", "https://localhost:8000")
USER_EMAIL = os.getenv("USER_EMAIL", "User")
USER_TEAM = os.getenv("USER_TEAM", "Finance Ops")
RESPONSE_API_ENDPOINT = f"{API_BASE_URL}/safe_infer/llm/v1/"
LLM_PROVIDER_API_ENDPOINT = f"{API_BASE_URL}/api/llm/provider"
#SELECTED_MODEL = os.getenv("MODEL")
X_PEBBLO_USER = os.getenv("X_PEBBLO_USER", None)
#MODEL_NAME = os.getenv("MODEL_NAME", SELECTED_MODEL)
AVAILABLE_MODELS, DEFAULT_MODEL = get_available_models()
SELECTED_MODEL = DEFAULT_MODEL

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'selected_model' not in st.session_state:
    st.session_state.selected_model = SELECTED_MODEL
if 'api_key' not in st.session_state:
    st.session_state.api_key = API_KEY
if 'model_name' not in st.session_state:
    st.session_state.model_name = DEFAULT_MODEL

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

def call_open_ai(message: str, model: str, api_key: str = "") -> Dict[str, Any]:
    try:
        default_headers = {"X-PEBBLO-USER": X_PEBBLO_USER} if X_PEBBLO_USER else None
        client = OpenAI(
            base_url=RESPONSE_API_ENDPOINT,
            api_key=api_key,
            default_headers=default_headers
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": message}]
        )
        
        return {"status": "success", "data": response.choices[0].message.content}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}

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
            file_name=f"finance_chatbot_{time.strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
    
    # Statistics
    st.subheader("📊 Statistics")
    st.metric("Messages", len(st.session_state.chat_history))
    st.markdown(f"""
<div style="font-size:0.8rem;">
    Current Model: <br><span style="font-size:1.2rem;"><b>{st.session_state.model_name}</b></span>
</div>
""", unsafe_allow_html=True)
with st.sidebar:
    st.header("⚙️ Configuration")

    # Model selection
    available_models = AVAILABLE_MODELS
    if available_models:
        st.subheader("🤖 Model Selection")
        selected_model = st.selectbox(
            "Choose a model:",
            available_models,
            index=available_models.index(st.session_state.selected_model) if st.session_state.selected_model in available_models else 0
        )
        st.session_state.selected_model = selected_model
        st.session_state.model_name = selected_model




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
        model = st.session_state.selected_model

        result = call_open_ai(
            message=user_input,
            model=model,
            api_key=st.session_state.api_key
        )
        result = {"status": "success", "data": result}
    if result["status"] == "success":
        # Extract response content
        response = result['data']['data']

        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response,
            "model": st.session_state.selected_model,
            "timestamp": time.strftime("%H:%M:%S")
        })
        
        # Display bot response
        display_chat_message(
            "assistant", 
            response,
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
