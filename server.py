#!/usr/bin/env python3
"""Minimal MCP server that executes commands on remote hosts over SSH."""

from __future__ import annotations

import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal, cast

import paramiko
from mcp.server.fastmcp import FastMCP

SERVER_NAME = "ssh-mcp"
HOST_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
USER_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
SUPPORTED_TRANSPORTS = {"stdio", "streamable-http"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    value = raw_value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False

    raise ValueError(
        f"Invalid boolean value for {name}: {raw_value!r}. Use one of: true/false, 1/0, yes/no, on/off."
    )


def _normalize_http_path(name: str, default: str) -> str:
    value = os.getenv(name, default).strip() or default
    if not value.startswith("/"):
        raise ValueError(f"{name} must start with '/': {value!r}")
    return value


DEFAULT_HOST = os.getenv("SSH_DEFAULT_HOST", "").strip()
DEFAULT_USER = os.getenv("SSH_DEFAULT_USER", "").strip()
DEFAULT_PASSWORD = os.getenv("SSH_DEFAULT_PASSWORD", "").strip()
DEFAULT_PORT = int(os.getenv("SSH_DEFAULT_PORT", "22"))
DEFAULT_TIMEOUT_SEC = int(os.getenv("SSH_DEFAULT_TIMEOUT_SEC", "60"))
CONNECT_TIMEOUT_SEC = int(os.getenv("SSH_CONNECT_TIMEOUT_SEC", "10"))
MAX_OUTPUT_CHARS = int(os.getenv("SSH_MAX_OUTPUT_CHARS", "12000"))
ALLOWED_HOSTS = {
    host.strip() for host in os.getenv("SSH_ALLOWED_HOSTS", "").split(",") if host.strip()
}
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio").strip().lower() or "stdio"
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1").strip() or "127.0.0.1"
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_MOUNT_PATH = _normalize_http_path("MCP_MOUNT_PATH", "/")
MCP_STREAMABLE_HTTP_PATH = _normalize_http_path("MCP_STREAMABLE_HTTP_PATH", "/mcp")
MCP_STATELESS_HTTP = _env_bool("MCP_STATELESS_HTTP", default=False)
if MCP_PORT <= 0 or MCP_PORT > 65535:
    raise ValueError("MCP_PORT must be between 1 and 65535")

mcp = FastMCP(
    SERVER_NAME,
    host=MCP_HOST,
    port=MCP_PORT,
    mount_path=MCP_MOUNT_PATH,
    streamable_http_path=MCP_STREAMABLE_HTTP_PATH,
    stateless_http=MCP_STATELESS_HTTP,
    json_response=True,
)


def _validate_host(host: str) -> None:
    if not HOST_PATTERN.match(host):
        raise ValueError(
            "Invalid host format. Use a hostname or IPv4 address (letters, numbers, ., _, -)."
        )
    if ALLOWED_HOSTS and host not in ALLOWED_HOSTS:
        allowed = ", ".join(sorted(ALLOWED_HOSTS))
        raise ValueError(f"Host '{host}' is not allowed. Allowed hosts: {allowed}")


def _validate_user(user: str) -> None:
    if not USER_PATTERN.match(user):
        raise ValueError("Invalid user format. Use letters, numbers, ., _, -.")


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    remainder = len(text) - MAX_OUTPUT_CHARS
    return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated {remainder} characters]"


def _validate_transport(transport: str) -> Literal["stdio", "streamable-http"]:
    if transport not in SUPPORTED_TRANSPORTS:
        supported = ", ".join(sorted(SUPPORTED_TRANSPORTS))
        raise ValueError(
            f"Unsupported MCP transport {transport!r}. Supported transports: {supported}"
        )
    return cast(Literal["stdio", "streamable-http"], transport)


