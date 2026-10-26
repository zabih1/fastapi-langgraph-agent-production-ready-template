# MCP Support (Client)

> Status: this covers the MCP **client** side of upstream issue #19
> ("Add Support for MCP & A2A"). A2A support is a separate follow-up.

MCP (Model Context Protocol) lets the agent use tools from external
servers — for example a filesystem server, a database server, or a
company-internal tool server — alongside its built-in tools
(`duckduckgo_search`, `ask_human`).

## Setup

Install the optional MCP dependency:

```bash
pip install .[mcp]
# or, with uv:
uv sync --extra mcp
```

Then set `MCP_SERVERS` to a JSON object mapping server names to
connection details:

```bash
# stdio server (spawned locally)
MCP_SERVERS='{"filesystem": {"transport": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]}}'

# remote server (streamable HTTP)
MCP_SERVERS='{"remote": {"transport": "streamable_http", "url": "https://example.com/mcp", "headers": {"Authorization": "Bearer <token>"}}}'
```

Supported transports:

| Transport | Required fields |
| --- | --- |
| `stdio` | `command`, plus optional `args` and `env` |
| `streamable_http` | `url`, plus optional `headers` |
| `sse` | `url`, plus optional `headers` |

An optional `timeout` (seconds) can be set on any server.

## Behaviour

- When `MCP_SERVERS` is empty, MCP is disabled and nothing changes.
- MCP tools are loaded once, when the graph is first created, and are
  re-bound to the LLM together with the built-in tools.
- If a server name clashes with a built-in tool, the built-in tool
  wins and the MCP tool is skipped (with a warning log).
- If MCP config is invalid, or a server cannot be reached, or
  `langchain-mcp-adapters` is not installed, the agent logs a warning
  and keeps running with its built-in tools only. A broken MCP server
  must not take the whole agent down.
- The MCP client is kept alive for the lifetime of the agent process,
  because MCP tools call back into their server sessions.

## Security notes

- Only connect to MCP servers you trust: their tools run with the
  agent's permissions and can read whatever the server exposes.
- Prefer scoped credentials (per-server tokens, read-only filesystem
  roots) over broad ones, and keep tokens in environment variables,
  not in the repo.
- `ask_human` remains the guard for irreversible actions: use it
  before an MCP tool deletes data, sends messages, or spends money.
