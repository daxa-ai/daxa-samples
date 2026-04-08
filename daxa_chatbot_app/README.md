# Daxa Chatbot App

A Streamlit-based chatbot with four modes selectable from the sidebar tab bar:

| Mode | LLM | MCP gateway | Pebblo headers |
|------|-----|-------------|----------------|
| **Safe Infer** | SafeInfer (Proxima) | — | ✅ |
| **Safe Agent** | OpenAI (direct) | Proxima | ✅ |
| **Direct Infer** | OpenAI (direct) | — | ❌ |
| **Direct Agent** | OpenAI (direct) | None (upstream direct) | ❌ |

---

## Project Structure

```
daxa_chatbot_app/
├── safe_infer_chatbot.py   # Main app — all four modes (port 8501)
├── pages/
│   └── test.py             # Test page (/test — port 8501/test)
├── utils.py                # Shared config, API helpers, UI helpers
├── mcp_utils.py            # LangGraph + MultiServerMCPClient orchestration
├── oauth_utils.py          # MCP OAuth 2.0 + PKCE discovery & token exchange
├── requirements.txt
├── .env                    # Environment variables
└── README.md
```

---

## Prerequisites

- Python 3.11+
- **OpenAI API key** — used by the LangGraph LLM in all Agent modes and Direct Infer
- **Proxima (Daxa) gateway** — required for Safe Infer and Safe Agent modes
- **Pebblo API key per MCP server** — issued by the Proxima admin; required for Safe Agent only

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

Create a `.env` file in the `daxa_chatbot_app/` directory:

```env
# ── SafeInfer / Proxima gateway ──────────────────────────────────────────────
PROXIMA_HOST=https://<your-proxima-host>/
PEBBLO_API_KEY=pebblo_<your-global-key>

# ── User identity (forwarded to Proxima as x-pebblo-users / x-pebblo-user-groups) ──
USER_EMAIL=you@example.com
USER_TEAM=YourTeam
X_PEBBLO_USER=you@example.com
X_PEBBLO_USER_GROUPS=your-group@example.com

# ── LLM — used by LangGraph in all Agent modes and Direct Infer ──────────────
OPENAI_API_KEY=sk-proj-...
MODEL=gpt-4o-mini

# ── MCP user path segment ({user_id} in /mcp/{user_id}/{server}) ─────────────
MCP_USER_ID=<your-proxima-user-slug>

# ── Feature flags — set to True to show that server section in the sidebar ───
ATLASSIAN_OAUTH=True        # Show Atlassian (OAuth) expander + Connect button
ATLASSIAN_DOCKER=True       # Show Atlassian (no-auth / Docker) expander
CUSTOMER_BILLING=True       # Show Customer Billing expander

# ── Safe Agent MCP URLs (via Proxima gateway) ─────────────────────────────────
ATLASSIAN_MCP_URL=https://<proxima-host>/mcp/<user_id>/<atlassian-server-name>
ATLASSIAN_API_KEY=pebblo_<atlassian-oauth-server-key>

ATLASSIAN_DOCKER_MCP_URL=https://<proxima-host>/mcp/<user_id>/<atlassian-docker-server-name>
ATLASSIAN_DOCKER_API_KEY=pebblo_<atlassian-docker-server-key>

CUSTOMER_BILLING_MCP_URL=https://<proxima-host>/mcp/<user_id>/<billing-server-name>
CUSTOMER_BILLING_API_KEY=pebblo_<billing-server-key>

# ── Direct Agent MCP URLs (no Proxima — connect straight to upstream) ─────────
DIRECT_ATLASSIAN_MCP_URL=https://<direct-atlassian-mcp-host>/mcp
DIRECT_CUSTOMER_BILLING_MCP_URL=https://billing-mcp.daxa.ai/mcp

# ── OAuth redirect URIs (must match the Streamlit app URL exactly) ───────────
DAXA_REDIRECT_URI=http://localhost:8501
DAXA_TEST_REDIRECT_URI=http://localhost:8501/test
```

> **Note:** `ATLASSIAN_API_KEY` / `ATLASSIAN_DOCKER_API_KEY` / `CUSTOMER_BILLING_API_KEY` are **per-server** Pebblo keys issued by Proxima — used only in Safe Agent mode. Direct Agent sends no Pebblo headers.

### 5. Run the app

```bash
streamlit run safe_infer_chatbot.py
```

- Main app: `http://localhost:8501`
- Test page: `http://localhost:8501/test`

---

## Modes

### Safe Infer

