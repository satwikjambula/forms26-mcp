import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mcp.types import Tool, ToolAnnotations

from forms26_mcp.core import apex_plan, api_scaffold, assessment
from forms26_mcp.upstream import UpstreamBridge, UpstreamConfig, module_spec


def fixture_index():
    return {"key": {"name": "ORDERS", "type": "FORM"}, "fingerprint": {"sha256": "a"*64},
            "indexVersion": 6, "blocks": [{"name": "ORDERS", "queryDataSourceName": "ORDERS",
                "items": [{"name": "ID", "columnName": "ID", "dataType": "Number", "propertyClass": "BASE"}],
                "relations": [{"name": "LINES", "detailBlock": "LINES", "preventMasterlessOperations": True}]}],
            "triggers": [{"name": "WHEN-VALIDATE-ITEM", "level": "ITEM", "blockName": "ORDERS", "itemName": "ID",
                "textRef": {"file": "plsql/triggers/check.sql", "startLine": 1, "endLine": 2}}],
            "programUnits": [{"name": "PKG", "unitType": "PACKAGE_SPEC", "textRef": {"file": "spec.sql", "startLine": 1, "endLine": 1}},
                             {"name": "PKG", "unitType": "PACKAGE_BODY", "textRef": {"file": "body.sql", "startLine": 1, "endLine": 1}}],
            "propertyClasses": ["BASE"], "propertyClassDetails": [{"name": "BASE", "dml": {"databaseItem": True}}],
            "recordGroups": [{"name": "CUSTOMERS", "queryText": "SELECT ID FROM CUSTOMERS"}],
            "attachedLibraries": [{"name": "UTILS"}]}


