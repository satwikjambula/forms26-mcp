import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from mcp.types import Tool

from forms26_mcp.testkit import TestkitBridge, TestkitConfig
from forms26_mcp.upstream import UpstreamConfig


class TestkitConfigTests(unittest.TestCase):
    def test_config_is_strict_and_status_does_not_expose_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = {"command": "node", "args": ["mcp.js"], "workspace_root": directory,
                      "env": {"SECRET": "do-not-return"}}
            path.write_text(json.dumps(config))
            bridge = TestkitBridge(TestkitConfig.from_file(str(path)))
            self.assertNotIn("do-not-return", json.dumps(bridge.status()))
            for change in [{"sqlcl": True}, {"workspace_root": "relative"},
                           {"quality_policy_path": 1}, {"timeout_seconds": 0}]:
                path.write_text(json.dumps({**config, **change}))
                with self.assertRaises(ValueError):
                    TestkitConfig.from_file(str(path))


class TestkitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.export = self.root / "export"
        (self.export / "pages").mkdir(parents=True)
        self.page = self.export / "pages/p00001.apx"
        self.page.write_text('page 1 ( name: Example )\n')
        self.bridge = TestkitBridge(TestkitConfig(UpstreamConfig("node"), self.root))
        self.bridge.peer.session = SimpleNamespace(call_tool=AsyncMock())
        self.bridge.peer.tools = {name: Tool(name=name, inputSchema={}) for name in
            ["onboard_generated_apex_app", "inspect_apex_export", "generate_flow_map", "analyze_coverage"]}
        self.bridge.native_call = AsyncMock(return_value={"is_error": False,
            "report": {"generate": {"generated": 1}, "qualityGate": None}, "messages": []})

    def tearDown(self):
        self.directory.cleanup()

    async def test_requires_completed_development_and_real_export_before_writes(self):
        for complete, ref, export in [(False, "abc", "export"), (True, "", "export"),
                                      (True, "abc", "missing")]:
            with self.assertRaises((ValueError, FileNotFoundError)):
                await self.bridge.generate(export, "run", ref, complete)
        self.assertFalse((self.root / "qa-output").exists())
        self.bridge.native_call.assert_not_called()
        self.page.unlink()
        with self.assertRaisesRegex(ValueError, "No page"):
            await self.bridge.generate("export", "run", "abc", True)

    async def test_generation_delegates_to_native_tool_and_records_handoff(self):
        result = await self.bridge.generate("export", "build-abc", "commit:abc", True,
            migration_evidence={"source_sha256": "a"*64, "acceptance_criteria": ["Verify rollback"]})
        name, arguments = self.bridge.native_call.call_args.args
        self.assertEqual(name, "onboard_generated_apex_app")
        self.assertIs(arguments["sqlcl"], False)
        self.assertNotIn("sqlclExecutablePath", arguments)
        self.assertEqual(result["status"], "GENERATED_NOT_EXECUTED")
        self.assertFalse(result["tests_executed"])
        self.assertFalse(result["development_verified_by_forms26"])
        self.assertTrue(result["source_unchanged"])
        handoff = json.loads((self.root / result["output_path"] / "handoff.json").read_text())
        self.assertEqual(handoff["migration_evidence"]["source_sha256"], "a"*64)
        self.assertEqual(len(handoff["export_snapshot"]["sha256"]), 64)

    async def test_existing_output_is_never_overwritten(self):
        target = self.root / "qa-output/run/tests/manual.spec.ts"
        target.parent.mkdir(parents=True)
        target.write_text("human-authored")
        with self.assertRaisesRegex(ValueError, "already exists"):
            await self.bridge.generate("export", "run", "abc", True)
        self.assertEqual(target.read_text(), "human-authored")
        self.bridge.native_call.assert_not_called()

    async def test_quality_failure_preserves_native_report_and_output_evidence(self):
        native = {"generate": {"generated": 1}, "qualityGate": {"passed": False, "rules": [{"status": "blocked"}]}}
        self.bridge.native_call.return_value = {"is_error": True, "report": native, "messages": []}
        result = await self.bridge.generate("export", "blocked", "abc", True)
        self.assertEqual(result["status"], "QUALITY_GATE_FAILED")
        self.assertEqual(result["native_result"]["report"], native)
        self.assertFalse(result["tests_executed"])

    async def test_source_drift_is_reported_even_if_native_generation_succeeds(self):
        async def generate(*args):
            self.page.write_text("changed during generation")
            return {"is_error": False, "report": {"generate": {"generated": 1}}, "messages": []}
        self.bridge.native_call.side_effect = generate
        result = await self.bridge.generate("export", "drift", "abc", True)
        self.assertEqual(result["status"], "SOURCE_CHANGED")
        self.assertFalse(result["source_unchanged"])

    async def test_paths_symlinks_overlap_and_size_limits_are_enforced(self):
        with self.assertRaises(ValueError):
            self.bridge.snapshot("../outside")
        link = self.export / "leak.apx"
        link.symlink_to(self.page)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.bridge.snapshot("export")
        link.unlink()
        with patch("forms26_mcp.testkit.MAX_EXPORT_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "64 MiB"):
                self.bridge.snapshot("export")
        for name in ["../bad", "A/B", "..", "x"*81]:
            with self.assertRaises(ValueError):
                await self.bridge.generate("export", name, "abc", True)
        (self.root / "qa-output").symlink_to(self.export, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "overlap"):
            await self.bridge.generate("export", "nested", "abc", True)

    async def test_read_proxy_rejects_generation_and_sqlcl_expansion(self):
        await self.bridge.read("inspect_apex_export", {"exportDir": "export"})
        self.assertEqual(self.bridge.native_call.call_args.args[1]["exportDir"], str(self.export))
        for name, args in [("generate_apex_tests", {}), ("onboard_generated_apex_app", {}),
                           ("inspect_apex_export", {"exportDir": "export", "sqlcl": True})]:
            with self.assertRaises(ValueError):
                await self.bridge.read(name, args)

    async def test_native_error_json_and_multiple_text_blocks_are_preserved(self):
        bridge = self.bridge
        bridge.native_call = TestkitBridge.native_call.__get__(bridge)
        bridge.peer.session.call_tool.return_value = SimpleNamespace(isError=True, structuredContent=None,
            content=[SimpleNamespace(type="text", text='{"qualityGate":{"passed":false}}'),
                     SimpleNamespace(type="text", text="extra diagnostic")])
        result = await bridge.native_call("onboard_generated_apex_app", {})
        self.assertTrue(result["is_error"])
        self.assertFalse(result["report"]["qualityGate"]["passed"])
        self.assertEqual(result["messages"], ["extra diagnostic"])

    async def test_baseline_touch_log_and_operator_policy_are_forwarded(self):
        baseline = self.root / "baseline/pages"
        baseline.mkdir(parents=True)
        (baseline / "page.apx").write_text("page 1 ( name: Old )")
        (self.root / "policy.json").write_text('{"version":1,"maxParserWarnings":0}')
        self.bridge.config = TestkitConfig(UpstreamConfig("node"), self.root, "policy.json")
        result = await self.bridge.generate("export", "with-baseline", "abc", True, "baseline", "missing-log.json")
        arguments = self.bridge.native_call.call_args.args[1]
        self.assertEqual(arguments["baselineExportDir"], str(self.root / "baseline"))
        self.assertEqual(arguments["qualityPolicyPath"], str(self.root / "policy.json"))
        self.assertTrue(result["quality_policy_sha256"])
        self.assertTrue(result["baseline_snapshot"])

    async def test_missing_generation_report_and_zero_tests_are_not_success(self):
        for index, report, expected in [(0, {"message": "done"}, "GENERATION_FAILED"),
                                         (1, {"generate": {"generated": 0}}, "NO_TESTS_GENERATED")]:
            self.bridge.native_call.return_value = {"is_error": False, "report": report, "messages": []}
            result = await self.bridge.generate("export", "empty-" + str(index), "abc", True)
            self.assertEqual(result["status"], expected)


if __name__ == "__main__":
    unittest.main()
