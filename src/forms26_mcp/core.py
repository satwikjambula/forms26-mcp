"""Deterministic, evidence-linked analysis; no source code is executed."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path

from defusedxml import ElementTree as ET

MAX_BYTES = 32 * 1024 * 1024
KINDS = {"Block", "Item", "Trigger", "ProgramUnit", "LOV", "RecordGroup",
         "Relation", "AttachedLibrary", "Canvas", "Window", "Menu", "MenuItem"}
CODE_FIELDS = {"Trigger": "TriggerText", "ProgramUnit": "ProgramUnitText",
               "RecordGroup": "RecordGroupQuery", "MenuItem": "CommandText"}
RULES = {
    "navigation": (r"\b(?:GO_ITEM|GO_BLOCK|NEXT_RECORD|PREVIOUS_RECORD|FIRST_RECORD|LAST_RECORD|EXECUTE_QUERY|ENTER_QUERY|CLEAR_BLOCK|SET_ITEM_PROPERTY|SET_BLOCK_PROPERTY)\b", "high",
                   "Replace Forms navigation and mutable item state with APEX events, processes, and explicit request state."),
    "transaction": (r"\b(?:COMMIT_FORM|POST|ROLLBACK_FORM|DO_KEY)\s*(?:\(|;)", "high",
                    "Review transaction boundaries, validation ordering, optimistic locking, and API retry behavior."),
    "integration": (r"\b(?:HOST|WEBUTIL\.[A-Z_]+|CLIENT_HOST|TEXT_IO\.[A-Z_]+|OLE2\.[A-Z_]+|RUN_PRODUCT|RUN_REPORT_OBJECT|JAVA_IMPORTER\.[A-Z_]+)\b", "high",
                    "Replace desktop, file, report, or Java integrations with a reviewed server-side service."),
    "cross_form": (r"\b(?:CALL_FORM|OPEN_FORM|NEW_FORM)\b", "medium",
                   "Replace cross-form calls with APEX navigation or explicit service orchestration."),
    "dynamic_sql": (r"\b(?:FORMS_DDL|EXECUTE\s+IMMEDIATE|DBMS_SQL\.[A-Z_]+)\b", "high",
                    "Inspect dynamic SQL, bind variables, object resolution, and authorization manually."),
    "session_state": (r":(?:GLOBAL|SYSTEM|PARAMETER)\.[A-Z_][A-Z0-9_$#]*", "high",
                      "Make session dependencies explicit; decide which values are parameters versus APEX session state."),
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def properties(element) -> dict:
    result = {local_name(k): v for k, v in element.attrib.items()}
    for child in element:
        if local_name(child.tag) == "Property":
            key = child.get("Name", "")
            result[key] = child.get("Value", child.text or "")
        elif local_name(child.tag) in CODE_FIELDS.values():
            result[local_name(child.tag)] = "".join(child.itertext())
    return result


def mask_plsql(code: str) -> str:
    """Mask comments and string literals while retaining character and line offsets."""
    chars = list(code)
    i = 0
    while i < len(code):
        start = i
        if code.startswith("--", i):
            end = code.find("\n", i)
            i = len(code) if end < 0 else end
        elif code.startswith("/*", i):
            end = code.find("*/", i + 2)
            i = len(code) if end < 0 else end + 2
        elif code[i:i+2].lower() == "q'" and i + 2 < len(code):
            delimiter = code[i+2]
            close = {"[": "]", "{": "}", "(": ")", "<": ">"}.get(delimiter, delimiter)
            end = code.find(close + "'", i + 3)
            i = len(code) if end < 0 else end + 2
        elif code[i] == "'":
            i += 1
            while i < len(code):
                if code[i:i+2] == "''":
                    i += 2
                elif code[i] == "'":
                    i += 1
                    break
                else:
                    i += 1
        else:
            i += 1
            continue
        for j in range(start, i):
            if chars[j] != "\n":
                chars[j] = " "
    return "".join(chars)


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Forms root must be a directory")

    def resolve(self, path: str) -> Path:
        target = (self.root / path).resolve(strict=True)
        if not target.is_relative_to(self.root) or not target.is_file():
            raise ValueError("File must be inside the configured Forms root")
        if target.suffix.lower() != ".xml":
            raise ValueError("Export binary Forms modules to XML with Forms2XML first")
        return target

    def inventory(self, offset: int = 0, limit: int = 100) -> dict:
        page_bounds(offset, limit)
        files = []
        for path in self.root.rglob("*"):
            if path.suffix.lower() == ".xml" and path.is_file():
                resolved = path.resolve()
                if resolved.is_relative_to(self.root):
                    files.append({"path": path.relative_to(self.root).as_posix(), "bytes": path.stat().st_size})
        files.sort(key=lambda x: x["path"])
        return paginate(files, offset, limit)

    def parse(self, path: str) -> dict:
        target = self.resolve(path)
        with target.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("XML exceeds the 32 MiB limit; split the export by module")
        # Normal Forms exports may declare forms.dtd. ElementTree does not fetch
        # that DTD; entities and external references are explicitly forbidden.
        root = ET.fromstring(raw, forbid_dtd=False, forbid_entities=True, forbid_external=True)
        modules = [x for x in root.iter() if local_name(x.tag) in
                   {"FormModule", "MenuModule", "ObjectLibrary"}]
        if len(modules) != 1:
            raise ValueError("Expected one FormModule, MenuModule, or ObjectLibrary per XML file")
        components = []
        stack = [(modules[0], "", None)]
        seen_nodes = 0
        while stack:
            element, parent_ref, block = stack.pop()
            seen_nodes += 1
            if seen_nodes > 200_000:
                raise ValueError("XML exceeds the 200,000-node limit")
            kind = local_name(element.tag)
            props = properties(element)
            if kind == "Block":
                block = props.get("Name", "")
            ref = parent_ref
            if kind in KINDS:
                ref = f"c{len(components)+1:05d}"
                source = props.pop(CODE_FIELDS.get(kind, ""), "")
                components.append({"id": ref, "kind": kind,
                                   "name": props.get("Name", kind), "parent_id": parent_ref,
                                   "block": block, "properties": props, "source": source})
            for child in reversed(list(element)):
                stack.append((child, ref, block))
        return {"path": target.relative_to(self.root).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "module": properties(modules[0]).get("Name", target.stem),
                "module_kind": local_name(modules[0].tag), "components": components}


def page_bounds(offset: int, limit: int) -> None:
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError("offset must be >= 0 and limit must be 1..200")


def paginate(records: list, offset: int, limit: int) -> dict:
    page_bounds(offset, limit)
    return {"total": len(records), "items": records[offset:offset+limit],
            "next_offset": offset + limit if offset + limit < len(records) else None}


def findings(model: dict) -> list[dict]:
    result = []
    for component in model["components"]:
        code = mask_plsql(component["source"])
        for rule, (pattern, severity, action) in RULES.items():
            matches = list(re.finditer(pattern, code, re.I))
            if matches:
                result.append({"rule": rule, "severity": severity,
                               "component_id": component["id"], "name": component["name"],
                               "occurrences": len(matches),
                               "lines": [code.count("\n", 0, m.start()) + 1 for m in matches[:20]],
                               "action": action})
        if any(k.startswith("Subclass") and v for k, v in component["properties"].items()):
            result.append({"rule": "inheritance", "severity": "high",
                           "component_id": component["id"], "name": component["name"],
                           "occurrences": 1, "lines": [],
                           "action": "Resolve subclassed objects and libraries before accepting this analysis as complete."})
    return result


def assessment(model: dict, hours_per_point: float | None = None) -> dict:
    counts = Counter(c["kind"] for c in model["components"])
    risks = findings(model)
    lines = sum(sum(bool(x.strip()) for x in mask_plsql(c["source"]).splitlines())
                for c in model["components"])
    factors = {"base": 5, "blocks": counts["Block"] * 3,
               "items": math.ceil(counts["Item"] / 5),
               "code_units": counts["Trigger"] + counts["ProgramUnit"],
               "code_lines": math.ceil(lines / 20),
               "risks": sum(5 if r["severity"] == "high" else 2 for r in risks),
               "libraries": counts["AttachedLibrary"] * 5,
               "relations": counts["Relation"] * 3}
    points = sum(factors.values())
    result = {"module": model["module"], "sha256": model["sha256"],
              "target": "APEX and ORDS APIs on Oracle AI Database 26ai",
              "counts": dict(counts), "nonblank_code_lines": lines,
              "complexity_points": points, "factors": factors,
              "risk_count": len(risks), "confidence": "uncalibrated heuristic",
              "limitations": ["No Forms runtime behavior or database compatibility has been verified.",
                             "SQL and PL/SQL dependency discovery is heuristic, not a compiler.",
                             "Attached PLLs, OLB inheritance, dynamic SQL and external integrations need separate review.",
                             "Points cover observed module complexity; portfolio, UAT, deployment and training require separate planning."]}
    if hours_per_point is not None:
        if not math.isfinite(hours_per_point) or not 0 < hours_per_point <= 1000:
            raise ValueError("hours_per_point must be finite and in (0, 1000]")
        result["illustrative_hours"] = {"low": round(points * hours_per_point, 1),
                                        "high": round(points * hours_per_point * 1.75, 1),
                                        "team_hours_per_point": hours_per_point,
                                        "basis": "User-supplied rate; 1.75 uncertainty factor is a planning assumption, not a measured confidence interval"}
    return result


TRIGGER_MAP = {
    "WHEN-VALIDATE-ITEM": ("APEX item validation + shared package validation", "validate"),
    "WHEN-VALIDATE-RECORD": ("APEX row validation + shared package validation", "validate"),
    "PRE-INSERT": ("Shared package create operation; APEX page process calls it", "create"),
    "PRE-UPDATE": ("Shared package update operation; APEX page process calls it", "update"),
    "PRE-DELETE": ("Shared package delete operation; APEX page process calls it", "delete"),
    "POST-QUERY": ("Report query/view projection or set-based enrichment", "read"),
    "WHEN-BUTTON-PRESSED": ("APEX button, dynamic action, or submit process", "review"),
    "WHEN-NEW-FORM-INSTANCE": ("APEX initialization process; review session semantics", "review"),
}


def apex_plan(model: dict) -> dict:
    blocks = []
    mappings = []
    for component in model["components"]:
        if component["kind"] == "Block":
            p = component["properties"]
            table = p.get("QueryDataSourceName") or p.get("DMLDataTargetName")
            blocks.append({"source_id": component["id"], "name": component["name"],
                           "data_source_hint": table,
                           "suggested_region": "Form or Interactive Grid (choose after reviewing record cardinality)" if table else "Control region",
                           "status": "requires schema and UX review"})
        elif component["kind"] == "Trigger":
            target, operation = TRIGGER_MAP.get(component["name"].upper(),
                                               ("Manual event/lifecycle redesign", "review"))
            mappings.append({"source_id": component["id"], "trigger": component["name"],
                             "block": component["block"], "apex_target": target,
                             "shared_api_operation": operation})
    return {"module": model["module"], "sha256": model["sha256"],
            "regions": blocks, "trigger_mappings": mappings,
            "architecture": "APEX processes and ORDS handlers call the same reviewed PL/SQL service package.",
            "acceptance": ["Reproduce trigger ordering and validation outcomes using representative cases.",
                           "Verify primary keys, constraints, authorization and row visibility.",
                           "Verify master/detail behavior, LOVs, keyboard workflows and reports.",
                           "Keep Forms navigation and UI/session state out of database packages.",
                           "Test concurrent updates, rollback and API retries."],
            "artifact_type": "design blueprint; not an importable APEX application"}


def identifier(name: str) -> str:
    value = name.upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", value):
        raise ValueError("Use a simple unquoted Oracle identifier of 1..30 ASCII characters")
    return value


def api_scaffold(model: dict, block_name: str, package_name: str) -> dict:
    package = identifier(package_name)
    blocks = [c for c in model["components"] if c["kind"] == "Block" and c["name"] == block_name]
    if len(blocks) != 1:
        raise ValueError("Select an exact, unique block name from the analysis")
    block = blocks[0]
    fields = [c for c in model["components"] if c["kind"] == "Item" and c["parent_id"] == block["id"]]
    # Names supplied by legacy files are returned as data, never interpolated into SQL.
    unit_ids = [c["id"] for c in model["components"] if c["source"] and
                (c["block"] == block_name or c["block"] is None)]
    sql = f"""-- DRAFT: compile and test in a disposable development schema only.
