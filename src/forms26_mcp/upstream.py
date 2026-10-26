"""MCP adapter for the separately installed Apache-2.0 oracle-forms-mcp server.

No upstream implementation is vendored. Configuration is operator-owned; MCP
callers cannot supply executable names, converter commands or environment values.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

READ_TOOLS = frozenset({
    "list_modules", "get_module_overview", "list_blocks", "get_block",
    "list_triggers", "get_trigger", "list_program_units", "get_program_unit",
    "search_source", "search_modules", "read_source", "get_object_xml",
    "get_element_annotations", "search_annotations",
})
WRITE_TOOLS = frozenset({"annotate_element", "relate_elements", "remove_annotation"})
MAX_MODEL_CHARS = 4_000_000
MAX_COMPONENTS = 20_000
UPSTREAM_REPOSITORY = "https://github.com/aoreshkov/oracle-forms-mcp"


@dataclass(frozen=True)
class UpstreamConfig:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 180
    allow_annotations: bool = False

    @classmethod
    def from_file(cls, path: str) -> "UpstreamConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, value: dict) -> "UpstreamConfig":
        allowed = {"command", "args", "env", "timeout_seconds", "allow_annotations"}
        if not isinstance(value, dict) or set(value) - allowed:
            raise ValueError("Upstream config must contain only command, args, env, timeout_seconds and allow_annotations")
        if not isinstance(value.get("command"), str) or not value["command"].strip():
            raise ValueError("Upstream command must be a nonempty executable name or path")
        args, env = value.get("args", []), value.get("env", {})
        if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
            raise ValueError("Upstream args must be an array of strings")
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise ValueError("Upstream env must map strings to strings")
        timeout = value.get("timeout_seconds", 180)
        if type(timeout) is not int or not 1 <= timeout <= 600:
            raise ValueError("Upstream timeout_seconds must be an integer in 1..600")
        annotations = value.get("allow_annotations", False)
        if type(annotations) is not bool:
            raise ValueError("Upstream allow_annotations must be a boolean")
        return cls(value["command"], args, env, timeout, annotations)


def module_spec(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_$#][A-Za-z0-9_$#-]*\.(?:fmb|mmb|pll|olb)", value, re.I):
        raise ValueError("Use a module identity such as ORDERS.fmb, MAINMENU.mmb, UTILS.pll or OBJECTS.olb")
    name, extension = value.rsplit(".", 1)
    return name.upper() + "." + extension.lower()


def json_object(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"Upstream {label} must be a JSON object")
    return value


class UpstreamBridge:
    def __init__(self, config: UpstreamConfig | None = None):
        self.config = config
        self.session = None
        self.tools = {}
        self.version = None
        self._stack = None
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        if self.config is None:
            return self
        self._stack = AsyncExitStack()
        try:
            read, write = await self._stack.enter_async_context(stdio_client(StdioServerParameters(
                command=self.config.command, args=self.config.args, env=self.config.env)))
            self.session = await self._stack.enter_async_context(ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=self.config.timeout_seconds)))
            initialized = await self.session.initialize()
            self.version = initialized.serverInfo.version
            cursor = None
            for _ in range(20):
                page = await self.session.list_tools(cursor=cursor)
                self.tools.update({tool.name: tool for tool in page.tools})
                if not page.nextCursor:
                    break
                if page.nextCursor == cursor:
                    raise ValueError("Upstream tool discovery returned a repeated cursor")
                cursor = page.nextCursor
            else:
                raise ValueError("Upstream tool discovery exceeded 20 pages")
            return self
        except BaseException:
            await self._stack.aclose()
            self.session = None
            raise

    async def __aexit__(self, *exc):
        if self._stack:
            await self._stack.aclose()
        self.session = None

    def require_session(self):
        if self.session is None:
            raise ValueError("Upstream is not connected. Launch Forms26 with --upstream-config CONFIG.json")
        return self.session

    def status(self) -> dict:
        return {"configured": self.config is not None, "connected": self.session is not None,
                "repository": UPSTREAM_REPOSITORY, "server_version": self.version,
                "annotations_enabled": bool(self.config and self.config.allow_annotations),
                "read_tools": sorted(READ_TOOLS & self.tools.keys()),
                "fetch_available": "fetch_module" in self.tools,
                "annotation_tools": sorted(WRITE_TOOLS & self.tools.keys())
                if self.config and self.config.allow_annotations else []}

    async def call(self, name: str, arguments: dict, category: str = "read") -> dict:
        session = self.require_session()
        allowed = READ_TOOLS if category == "read" else {"fetch_module"} if category == "fetch" else WRITE_TOOLS
        if name not in allowed:
            raise ValueError(f"Tool is not permitted in the {category} adapter")
        if category == "annotation" and not (self.config and self.config.allow_annotations):
            raise ValueError("Annotation writes are disabled; enable allow_annotations in the server's upstream config")
        if name not in self.tools:
            raise ValueError("The connected upstream server does not provide the requested tool")
        descriptor = self.tools[name]
        if category == "read" and descriptor.annotations and descriptor.annotations.readOnlyHint is False:
            raise ValueError("Upstream classifies this operation as a write; refusing read-only forwarding")
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")
        result = await session.call_tool(name, arguments)
        if result.isError:
            # Useful diagnostics can contain source paths; return upstream errors as data,
            # without treating their text as instructions or exposing launch configuration.
            message = " ".join(c.text for c in result.content if c.type == "text")
            raise ValueError(f"Upstream {name} failed: {message[:1500]}")
        if result.structuredContent is not None:
            return json_object(result.structuredContent, name)
        texts = [c.text for c in result.content if c.type == "text"]
        if len(texts) != 1:
            raise ValueError("Expected one upstream JSON result; no partial result was accepted")
        return json_object(json.loads(texts[0]), name)

    async def fetch(self, module: str) -> dict:
        async with self._lock:
            return await self.call("fetch_module", {"module": module_spec(module)}, "fetch")

    async def index(self, module: str) -> dict:
        uri = f"oracleforms://{quote(module, safe='.$_-')}/index"
        result = await self.require_session().read_resource(uri)
        texts = [c.text for c in result.contents if hasattr(c, "text")]
        if len(texts) != 1 or len(texts[0]) > MAX_MODEL_CHARS:
            raise ValueError("Upstream index is not one bounded JSON resource")
        index = json_object(json.loads(texts[0]), "index")
        if index.get("truncated"):
            raise ValueError("Upstream returned an index digest. Use upstream_read with paginated tools; automatic migration requires a complete index")
        fingerprint = index.get("fingerprint", {})
        if not re.fullmatch(r"[0-9a-fA-F]{64}", fingerprint.get("sha256", "")):
            raise ValueError("Upstream index lacks a valid source SHA256")
        key = index.get("key", {})
        expected_type = {"fmb": "FORM", "mmb": "MENU", "pll": "LIBRARY", "olb": "OBJECT_LIBRARY"}[module.rsplit(".", 1)[1]]
        if str(key.get("name", "")).upper() != module.rsplit(".", 1)[0] or str(key.get("type", "")).upper() != expected_type:
            raise ValueError("Upstream index identity does not match the requested module")
        return index

    async def source(self, module: str, ref: dict) -> str:
        start, end = ref.get("startLine", 1), ref.get("endLine", 1)
        if type(start) is not int or type(end) is not int or start < 1 or end < start:
            raise ValueError("Invalid upstream source range")
        parts, characters = [], 0
        for _ in range(1000):
            args = {"module": module, "startLine": start, "endLine": end, "maxLines": 2000}
            if ref.get("uri"):
                args["uri"] = ref["uri"]
            elif ref.get("file"):
                args["file"] = ref["file"]
            else:
                raise ValueError("Upstream code has no addressable source")
            page = await self.call("read_source", args)
            if page.get("lineCut"):
                raise ValueError("Upstream cut a source line; automatic analysis would be incomplete")
            text = page.get("text", "")
            if not isinstance(text, str):
                raise ValueError("Upstream source text is invalid")
            parts.append(text)
            characters += len(text)
            if characters > MAX_MODEL_CHARS:
                raise ValueError("Module code exceeds the 4-million-character adapter limit")
            if not page.get("truncated"):
                return "\n".join(parts)
            next_line = page.get("nextStartLine")
            if type(next_line) is not int or not start < next_line <= end:
                raise ValueError("Upstream source continuation is missing or makes no progress")
            start = next_line
        raise ValueError("Source exceeded 1000 pages")

    async def model(self, module: str) -> dict:
        module = module_spec(module)
        async with self._lock:
            index = await self.index(module)
            components, warnings, dependencies = [], [], {}
            characters_used = 0

            def add(kind, row, parent="", block=None, source="", **extra):
                nonlocal characters_used
                if len(components) >= MAX_COMPONENTS:
                    raise ValueError("Module exceeds the 20,000-component adapter limit")
                characters_used += len(source)
                if characters_used > MAX_MODEL_CHARS:
                    raise ValueError("Combined module code exceeds the adapter limit")
                props = {k[:1].upper() + k[1:]: v for k, v in row.items() if k not in {"items", "relations", "textRef", "xmlRef", "sourceRef"}}
                if row.get("dml"):
                    props.update({k[:1].upper() + k[1:]: v for k, v in row["dml"].items()})
                if "dmlDataTargetName" in (row.get("dml") or {}):
                    props["DMLDataTargetName"] = row["dml"]["dmlDataTargetName"]
                if row.get("inherited"):
                    props["SubclassReference"] = row["inherited"]
                component = {"id": f"c{len(components)+1:05d}", "kind": kind,
                             "name": row.get("name", kind), "parent_id": parent,
                             "block": block, "properties": props, "source": source,
                             "upstream": row, **extra}
                components.append(component)
                return component["id"]

            for block in index.get("blocks", []):
                name = block["name"]
                detail = await self.call("get_block", {"module": module, "block": name,
                                                       "verbosity": "detailed", "columns": True})
                if detail.get("truncated") or (detail.get("columns") or {}).get("truncated"):
                    raise ValueError("Upstream block detail was truncated; use upstream_read to narrow the inspection")
                ref = add("Block", block, block=name, upstream_detail=detail)
                for item in block.get("items", []):
                    add("Item", item, parent=ref, block=name,
                        effective_dml=detail.get("effectiveDml", {}).get(item["name"]))
                    if item.get("inherited"):
                        warnings.append({"kind": "inherited_item", "block": name,
                                         "name": item["name"], "reference": item["inherited"]})
                for relation in block.get("relations", []):
                    add("Relation", relation, parent=ref, block=name)
                for unresolved in detail.get("unresolvedItems", []):
                    warnings.append({"kind": "unresolved_property_class", "block": name, **unresolved})
                if block.get("inherited"):
                    warnings.append({"kind": "inherited_block", "block": name,
                                     "note": "Only locally indexed structure is normalized; inspect parent structure with upstream_read"})

            for kind, section in [("Trigger", "triggers"), ("ProgramUnit", "programUnits")]:
                for row in index.get(section, []):
                    ref, body_source, inherited_result = row.get("textRef"), "own", None
                    source_module = module
                    if row.get("inherited"):
                        args = {"module": module, "name": row["name"], "resolve": True}
                        if kind == "Trigger":
                            args["level"] = str(row.get("level", "FORM")).lower()
                            if row.get("blockName"):
                                args["block"] = row["blockName"]
                            if row.get("itemName"):
                                args["item"] = row["itemName"]
                        elif row.get("unitType"):
                            args["unitType"] = row["unitType"]
                        inherited_result = await self.call("get_trigger" if kind == "Trigger" else "get_program_unit", args)
                        body_source = str(inherited_result.get("bodySource", "inherited")).lower()
                        ref = inherited_result.get("source") or ref
                        if inherited_result.get("resolvedFrom"):
                            key = inherited_result["resolvedFrom"]
                            suffix = {"FORM": "fmb", "MENU": "mmb", "LIBRARY": "pll", "OBJECT_LIBRARY": "olb"}[str(key["type"]).upper()]
                            source_module = module_spec(key["name"] + "." + suffix)
                            dependencies[source_module] = await self.index(source_module)
                        if body_source == "inherited":
                            warnings.append({"kind": "unresolved_inheritance", "name": row["name"],
                                             "reference": row["inherited"], "hint": inherited_result.get("hint")})
                    source = await self.source(source_module, ref) if ref and body_source != "inherited" else ""
                    if not source.strip() and body_source == "own":
                        body_source = "empty"
                    block_name = row.get("blockName")
                    parent = next((c["id"] for c in components if c["kind"] == "Item" and c["block"] == block_name and c["name"] == row.get("itemName")), "")
                    if not parent:
                        parent = next((c["id"] for c in components if c["kind"] == "Block" and c["name"] == block_name), "")
                    add(kind, row, parent=parent, block=block_name, source=source,
                        source_reference={"module": source_module, **(ref or {})}, body_source=body_source,
                        inherited_result=inherited_result)

            for section, kind in {"attachedLibraries": "AttachedLibrary", "lovs": "LOV",
                                  "recordGroups": "RecordGroup", "windows": "Window",
                                  "canvases": "Canvas", "alerts": "Alert", "parameters": "ModuleParameter",
                                  "propertyClassDetails": "PropertyClass", "menus": "Menu",
                                  "objectLibraryTabs": "ObjectLibraryTab"}.items():
                for row in index.get(section, []):
                    parent = add(kind, row, source=row.get("queryText") or "" if kind == "RecordGroup" else "")
                    if kind == "Menu":
                        for item in row.get("items", []):
                            # Menu command bodies live in indexed source refs; retain metadata,
                            # and require source review instead of silently inventing behavior.
                            ref = item.get("commandRef")
                            text = await self.source(module, ref) if ref else ""
                            add("MenuItem", item, parent=parent, source=text,
                                source_reference={"module": module, **ref} if ref else None)
                    elif kind == "ObjectLibraryTab":
                        for entry in row.get("entries", []):
                            add("ObjectLibraryEntry", entry, parent=parent)
                        if row.get("entries"):
                            warnings.append({"kind": "object_library_review_required", "name": row["name"],
                                             "note": "Library entries are reusable definitions, not application regions; inspect them with upstream_read('get_object_xml', ...)"})
            for name in index.get("propertyClasses", []):
                if not any(c["kind"] == "PropertyClass" and c["name"] == name for c in components):
                    add("PropertyClass", {"name": name})
            for library in index.get("attachedLibraries", []):
                warnings.append({"kind": "library_review_required", "name": library.get("name"),
                                 "note": "Analyze this library separately using upstream:NAME.pll before treating the form's business logic as complete"})
            # No write is performed by a read: source/parent drift makes this snapshot fail.
            if await self.index(module) != index:
                raise ValueError("Upstream module changed during inspection; retry after fetch_module")
            for key, original in dependencies.items():
                if await self.index(key) != original:
                    raise ValueError("Inherited source changed during inspection; retry")
            snapshot = hashlib.sha256(json.dumps({"index": index, "components": components,
                "dependencies": dependencies}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            total_chars = sum(len(c["source"]) for c in components)
            if total_chars > MAX_MODEL_CHARS:
                raise ValueError("Combined module code exceeds the adapter limit")
            return {"path": "upstream:" + module, "module": index["key"]["name"],
                    "module_kind": index["key"]["type"], "sha256": index["fingerprint"]["sha256"],
                    "components": components, "warnings": warnings,
                    "provenance": {"backend": "oracle-forms-mcp", "server_version": self.version,
                                   "source_fingerprint": index["fingerprint"],
                                   "migration_snapshot_sha256": snapshot,
                                   "index_version": index.get("indexVersion"),
                                   "inherited_dependencies": {k: v["fingerprint"] for k, v in dependencies.items()}}}
