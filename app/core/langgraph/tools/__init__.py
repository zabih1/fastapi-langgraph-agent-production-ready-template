"""LangGraph tools for enhanced language model capabilities.

This package contains custom tools that can be used with LangGraph to extend
the capabilities of language models. Currently includes tools for web search
and other external integrations.

MCP tools are loaded separately, not listed here, because they are
configured at runtime (see ``../mcp.py``) and loaded by the agent in
``graph.py`` when ``MCP_SERVERS`` is set.
"""

from langchain_core.tools.base import BaseTool

from .ask_human import ask_human
from .duckduckgo_search import duckduckgo_search_tool

tools: list[BaseTool] = [duckduckgo_search_tool, ask_human]
