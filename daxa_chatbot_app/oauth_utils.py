"""
MCP OAuth 2.0 + PKCE utilities.

Discovery order (most to least likely for Proxima/Pebblo gateway):
  1. Probe the MCP URL directly with Pebblo headers — extract auth URL from 401 response
     (WWW-Authenticate header, JSON body, Location header, or linked resource metadata)
  2. GET {mcp_base}/.well-known/oauth-protected-resource  → follow to auth server
  3. GET {mcp_base}/.well-known/oauth-authorization-server (RFC 8414)
  4. Dynamic client registration (RFC 7591) if a registration_endpoint is found

Redirect mechanism:
  Two-step to avoid iframe sandbox restrictions:
    Step 1 — button click builds the auth URL, stores in session state, reruns
    Step 2 — a visible <a href="..." target="_top"> link is rendered; user clicks it
  On return the Streamlit page receives ?code=...&state=... in query params.
"""

import base64
import hashlib
import logging
import os
import re
import secrets
import urllib.parse
from typing import Optional

import httpx
import streamlit as st

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level PKCE store — survives Streamlit session resets on OAuth redirect
# Key: state_token (the random suffix of daxa_mcp:{service}:{state_token})
# Value: {"verifier": str, "metadata": dict, "client_id": str, "client_secret": str|None}
# ---------------------------------------------------------------------------
_PKCE_STORE: dict = {}


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _sk(service: str, suffix: str) -> str:
    return f"oauth_{service}_{suffix}"


def get_token(service: str) -> Optional[str]:
    return st.session_state.get(_sk(service, "token"))


def set_token(service: str, token: str) -> None:
    st.session_state[_sk(service, "token")] = token


def clear_token(service: str) -> None:
    for key in ("token", "client_id", "client_secret", "pkce", "state", "metadata", "pending_url"):
        st.session_state.pop(_sk(service, key), None)


def is_connected(service: str) -> bool:
    return bool(get_token(service))


# ---------------------------------------------------------------------------
# OAuth discovery — multiple strategies
# ---------------------------------------------------------------------------

def _base_url(mcp_url: str) -> str:
    p = urllib.parse.urlparse(mcp_url)
    return f"{p.scheme}://{p.netloc}"


def _fetch_json(url: str, timeout: int = 5) -> Optional[dict]:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _probe_mcp_for_auth_url(mcp_url: str, pebblo_headers: dict) -> Optional[str]:
    """
    Hit the MCP URL with Pebblo headers and extract an OAuth authorization URL
    from the server's 401 / redirect response.

    Checks (in order):
      - HTTP redirect Location header
      - WWW-Authenticate: Bearer realm / resource_metadata
      - JSON body fields: authorizationUrl, auth_url, authorization_uri, loginUrl, …
      - Linked resource metadata (oauth-protected-resource)
    """
    headers = {**pebblo_headers, "Accept": "application/json, text/event-stream"}
    logger.info("[OAuth] Probing MCP URL: %s", mcp_url)

    for method in ("get", "post"):
        try:
            resp = getattr(httpx, method)(
                mcp_url, headers=headers, timeout=6, follow_redirects=False
            )
            logger.info("[OAuth] %s %s → HTTP %d", method.upper(), mcp_url, resp.status_code)

            # Redirect straight to auth page
            if resp.status_code in (301, 302, 307, 308):
                loc = resp.headers.get("location", "")
                logger.info("[OAuth] Redirect → %s", loc)
                if loc:
                    return loc

            if resp.status_code == 401:
                www_auth = resp.headers.get("www-authenticate", "")
                logger.info("[OAuth] 401 WWW-Authenticate: %s", www_auth)

                # WWW-Authenticate: Bearer resource_metadata="https://..."
                m = re.search(r'resource_metadata=["\']?([^\s,"\']+)', www_auth, re.I)
                if m:
                    resource_meta = _fetch_json(m.group(1))
                    logger.info("[OAuth] resource_metadata → %s", resource_meta)
                    if resource_meta:
                        for as_url in resource_meta.get("authorization_servers", []):
                            meta = _fetch_json(
                                f"{as_url.rstrip('/')}/.well-known/oauth-authorization-server"
                            )
                            if meta and "authorization_endpoint" in meta:
                                logger.info("[OAuth] Found auth endpoint via resource_metadata: %s", meta["authorization_endpoint"])
                                return meta["authorization_endpoint"]

                # WWW-Authenticate: Bearer realm="https://..."
                m = re.search(r'realm=["\']?(https?://[^\s,"\']+)', www_auth, re.I)
                if m and m.group(1).startswith("http"):
                    logger.info("[OAuth] Found auth URL via realm: %s", m.group(1))
                    return m.group(1)

                # JSON body with explicit auth URL field
                try:
                    body = resp.json()
                    logger.info("[OAuth] 401 body: %s", str(body)[:300])
                    for key in (
                        "authorizationUrl", "authorization_url", "auth_url",
                        "authorization_uri", "loginUrl", "login_url", "oauth_url",
                    ):
                        val = body.get(key) or (body.get("error") or {}).get(key)
                        if val:
                            logger.info("[OAuth] Found auth URL in body[%s]: %s", key, val)
                            return val
                except Exception:
                    pass

        except Exception as exc:
            logger.warning("[OAuth] Probe %s failed: %s", method.upper(), exc)

    logger.info("[OAuth] Direct probe found no auth URL")
    return None