class ConfigTests(unittest.TestCase):
    def test_config_validation_and_module_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"command": "/bin/server", "args": ["--forms-dir", "/forms"], "env": {"ORACLE_HOME": "/oracle"}}))
            config = UpstreamConfig.from_file(str(path))
            self.assertFalse(config.allow_annotations)
            for bad in [{"command": ["sh"]}, {"command": "x", "args": "--flag"},
                        {"command": "x", "env": {"X": 2}}, {"command": "x", "timeout_seconds": True},
                        {"command": "x", "timeout_seconds": 0}, {"command": "x", "allow_annotations": "yes"},
                        {"command": "x", "shell": True}]:
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    UpstreamConfig.from_file(str(path))
        self.assertEqual(module_spec("orders.FMB"), "ORDERS.fmb")
        for bad in ["../orders.fmb", "/orders.fmb", "ORDERS", "x.xml", "A.fmb;whoami", "A:Z.pll"]:
            with self.assertRaises(ValueError):
                module_spec(bad)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def bridge(self):
        bridge = UpstreamBridge(UpstreamConfig("server", env={"SECRET": "never-expose"}))
        bridge.session = SimpleNamespace(call_tool=AsyncMock(), read_resource=AsyncMock())
        bridge.version = "0.15.0"
        return bridge

    async def test_read_allowlist_and_annotation_separation(self):
        bridge = self.bridge()
        bridge.tools = {name: Tool(name=name, inputSchema={"type": "object"})
                        for name in ["list_modules", "fetch_module", "annotate_element"]}
        bridge.session.call_tool.return_value = SimpleNamespace(isError=False, structuredContent={"modules": []}, content=[])
        await bridge.call("list_modules", {})
        for name in ["fetch_module", "annotate_element", "execute_sql", "run_command"]:
            with self.assertRaises(ValueError):
                await bridge.call(name, {})
        with self.assertRaisesRegex(ValueError, "disabled"):
            await bridge.call("annotate_element", {}, "annotation")
        self.assertNotIn("never-expose", json.dumps(bridge.status()))
        bridge.tools["list_modules"].annotations = ToolAnnotations(readOnlyHint=False)
        with self.assertRaisesRegex(ValueError, "write"):
            await bridge.call("list_modules", {})

    async def test_upstream_errors_and_json_text_fallback(self):
        bridge = self.bridge()
        bridge.tools = {"list_modules": Tool(name="list_modules", inputSchema={})}
        bridge.session.call_tool.return_value = SimpleNamespace(isError=False, structuredContent=None,
            content=[SimpleNamespace(type="text", text='{"modules": []}')])
        self.assertEqual(await bridge.call("list_modules", {}), {"modules": []})
        bridge.session.call_tool.return_value.isError = True
        with self.assertRaisesRegex(ValueError, "failed"):
            await bridge.call("list_modules", {})

    async def test_digest_invalid_hash_and_wrong_identity_fail_closed(self):
        bridge = self.bridge()
        for value in [{"truncated": True}, {"key": {"name": "ORDERS", "type": "FORM"}},
                      {"key": {"name": "OTHER", "type": "FORM"}, "fingerprint": {"sha256": "a"*64}}]:
            bridge.session.read_resource.return_value = SimpleNamespace(contents=[SimpleNamespace(text=json.dumps(value))])
            with self.assertRaises(ValueError):
                await bridge.index("ORDERS.fmb")

    async def test_source_continuation_and_cut_line_detection(self):
        bridge = self.bridge()
        bridge.call = AsyncMock(side_effect=[{"text": "BEGIN", "truncated": True, "nextStartLine": 2},
                                             {"text": "END;", "truncated": False}])
        text = await bridge.source("ORDERS.fmb", {"file": "unit.sql", "startLine": 1, "endLine": 2})
        self.assertEqual(text, "BEGIN\nEND;")
        bridge.call = AsyncMock(return_value={"text": "cut", "truncated": True, "lineCut": True})
        with self.assertRaisesRegex(ValueError, "cut"):
            await bridge.source("ORDERS.fmb", {"file": "x", "startLine": 1, "endLine": 2})
        bridge.call = AsyncMock(return_value={"text": "x", "truncated": True, "nextStartLine": 1})
        with self.assertRaisesRegex(ValueError, "progress"):
            await bridge.source("ORDERS.fmb", {"file": "x", "startLine": 1, "endLine": 2})

    async def test_normalizes_semantics_and_disambiguates_package_units(self):
        bridge = self.bridge()
        index = fixture_index()
        bridge.index = AsyncMock(return_value=index)
        bridge.source = AsyncMock(side_effect=["BEGIN\nCOMMIT_FORM;", "PACKAGE PKG IS END;", "PACKAGE BODY PKG IS END;"])
        bridge.call = AsyncMock(return_value={"effectiveDml": {"ID": {"databaseItem": True, "insertAllowed": False}},
            "unresolvedItems": [{"name": "OTHER", "reason": "CLASS_NOT_FOUND"}], "columns": {"columns": [{"name": "ID"}]}})
        model = await bridge.model("orders.fmb")
        self.assertEqual(assessment(model)["counts"]["PropertyClass"], 1)
        self.assertEqual(len([c for c in model["components"] if c["kind"] == "ProgramUnit"]), 2)
        self.assertEqual(next(c for c in model["components"] if c["kind"] == "RecordGroup")["source"], "SELECT ID FROM CUSTOMERS")
        plan = apex_plan(model)
        self.assertFalse(plan["regions"][0]["legacy_semantics"]["effectiveDml"]["ID"]["insertAllowed"])
        api = api_scaffold(model, "ORDERS", "ORDERS_API")
        self.assertFalse(api["field_hints"][0]["effective_dml"]["insertAllowed"])
        self.assertEqual(len(model["provenance"]["migration_snapshot_sha256"]), 64)

    async def test_inherited_empty_body_stays_unresolved(self):
        bridge = self.bridge()
        index = fixture_index()
        index["blocks"] = []
        index["programUnits"] = []
        index["triggers"][0]["inherited"] = {"module": "PARENT"}
        bridge.index = AsyncMock(return_value=index)
        bridge.call = AsyncMock(return_value={"bodySource": "inherited", "hint": "Fetch PARENT.fmb"})
        bridge.source = AsyncMock()
        model = await bridge.model("ORDERS.fmb")
        trigger = next(c for c in model["components"] if c["kind"] == "Trigger")
        self.assertEqual(trigger["body_source"], "inherited")
        self.assertEqual(trigger["source"], "")
        bridge.source.assert_not_called()
        self.assertIn("unresolved_inheritance", [w["kind"] for w in model["warnings"]])

    async def test_resolved_body_retains_parent_fingerprint_and_source_range(self):
        bridge = self.bridge()
        index = fixture_index()
        index["blocks"] = index["programUnits"] = []
        index["triggers"][0]["inherited"] = {"module": "PARENT"}
        parent = {"key": {"name": "PARENT", "type": "FORM"}, "fingerprint": {"sha256": "b"*64}}
        bridge.index = AsyncMock(side_effect=[index, parent, index, parent])
        bridge.call = AsyncMock(return_value={"bodySource": "resolved", "resolvedFrom": parent["key"],
            "source": {"uri": "oracleforms://PARENT.fmb/plsql/triggers/PARENT.T.sql", "startLine": 1, "endLine": 2}})
        bridge.source = AsyncMock(return_value="BEGIN\nCOMMIT_FORM;")
        model = await bridge.model("ORDERS.fmb")
        trigger = next(c for c in model["components"] if c["kind"] == "Trigger")
        self.assertEqual(trigger["body_source"], "resolved")
        self.assertEqual(trigger["source_reference"]["module"], "PARENT.fmb")
        self.assertEqual(model["provenance"]["inherited_dependencies"]["PARENT.fmb"]["sha256"], "b"*64)

    async def test_truncation_and_source_drift_stop_automatic_drafting(self):
        bridge = self.bridge()
        index = fixture_index()
        bridge.index = AsyncMock(return_value=index)
        bridge.call = AsyncMock(return_value={"truncated": True})
        with self.assertRaisesRegex(ValueError, "truncated"):
            await bridge.model("ORDERS.fmb")
        index["blocks"] = index["triggers"] = index["programUnits"] = []
        changed = copy.deepcopy(index)
        changed["fingerprint"]["sha256"] = "b"*64
        bridge.index = AsyncMock(side_effect=[index, changed])
        with self.assertRaisesRegex(ValueError, "changed"):
            await bridge.model("ORDERS.fmb")


if __name__ == "__main__":
    unittest.main()