@mcp.tool()
def ssh_exec(
    command: str,
    host: str = "",
    user: str = "",
    password: str = "",
    port: int = 0,
    identity_file: str = "",
    timeout_sec: int = 0,
    strict_host_key_checking: bool = True,
) -> dict[str, Any]:
    """Run one shell command on a remote machine via SSH and return stdout/stderr/exit code.

    Authentication (in order of precedence):
    - 'password': use password-based auth (disables key lookup).
    - 'identity_file': use a specific private key file.
    - Neither provided: try keys from ~/.ssh and the SSH agent automatically.
    """
    if not command.strip():
        raise ValueError("command must not be empty")

    target_host = host.strip() or DEFAULT_HOST
    target_user = user.strip() or DEFAULT_USER
    target_password = password.strip() or DEFAULT_PASSWORD
    target_port = port or DEFAULT_PORT
    target_timeout = timeout_sec or DEFAULT_TIMEOUT_SEC

    if not target_host:
        raise ValueError("host is required (or set SSH_DEFAULT_HOST)")
    if target_port <= 0 or target_port > 65535:
        raise ValueError("port must be between 1 and 65535")
    if target_timeout <= 0:
        raise ValueError("timeout_sec must be > 0")

    _validate_host(target_host)
    if target_user:
        _validate_user(target_user)

    target = f"{target_user}@{target_host}" if target_user else target_host

    client = paramiko.SSHClient()

    # Load known hosts for host key verification.
    client.load_system_host_keys()
    known_hosts_path = os.path.expanduser("~/.ssh/known_hosts")
    if os.path.exists(known_hosts_path):
        try:
            client.load_host_keys(known_hosts_path)
        except paramiko.SSHException:
            pass

    if strict_host_key_checking:
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: dict[str, Any] = {
        "hostname": target_host,
        "port": target_port,
        "timeout": CONNECT_TIMEOUT_SEC,
    }
    if target_user:
        connect_kwargs["username"] = target_user
    if target_password:
        # Explicit password: disable key lookup so the intent is unambiguous.
        connect_kwargs["password"] = target_password
        connect_kwargs["look_for_keys"] = False
        connect_kwargs["allow_agent"] = False
    if identity_file.strip():
        connect_kwargs["key_filename"] = identity_file.strip()

    try:
        client.connect(**connect_kwargs)
    except paramiko.AuthenticationException as exc:
        return {
            "ok": False,
            "error": f"Authentication failed: {exc}",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "target": target,
            "command": command,
        }
    except paramiko.SSHException as exc:
        return {
            "ok": False,
            "error": f"SSH error: {exc}",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "target": target,
            "command": command,
        }
    except (socket.timeout, TimeoutError):
        return {
            "ok": False,
            "error": f"Connection timed out after {CONNECT_TIMEOUT_SEC} seconds",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "target": target,
            "command": command,
        }
    except OSError as exc:
        return {
            "ok": False,
            "error": f"Connection error: {exc}",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "target": target,
            "command": command,
        }

    try:
        _stdin, _stdout, _stderr = client.exec_command(command, timeout=target_timeout)

        # Read stdout and stderr concurrently to avoid deadlocks when either
        # stream produces enough output to fill the remote SSH buffer.
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_out = pool.submit(lambda: _stdout.read().decode(errors="replace"))
            f_err = pool.submit(lambda: _stderr.read().decode(errors="replace"))
            stdout_text = f_out.result()
            stderr_text = f_err.result()

        exit_code = _stdout.channel.recv_exit_status()
    except socket.timeout:
        return {
            "ok": False,
            "error": f"Command timed out after {target_timeout} seconds",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "target": target,
            "command": command,
        }
    except paramiko.SSHException as exc:
        return {
            "ok": False,
            "error": f"SSH error during command execution: {exc}",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "target": target,
            "command": command,
        }
    finally:
        client.close()

    return {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "stdout": _truncate(stdout_text),
        "stderr": _truncate(stderr_text),
        "target": target,
        "command": command,
    }


if __name__ == "__main__":
    transport = _validate_transport(MCP_TRANSPORT)
    try:
        mcp.run(transport=transport)
    except KeyboardInterrupt:
        pass