def _discover_via_well_known(mcp_url: str) -> Optional[dict]:
    """
    Try RFC 8414 / MCP well-known endpoints at the server root and at the
    exact MCP URL path.
    """
    bases = [mcp_url.rstrip("/"), _base_url(mcp_url)]
    suffixes = [
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-protected-resource",
        "/.well-known/openid-configuration",
    ]
    for base in bases:
        for suffix in suffixes:
            url = base + suffix
            logger.info("[OAuth] Trying well-known: %s", url)
            data = _fetch_json(url)
            if data:
                logger.info("[OAuth] Got metadata from %s", url)
                # oauth-protected-resource → follow to auth server
                for as_url in data.get("authorization_servers", []):
                    meta = _fetch_json(
                        f"{as_url.rstrip('/')}/.well-known/oauth-authorization-server"
                    )
                    if meta and "authorization_endpoint" in meta:
                        logger.info("[OAuth] auth endpoint via protected-resource: %s", meta["authorization_endpoint"])
                        return meta
                if "authorization_endpoint" in data:
                    logger.info("[OAuth] auth endpoint from well-known: %s", data["authorization_endpoint"])
                    return data
    logger.info("[OAuth] No well-known metadata found")
    return None


def _dynamic_register(registration_endpoint: str, redirect_uri: str) -> Optional[dict]:
    """RFC 7591 dynamic client registration (public client, no secret)."""
    try:
        r = httpx.post(
            registration_endpoint,
            json={
                "client_name": "Daxa Chatbot",
                "redirect_uris": [redirect_uri],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
            },
            timeout=5,
        )
        if r.status_code in (200, 201):
            return r.json()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Build auth URL
# ---------------------------------------------------------------------------

def _normalize_https(url: str, reference_url: str) -> str:
    """
    If *url* uses http:// but *reference_url* uses https://, upgrade to https.
    Fixes servers that return http:// in their well-known metadata.
    """
    if url.startswith("http://") and reference_url.startswith("https://"):
        return "https://" + url[len("http://"):]
    return url


