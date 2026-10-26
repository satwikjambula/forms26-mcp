"""Exercise the real stdio protocol and every tool, without Oracle credentials."""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    project = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith("ORACLE_")}
    server = StdioServerParameters(command=sys.executable,
        args=["-m", "forms26_mcp.server", "--root", str(project / "examples")], env=env)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            expected = {"list_forms", "analyze_form", "list_components", "get_source",
                        "migration_risks", "plan_apex", "draft_api", "inspect_database_objects",
                        "upstream_status", "upstream_read", "upstream_fetch", "upstream_annotate"}
            assert {t.name for t in tools.tools} == expected

            async def call(name, args):
                result = await session.call_tool(name, args)
                assert not result.isError, (name, result)
                return result.structuredContent or json.loads(result.content[0].text)

            assert (await call("list_forms", {}))["total"] == 1
            assert not (await call("upstream_status", {}))["configured"]
            base = {"path": "orders_fmb.xml"}
            assert (await call("analyze_form", base))["counts"]["Block"] == 3
            components = await call("list_components", {**base, "kind": "Trigger", "limit": 1})
            assert components["next_offset"] == 1
            source = await call("get_source", {**base, "component_id": components["items"][0]["id"], "limit": 20})
            assert source["next_offset"] == 20
            assert (await call("migration_risks", base))["total"] == 4
            assert len((await call("plan_apex", base))["regions"]) == 3
            api = await call("draft_api", {**base, "block_name": "ORDERS", "package_name": "ORDERS_API"})
            assert "NOT_PUBLISHED" in api["ords_sql"]
            assert (await call("inspect_database_objects", {"names": ["ORDERS"]}))["status"] == "not_configured"
            invalid = await session.call_tool("analyze_form", {"path": "../pyproject.toml"})
            assert invalid.isError
            invalid = await session.call_tool("draft_api", {**base, "block_name": "ORDERS", "package_name": "X';DROP TABLE T"})
            assert invalid.isError
            await session.read_resource("forms26://workflow")
            prompt = await session.get_prompt("modernize_form", {"path": "orders_fmb.xml"})
            assert prompt.messages
            print("PASS: stdio initialization, 12 tools, pagination, source retrieval, errors, resource and prompt")


if __name__ == "__main__":
    asyncio.run(main())
