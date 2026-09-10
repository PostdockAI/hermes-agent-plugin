"""Plugin-provided ``hermes myagent`` setup commands."""

from __future__ import annotations

import argparse
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

import httpx

from hermes_cli.config import get_env_value_prefer_dotenv, remove_env_value, save_env_value
from hermes_cli.mcp_config import _remove_mcp_server, _save_mcp_server


DEFAULT_API_URL = "https://myagent.to"
PERMISSIONS = ["identity:read", "messages:write", "inbox:read", "inbox:bookmark"]


def register_cli(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="myagent_command", required=False)
    connect = commands.add_parser("connect", help="Connect this Hermes profile to an agent address")
    connect.add_argument("--api", default=DEFAULT_API_URL, help=f"Core API URL (default: {DEFAULT_API_URL})")
    connect.add_argument("--no-browser", action="store_true", help="Print the approval URL without opening it")
    commands.add_parser("status", help="Check the saved connection")
    commands.add_parser("doctor", help="Check authentication and MCP configuration")
    commands.add_parser("disconnect", help="Remove the local myagent connection")
    parser.set_defaults(func=dispatch)


def dispatch(args: argparse.Namespace) -> int:
    command = getattr(args, "myagent_command", None) or "status"
    if command == "connect":
        return _connect(args)
    if command == "status":
        return _status(check_mcp=False)
    if command == "doctor":
        return _status(check_mcp=True)
    if command == "disconnect":
        return _disconnect()
    print(f"unknown subcommand: {command}", file=sys.stderr)
    return 2


def _connect(args: argparse.Namespace) -> int:
    api_url = str(args.api).rstrip("/")
    if not api_url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        print("API URL must use HTTPS (HTTP is allowed only for localhost).", file=sys.stderr)
        return 2

    try:
        with httpx.Client(base_url=f"{api_url}/", timeout=20.0) as client:
            started = _post(client, "v1/connect/start", {"permissions": PERMISSIONS})
            verification_url = str(started["verification_url"])
            print("\nAuthorize this Hermes connection:")
            print(f"  {verification_url}")
            print(f"  Code: {started['user_code']}\n")
            if not args.no_browser:
                webbrowser.open(verification_url)
            print("Waiting for approval (Ctrl-C to cancel)…")
            deadline = time.monotonic() + int(started.get("expires_in", 600))
            interval = max(1, int(started.get("interval", 2)))
            while time.monotonic() < deadline:
                result = _post(client, "v1/connect/poll", {"device_code": started["device_code"]})
                if result.get("status") == "approved":
                    return _save_connection(
                        api_url,
                        str(result["address"]),
                        str(result["secret"]),
                        str(Path.cwd().resolve()),
                        client,
                    )
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\nConnection cancelled.")
        return 130
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        print(f"Connection failed: {_error_message(exc)}", file=sys.stderr)
        return 1

    print("Connection code expired. Run the command again.", file=sys.stderr)
    return 1


def _save_connection(
    api_url: str,
    address: str,
    secret: str,
    workspace: str,
    client: httpx.Client,
) -> int:
    identity = _get(client, "v1/whoami", secret)
    if identity.get("address") != address:
        raise ValueError("approved credential returned the wrong agent address")

    save_env_value("MYAGENT_API_URL", api_url)
    save_env_value("MYAGENT_TOKEN", secret)
    save_env_value("MYAGENT_ADDRESS", address)
    save_env_value("MYAGENT_ALLOW_ALL_USERS", "true")
    save_env_value("MYAGENT_WORKSPACE", workspace)
    saved = _save_mcp_server(
        "myagent",
        {
            "url": f"{api_url}/mcp",
            "headers": {"Authorization": "Bearer ${MYAGENT_TOKEN}"},
        },
    )
    if not saved:
        raise ValueError("Hermes rejected the MCP server configuration")
    print(f"✓ Connected {address}")
    print(f"✓ Workspace {workspace}")
    print("Run `hermes gateway run` to receive messages.")
    return 0


def _status(*, check_mcp: bool) -> int:
    api_url = _setting("MYAGENT_API_URL")
    secret = _setting("MYAGENT_TOKEN")
    if not api_url or not secret:
        print("Not connected. Run `hermes myagent connect`.")
        return 1
    try:
        with httpx.Client(base_url=f"{api_url.rstrip('/')}/", timeout=20.0) as client:
            identity = _get(client, "v1/whoami", secret)
    except httpx.HTTPError as exc:
        print(f"Connection check failed: {_error_message(exc)}", file=sys.stderr)
        return 1
    print(f"✓ Connected as {identity.get('address', 'unknown')}")
    workspace = _setting("MYAGENT_WORKSPACE")
    if not workspace or not Path(workspace).is_dir():
        print("✗ Saved workspace is missing. Reconnect from the intended workspace.", file=sys.stderr)
        return 1
    print(f"✓ Workspace {workspace}")
    if check_mcp:
        from hermes_cli.mcp_config import _get_mcp_servers

        server = _get_mcp_servers().get("myagent")
        expected = f"{api_url.rstrip('/')}/mcp"
        if not isinstance(server, dict) or server.get("url") != expected:
            print("✗ myagent MCP server is missing or points to a different API.", file=sys.stderr)
            return 1
        print("✓ MCP server configured")
    return 0


def _disconnect() -> int:
    for key in (
        "MYAGENT_API_URL",
        "MYAGENT_TOKEN",
        "MYAGENT_ADDRESS",
        "MYAGENT_ALLOW_ALL_USERS",
        "MYAGENT_WORKSPACE",
    ):
        remove_env_value(key)
    _remove_mcp_server("myagent")
    print("✓ Removed the local myagent connection. The server credential can be revoked in your account.")
    return 0


def _setting(key: str) -> str:
    return str(get_env_value_prefer_dotenv(key) or os.getenv(key) or "").strip()


def _post(client: httpx.Client, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=body)
    response.raise_for_status()
    return response.json()


def _get(client: httpx.Client, path: str, secret: str) -> dict[str, Any]:
    response = client.get(path, headers={"authorization": f"Bearer {secret}"})
    response.raise_for_status()
    return response.json()


def _error_message(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            return str(exc.response.json().get("error", {}).get("message") or exc)
        except ValueError:
            pass
    return str(exc)
