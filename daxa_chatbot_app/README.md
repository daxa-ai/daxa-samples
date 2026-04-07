# Daxa Chatbot App

A Streamlit-based chatbot with two modes:

- **Safe Infer** — Secure LLM chat routed through the SafeInfer (Proxima) gateway with content safety and PII classification.
- **Safe Agent** — LangGraph agent that queries one or more MCP servers (Atlassian, Customer Billing) via the Proxima MCP gateway, with per-server Pebblo authentication and OAuth 2.0 + PKCE for services that require it.

---

## Project Structure

```
daxa_chatbot_app/
├── safe_infer_chatbot.py   # Main app (Safe Infer + Safe Agent — port 8501)
├── pages/
│   └── test.py             # Test page (/test — port 8501/test)
├── utils.py                # Shared config, API helpers, UI helpers
├── mcp_utils.py            # LangGraph + MultiServerMCPClient orchestration
├── oauth_utils.py          # MCP OAuth 2.0 + PKCE discovery & token exchange
├── requirements.txt
├── .env                    # Environment variables (copy from .env.example)
└── README.md
```

---

## Prerequisites

- Python 3.11+
- A running **Proxima** (Daxa) gateway instance with at least one MCP server registered
- An **OpenAI API key** (used by the LangGraph LLM in Safe Agent mode)
- A **Pebblo API key** per MCP server (issued by the Proxima gateway admin)

---

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd dristysrivastava-daxa-samples/daxa_chatbot_app
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy or create a `.env` file in the `daxa_chatbot_app/` directory:

```env
# ── SafeInfer / Proxima gateway ──────────────────────────────────────────────
PROXIMA_HOST=https://<your-proxima-host>/
PEBBLO_API_KEY=pebblo_<your-global-key>

# ── User identity (forwarded to Proxima as x-pebblo-users / x-pebblo-user-groups) ──
USER_EMAIL=you@example.com
USER_TEAM=YourTeam
X_PEBBLO_USER=you@example.com
X_PEBBLO_USER_GROUPS=your-group@example.com

# ── LLM (used by LangGraph in Safe Agent mode) ───────────────────────────────
OPENAI_API_KEY=sk-proj-...
MODEL=gpt-4o-mini             # any OpenAI model name

# ── MCP Server URLs (pre-fill sidebar; leave blank to enter manually in UI) ──
ATLASSIAN_MCP_URL=https://<proxima-host>/mcp/<user_id>/<atlassian-server-name>
ATLASSIAN_API_KEY=pebblo_<atlassian-server-key>

CUSTOMER_BILLING_MCP_URL=https://<proxima-host>/mcp/<user_id>/<billing-server-name>
CUSTOMER_BILLING_API_KEY=pebblo_<billing-server-key>

# ── OAuth redirect URIs (must match the Streamlit app URL exactly) ───────────
DAXA_REDIRECT_URI=http://localhost:8501
DAXA_TEST_REDIRECT_URI=http://localhost:8501/test
```

> **Note:** Each MCP server registered on Proxima has its own Pebblo API key (`x-pebblo-auth` header). Get them from the Proxima admin panel.

### 5. Run the app

```bash
streamlit run safe_infer_chatbot.py
```

- Main app: `http://localhost:8501`
- Test page: `http://localhost:8501/test`

---

## Modes

### Safe Infer

Chat directly with the SafeInfer LLM gateway.

1. Select **Safe Infer** in the sidebar mode selector.
2. Choose a model from the dropdown (fetched from `{PROXIMA_HOST}/safe_infer/llm/v1/models`) or type a model ID manually.
3. Type your message and press **Send**.
4. Responses are streamed through the Proxima gateway with content safety applied.

Sidebar options:
- **API Status** — test connectivity to the Proxima gateway
- **Clear Chat History** — reset the conversation
- **Export Chat** — download conversation as JSON

---

### Safe Agent (MCP)

A LangGraph agent that connects to MCP servers via the Proxima gateway and uses their tools to answer queries.

#### Step 1 — Configure MCP Servers in the sidebar

Expand the **MCP Servers** section. Each server has:
- **MCP URL** — pre-filled from `.env`; edit if needed
- **Pebblo API Key** — pre-filled from `.env`; the per-server key issued by Proxima
- **Save** — persists URL + key for the session

Supported servers:
| Server | Transport | Auth |
|--------|-----------|------|
| Atlassian (Jira/Confluence) | SSE | OAuth 2.0 + PKCE |
| Customer Billing | Streamable HTTP | Pebblo API key only |

#### Step 2 — Connect OAuth servers (Atlassian)

Services that use OAuth must be connected before sending queries.

1. Click **🔐 Connect to Atlassian** under the Atlassian expander.
2. The app discovers the OAuth endpoint automatically:
   - Probes the MCP URL for an auth challenge
   - Falls back to `/.well-known/oauth-authorization-server` (RFC 8414)
   - Performs dynamic client registration (RFC 7591) to get a `client_id`
   - Generates a PKCE `code_verifier` / `code_challenge` pair