Chat with the SafeInfer LLM gateway. All traffic is routed through Proxima with content safety and PII classification.

1. Select **Safe Infer** in the sidebar tab bar.
2. Choose a model from the dropdown (fetched from `{PROXIMA_HOST}/safe_infer/llm/v1/models`) or type a model ID.
3. Type your message and press **🚀 Send**.

Sidebar options: API Status · Model selector · Sample Prompts · Export Chat · Statistics.

---

### Direct Infer

Chat directly with OpenAI — no Proxima gateway, no content filtering, no Pebblo headers.

1. Select **Direct Infer** in the sidebar tab bar.
2. Enter a model ID in the sidebar (defaults to `MODEL` from `.env`, e.g. `gpt-4o-mini`).
3. Type your message and press **🚀 Send**.

Uses `OPENAI_API_KEY` from `.env`. Maintains its own chat history separate from Safe Infer.

---

### Safe Agent

A LangGraph agent that connects to MCP servers **via the Proxima gateway** with full Pebblo authentication.

#### Step 1 — Configure MCP Servers

Expand the **MCP Servers** section in the sidebar. Server expanders are **collapsed by default** — click to open. A 🟢 badge indicates the URL is already configured from `.env`.

Which servers appear is controlled by feature flags in `.env`:

| Flag | Server shown | Transport | Auth |
|------|-------------|-----------|------|
| `ATLASSIAN_OAUTH=True` | **Atlassian (OAuth)** + 🔐 Connect button | SSE | Pebblo API key + OAuth 2.0 + PKCE |
| `ATLASSIAN_DOCKER=True` | **Atlassian** (no OAuth) | Streamable HTTP | Pebblo API key only |
| `CUSTOMER_BILLING=True` | **Customer Billing** | Streamable HTTP | Pebblo API key only |

Each expander has:
- **MCP URL** — pre-filled from `.env`; edit if needed
- **Pebblo API Key** — pre-filled from `.env`; the per-server key issued by Proxima
- **Save** — persists URL + key for the session

#### Step 2 — Connect OAuth (Atlassian — only when `ATLASSIAN_OAUTH=True`)

1. Click **🔐 Connect to Atlassian**.
2. The app auto-discovers the OAuth endpoint:
   - Probes the MCP URL for an auth challenge
   - Falls back to `/.well-known/oauth-authorization-server` (RFC 8414)
   - Performs dynamic client registration (RFC 7591) — no pre-configured `client_id` needed
   - Generates a PKCE `code_verifier` / `code_challenge` pair
3. A **🔐 Click to authenticate** link appears — click it to open the provider login.
4. After approving, the browser redirects back to the app.
5. The app exchanges the auth code for a token (PKCE, no client secret).
6. Sidebar shows **✅ Connected**.

> **PKCE state across redirects:** `state` token and `code_verifier` are stored in a module-level `_PKCE_STORE` dict (not `st.session_state`) so they survive the Streamlit session reset that happens on the OAuth redirect.

#### Step 3 — Set User Context *(optional)*

- **User** (`x-pebblo-users`) — forwarded to Proxima (defaults to `X_PEBBLO_USER` from `.env`)
- **User Groups** (`x-pebblo-user-groups`) — forwarded to Proxima (defaults to `X_PEBBLO_USER_GROUPS` from `.env`)

#### Step 4 — Send a query

The agent: builds server config → connects to each server individually (skips failing ones) → retrieves tools → runs LangGraph loop → streams status → displays answer + tools used.

Headers sent to Proxima per request:

| Header | Value | Purpose |
|--------|-------|---------|
| `x-pebblo-auth` | `Bearer <server-api-key>` | Per-server Pebblo authentication |
| `x-pebblo-users` | `<user-email>` | Identity forwarding |
| `x-pebblo-user-groups` | `<group>` | Group-based access control |
| `Authorization` | `Bearer <oauth-token>` | OAuth token for Atlassian (OAuth server only) |

---

### Direct Agent

Same LangGraph agent as Safe Agent, but connects **directly to the upstream MCP services** — no Proxima gateway, no Pebblo headers.

#### Step 1 — Configure MCP Servers

Server expanders are **collapsed by default** — click to open. A 🟢 badge indicates the URL is already configured.

Which servers appear is controlled by the same feature flags:

| Flag | Server shown | Transport | Auth |
|------|-------------|-----------|------|
| `ATLASSIAN_OAUTH=True` | **Atlassian (OAuth)** + 🔐 Connect button | SSE | OAuth token only |
| `ATLASSIAN_DOCKER=True` | **Atlassian** (no auth) | Streamable HTTP | None |
| `CUSTOMER_BILLING=True` | **Customer Billing** | Streamable HTTP | None |

