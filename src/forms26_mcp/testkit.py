"""Post-development QA through the separately installed apx-testkit MCP.

The native generator authors the assertions. Forms26 validates the handoff,
confines file access and records evidence; it never invents Playwright APIs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .upstream import UpstreamBridge, UpstreamConfig

READ_ARGUMENTS = {
    "inspect_apex_export": {"exportDir"},
    "generate_flow_map": {"exportDir"},
    "diff_apex_exports": {"oldExportDir", "newExportDir", "format"},
    "analyze_coverage": {"exportDir", "touchLogPath", "includeHtml"},
}
EXPORT_PATHS = {"exportDir", "oldExportDir", "newExportDir"}
MAX_EXPORT_BYTES = 64 * 1024 * 1024
MAX_RESULT_CHARS = 2_000_000
REPOSITORY = "https://github.com/satwikjambula/apx-testkit"


@dataclass(frozen=True)
class TestkitConfig:
    connection: UpstreamConfig
    workspace_root: Path
    quality_policy_path: str | None = None

    @classmethod
    def from_file(cls, path: str) -> "TestkitConfig":
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        allowed = {"command", "args", "env", "timeout_seconds", "workspace_root", "quality_policy_path"}
        if not isinstance(value, dict) or set(value) - allowed:
            raise ValueError("Unknown testkit configuration field")
        raw_root = value.get("workspace_root")
        if not isinstance(raw_root, str) or not Path(raw_root).is_absolute():
            raise ValueError("testkit workspace_root must be an absolute directory")
        root = Path(raw_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("testkit workspace_root must be a directory")
        policy = value.get("quality_policy_path")
        if policy is not None and not isinstance(policy, str):
            raise ValueError("quality_policy_path must be a workspace-relative path")
        connection = UpstreamConfig.from_dict({k: v for k, v in value.items()
            if k in {"command", "args", "env", "timeout_seconds"}})
        return cls(connection, root, policy)


class TestkitBridge:
    def __init__(self, config: TestkitConfig | None = None):
        self.config = config
        # Reuse the managed stdio transport/session lifecycle, not the Forms API.
        self.peer = UpstreamBridge(config.connection if config else None)
        self._generation_lock = asyncio.Lock()

    async def __aenter__(self):
        await self.peer.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self.peer.__aexit__(*exc)

    def require_session(self):
        if self.peer.session is None:
            raise ValueError("apx-testkit is not connected; configure --testkit-config CONFIG.json")
        return self.peer.session

    def status(self) -> dict:
        names = set(READ_ARGUMENTS) | {"onboard_generated_apex_app"}
        return {"configured": self.config is not None, "connected": self.peer.session is not None,
                "repository": REPOSITORY, "server_version": self.peer.version,
                "generation_tool": "onboard_generated_apex_app",
                "generation_available": "onboard_generated_apex_app" in self.peer.tools,
                "sqlcl_enabled": False, "runs_playwright": False,
                "tools": [t.model_dump(mode="json", exclude_none=True)
                          for name, t in sorted(self.peer.tools.items()) if name in names]}

    def under_root(self, value: str, *, exists: bool = True) -> Path:
        if self.config is None:
            raise ValueError("Testkit workspace is not configured")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A nonempty workspace path is required")
        target = (self.config.workspace_root / value).resolve(strict=False)
        if not target.is_relative_to(self.config.workspace_root):
            raise ValueError("Testkit paths must stay inside workspace_root")
        if exists:
            target = target.resolve(strict=True)
            if not target.is_relative_to(self.config.workspace_root):
                raise ValueError("Testkit paths must stay inside workspace_root")
        return target

    def snapshot(self, value: str) -> tuple[Path, dict]:
        root = self.under_root(value)
        if not root.is_dir() or not (root / "pages").is_dir():
            raise ValueError("Post-development testing needs an actual APEXlang export with pages/")
        entries, size, page_count = [], 0, 0
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("Export symlinks are not accepted for a stable test handoff")
            if not path.is_file():
                continue
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError("Export file escapes its source directory")
            relative = path.relative_to(root).as_posix()
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while data := stream.read(65536):
                    size += len(data)
                    if size > MAX_EXPORT_BYTES:
                        raise ValueError("Test export exceeds the 64 MiB handoff limit")
                    digest.update(data)
            entries.append({"path": relative, "sha256": digest.hexdigest()})
            page_count += relative.startswith("pages/") and path.suffix.lower() == ".apx"
            if len(entries) > 10_000:
                raise ValueError("Test export exceeds 10,000 files")
        if not page_count:
            raise ValueError("No page .apx files found; a Forms blueprint is not a completed APEX export")
        encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
        return root, {"sha256": hashlib.sha256(encoded).hexdigest(), "file_count": len(entries),
                      "page_source_files": page_count, "files": entries}

    async def native_call(self, name: str, arguments: dict) -> dict:
        session = self.require_session()
        if name not in self.peer.tools:
            raise ValueError("The connected apx-testkit does not provide " + name)
        result = await session.call_tool(name, arguments)
        texts = [c.text for c in result.content if c.type == "text"]
        if sum(map(len, texts)) > MAX_RESULT_CHARS:
            raise ValueError("apx-testkit result exceeds the 2-million-character limit")
        report = result.structuredContent
        if report is None and texts:
            try:
                report = json.loads(texts[0])
            except json.JSONDecodeError:
                pass
        return {"is_error": bool(result.isError), "report": report, "messages": texts if report is None else texts[1:]}

    async def read(self, tool_name: str, arguments: dict) -> dict:
        self.require_session()
        if tool_name not in READ_ARGUMENTS:
            raise ValueError("Only native inspection, flow, diff and coverage tools are available through testkit_read")
        if not isinstance(arguments, dict) or set(arguments) - READ_ARGUMENTS[tool_name]:
            raise ValueError("Unexpected arguments for the selected read-only testkit tool")
        descriptor = self.peer.tools.get(tool_name)
        if descriptor and descriptor.annotations and descriptor.annotations.readOnlyHint is False:
            raise ValueError("Native tool now advertises a write; refusing read-only forwarding")
        args = dict(arguments)
        for key in EXPORT_PATHS & args.keys():
            args[key] = str(self.snapshot(args[key])[0])
        if "touchLogPath" in args:
            args["touchLogPath"] = str(self.under_root(args["touchLogPath"], exists=False))
        return await self.native_call(tool_name, args)

    async def generate(self, export_path: str, run_name: str, development_ref: str,
                       development_complete: bool, baseline_export_path: str | None = None,
                       touch_log_path: str | None = None, migration_evidence: dict | None = None) -> dict:
        self.require_session()
        if development_complete is not True:
            raise ValueError("Complete development and export the application before declaring development_complete=true")
        if not isinstance(development_ref, str) or not development_ref.strip() or len(development_ref) > 200:
            raise ValueError("Provide a development commit, build ID or reviewed artifact reference (1..200 characters)")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", run_name) or ".." in run_name:
            raise ValueError("run_name must be a simple output name of 1..80 ASCII characters")
        async with self._generation_lock:
            export, before = self.snapshot(export_path)
            baseline, baseline_before = self.snapshot(baseline_export_path) if baseline_export_path else (None, None)
            policy = self.under_root(self.config.quality_policy_path) if self.config.quality_policy_path else None
            policy_hash = hashlib.sha256(policy.read_bytes()).hexdigest() if policy else None
            touch = self.under_root(touch_log_path, exists=False) if touch_log_path else None
            output = self.under_root("qa-output/" + run_name, exists=False)
            for source in [export, baseline]:
                if source and (output.is_relative_to(source) or source.is_relative_to(output)):
                    raise ValueError("Generated output must not overlap an export")
            output.parent.mkdir(parents=True, exist_ok=True)
            try:
                output.mkdir(exist_ok=False)
            except FileExistsError:
                raise ValueError("QA output already exists; choose a fresh run_name so existing tests are never overwritten") from None
            args = {"exportDir": str(export), "testsOutDir": str(output / "tests"),
                    "docsOutDir": str(output / "docs"), "sqlcl": False}
            if baseline:
                args["baselineExportDir"] = str(baseline)
            if touch:
                args["touchLogPath"] = str(touch)
            if policy:
                args["qualityPolicyPath"] = str(policy)
            try:
                native = await self.native_call("onboard_generated_apex_app", args)
            except Exception as error:
                native = {"is_error": True, "report": None, "messages": [str(error)]}
            try:
                unchanged = before == self.snapshot(str(export))[1]
                if baseline:
                    unchanged = unchanged and baseline_before == self.snapshot(str(baseline))[1]
                if policy:
                    unchanged = unchanged and policy_hash == hashlib.sha256(policy.read_bytes()).hexdigest()
            except (OSError, ValueError):
                unchanged = False
            native_report = native.get("report")
            generation = native_report.get("generate") if isinstance(native_report, dict) else None
            if not native["is_error"] and (not isinstance(generation, dict) or type(generation.get("generated")) is not int):
                native["is_error"] = True
                native.setdefault("messages", []).append("The native response lacks a recognized generation report; output is not verified")
            quality_failed = isinstance(native_report, dict) and isinstance(native_report.get("qualityGate"), dict) and native_report["qualityGate"].get("passed") is False
            status = "SOURCE_CHANGED" if not unchanged else "QUALITY_GATE_FAILED" if quality_failed else "GENERATION_FAILED" if native["is_error"] else "NO_TESTS_GENERATED" if generation["generated"] < 1 else "GENERATED_NOT_EXECUTED"
            result = {"status": status, "development_ref": development_ref.strip(),
                      "development_complete_declared": True, "development_verified_by_forms26": False,
                      "export_snapshot": before, "baseline_snapshot": baseline_before,
                      "quality_policy_sha256": policy_hash, "source_unchanged": unchanged,
                      "output_path": output.relative_to(self.config.workspace_root).as_posix(),
                      "generator": {"repository": REPOSITORY, "server_version": self.peer.version},
                      "native_result": native, "migration_evidence": migration_evidence,
                      "tests_executed": False, "live_application_verified": False,
                      "sqlcl_requested": False,
                      "next_step": "Review generated output and native verification gaps; configure a development APP_BASE/auth fixture before separately running Playwright. Smoke generation does not verify migrated business rules."}
            (output / "handoff.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            return result