def _build_auth_url_from_discovered(
    service: str,
    mcp_url: str,
    redirect_uri: str,
    pebblo_headers: Optional[dict],
    direct_auth_url: Optional[str],
    metadata: Optional[dict],
) -> tuple[Optional[str], Optional[str]]:
    """
    Build the full OAuth redirect URL from already-discovered info.
    Returns (auth_url, error_message).
    """
    # ── Path A: direct auth URL from 401 probe ───────────────────────────────
    if direct_auth_url:
        direct_auth_url = _normalize_https(direct_auth_url, mcp_url)
        verifier, challenge = _generate_pkce()
        state_token = secrets.token_urlsafe(16)
        meta_direct = {"authorization_endpoint": direct_auth_url}

        parsed = urllib.parse.urlparse(direct_auth_url)
        existing_params = dict(urllib.parse.parse_qsl(parsed.query))
        existing_params.update({
            "redirect_uri": redirect_uri,
            "state": f"daxa_mcp:{service}:{state_token}",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        if "client_id" not in existing_params:
            client_id = st.session_state.get(_sk(service, "client_id"), f"daxa-chatbot-{service}")
            existing_params["client_id"] = client_id
            st.session_state[_sk(service, "client_id")] = client_id
        else:
            client_id = existing_params["client_id"]

        # Persist PKCE state in process-level store (survives session reset on redirect)
        _PKCE_STORE[state_token] = {
            "verifier": verifier,
            "metadata": meta_direct,
            "client_id": client_id,
            "client_secret": None,
        }
        logger.info("[OAuth] Stored PKCE for state_token=%s (direct path)", state_token)

        final = parsed._replace(query=urllib.parse.urlencode(existing_params)).geturl()
        logger.info("[OAuth] Built auth URL (direct): %s", final)
        return final, None

    # ── Path B: well-known metadata ──────────────────────────────────────────
    if not metadata:
        return None, (
            f"Could not reach the OAuth endpoint for this MCP server.\n\n"
            f"Tried:\n"
            f"- HTTP probe of `{mcp_url}` (no 401 auth challenge returned)\n"
            f"- `{_base_url(mcp_url)}/.well-known/oauth-authorization-server`\n\n"
            f"Make sure the MCP URL is correct and reachable."
        )

    auth_endpoint = metadata.get("authorization_endpoint", "")
    if not auth_endpoint:
        return None, "OAuth metadata found but missing `authorization_endpoint`."

    # Fix http → https if the server returned a wrong scheme
    auth_endpoint = _normalize_https(auth_endpoint, mcp_url)
    logger.info("[OAuth] auth_endpoint (normalized): %s", auth_endpoint)

    # Write normalized auth_endpoint back into metadata so token_endpoint
    # normalization in handle_oauth_callback has a valid https:// reference
    metadata = dict(metadata)  # shallow copy — don't mutate caller's dict
    metadata["authorization_endpoint"] = auth_endpoint
    # Also normalize token_endpoint now while we have mcp_url as reference
    if "token_endpoint" in metadata:
        metadata["token_endpoint"] = _normalize_https(metadata["token_endpoint"], mcp_url)
        logger.info("[OAuth] token_endpoint (normalized): %s", metadata["token_endpoint"])

    # Reuse or dynamically register a client_id
    client_id: Optional[str] = st.session_state.get(_sk(service, "client_id"))
    if not client_id:
        reg_ep = metadata.get("registration_endpoint")
        if reg_ep:
            logger.info("[OAuth] Registering client at %s", reg_ep)
            info = _dynamic_register(reg_ep, redirect_uri)
            if info:
                client_id = info.get("client_id")
                st.session_state[_sk(service, "client_id")] = client_id
                st.session_state[_sk(service, "client_secret")] = info.get("client_secret")
                logger.info("[OAuth] Dynamic registration OK, client_id=%s", client_id)
            else:
                logger.warning("[OAuth] Dynamic registration failed at %s", reg_ep)

    if not client_id:
        return None, (
            "OAuth metadata found but the server does not support dynamic client "
            "registration and no client_id is available."
        )

    verifier, challenge = _generate_pkce()
    state_token = secrets.token_urlsafe(16)

    # Persist PKCE state in process-level store (survives session reset on redirect)
    _PKCE_STORE[state_token] = {
        "verifier": verifier,
        "metadata": metadata,
        "client_id": client_id,
        "client_secret": st.session_state.get(_sk(service, "client_secret")),
    }
    logger.info("[OAuth] Stored PKCE for state_token=%s (well-known path)", state_token)

    params: dict = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": f"daxa_mcp:{service}:{state_token}",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    scopes = metadata.get("scopes_supported", [])
    if scopes:
        params["scope"] = " ".join(scopes[:8])

    final = f"{auth_endpoint}?{urllib.parse.urlencode(params)}"
    logger.info("[OAuth] Built auth URL (well-known): %s", final)
    return final, None


def build_auth_url(
    service: str,
    mcp_url: str,
    redirect_uri: str,
    pebblo_headers: Optional[dict] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Full discover + build in one call (used when no pre-discovery was done)."""
    pebblo_headers = pebblo_headers or {}
    direct = _probe_mcp_for_auth_url(mcp_url, pebblo_headers)
    metadata = None if direct else _discover_via_well_known(mcp_url)
    return _build_auth_url_from_discovered(
        service, mcp_url, redirect_uri, pebblo_headers, direct, metadata
    )


# ---------------------------------------------------------------------------
# OAuth callback handler  (call once near top of each page)
# ---------------------------------------------------------------------------

def handle_oauth_callback(redirect_uri: str) -> Optional[str]:
    """
    Inspect st.query_params for an OAuth callback code.
    Exchanges the code for a token, stores it, clears query params, and reruns.
    Returns the service name on success, None if no callback pending.
    """
    params = st.query_params
    code: Optional[str] = params.get("code")
    state: str = params.get("state", "")
    error: Optional[str] = params.get("error")

    if error:
        st.error(
            f"OAuth error: **{error}**"
            + (f" — {params.get('error_description', '')}" if params.get("error_description") else "")
        )
        st.query_params.clear()
        return None

    if not code or not state.startswith("daxa_mcp:"):
        return None

    parts = state.split(":", 2)
    if len(parts) != 3:
        return None

    _, service, orig_state = parts

    # Look up PKCE state from process-level store (robust to Streamlit session resets)
    pkce_entry = _PKCE_STORE.get(orig_state)
    if not pkce_entry:
        st.error("OAuth state mismatch — please try connecting again.")
        logger.warning("[OAuth] No PKCE entry found for state_token=%s (known states: %s)",
                       orig_state, list(_PKCE_STORE.keys()))
        st.query_params.clear()
        return None

    # Clean up used entry immediately
    _PKCE_STORE.pop(orig_state, None)

    metadata: dict = pkce_entry.get("metadata", {})
    token_endpoint = metadata.get("token_endpoint")
    # Normalize http→https using the auth endpoint as reference (same server)
    auth_ep_ref = metadata.get("authorization_endpoint", "")
    if token_endpoint and auth_ep_ref:
        token_endpoint = _normalize_https(token_endpoint, auth_ep_ref)
    client_id = pkce_entry.get("client_id")
    client_secret = pkce_entry.get("client_secret")
    verifier = pkce_entry.get("verifier")

    # Persist client_id in session for potential reuse (skips re-registration)
    if client_id:
        st.session_state[_sk(service, "client_id")] = client_id

    if not token_endpoint:
        # Server gave a direct auth URL without a separate token endpoint —
        # this can happen with some gateway implementations. Surface the code
        # so the caller can use it.
        st.warning(
            "Received authorization code but no token_endpoint is configured. "
            "The MCP server may handle token exchange internally."
        )
        st.query_params.clear()
        return service

    if not client_id:
        st.error("OAuth configuration missing for token exchange.")
        st.query_params.clear()
        return None

    payload: dict = {
        
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    try:
        resp = httpx.post(token_endpoint, data=payload, timeout=10)
        if resp.status_code == 200:
            access_token = resp.json().get("access_token")
            if access_token:
                set_token(service, access_token)
                st.query_params.clear()
                st.rerun()
                return service
            st.error("Token response did not contain an access_token.")
        else:
            st.error(f"Token exchange failed ({resp.status_code}): {resp.text[:300]}")
    except Exception as exc:
        st.error(f"Token exchange error: {exc}")

    st.query_params.clear()
    return None


# ---------------------------------------------------------------------------
# UI widget: Connect / Disconnect button for one service
# ---------------------------------------------------------------------------

def render_oauth_connect_button(
    service: str,
    label: str,
    mcp_url: str,
    redirect_uri: str,
    button_key: str,
    pebblo_headers: Optional[dict] = None,
) -> None:
    """
    Two-step OAuth connect widget.

    Step 1 — "Connect" button: probes MCP URL, builds auth URL, stores it,
              reruns so the page re-renders.
    Step 2 — Shows a styled anchor link the user clicks to navigate to the
              auth page (same browser tab via target="_top").

    On successful OAuth return the page receives ?code=...&state=... and
    handle_oauth_callback() (called at page top) completes the token exchange.
    """
    if not mcp_url.strip():
        st.caption("Enter a URL above to enable authentication.")
        return

    if is_connected(service):
        col_status, col_btn = st.columns([3, 2])
        with col_status:
            st.markdown(
                "<span style='color:#3DC667; font-size:0.85rem;'>✅ Connected</span>",
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button("Disconnect", key=f"{button_key}_disconnect", use_container_width=True):
                clear_token(service)
                st.rerun()
        return

    # ── Step 2: auth URL already built — show clickable link ────────────────
    pending_url = st.session_state.get(_sk(service, "pending_url"))
    if pending_url:
        st.markdown(
            f"""
<a href="{pending_url}" target="_top"
   style="display:block; text-align:center; padding:7px 12px;
          background:#1f77b4; color:white; border-radius:6px;
          text-decoration:none; font-size:0.85rem; margin-top:4px;">
  🔐 Click to authenticate with {label}
</a>
""",
            unsafe_allow_html=True,
        )
        st.caption("You will be redirected to the auth page and returned here after login.")
        if st.button("Cancel", key=f"{button_key}_cancel", use_container_width=True):
            st.session_state.pop(_sk(service, "pending_url"), None)
            st.rerun()
        return

    # ── Step 1: discover auth URL on button click ────────────────────────────
    if st.button(f"🔐 Connect to {label}", key=button_key, use_container_width=True):
        base = _base_url(mcp_url)
        auth_url = None
        err = None

        with st.status(f"Connecting to {label}…", expanded=True) as status:
            # Step A: direct probe
            st.write(f"📡 Probing `{mcp_url}`…")
            direct = _probe_mcp_for_auth_url(mcp_url, pebblo_headers or {})
            if direct:
                st.write("✅ Auth URL found via server response")
            else:
                st.write("⬜ No auth challenge in direct probe")

            # Step B: well-known (only if direct probe missed)
            metadata = None
            if not direct:
                st.write(f"🔍 Checking `{base}/.well-known/…`")
                metadata = _discover_via_well_known(mcp_url)
                if metadata:
                    st.write("✅ OAuth metadata discovered via well-known")
                else:
                    st.write("⬜ No well-known metadata found")

            # Step C: build auth URL from already-discovered info (no re-probe)
            st.write("🔑 Registering client & building auth URL…")
            auth_url, err = _build_auth_url_from_discovered(
                service, mcp_url, redirect_uri, pebblo_headers,
                direct_auth_url=direct, metadata=metadata,
            )

            if auth_url:
                status.update(label=f"✅ Ready to authenticate with {label}", state="complete")
                st.write(f"✅ Auth URL ready")
            else:
                status.update(label=f"❌ Could not discover OAuth for {label}", state="error")

        if auth_url:
            st.session_state[_sk(service, "pending_url")] = auth_url
            st.rerun()
        else:
            st.error(err or f"Could not obtain OAuth URL for {label}.")
            logger.error("[OAuth] build_auth_url failed for %s: %s", service, err)
