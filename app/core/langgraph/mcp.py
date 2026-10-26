"""Model Context Protocol (MCP) client support for LangGraph tools.

This module is the scoped MCP part of upstream issue #19 ("Add Support
for MCP & A2A"). It covers the client side only: the agent can load tools
from external MCP servers and use them alongside its built-in tools.
A2A (agent-to-agent) support is intentionally left as a follow-up.

Configuration is a single JSON object in the ``MCP_SERVERS`` environment
variable, mapping a server name to its connection details:

.. code-block:: json

    {
        "filesystem": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
            "env": {}
        },
        "remote": {
            "transport": "streamable_http",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer <token>"}
        }
    }

When ``MCP_SERVERS`` is empty, this module is a no-op and the agent keeps
using only its built-in tools. The ``langchain-mcp-adapters`` package is
only imported when MCP tools are actually loaded, so parsing and
validation work without it installed. Install it with the ``mcp`` extra
(``pip install .[mcp]``) before enabling MCP servers.
"""

import inspect
import json
import logging
from typing import Any, Literal, Optional

from langchain_core.tools.base import BaseTool
from pydantic import BaseModel, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)

MCPTransport = Literal["stdio", "streamable_http", "sse"]


class MCPServerConfig(BaseModel):
    """Connection details for a single MCP server.

    Attributes:
        transport: How to reach the server. ``stdio`` spawns a local
            command, ``streamable_http`` and ``sse`` connect to a URL.
        command: Command to spawn for ``stdio`` servers.
        args: Arguments passed to ``command``.
        env: Environment variables passed to a ``stdio`` server process.
        url: Endpoint for ``streamable_http`` and ``sse`` servers.
        headers: HTTP headers sent to a remote server, e.g. auth headers.
        timeout: Optional per-request timeout in seconds.
    """

    transport: MCPTransport = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: Optional[float] = None

    @model_validator(mode="after")
    def _check_transport_fields(self) -> "MCPServerConfig":
        """Require the fields each transport actually needs."""
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio MCP servers require a 'command'")
        if self.transport in ("streamable_http", "sse") and not self.url:
            raise ValueError("streamable_http and sse MCP servers require a 'url'")
        return self


def parse_mcp_servers(raw: str | None) -> dict[str, MCPServerConfig]:
    """Parse the ``MCP_SERVERS`` JSON value into validated server configs.

    Args:
        raw: JSON object mapping server names to connection details,
            or an empty/blank string for "no MCP servers".

    Returns:
        Mapping of server name to validated config. Empty when ``raw``
        is blank.

    Raises:
        ValueError: If ``raw`` is not a JSON object, or any server
            config fails validation.
    """
    if raw is None or not raw.strip():
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MCP_SERVERS is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("MCP_SERVERS must be a JSON object mapping server names to configs")

    servers: dict[str, MCPServerConfig] = {}
    for name, config in parsed.items():
        if not isinstance(config, dict):
            raise ValueError(f"MCP server '{name}' must be a JSON object")
        try:
            servers[name] = MCPServerConfig.model_validate(config)
        except ValidationError as exc:
            raise ValueError(f"Invalid config for MCP server '{name}': {exc}") from exc
    return servers


def mcp_server_to_adapter_config(config: MCPServerConfig) -> dict[str, Any]:
    """Convert a validated config to ``langchain-mcp-adapters`` format.

    Args:
        config: Validated MCP server config.

    Returns:
        Connection dict accepted by ``MultiServerMCPClient``.
    """
    adapter_config: dict[str, Any] = {"transport": config.transport}
    if config.transport == "stdio":
        adapter_config["command"] = config.command
        adapter_config["args"] = config.args
        adapter_config["env"] = config.env
    else:
        adapter_config["url"] = config.url
        adapter_config["headers"] = config.headers
    if config.timeout is not None:
        adapter_config["timeout"] = config.timeout
    return adapter_config


async def load_mcp_tools(
    servers: dict[str, MCPServerConfig],
    client_class: Any = None,
) -> tuple[list[BaseTool], Any]:
    """Load tools from configured MCP servers.

    The returned client must be kept alive for as long as the tools are
    used (callers store it on the agent). This function does not close
    it, because MCP tools call back into their server sessions.

    Args:
        servers: Validated MCP server configs, as returned by
            :func:`parse_mcp_servers`.
        client_class: Optional client class to use instead of
            ``MultiServerMCPClient``. Mainly for tests; production code
            leaves it unset.

    Returns:
        A ``(tools, client)`` tuple. Both are empty/``None`` when no
        servers are configured.

    Raises:
        RuntimeError: If MCP servers are configured but
            ``langchain-mcp-adapters`` is not installed.
    """
    if not servers:
        return [], None

    if client_class is None:
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError as exc:
            raise RuntimeError(
                "MCP servers are configured but 'langchain-mcp-adapters' is not "
                "installed. Install the mcp extra, e.g. pip install .[mcp]."
            ) from exc
        client_class = MultiServerMCPClient

    connections = {name: mcp_server_to_adapter_config(config) for name, config in servers.items()}
    client = client_class(connections)
    tools_or_awaitable = client.get_tools()
    if inspect.isawaitable(tools_or_awaitable):
        tools_or_awaitable = await tools_or_awaitable
    tools = list(tools_or_awaitable)
    logger.info("Loaded %d tools from %d MCP server(s)", len(tools), len(servers))
    return tools, client