Each expander shows only a **URL** field — no Pebblo API key.

#### Step 2 — Connect OAuth (Atlassian — only when `ATLASSIAN_OAUTH=True`)

Same OAuth 2.0 + PKCE flow as Safe Agent. The Direct Agent uses a **separate token** (stored under `direct_atlassian`) so Safe Agent and Direct Agent OAuth sessions are independent.

#### Step 3 — Send a query

Same LangGraph loop. Headers per server:
- **Atlassian (OAuth):** `Authorization: Bearer <token>` only
- **Atlassian (Docker) / Customer Billing:** no headers

---

## Feature Flags

All three flags live in `.env` and take effect on app restart (or reload):

```env
ATLASSIAN_OAUTH=True    # Atlassian with OAuth — shows URL + Pebblo key (Safe Agent) or URL only (Direct Agent) + Connect button
ATLASSIAN_DOCKER=True   # Atlassian without OAuth — shows URL + Pebblo key (Safe) or URL only (Direct)
CUSTOMER_BILLING=True   # Customer Billing — shows URL + Pebblo key (Safe) or URL only (Direct)
```

Setting a flag to `False` hides the expander **and** prevents that server from being included in the MCP client when a query is sent.

---

## LangGraph Agent Architecture

Used by both Safe Agent and Direct Agent:

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

- **`call_model`** — `await model_with_tools.ainvoke(messages)` via OpenAI (`OPENAI_API_KEY`)
- **`tools`** — async; calls each `tool.ainvoke(args)` via `langchain-mcp-adapters`
- **`should_continue`** — routes to `tools` if LLM returned tool calls, else `END`
- Each MCP server is attempted individually — a failing server is skipped, others proceed

---

## MCP Transport Details

| Server | Transport | Why |
|--------|-----------|-----|
| Atlassian (OAuth) | `sse` | Upstream is SSE-based; requires a GET handshake to obtain a `sessionId` before POSTing messages |
| Atlassian (Docker / no-auth) | `streamable_http` | Local/Docker server; accepts POST directly |
| Customer Billing | `streamable_http` | Standard HTTP JSON-RPC; accepts POST directly |

> Using `streamable_http` for an SSE-based server returns 404 `"Missing sessionId parameter"` — the GET handshake that assigns a session is skipped.

---

## Troubleshooting

### 401 on MCP connection (Safe Agent)
- Confirm the correct **per-server** Pebblo API key is entered. Each server on Proxima has its own key — the global `PEBBLO_API_KEY` is for Safe Infer only.

### 401 on MCP connection (Direct Agent)
- No Pebblo key is needed. If Atlassian (OAuth) returns 401, click **Connect** to re-run the OAuth flow and get a fresh token.

### OAuth state mismatch
- Click **Connect** again to start a new PKCE flow. This can happen if the Streamlit process restarted between the connect click and the redirect.

### Token exchange failed (301)
- The token endpoint in the well-known metadata uses `http://` but the server is `https://`. The app normalises this automatically. If it persists, verify `DAXA_REDIRECT_URI` exactly matches the app URL.

### 404 on Atlassian MCP (POST)
- Confirms the transport is `sse` for OAuth Atlassian and `streamable_http` for Docker Atlassian.
- For Safe Agent: verify the Atlassian server is running on your Proxima instance (Redis routing cache — `host=None, port=None` means the backend process is not registered).

### Server not appearing in sidebar
- Check the corresponding feature flag in `.env` is set to `True`.
- Restart the app after changing `.env` values.

### Tools fetched but not used
- Confirm `OPENAI_API_KEY` is set and valid.
- Check logs for `[Graph] call_model: tool_calls=[]`. If empty, try a more direct query: *"Use get_customer_balance to check balance for customer 123"*.

### LLM authentication error (401)
- All Agent modes and Direct Infer use **standard OpenAI** (`OPENAI_API_KEY`) — not the SafeInfer gateway.
- Safe Infer uses Proxima (`PROXIMA_HOST` + `PEBBLO_API_KEY`).

---

## Test Page (`/test`)

Open `http://localhost:8501/test` for additional controls:

- **API Type**: `completions` or `responses`
- **Stream**: `True` / `False`
- **Model**: dropdown or manual entry
- Full Safe Agent functionality (Atlassian + Customer Billing via Proxima)

---

**Powered by Daxa Proxima · SafeInfer · OpenAI · LangGraph · MCP**
