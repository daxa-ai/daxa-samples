# SafeInfer LLM Chatbot

A secure chatbot application powered by the SafeInfer LLM API. This Streamlit app offers a **Demo** environment (main page) and a **Test** environment (at `/test`) where you can choose API type, streaming, and model.

## Features

- **Demo (main page)**: Env-based config; single model and non-streaming completions
- **Test (`/test`)**: Choose **API Type** (completions / responses), **Stream** (True / False), and **Model** (from API) in the sidebar; OpenAI API calls use these selections
- **Secure conversations**: SafeInfer API with content safety
- **Interactive chat**: Clean UI with conversation history
- **Response analysis**: Optional classification/safety view when the API returns it
- **Chat export**: Export conversation as JSON
- **API health**: Test API connection from the sidebar
- **Responsive**: Works on desktop and mobile

## Quick Run

```bash
cd safe_infer_chatbot_app
pip install -r requirements.txt
streamlit run safe_infer_chatbot.py
```

Open `http://localhost:8501` for the **Demo** page. For the **Test** page, open `http://localhost:8501/test` (the Test link is hidden from the sidebar; use the URL).

## Prerequisites

- Python 3.8+
- SafeInfer API (default base: `http://localhost`)
- API key (set via env; see Configuration)

## Installation

1. **Clone and enter the app directory**:
   ```bash
   git clone <repository-url>
   cd daxa-samples/safe_infer_chatbot_app
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set environment variables** (see Configuration below).

4. **Run the app**:
   ```bash
   streamlit run safe_infer_chatbot.py
   ```

5. Open `http://localhost:8501` for Demo, or `http://localhost:8501/test` for Test.

## Configuration

### Environment Variables

| Variable         | Description                                  |
|------------------|----------------------------------------------|
| `PROXIMA_HOST`   | SafeInfer API base URL (default: `http://localhost`) |
| `PEBBLO_API_KEY` | Pebblo API key                               |
| `MODEL`          | Default model (Demo page and fallback)       |
| `MODEL_NAME`     | Display name for the model                   |
| `USER_EMAIL`     | User email (e.g. for welcome message)       |
| `USER_TEAM`      | User team (e.g. for welcome message)         |
| `X_PEBBLO_USER`  | Pebblo user (sent in API headers)           |

### API Endpoints

- **Completions**: `{PROXIMA_HOST}/safe_infer/llm/v1/` (OpenAI-compatible chat completions)
- **Responses**: same base; Responses API via `client.responses`
- **Models list**: `{PROXIMA_HOST}/safe_infer/llm/v1/models`
- **Health**: `{PROXIMA_HOST}/safe_infer/healthz`

## Usage

### Demo (main page)

- Uses `MODEL`, `PEBBLO_API_KEY`, and `PROXIMA_HOST` from the environment.
- Chat uses **completions** API, non-streaming.
- Sidebar: API Status, Chat Management (clear/export), Statistics.

### Test (`/test`)

- Open **`http://localhost:8501/test`** (link is not shown in the sidebar).
- **Sidebar – Test Settings**:
  - **API Type**: `completions` or `responses`
  - **Stream**: `True` or `False`
  - **Model**: dropdown from `/safe_infer/llm/v1/models`, or fallback text input if the API fails
  - **Refresh models**: reload model list
- All OpenAI-style API calls use the selected API type, model, and stream.
- Sidebar also has API Status, Chat Management, and Statistics (including current API type, stream, and model).

### General

- **Test API Connection**: in the sidebar, to check connectivity.
- **Clear Chat History**: resets the current conversation.
- **Export Chat**: downloads the current conversation as JSON.

## Project Structure

```
safe_infer_chatbot_app/
├── safe_infer_chatbot.py   # Main app (Demo page)
├── pages/
│   └── test.py             # Test page (/test)
├── utils.py                # Shared config, API helpers, UI helpers
├── requirements.txt
├── README.md
└── .env                    # Optional; use export for env vars
```

- **utils.py**: `get_available_models`, `call_llm` (completions/responses, stream on/off), `display_chat_message`, `test_api_connection`, and shared CSS/config.

## Troubleshooting

1. **Connection errors**
   - Confirm SafeInfer API is running and `PROXIMA_HOST` is correct.
   - Use “Test API Connection” in the sidebar.

2. **API key**
   - Set `PEBBLO_API_KEY` (and `X_PEBBLO_USER` if required).

3. **No models on Test page**
   - Ensure `PROXIMA_HOST` and `PEBBLO_API_KEY` are set.
   - Use “Refresh models” or the Model fallback text input.

4. **Debug**
   - `export STREAMLIT_LOG_LEVEL=debug`

## Support

- **SafeInfer API**: Contact your SafeInfer provider.
- **App issues**: Open an issue in the repository.

---

**Powered by SafeInfer LLM API | Secure • Intelligent • Reliable**
