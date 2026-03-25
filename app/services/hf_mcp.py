from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from huggingface_hub import InferenceClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.settings import Settings

log = logging.getLogger("hireiq.mcp")

NOTION_API = "https://api.notion.com/v1"
NOTION_VER = "2022-06-28"


# ─── Exceptions ──────────────────────────────────────────────────────────────


class HireIQError(Exception):
    def __init__(
        self,
        detail: str,
        *,
        status_code: int = 500,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.extra = extra or {}


# ─── HTTP fallback (when MCP stdio is unavailable) ──────────────────────────


class NotionHTTPFallback:
    """Direct Notion REST client — used when MCP stdio is unavailable."""

    def __init__(self, token: str) -> None:
        self._token = token

    def _h(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": NOTION_VER,
            "Content-Type": "application/json",
        }

    async def call_tool(self, tool: str, args: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as c:
            if tool == "API-post-page":
                r = await c.post(f"{NOTION_API}/pages", headers=self._h(), json=args)
            elif tool == "API-post-database":
                r = await c.post(f"{NOTION_API}/databases", headers=self._h(), json=args)
            elif tool == "API-post-search":
                r = await c.post(f"{NOTION_API}/search", headers=self._h(), json=args)
            elif tool == "API-get-block-children":
                bid = args.pop("block_id")
                r = await c.get(
                    f"{NOTION_API}/blocks/{bid}/children",
                    headers=self._h(),
                    params=args,
                )
            elif tool == "API-get-self":
                r = await c.get(f"{NOTION_API}/users/me", headers=self._h())
            elif tool == "API-patch-page":
                pid = args.pop("page_id")
                r = await c.patch(
                    f"{NOTION_API}/pages/{pid}", headers=self._h(), json=args
                )
            elif tool == "API-retrieve-a-page":
                pid = args.pop("page_id")
                r = await c.get(f"{NOTION_API}/pages/{pid}", headers=self._h())
            elif tool == "API-query-database":
                dbid = args.pop("database_id")
                r = await c.post(
                    f"{NOTION_API}/databases/{dbid}/query",
                    headers=self._h(),
                    json=args,
                )
            else:
                return {"error": f"Unknown tool: {tool}"}
            return r.json()


# ─── Block builders ──────────────────────────────────────────────────────────


def _rt(content: str) -> list:
    """Rich-text helper."""
    return [{"text": {"content": content}}]


def _heading(text: str, level: int = 2) -> dict:
    k = f"heading_{level}"
    return {"object": "block", "type": k, k: {"rich_text": _rt(text)}}


def _para(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rt(text)},
    }


def _bullet(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rt(text)},
    }


# ─── Service ─────────────────────────────────────────────────────────────────


class HFMCPService:
    """HuggingFace InferenceClient for content generation + Notion MCP for
    all reads and writes."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._hf = InferenceClient(
            model=settings.hf_model,
            token=settings.hf_api_key,
        )

    async def close(self) -> None:
        pass

    # ── Notion transport layer (MCP primary, httpx fallback) ─────────────

    @asynccontextmanager
    async def notion_mcp(self):
        """Spin up Notion MCP stdio server and yield a ClientSession."""
        params = StdioServerParameters(
            command="npx",
            args=["-y", "@notionhq/notion-mcp-server"],
            env={**os.environ, "NOTION_TOKEN": self.settings.notion_token},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    def notion_session(self):
        return self.notion_mcp()

    async def mcp_call(self, session: Any, tool: str, args: dict) -> dict:
        """Execute a single MCP tool call, returning parsed JSON."""
        if isinstance(session, NotionHTTPFallback):
            return await session.call_tool(tool, args)
        result = await session.call_tool(tool, args)
        text = result.content[0].text if result.content else "{}"
        return json.loads(text)

    # ── Notion helpers ───────────────────────────────────────────────────

    async def mcp_create_page(
        self,
        session: Any,
        parent_id: str,
        title: str,
        children: list,
    ) -> dict:
        """Create a Notion page via MCP API-post-page tool."""
        result = await self.mcp_call(
            session,
            "API-post-page",
            {
                "parent": {"page_id": parent_id},
                "properties": {"title": {"title": _rt(title)}},
                "children": children[:100],
            },
        )
        if result.get("status") and result["status"] >= 400:
            raise HireIQError(
                f"Notion MCP error: {result.get('message', str(result)[:200])}",
                status_code=502,
            )
        return result

    async def mcp_create_database(
        self,
        session: Any,
        parent_id: str,
        title: str,
        properties: dict,
    ) -> dict:
        """Create a Notion page representing a database (columns listed as content)."""
        blocks = [_heading(title), _para("Records will be added as sub-pages.")]
        blocks.append(_heading("Fields", 3))
        for col_name in properties:
            blocks.append(_bullet(col_name))
        result = await self.mcp_call(
            session,
            "API-post-page",
            {
                "parent": {"page_id": parent_id},
                "properties": {"title": {"title": _rt(title)}},
                "children": blocks[:100],
            },
        )
        if result.get("status") and result["status"] >= 400:
            raise HireIQError(
                f"Notion MCP error: {result.get('message', str(result)[:200])}",
                status_code=502,
            )
        return result

    async def mcp_add_database_row(
        self,
        session: Any,
        database_id: str,
        properties: dict,
    ) -> dict:
        """Add a row to a Notion database (API-post-page with database parent)."""
        result = await self.mcp_call(
            session,
            "API-post-page",
            {
                "parent": {"database_id": database_id},
                "properties": properties,
            },
        )
        if result.get("status") and result["status"] >= 400:
            raise HireIQError(
                f"Notion MCP error: {result.get('message', str(result)[:200])}",
                status_code=502,
            )
        return result

    async def mcp_search(self, session: Any, query: str = "") -> list:
        """Search Notion pages/databases."""
        result = await self.mcp_call(
            session, "API-post-search", {"query": query, "page_size": 50}
        )
        return result.get("results", [])

    async def mcp_query_database(
        self,
        session: Any,
        database_id: str,
        filter_obj: dict | None = None,
    ) -> list:
        """Query a Notion database."""
        args: dict[str, Any] = {"database_id": database_id}
        if filter_obj:
            args["filter"] = filter_obj
        result = await self.mcp_call(session, "API-query-database", args)
        return result.get("results", [])

    async def mcp_patch_page(
        self, session: Any, page_id: str, properties: dict
    ) -> dict:
        """Update a Notion page's properties."""
        return await self.mcp_call(
            session,
            "API-patch-page",
            {"page_id": page_id, "properties": properties},
        )

    async def check_health(self) -> bool:
        """Verify MCP connection with API-get-self."""
        try:
            async with self.notion_session() as mcp:
                me = await self.mcp_call(mcp, "API-get-self", {})
                return bool(me.get("id"))
        except Exception:
            return False

    # ── HuggingFace text generation ──────────────────────────────────────

    async def generate_text(
        self, system: str, user_msg: str, *, max_tokens: int = 4096
    ) -> str:
        """Generate text via HuggingFace InferenceClient (streaming)."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]
        out = ""
        for chunk in self._hf.chat_completion(
            messages=messages, max_tokens=max_tokens, stream=True
        ):
            if chunk.choices:
                d = chunk.choices[0].delta
                if d.content:
                    out += d.content
        if not out.strip():
            raise HireIQError(
                "HuggingFace model returned no text response.", status_code=502
            )
        return out
