# SSH MCP Server

A minimal MCP server that exposes one tool — `ssh_exec` — so Claude Code, OpenAI Codex, or any MCP-compatible AI can run commands on a remote host over SSH and inspect the output.

## What it does

- Starts an MCP stdio server.
- Exposes `ssh_exec(command, host, user, password, port, identity_file, timeout_sec, strict_host_key_checking)`.
- Uses [paramiko](https://www.paramiko.org/) for SSH — no dependency on a system `ssh` binary.
- Supports **password authentication** and **public key authentication**.
- Returns structured output: `ok`, `exit_code`, `stdout`, `stderr`, `target`.

## Prerequisites

- Docker
- Claude Code CLI (`claude`) and/or OpenAI Codex CLI (`codex`) installed and authenticated

## Build the image

```bash
cd /path/to/ssh-mcp
docker build -t ssh-mcp:latest .
```

---

## Add to Claude Code

### Option 1: Claude Code CLI (recommended)

**Key-based auth:**
```bash
claude mcp add sshRemote -- \
  docker run --rm -i \
  -v "$HOME/.ssh:/home/app/.ssh:ro" \
  -e HOME=/home/app \
  -e SSH_DEFAULT_HOST=your-host.example.com \
  -e SSH_DEFAULT_USER=ubuntu \
  -e SSH_ALLOWED_HOSTS=your-host.example.com \
  ssh-mcp:latest
```

**Password auth:**
```bash
claude mcp add sshRemote -- \
  docker run --rm -i \
  -e SSH_DEFAULT_HOST=your-host.example.com \
  -e SSH_DEFAULT_USER=ubuntu \
  -e SSH_DEFAULT_PASSWORD=your-password \
  -e SSH_ALLOWED_HOSTS=your-host.example.com \
  ssh-mcp:latest
```

Verify it was added:

```bash
claude mcp list
```

### Option 2: `~/.claude.json` (manual config)

Add the following to your `~/.claude.json` under the `mcpServers` key:

```json
{
  "mcpServers": {
    "sshRemote": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/Users/<your-user>/.ssh:/home/app/.ssh:ro",
        "-e", "HOME=/home/app",
        "-e", "SSH_DEFAULT_HOST=your-host.example.com",
        "-e", "SSH_DEFAULT_USER=ubuntu",
        "-e", "SSH_ALLOWED_HOSTS=your-host.example.com",
        "ssh-mcp:latest"
      ]
    }
  }
}
```

### Option 3: Project-level config (`.claude/settings.json`)

To scope the server to a single project, add it to `.claude/settings.json` in your project root:

```json
{
  "mcpServers": {
    "sshRemote": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "/Users/<your-user>/.ssh:/home/app/.ssh:ro",
        "-e", "HOME=/home/app",
        "-e", "SSH_DEFAULT_HOST=your-host.example.com",
        "-e", "SSH_DEFAULT_USER=ubuntu",
        "-e", "SSH_ALLOWED_HOSTS=your-host.example.com",
        "ssh-mcp:latest"
      ]
    }
  }
}
```

---

## Add to OpenAI Codex

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

---

## Specifying host, user, and port

You have two ways to provide connection details:

### Via environment variables (defaults for every call)

Pass `-e` flags to `docker run`:

| Variable | Example | Description |
|---|---|---|
| `SSH_DEFAULT_HOST` | `my-server.example.com` | Remote hostname or IP |
| `SSH_DEFAULT_USER` | `ubuntu` | SSH login username |
| `SSH_DEFAULT_PORT` | `2222` | SSH port (default: `22`) |
| `SSH_ALLOWED_HOSTS` | `my-server.example.com` | Comma-separated allowlist of hosts |

### Via tool arguments (per-call override)

You can also pass connection details directly when prompting the AI:

```
Run ssh_exec with host="10.0.1.50", user="admin", port=2222, command="uptime"
```

Per-call arguments override the environment variable defaults.

---

## Authentication

The `ssh_exec` tool selects the auth method based on what you provide:

| What you provide | Auth method used |
|---|---|
| `password` | Password auth only (key lookup disabled) |
| `identity_file` | The specified private key file |
| Neither | Keys from `~/.ssh` and the SSH agent, tried automatically |

### Password authentication

Pass the password as an environment variable default or as a per-call argument:

**As a default (env var):**
```bash
-e SSH_DEFAULT_PASSWORD=hunter2
```

**As a per-call argument:**
```
Run ssh_exec with host="10.0.1.50", user="admin", password="hunter2", command="uptime"
```

When a password is supplied, key lookup and the SSH agent are disabled so the auth method is unambiguous.

### Public key authentication

Mount your `~/.ssh` directory into the container and the server will automatically try the keys it finds there (including the SSH agent if a socket is forwarded):

```bash
-v "$HOME/.ssh:/home/app/.ssh:ro"
-e HOME=/home/app
```

To use a specific key file instead of scanning `~/.ssh`, pass it as a per-call argument:

```
Run ssh_exec with host="10.0.1.50", user="admin", identity_file="/home/app/.ssh/id_deploy", command="uptime"
```

**Setup (if you don't already have a key pair):**

1. Generate a key:
   ```bash
   ssh-keygen -t ed25519 -C "ssh-mcp"
   ```

2. Copy it to the remote host:
   ```bash
   ssh-copy-id -i ~/.ssh/id_ed25519.pub user@your-host.example.com
   ```

3. Test passwordless login:
   ```bash
   ssh user@your-host.example.com "echo ok"
   ```

---

## Environment variables reference

| Variable | Default | Description |
|---|---|---|
| `SSH_DEFAULT_HOST` | _(none)_ | Default remote host |
| `SSH_DEFAULT_USER` | _(none)_ | Default SSH username |
| `SSH_DEFAULT_PASSWORD` | _(none)_ | Default SSH password (password auth) |
| `SSH_DEFAULT_PORT` | `22` | Default SSH port |
| `SSH_DEFAULT_TIMEOUT_SEC` | `60` | Default command timeout (seconds) |
| `SSH_CONNECT_TIMEOUT_SEC` | `10` | SSH connection timeout (seconds) |
| `SSH_ALLOWED_HOSTS` | _(none, allow all)_ | Comma-separated host allowlist |
| `SSH_MAX_OUTPUT_CHARS` | `12000` | Output truncation limit |

---

## Example prompts

- "Use `sshRemote` `ssh_exec` and run `uname -a`."
- "Run `df -h` on the remote host and summarize disk usage."
- "Run `journalctl -u nginx -n 200 --no-pager` and find recent errors."
- "Check CPU load on `my-server.example.com` with `uptime`."

---

## Security notes

- This server can execute arbitrary remote shell commands — treat it as a high-privilege tool.
- Always set `SSH_ALLOWED_HOSTS` to restrict which hosts can be targeted.
- Use a least-privileged SSH user on the remote host where possible.
- Keep `strict_host_key_checking=true` (the default) to prevent MITM attacks.
- Prefer key-based auth over passwords where possible. If you do use a password, pass it via an environment variable rather than as a tool argument so it stays out of conversation logs.
