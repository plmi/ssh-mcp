# SSH MCP Server for Codex (Docker-first)

Very small MCP server that exposes one tool, `ssh_exec`, so Codex can run commands on a remote host over SSH and inspect outputs.

## What it does

- Starts an MCP stdio server.
- Exposes `ssh_exec(command, host, user, port, identity_file, timeout_sec, strict_host_key_checking)`.
- Uses OpenSSH inside a Docker container.
- Returns structured output: `ok`, `exit_code`, `stdout`, `stderr`, `target`.

## Prerequisites

- Docker
- Network access + credentials to your remote host
- Codex CLI installed and authenticated

## Build image

```bash
cd /Users/michael/projects/ssh-mcp
docker build -t ssh-mcp:latest .
```

## Quick local run

This launches the MCP server over stdio in a container.

```bash
docker run --rm -i \
  -v "$HOME/.ssh:/home/app/.ssh:ro" \
  -e HOME=/home/app \
  ssh-mcp:latest
```

## Add to Codex

You can configure this server with either the Codex CLI or `~/.codex/config.toml`.

### Option 1: Codex CLI (recommended)

```bash
codex mcp add sshRemote -- \
  docker run --rm -i \
  -v $HOME/.ssh:/home/app/.ssh:ro \
  -e HOME=/home/app \
  -e SSH_DEFAULT_HOST=your-host.example.com \
  -e SSH_DEFAULT_USER=ubuntu \
  -e SSH_ALLOWED_HOSTS=your-host.example.com \
  ssh-mcp:latest

codex mcp list
```

### Option 2: `~/.codex/config.toml`

```toml
[mcp_servers.sshRemote]
command = "docker"
args = [
  "run", "--rm", "-i",
  "-v", "/Users/<your-user>/.ssh:/home/app/.ssh:ro",
  "-e", "HOME=/home/app",
  "-e", "SSH_DEFAULT_HOST=your-host.example.com",
  "-e", "SSH_DEFAULT_USER=ubuntu",
  "-e", "SSH_ALLOWED_HOSTS=your-host.example.com",
  "ssh-mcp:latest"
]
startup_timeout_sec = 20
tool_timeout_sec = 120
```

Then restart Codex (CLI/TUI/IDE extension) and verify:

```bash
codex mcp list
```

## Using it in Codex

Example prompts:

- "Use `sshRemote` `ssh_exec` and run `uname -a`."
- "Run `df -h` on the remote host and summarize disk issues."
- "Run `journalctl -u nginx -n 200 --no-pager` and find recent errors."

## Environment variables

- `SSH_DEFAULT_HOST`: default host if `host` is omitted.
- `SSH_DEFAULT_USER`: default SSH username.
- `SSH_DEFAULT_PORT`: default port (default `22`).
- `SSH_DEFAULT_TIMEOUT_SEC`: default command timeout (default `60`).
- `SSH_CONNECT_TIMEOUT_SEC`: SSH connect timeout (default `10`).
- `SSH_ALLOWED_HOSTS`: comma-separated host allowlist. If set, only these hosts are permitted.
- `SSH_MAX_OUTPUT_CHARS`: truncates output size returned to Codex (default `12000`).

## SSH key notes

- The container uses mounted keys from `$HOME/.ssh`.
- If your key is passphrase-protected, make sure your host SSH agent and auth flow are already working.
- Keep host key verification on (`strict_host_key_checking=true`) unless you intentionally want first-connect auto-accept.

## Security notes

- This server executes arbitrary remote shell commands. Treat it as high-privilege.
- Restrict with `SSH_ALLOWED_HOSTS` whenever possible.
- Prefer least-privileged SSH users.