-- Deliberately fails until a developer implements the reviewed business rules.
CREATE OR REPLACE PACKAGE {package} AUTHID DEFINER AS
  FUNCTION validate_payload(p_payload IN CLOB) RETURN CLOB;
END {package};
/
CREATE OR REPLACE PACKAGE BODY {package} AS
  FUNCTION validate_payload(p_payload IN CLOB) RETURN CLOB IS
  BEGIN
    raise_application_error(-20001, 'Migration rules have not been implemented');
    RETURN NULL;
  END validate_payload;
END {package};
/
"""
    module = "migration." + package.lower()
    ords = f"""-- DRAFT: requires an ORDS-enabled development schema.
-- Keep NOT_PUBLISHED until authentication, authorization and tests are complete.
BEGIN
  ORDS.DEFINE_MODULE(p_module_name => '{module}',
    p_base_path => '/migration/{package.lower()}/',
    p_status => 'NOT_PUBLISHED', p_items_per_page => 25);
  ORDS.DEFINE_TEMPLATE(p_module_name => '{module}', p_pattern => 'validate');
  ORDS.DEFINE_HANDLER(p_module_name => '{module}', p_pattern => 'validate',
    p_method => 'POST', p_source_type => ORDS.source_type_plsql,
    p_mimes_allowed => 'application/json',
    p_source => 'DECLARE
      l_payload CLOB := :body_text;
      l_result CLOB;
    BEGIN
      l_result := {package}.validate_payload(l_payload);
      -- TODO: implement bounded/chunked JSON response output and error mapping.
      :status_code := 501;
    END;');
END;
/
-- Deployment tooling owns COMMIT and rollback/recovery decisions.
"""
    contract = {"openapi": "3.1.0", "info": {"title": package + " validation draft", "version": "0.1.0"},
                "paths": {f"/migration/{package.lower()}/validate": {"post": {
                    "operationId": package.lower() + "_validate",
                    "description": "Draft validation endpoint. Current package deliberately raises -20001; no business logic is implemented.",
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}}},
                    "responses": {"501": {"description": "Scaffold only; business rules and response handling are pending"},
                                  "500": {"description": "Unimplemented package raises an error"}}}}},
                "x-review-required": ["Define field types and required values from verified schema and rules",
                                      "Define authentication and authorization before publishing",
                                      "Specify success/error responses, rate limits and idempotency"]}
    return {"module": model["module"], "sha256": model["sha256"], "block": block_name,
            "source_component_ids": unit_ids,
            "field_hints": [{"source_id": c["id"], "name": c["name"],
                             "column": c["properties"].get("ColumnName"),
                             "forms_datatype": c["properties"].get("DataType")} for c in fields],
            "package_sql": sql, "ords_sql": ords, "openapi": contract,
            "apex_call_pattern": f"Use {package}.validate_payload from a reviewed APEX validation/process with explicit JSON inputs.",
            "pending": ["Implement validation from source and verified database constraints",
                        "Add create/update/delete/read operations after schema and transaction review",
                        "Implement JSON serialization, validation errors and ORDS response handling",
                        "Add authorization, audit behavior and concurrency tests"],
            "status": "scaffold only; no conversion or deployment has occurred"}
