import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from forms26_mcp.core import (Workspace, apex_plan, api_scaffold, assessment,
                             findings, mask_plsql, paginate)
from forms26_mcp.database import inspect_objects

PROJECT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace(PROJECT / "examples")
        self.model = self.workspace.parse("orders_fmb.xml")

    def test_realistic_export_preserves_logic_and_relations(self):
        result = assessment(self.model)
        self.assertEqual(result["counts"]["Block"], 3)
        self.assertEqual(result["counts"]["Item"], 8)
        self.assertEqual(result["counts"]["Trigger"], 3)
        self.assertEqual(result["counts"]["Relation"], 1)
        self.assertEqual(len(self.model["sha256"]), 64)
        validate = next(c for c in self.model["components"] if c["name"] == "WHEN-VALIDATE-RECORD")
        self.assertIn("ORDER_TOTAL < 0", validate["source"])
        self.assertEqual(validate["block"], "ORDERS")
        self.assertNotIn("illustrative_hours", result)

    def test_risk_evidence_links_back_to_source(self):
        risks = findings(self.model)
        self.assertEqual({r["rule"] for r in risks}, {"session_state", "navigation", "transaction", "integration"})
        source = {c["id"]: c["source"].splitlines() for c in self.model["components"]}
        for risk in risks:
            for line in risk["lines"]:
                self.assertTrue(source[risk["component_id"]][line-1].strip())

    def test_literals_and_comments_do_not_become_risks(self):
        code = "-- HOST('bad');\n/* :GLOBAL.X */\nx := 'GO_BLOCK(''A'')'; y := q'[CALL_FORM('B')]';\nCOMMIT_FORM;"
        masked = mask_plsql(code)
        self.assertEqual(masked.count("\n"), code.count("\n"))
        self.assertEqual(len(masked), len(code))
        self.assertNotIn("HOST", masked)
        self.assertNotIn("GLOBAL", masked)
        self.assertNotIn("GO_BLOCK", masked)
        self.assertNotIn("CALL_FORM", masked)
        synthetic = {"components": [{"id": "c1", "name": "SAVE", "source": code, "properties": {}}]}
        self.assertEqual([r["rule"] for r in findings(synthetic)], ["transaction"])

    def test_namespaced_and_property_style_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "form.xml").write_text('''<Module xmlns="urn:oracle:forms"><FormModule Name="X"><Block><Property Name="Name" Value="B"/><Trigger Name="T"><Property Name="TriggerText" Value="BEGIN GO_BLOCK('B'); END;"/></Trigger></Block></FormModule></Module>''')
            model = Workspace(directory).parse("form.xml")
            self.assertEqual(model["components"][0]["name"], "B")
            self.assertEqual(model["components"][1]["block"], "B")
            self.assertEqual(findings(model)[0]["rule"], "navigation")

    def test_entity_expansion_and_external_entities_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "evil.xml")
            for entity in ['"expanded"', 'SYSTEM "file:///etc/passwd"']:
                target.write_text(f'<!DOCTYPE Module [<!ENTITY x {entity}>]><Module><FormModule Name="&x;"/></Module>')
                with self.assertRaises(Exception):
                    Workspace(directory).parse("evil.xml")

    def test_traversal_symlinks_and_binary_modules_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "root"
            root.mkdir()
            (parent / "outside.xml").write_text("<Module/>")
            (root / "leak.xml").symlink_to(parent / "outside.xml")
            (root / "form.fmb").write_bytes(b"binary")
            workspace = Workspace(root)
            for name in ["../outside.xml", "leak.xml", str(parent / "outside.xml"), "form.fmb"]:
                with self.assertRaises(ValueError):
                    workspace.parse(name)
            self.assertEqual(workspace.inventory()["total"], 0)

    def test_apex_and_api_share_package_and_preserve_evidence(self):
        apex = apex_plan(self.model)
        self.assertEqual(len(apex["regions"]), 3)
        validation = next(m for m in apex["trigger_mappings"] if m["trigger"] == "WHEN-VALIDATE-RECORD")
        self.assertEqual(validation["shared_api_operation"], "validate")
        api = api_scaffold(self.model, "ORDERS", "ORDERS_SERVICE")
        self.assertEqual(len(api["field_hints"]), 4)
        self.assertIn("raise_application_error", api["package_sql"])
        self.assertIn("NOT_PUBLISHED", api["ords_sql"])
        self.assertIn("ORDERS_SERVICE.validate_payload", api["ords_sql"])
        self.assertEqual(api["sha256"], apex["sha256"])
        json.dumps(api)
        for name in ["x';DROP TABLE T;--", "a.b", "1BAD", "é", "A"*31]:
            with self.assertRaises(ValueError):
                api_scaffold(self.model, "ORDERS", name)
        with self.assertRaises(ValueError):
            api_scaffold(self.model, "NONEXISTENT", "API")

    def test_calibration_and_pagination_bounds(self):
        result = assessment(self.model, 2)
        self.assertEqual(result["illustrative_hours"]["low"], result["complexity_points"] * 2)
        for invalid in [0, -1, float("inf"), float("nan")]:
            with self.assertRaises(ValueError):
                assessment(self.model, invalid)
        self.assertEqual(paginate([1,2,3], 0, 2)["next_offset"], 2)
        self.assertIsNone(paginate([1,2,3], 2, 2)["next_offset"])
        for offset, limit in [(-1, 10), (0, 201), (0, 0)]:
            with self.assertRaises(ValueError):
                paginate([], offset, limit)

    def test_database_configuration_and_identifier_limits(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(inspect_objects(["ORDERS"])["status"], "not_configured")
        for names in [[], ["X"]*21, ["X; DROP TABLE Y"], ["A.B"]]:
            with self.assertRaises(ValueError):
                inspect_objects(names)

    def test_database_uses_read_only_transaction_and_bound_dictionary_queries(self):
        cursor = MagicMock()
        cursor.description = [("VALUE",)]
        cursor.fetchmany.side_effect = [[("ORDERS",)], [("ORDER_ID",)], [("PK_ORDERS",)]]
        connection = MagicMock()
        connection.version = "26.0.0.0.0"
        connection.cursor.return_value.__enter__.return_value = cursor
        connect = MagicMock()
        connect.return_value.__enter__.return_value = connection
        driver = types.SimpleNamespace(connect=connect, Error=RuntimeError)
        config = {"ORACLE_DSN": "example.invalid/service", "ORACLE_USER": "READER",
                  "ORACLE_PASSWORD": "test-only", "ORACLE_SCHEMA": "APP"}
        with patch.dict(os.environ, config, clear=True), patch.dict("sys.modules", {"oracledb": driver}):
            result = inspect_objects(["orders"])
        self.assertEqual(result["database_version"], "26.0.0.0.0")
        self.assertEqual(result["schema"], "APP")
        self.assertEqual(cursor.execute.call_args_list[0].args, ("SET TRANSACTION READ ONLY",))
        for call in cursor.execute.call_args_list[1:]:
            self.assertTrue(call.args[0].startswith("SELECT"))
            self.assertEqual(call.kwargs, {"owner": "APP", "name": "ORDERS"})
        self.assertEqual(connection.call_timeout, 10000)
        connection.rollback.assert_called_once()

    def test_database_errors_do_not_expose_connection_details(self):
        connect = MagicMock(side_effect=RuntimeError("secret DSN or password"))
        driver = types.SimpleNamespace(connect=connect, Error=RuntimeError)
        config = {"ORACLE_DSN": "x", "ORACLE_USER": "READER", "ORACLE_PASSWORD": "test-only", "ORACLE_SCHEMA": "APP"}
        with patch.dict(os.environ, config, clear=True), patch.dict("sys.modules", {"oracledb": driver}):
            with self.assertRaises(ValueError) as raised:
                inspect_objects(["ORDERS"])
        self.assertNotIn("secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
