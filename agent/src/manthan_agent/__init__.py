"""Manthan investigation agent.

A small loop that drives an LLM (via OpenRouter) over a SQL data plane
(Coral, via MCP) to investigate billing-operations cases, draft replies,
and propose actions. Every step is cited and audited.

No agent framework. The whole loop is readable in one sitting.
"""

__version__ = "0.1.0"
