"""
Configuration file for SafeInfer LLM Chatbot
"""

# API Configuration
import os


API_BASE_URL = os.getenv("PROXIMA_HOST")
API_ENDPOINT = f"{API_BASE_URL}/safe_infer/llm/v1/responses"
HEALTH_ENDPOINT = f"{API_BASE_URL}/safe_infer/healthz"

# Default settings
DEFAULT_MODEL = "gpt-4o"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1000
DEFAULT_TIMEOUT = 30

# Available models
AVAILABLE_MODELS = [
    "gpt-4o-mini",
    "gpt-4o"
]

# UI Configuration
PAGE_TITLE = "SafeInfer LLM Chatbot"
PAGE_ICON = "🛡️"
LAYOUT = "wide"
INITIAL_SIDEBAR_STATE = "expanded"

# Chat Configuration
APP_NAME = "safe_infer_chatbot"
CHAT_HISTORY_LIMIT = 100  # Maximum number of messages to keep in history

# Export Configuration
EXPORT_FORMAT = "json"
EXPORT_FILENAME_PREFIX = "safe_infer_chat"

# Styling Configuration
PRIMARY_COLOR = "#667eea"
SECONDARY_COLOR = "#764ba2"
USER_MESSAGE_COLOR = "#e3f2fd"
BOT_MESSAGE_COLOR = "#f3e5f5"
MODEL_INFO_COLOR = "#fff3e0"

# Error Messages
ERROR_MESSAGES = {
    "connection": "Cannot connect to SafeInfer API. Please ensure the service is running on localhost.",
    "timeout": "Request timed out. Please try again.",
    "api_error": "API Error: {status_code} - {message}",
    "parse_error": "Error parsing response: {error}",
    "model_error": "Model '{model}' is not available. Please select a different model."
}

# Success Messages
SUCCESS_MESSAGES = {
    "api_connected": "API is accessible",
    "model_switched": "Switched to {model}",
    "chat_exported": "Chat exported successfully",
    "chat_cleared": "Chat history cleared"
}
