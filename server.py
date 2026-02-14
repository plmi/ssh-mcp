#!/usr/bin/env python3
"""Minimal MCP server that executes commands on remote hosts over SSH."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from typing import Any

from mcp.server.fastmcp import FastMCP

SERVER_NAME = "ssh-mcp"
HOST_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
USER_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

DEFAULT_HOST = os.getenv("SSH_DEFAULT_HOST", "").strip()
DEFAULT_USER = os.getenv("SSH_DEFAULT_USER", "").strip()
DEFAULT_PORT = int(os.getenv("SSH_DEFAULT_PORT", "22"))
DEFAULT_TIMEOUT_SEC = int(os.getenv("SSH_DEFAULT_TIMEOUT_SEC", "60"))
CONNECT_TIMEOUT_SEC = int(os.getenv("SSH_CONNECT_TIMEOUT_SEC", "10"))
MAX_OUTPUT_CHARS = int(os.getenv("SSH_MAX_OUTPUT_CHARS", "12000"))
ALLOWED_HOSTS = {
    host.strip() for host in os.getenv("SSH_ALLOWED_HOSTS", "").split(",") if host.strip()
}

mcp = FastMCP(SERVER_NAME, json_response=True)


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


@mcp.tool()
def ssh_exec(
    command: str,
    host: str = "",
    user: str = "",
    port: int = 22,
    identity_file: str = "",
    timeout_sec: int = 60,
    strict_host_key_checking: bool = True,
) -> dict[str, Any]:
    """Run one shell command on a remote machine via SSH and return stdout/stderr/exit code."""
    if not command.strip():
        raise ValueError("command must not be empty")

    target_host = host.strip() or DEFAULT_HOST
    target_user = user.strip() or DEFAULT_USER
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
    ssh_cmd = [
        "ssh",
        "-p",
        str(target_port),
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={CONNECT_TIMEOUT_SEC}",
    ]

    if strict_host_key_checking:
        ssh_cmd.extend(["-o", "StrictHostKeyChecking=yes"])
    else:
        ssh_cmd.extend(["-o", "StrictHostKeyChecking=accept-new"])

    if identity_file.strip():
        ssh_cmd.extend(["-i", identity_file.strip()])

    ssh_cmd.extend([target, command])

    try:
        completed = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=target_timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": f"ssh binary not found: {exc}",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "target": target,
            "command": command,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return {
            "ok": False,
            "error": f"Command timed out after {target_timeout} seconds",
            "exit_code": None,
            "stdout": _truncate(stdout),
            "stderr": _truncate(stderr),
            "target": target,
            "command": command,
            "ssh_invocation": " ".join(shlex.quote(token) for token in ssh_cmd),
        }

    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": _truncate(completed.stdout),
        "stderr": _truncate(completed.stderr),
        "target": target,
        "command": command,
        "ssh_invocation": " ".join(shlex.quote(token) for token in ssh_cmd),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