3. A **🔐 Click to authenticate** link appears — click it to open the provider login in the same tab.
4. After approving access on the provider page, you are redirected back to the app.
5. The app exchanges the authorization code for an access token (PKCE flow, no client secret needed).
6. The sidebar shows **✅ Connected**.

To disconnect, click **Disconnect** — this clears the stored token.

> **How PKCE state survives the redirect:** The `state` token and `code_verifier` are stored in a module-level Python dict (`_PKCE_STORE` in `oauth_utils.py`), keyed by the random state value. This survives the Streamlit session reset that occurs when the browser is redirected back from the OAuth provider. After the code exchange the entry is deleted immediately.

#### Step 3 — Set identity headers *(optional)*

In the **Identity** section, set:
- **Pebblo User** — forwarded as `x-pebblo-users` (defaults to `X_PEBBLO_USER` from `.env`)
- **User Groups** — forwarded as `x-pebblo-user-groups` (defaults to `X_PEBBLO_USER_GROUPS` from `.env`)

#### Step 4 — Send a query

Type your query in the text area and click **🚀 Send**.

The app:
1. Builds the MCP server config (URL + per-server Pebblo API key + OAuth token if connected)
2. Attempts to connect to each server **individually** — a server that fails (e.g. 404, auth error) is skipped with a warning; remaining servers still work
3. Retrieves the tools list from all connected servers
4. Runs a LangGraph `StateGraph` loop: `call_model → tools → call_model → … → END`
5. Streams status updates: *Analyzing → Selected tool: X → Received response → Processing…*
6. Displays the final answer and which tools were used

---

## LangGraph Agent Architecture

```
START
  │
  ▼
call_model  ──── (has tool_calls?) ────► tools
  ▲                                        │
  └────────────────────────────────────────┘
  │
  ▼ (no tool_calls)
 END
```

- **`call_model`** — async `model_with_tools.ainvoke(messages)` using standard OpenAI (`OPENAI_API_KEY`)
- **`tools`** — async tool node; calls each `tool.ainvoke(args)` via `langchain-mcp-adapters`
- **`should_continue`** — routes to `tools` if the LLM returned tool calls, else `END`
- Recursion limit: 10 iterations

---

## MCP Transport Details

| Server | Transport in config | Why |
|--------|---------------------|-----|
| Atlassian | `sse` | Upstream is `https://mcp.atlassian.com/v1/sse` (SSE-based); requires GET handshake to obtain a `sessionId` before POSTing messages |
| Customer Billing | `streamable_http` | Standard HTTP JSON-RPC; accepts POST directly |

> Using `streamable_http` for an SSE-based server causes a 404 `"Missing sessionId parameter"` error from the upstream because it skips the GET handshake that assigns a session.

---

## Headers Sent to Proxima

| Header | Value | Purpose |
|--------|-------|---------|
| `x-pebblo-auth` | `Bearer <server-api-key>` | Per-server Pebblo authentication |
| `x-pebblo-users` | `<user-email>` | Identity forwarding |
| `x-pebblo-user-groups` | `<group>` | Group-based access control |
| `Authorization` | `Bearer <oauth-token>` | OAuth token for Atlassian |

---

## Troubleshooting

### 401 on MCP connection
- Make sure the correct **per-server** Pebblo API key is entered (each server on Proxima has its own key).
- The global `PEBBLO_API_KEY` is used for Safe Infer only, not for MCP servers.

### OAuth state mismatch
- Click **Connect** again — a new PKCE flow will be started.
- This can happen if the Streamlit process was restarted between the connect click and the redirect callback.

### Token exchange failed (301)
- The token endpoint URL returned by the well-known metadata uses `http://` but the server is `https://`. The app normalizes this automatically. If you still see it, check that `DAXA_REDIRECT_URI` matches the exact URL the app is running on.

### 404 on Atlassian MCP (POST)
- Ensure the Atlassian server transport is set to `sse` in `mcp_utils.py` (`build_mcp_servers`). The upstream Atlassian MCP is SSE-based and rejects raw POSTs without a `sessionId`.
- Verify the server is running on your Proxima instance (check the Proxima admin panel or Redis routing cache).

### Tools fetched but not used by the LLM
- Confirm `OPENAI_API_KEY` is set in `.env` and is valid.
- Check logs for `[Graph] call_model: tool_calls=[]` — if empty, the LLM decided no tools were needed. Try a more explicit query like *"Use the get_customer_balance tool to check balance for customer 123"*.

### LLM authentication error (401)
- Safe Agent uses **standard OpenAI** (`OPENAI_API_KEY`), not the SafeInfer gateway.
- Safe Infer mode uses the Proxima gateway (`PROXIMA_HOST` + `PEBBLO_API_KEY`).

---

## Test Page (`/test`)

Open `http://localhost:8501/test` for a test environment with additional controls:

- **API Type**: `completions` or `responses`
- **Stream**: `True` / `False`
- **Model**: dropdown or manual entry
- Full MCP / Safe Agent functionality with all three servers (Atlassian, Customer Billing)

---

**Powered by Daxa Proxima · SafeInfer · LangGraph · MCP**
