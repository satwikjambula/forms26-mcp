"""Exercise client -> Forms26 -> actual apx-testkit without a live APEX instance."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(args):
    project = Path(__file__).resolve().parents[1]
    argv = ["-m", "forms26_mcp.server", "--root", str(project / "examples"),
            "--testkit-config", str(Path(args.config).resolve())]
    if args.forms_upstream_config:
        argv += ["--upstream-config", str(Path(args.forms_upstream_config).resolve())]
    params = StdioServerParameters(command=sys.executable, args=argv,
        env={k: v for k, v in os.environ.items() if k in {"PATH", "PYTHONPATH", "SYSTEMROOT"}})
    report = {"cases": [], "failures": [], "runs_browser": False}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(name, arguments, expect_error=False):
                result = await session.call_tool(name, arguments)
                if bool(result.isError) != expect_error:
                    raise RuntimeError(str(result.content))
                if result.structuredContent is not None:
                    return result.structuredContent
                if expect_error:
                    return {"error": result.content[0].text}
                return json.loads(result.content[0].text)

            status = await call("testkit_status", {})
            assert status["connected"] and status["generation_available"]
            report["server_version"] = status["server_version"]
            migration = "orders_fmb.xml"
            if args.forms_upstream_config:
                await call("upstream_fetch", {"module": "ORDERS.fmb"})
                migration = "upstream:ORDERS.fmb"
            for index, export in enumerate(args.exports):
                request = {"export_path": export, "run_name": args.run_prefix + "-" + str(index),
                    "development_ref": args.development_ref, "development_complete": True,
                    "migration_source_path": migration}
                await call("generate_post_development_tests", {**request, "development_complete": False}, True)
                native = await call("testkit_read", {"tool_name": "inspect_apex_export", "arguments": {"exportDir": export}})
                assert native["report"] is not None
                generated = await call("generate_post_development_tests", request)
                assert generated["status"] == "GENERATED_NOT_EXECUTED"
                assert not generated["tests_executed"] and not generated["live_application_verified"]
                assert generated["migration_evidence"]["source_sha256"]
                native_report = generated["native_result"]["report"]
                assert native_report["sqlcl"]["requested"] is False
                assert native_report["coverage"]["included"] is False
                config = json.loads(Path(args.config).read_text())
                root = Path(config["workspace_root"])
                output = root / generated["output_path"]
                assert (output / "handoff.json").is_file()
                specs = sorted((output / "tests").glob("*.spec.ts"))
                assert len(specs) == native_report["generate"]["generated"]
                await call("generate_post_development_tests", request, True)
                entry = {"export": export, "status": generated["status"],
                         "specs": len(specs), "skipped_auth": native_report["generate"]["skippedAuth"],
                         "warnings": len(native_report["parserWarnings"]),
                         "verification_requirements": len(native_report["liveVerificationRequirements"]),
                         "export_sha256": generated["export_snapshot"]["sha256"]}
                report["cases"].append(entry)
                print("PASS", export, "specs:", len(specs), "generation only")
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--exports", nargs="+", required=True, help="Paths under the configured QA workspace")
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--development-ref", required=True)
    parser.add_argument("--forms-upstream-config")
    parser.add_argument("--output")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
