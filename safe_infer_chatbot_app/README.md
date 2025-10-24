# 🛡️ SafeInfer LLM Chatbot

A secure and intelligent chatbot application powered by the SafeInfer LLM API. This Streamlit-based web application provides a user-friendly interface for interacting with large language models while ensuring safety and security through SafeInfer's content filtering and classification capabilities.

## ✨ Features

- **🔒 Secure Conversations**: Powered by SafeInfer API with built-in content safety filtering
- **🤖 Multiple Model Support**: Choose between GPT-4o and GPT-4o-mini models
- **💬 Interactive Chat Interface**: Clean, modern UI with real-time conversation flow
- **📊 Response Analysis**: View detailed classification and safety analysis of AI responses
- **🔄 Regeneration**: Regenerate the last AI response with a single click
- **📥 Chat Export**: Export your conversation history in JSON format
- **🔗 API Health Monitoring**: Test API connectivity and status
- **⚙️ Configurable Settings**: Customize API keys, models, and preferences
- **📱 Responsive Design**: Works seamlessly on desktop and mobile devices

## ⚡ Quick Run

To run the application immediately:

```bash
cd safeinfer_chatbot_app
pip install -r requirements.txt
streamlit run safe_infer_chatbot.py
```

Then open your browser to `http://localhost:8501`

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- SafeInfer API service running (default: `http://localhost`)
- API key (optional, depending on your SafeInfer setup)

### Installation

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd daxa-samples/safeinfer_chatbot_app
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables** (optional):
   ```bash
   export PEBBLO_API_KEY="pebblo-api-key"
   export PROXIMA_HOST="http://your-proxima-host"
   export MODEL="model-name"
   export X_PEBBLO_USER="user-email"
   export MODEL_NAME="model-display-name"
   ```

4. **Run the application**:
   ```bash
   streamlit run safe_infer_chatbot.py
   ```

5. **Open your browser** and navigate to `http://localhost:8501`

## 🛠️ Configuration

### Environment Variables

- `PROXIMA_HOST`: Base URL for the SafeInfer API (default: `http://localhost`)
- `PEBBLO_API_KEY`: Pebblo API Key
-  `MODEL`: Model Name
- `MODEL_NAME`: Model Display Name
- `X_PEBBLO_USER`: User Email

### API Configuration

The application automatically configures the following endpoints:
- **Responses**: `{PROXIMA_HOST}/safe_infer/llm/v1/responses`
- **Health Check**: `{PROXIMA_HOST}/safe_infer/healthz`

## 📖 Usage Guide

### Starting a Conversation

1. **Test Connection**: Use the "Test API Connection" button to verify connectivity
2. **Start Chatting**: Type your message and click "Send" or press Enter

### Chat Features

- **Send Messages**: Type in the text area and click "🚀 Send"
- **Clear History**: Use "Clear Chat History" to start fresh
- **Export Chat**: Download your conversation as a JSON file

### Response Analysis

When the AI responds, you can expand the "🔍 Response Analysis" section to view:
- Content classification
- Safety scores
- Risk assessments
- Detailed metadata

## 🔧 Advanced Configuration

### Customizing the Application

Edit `config.py` to modify:
- Default models and settings
- UI styling and colors
- Error messages and timeouts
- Export formats and file naming

### API Integration

The application sends requests with the following structure:
```json
{
  "model": "gpt-4o-mini",
  "input": "Your message here",
  "app": "safe_infer_chatbot"
}
```

## 📁 Project Structure

```
safeinfer_chatbot_app/
├── safe_infer_chatbot.py    # Main application file
├── config.py               # Configuration settings
├── requirements.txt        # Python dependencies
├── __init__.py            # Package initialization
└── README.md              # This file
```

## 🔍 Troubleshooting

### Common Issues

1. **Connection Error**: 
   - Ensure SafeInfer API is running
   - Check `PROXIMA_HOST` environment variable
   - Verify network connectivity

2. **API Key Issues**:
   - Confirm API key is correct
   - Check if API key is required for your setup

3. **Model Not Available**:
   - Verify the model name is supported
   - Check API service configuration

4. **Timeout Errors**:
   - Increase timeout in config.py
   - Check API service performance

### Debug Mode

To enable debug logging, add this to your environment:
```bash
export STREAMLIT_LOG_LEVEL=debug
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is part of the daxa-samples repository. Please refer to the main repository for license information.

## 🆘 Support

For issues related to:
- **SafeInfer API**: Contact your SafeInfer service provider
- **Application Bugs**: Open an issue in the repository
- **Configuration**: Check the config.py file and documentation

## 🔗 Related Resources

- [SafeInfer Documentation](https://docs.safeinfer.com)
- [Streamlit Documentation](https://docs.streamlit.io)
- [OpenAI API Documentation](https://platform.openai.com/docs)

---

**🛡️ Powered by SafeInfer LLM API | Secure • Intelligent • Reliable**
