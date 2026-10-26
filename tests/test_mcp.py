"""Tests for MCP server configuration parsing and tool loading.

These tests do not need a live MCP server, an LLM key, or a database:
parsing is pure, and tool loading is tested with a fake client class.
"""

import asyncio

import pytest
from langchain_core.tools import tool

from app.core.langgraph.mcp import (
    MCPServerConfig,
    load_mcp_tools,
    mcp_server_to_adapter_config,
    parse_mcp_servers,
)


def test_parse_mcp_servers_empty() -> None:
    """Blank config means MCP is disabled."""
    assert parse_mcp_servers("") == {}
    assert parse_mcp_servers(None) == {}
    assert parse_mcp_servers("   ") == {}


def test_parse_mcp_servers_stdio() -> None:
    """A stdio server keeps its command, args, and env."""
    servers = parse_mcp_servers(
        '{"filesystem": {"transport": "stdio", "command": "npx", "args": ["-y", "server"], "env": {"HOME": "/tmp"}}}'
    )
    config = servers["filesystem"]
    assert isinstance(config, MCPServerConfig)
    assert config.transport == "stdio"
    assert config.command == "npx"
    assert config.args == ["-y", "server"]
    assert config.env == {"HOME": "/tmp"}


def test_parse_mcp_servers_streamable_http() -> None:
    """A remote server keeps its URL and headers."""
    servers = parse_mcp_servers(
        '{"remote": {"transport": "streamable_http", '
        '"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer x"}}}'
    )
    assert servers["remote"].url == "https://example.com/mcp"
    assert servers["remote"].headers == {"Authorization": "Bearer x"}


def test_parse_mcp_servers_rejects_invalid_json() -> None:
    """Garbage input must fail loudly, not silently disable MCP."""
    with pytest.raises(ValueError):
        parse_mcp_servers("{not json")


def test_parse_mcp_servers_rejects_non_object() -> None:
    """The top level must be an object, not a list."""
    with pytest.raises(ValueError):
        parse_mcp_servers('["filesystem"]')


def test_parse_mcp_servers_rejects_stdio_without_command() -> None:
    """A stdio server with nothing to spawn is a config error."""
    with pytest.raises(ValueError):
        parse_mcp_servers('{"bad": {"transport": "stdio"}}')


def test_parse_mcp_servers_rejects_http_without_url() -> None:
    """A remote server with no URL is a config error."""
    with pytest.raises(ValueError):
        parse_mcp_servers('{"bad": {"transport": "streamable_http"}}')


def test_parse_mcp_servers_rejects_unknown_transport() -> None:
    """Typos in the transport name must not silently become stdio."""
    with pytest.raises(ValueError):
        parse_mcp_servers('{"bad": {"transport": "grpc", "command": "x"}}')


def test_mcp_server_to_adapter_config_stdio() -> None:
    """Stdio configs map to the adapter's command/args/env format."""
    config = MCPServerConfig(transport="stdio", command="npx", args=["-y", "server"])
    assert mcp_server_to_adapter_config(config) == {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "server"],
        "env": {},
    }


def test_mcp_server_to_adapter_config_http() -> None:
    """Remote configs map to the adapter's url/headers format."""
    config = MCPServerConfig(transport="sse", url="https://example.com/sse")
    assert mcp_server_to_adapter_config(config) == {
        "transport": "sse",
        "url": "https://example.com/sse",
        "headers": {},
    }


def test_load_mcp_tools_empty_returns_no_client() -> None:
    """No servers means no client import and no tools."""
    tools, client = asyncio.run(load_mcp_tools({}))
    assert tools == []
    assert client is None


def test_load_mcp_tools_uses_client_class() -> None:
    """Loading delegates to the client and returns its tools."""

    @tool
    def fake_tool() -> str:
        """A fake MCP tool for tests."""
        return "ok"

    class FakeClient:
        """Stand-in for MultiServerMCPClient."""

        def __init__(self, connections: dict) -> None:
            self.connections = connections

        async def get_tools(self) -> list:
            return [fake_tool]

    servers = parse_mcp_servers('{"demo": {"transport": "stdio", "command": "demo"}}')
    tools, client = asyncio.run(load_mcp_tools(servers, client_class=FakeClient))
    assert isinstance(client, FakeClient)
    assert client.connections["demo"]["command"] == "demo"
    assert [t.name for t in tools] == ["fake_tool"]
