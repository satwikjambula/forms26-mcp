"""Check host -> Forms26 -> configured upstream server against supplied example modules.

This explicitly fetches modules (cache/converter writes). It never executes
legacy PL/SQL or writes to Oracle Database. The output contains counts/evidence,
not full source bodies. Install Forms26 first, then run with --config PATH.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(args):
    params = StdioServerParameters(command=sys.executable,
        args=["-m", "forms26_mcp.server", "--upstream-config", str(Path(args.config).resolve())],
        env={k: v for k, v in os.environ.items() if k in {"PYTHONPATH", "PATH", "SYSTEMROOT"}})
    report = {"upstream": None, "modules": [], "failures": []}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(name, arguments):
                result = await session.call_tool(name, arguments)
                if result.isError:
                    raise RuntimeError(" ".join(c.text for c in result.content if c.type == "text"))
                return result.structuredContent or json.loads(result.content[0].text)

            report["upstream"] = await call("upstream_status", {})
            if not report["upstream"]["connected"]:
                raise RuntimeError("Upstream did not connect")
            native_page = await call("upstream_read", {"tool_name": "list_modules", "arguments": {"limit": 1}})
            assert len(native_page.get("modules", [])) <= 1
            blocked = await session.call_tool("upstream_read", {"tool_name": "fetch_module", "arguments": {}})
            assert blocked.isError, "Read-only adapter must reject conversion writes"
            # Fetch all parents/libraries before inspection so cached inheritance can resolve.
            for module in args.modules:
                await call("upstream_fetch", {"module": module})
            for module in args.modules:
                try:
                    source = {"path": "upstream:" + module}
                    analysis = await call("analyze_form", source)
                    components, offset = [], 0
                    while True:
                        page = await call("list_components", {**source, "offset": offset, "limit": 200})
                        components.extend(page["items"])
                        if page["next_offset"] is None:
                            break
                        offset = page["next_offset"]
                    plan = await call("plan_apex", source)
                    risks = await call("migration_risks", source)
                    readable = next((c for c in components if c["source_characters"]), None)
                    if readable:
                        snippet = await call("get_source", {**source, "component_id": readable["id"], "limit": 32})
                        assert snippet["source"]
                    blocks = [c for c in components if c["kind"] == "Block"]
                    if blocks:
                        draft = await call("draft_api", {**source, "block_name": blocks[0]["name"], "package_name": "EXAMPLE_SERVICE"})
                        assert "NOT_PUBLISHED" in draft["ords_sql"]
                    result = {"module": module, "status": "pass", "counts": analysis["counts"],
                              "regions": len(plan["regions"]), "risks": risks["total"],
                              "warnings": analysis.get("warnings", []), "provenance": analysis["provenance"]}
                    report["modules"].append(result)
                    print("PASS", module, analysis["counts"])
                except Exception as error:
                    report["failures"].append({"module": module, "error": str(error)})
                    print("FAIL", module, str(error))
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--modules", nargs="+", required=True)
    parser.add_argument("--output")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
