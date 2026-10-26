"""One-time Gmail + Google Drive OAuth bootstrap.

Run this once after you've created a Google Cloud OAuth client (Desktop
application type) with the Gmail + Drive APIs enabled. It opens a browser,
captures the consent callback on a local port, and writes the resulting
refresh + access tokens back into manthanv2/agent/.env.

Usage:
    cd manthanv2/agent
    .venv/bin/python scripts/gmail_oauth_bootstrap.py

Requirements in .env first:
    GOOGLE_OAUTH_CLIENT_ID=<your client id>.apps.googleusercontent.com
    GOOGLE_OAUTH_CLIENT_SECRET=<your client secret>

After this script runs successfully:
    GMAIL_ACCESS_TOKEN=<short-lived>
    GMAIL_REFRESH_TOKEN=<long-lived>
    GOOGLE_DRIVE_ACCESS_TOKEN=<same access token, dual scope>
    GOOGLE_DRIVE_REFRESH_TOKEN=<same refresh token>

The access token expires every ~1 hour. Coral does NOT auto-refresh - the
seeders refresh on demand using the refresh token. Run this script again
if you ever need a fresh access token without doing the consent dance.
"""

from __future__ import annotations

import http.server
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel

from manthan_agent import config

console = Console()

# Combined scopes: Gmail read + Drive read.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

# Local loopback port - must match a redirect URI configured on the
# OAuth client in Google Cloud Console.
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}/callback"

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


# ────────────────────────────────────────────────────────────────────────
# Tiny single-shot HTTP server to receive the callback.
# ────────────────────────────────────────────────────────────────────────


class _CallbackResult:
    code: str | None = None
    error: str | None = None
    state: str | None = None


_result = _CallbackResult()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # stdlib requires this exact name
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return
        params = dict(urllib.parse.parse_qsl(parsed.query))
        _result.code = params.get("code")
        _result.error = params.get("error")
        _result.state = params.get("state")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = (
            "<!doctype html><meta charset=utf-8>"
            "<title>Manthan OAuth</title>"
            "<style>body{font-family:system-ui;max-width:520px;margin:80px auto;"
            "padding:0 24px;color:#111}h1{font-weight:600}</style>"
            "<h1>Got it.</h1>"
            "<p>You can close this tab and return to your terminal.</p>"
        )
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *_args: object) -> None:  # silence stdlib chatter
        pass


def _run_callback_server() -> http.server.HTTPServer:
    server = http.server.HTTPServer((CALLBACK_HOST, CALLBACK_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ────────────────────────────────────────────────────────────────────────
# .env writer - idempotent line replacement.
# ────────────────────────────────────────────────────────────────────────


def _write_env(updates: dict[str, str]) -> None:
    """Replace KEY=value lines in .env. Adds them if missing."""
    if not ENV_FILE.exists():
        raise SystemExit(f".env not found at {ENV_FILE}")
    lines = ENV_FILE.read_text().splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        replaced = False
        for key, value in updates.items():
            if line.startswith(f"{key}="):
                out.append(f"{key}={value}")
                seen.add(key)
                replaced = True
                break
        if not replaced:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out) + "\n")


# ────────────────────────────────────────────────────────────────────────
# Main flow
# ────────────────────────────────────────────────────────────────────────


def main() -> int:
    cfg = config.load()

    if not cfg.google_oauth_client_id or not cfg.google_oauth_client_secret:
        console.print(
            Panel(
                "[red]GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET "
                "are not set in .env[/red]\n\n"
                "Create a Desktop-application OAuth client in Google Cloud "
                "Console first:\n"
                "  1. https://console.cloud.google.com/apis/credentials\n"
                "  2. + Create Credentials → OAuth client ID → Desktop app\n"
                "  3. Name: 'Manthan Agent'\n"
                "  4. Add to .env, then re-run this script.\n\n"
                "Also enable the Gmail API and Drive API in Cloud Console:\n"
                "  https://console.cloud.google.com/apis/library/gmail.googleapis.com\n"
                "  https://console.cloud.google.com/apis/library/drive.googleapis.com\n\n"
                f"And add this exact redirect URI to your OAuth client:\n"
                f"  [bold]{REDIRECT_URI}[/bold]",
                title="Gmail OAuth bootstrap - missing prerequisites",
                border_style="red",
            )
        )
        return 1

    state = secrets.token_urlsafe(24)
    params = {
        "client_id": cfg.google_oauth_client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",      # makes Google issue a refresh token
        "prompt": "consent",           # always show consent → always get refresh token
        "state": state,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    console.print(f"[dim]→ starting callback server on {REDIRECT_URI}[/dim]")
    server = _run_callback_server()
    try:
        console.print("[dim]→ opening browser for consent…[/dim]")
        opened = webbrowser.open(auth_url)
        if not opened:
            console.print(
                f"[yellow]Browser didn't open. Visit this URL manually:[/yellow]\n"
                f"  {auth_url}"
            )

        # Wait up to 5 minutes for the user to consent.
        console.print("[dim]→ waiting for consent callback…[/dim]")
        start_ts = __import__("time").monotonic()
        while _result.code is None and _result.error is None:
            if __import__("time").monotonic() - start_ts > 300:
                console.print("[red]Timed out waiting for consent (5 min).[/red]")
                return 1
            __import__("time").sleep(0.5)
    finally:
        server.shutdown()

    if _result.error:
        console.print(f"[red]OAuth error:[/red] {_result.error}")
        return 1
    if _result.state != state:
        console.print("[red]State mismatch - possible CSRF, aborting.[/red]")
        return 1
    if not _result.code:
        console.print("[red]No authorization code received.[/red]")
        return 1

    console.print("[dim]→ exchanging code for tokens…[/dim]")
    resp = httpx.post(
        TOKEN_URL,
        data={
            "code": _result.code,
            "client_id": cfg.google_oauth_client_id,
            "client_secret": cfg.google_oauth_client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        console.print(
            f"[red]Token exchange failed:[/red] {resp.status_code} {resp.text}"
        )
        return 1
    data = resp.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")
    granted = data.get("scope", "")

    if not access_token or not refresh_token:
        console.print(
            f"[red]Missing token in response:[/red] {data}\n"
            "Common cause: this app was previously authorized without "
            "`prompt=consent`, so Google did not re-issue a refresh token. "
            "Revoke at https://myaccount.google.com/permissions and re-run."
        )
        return 1

    _write_env(
        {
            "GMAIL_ACCESS_TOKEN": access_token,
            "GMAIL_REFRESH_TOKEN": refresh_token,
            "GOOGLE_DRIVE_ACCESS_TOKEN": access_token,
            "GOOGLE_DRIVE_REFRESH_TOKEN": refresh_token,
        }
    )

    console.print(
        Panel(
            f"[green]✓[/green] tokens written to .env\n"
            f"  access expires in:  {expires_in}s\n"
            f"  granted scopes:     {granted}\n\n"
            "[dim]Gmail + Drive access tokens are short-lived (~1h). "
            "Seeders refresh on demand via the refresh token.[/dim]",
            title="Gmail OAuth bootstrap - ok",
            border_style="green",
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
