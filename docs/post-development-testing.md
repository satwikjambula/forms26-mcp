# Post-development testing with apx-testkit

Forms26 v0.3 integrates [satwikjambula/apx-testkit](https://github.com/satwikjambula/apx-testkit) as the QA provider after application development. Its native `onboard_generated_apex_app` tool generates deterministic Playwright smoke specs/page objects, documentation and a navigation flow map from a real APEXlang export. Forms26 delegates to that implementation; it does not reimplement its generator or invent runtime assertions.

The application must exist first. The Forms26 APEX blueprint and API package shells are not completed applications and are not valid test-generator inputs. A declaration that development is complete records caller intent; Forms26 does not certify it.

## Configure once

Install/build apx-testkit using its instructions. The tested revision is `10565ad65f8533b8aab8fa55ac1f546abfcd37aa`, which exposes MCP server version `0.1.0` and requires Node 22 or later:

```bash
git clone https://github.com/satwikjambula/apx-testkit.git
cd apx-testkit
git checkout 10565ad65f8533b8aab8fa55ac1f546abfcd37aa
npm ci --ignore-scripts
npm run build
```

Copy [examples/testkit-config.json](../examples/testkit-config.json) to `testkit-config.local.json`. Set its command/args to the built `packages/mcp/dist/server.js` and choose an existing, absolute `workspace_root` containing the completed application exports. Database credentials are not implicitly forwarded to this child process.

Launch Forms26 with:

```bash
python -m forms26_mcp.server --testkit-config /absolute/path/testkit-config.local.json
```

You can also pass `--root` and `--upstream-config` to use the Forms inspection server and QA server together. See [examples/mcp-config-full.json](../examples/mcp-config-full.json). The equivalent environment variable is `FORMS26_TESTKIT_CONFIG`.

The QA config supports `command`, `args`, `env`, `timeout_seconds`, `workspace_root` and optional `quality_policy_path`. Quality policy paths resolve beneath the QA workspace. The existing Forms server and QA server remain separate, managed child processes with their own configurations and licenses.

The selected apx-testkit revision accepts static APEXlang exports for APEX **26.1 and 26.2**. Its runtime wrappers are live-verified on **26.1**; these are separate claims. The parser checks the `.apex/apexlang.json` manifest and reports unsupported/missing metadata rather than assuming a release. Oracle AI Database 26ai does not by itself determine your APEX release.

## After development is done

1. Finish the application changes and obtain a real exported APEXlang directory, including its `pages/` and `.apex/` metadata.
2. Record a development commit, build ID or reviewed artifact reference.
3. Ask Forms26 to generate the post-development tests into a **fresh** named run.
4. Review generated code, parser warnings, skipped cases and live-verification requirements. Keep generated files owned by apx-testkit.
5. Separately configure the test project's `@apx/testkit` dependency, Playwright config, `APP_BASE`, authentication fixture and test data, then run the suite against the development application.
6. Analyze the resulting touch log/coverage through the read-only QA tools. Component touch coverage is not business-rule or SQL code coverage.

Example MCP call:

```json
{
  "name": "generate_post_development_tests",
  "arguments": {
    "export_path": "exports/order-app",
    "run_name": "build-abc123",
    "development_ref": "git:abc123",
    "development_complete": true,
    "migration_source_path": "upstream:ORDERS.fmb"
  }
}
```

`export_path`, optional `baseline_export_path` and optional `touch_log_path` are paths beneath the configured QA workspace. `migration_source_path` is optional and uses the Forms26 source namespace (`upstream:NAME.fmb` or a local XML path); it adds original-source evidence and migration acceptance criteria to the handoff. It does not invent business-rule assertions from the smoke generator.

Results are written under `workspace_root/qa-output/<run_name>/`:

- `tests/`: native generated `.page.ts` and `.spec.ts` files.
- `docs/`: native per-page documentation.
- `handoff.json`: development reference, source/export fingerprints, native onboarding report (including flow map), quality results, outstanding verification needs and optional Forms migration evidence.

Existing run directories are rejected, even if empty. Choose a new name; this wrapper does not overwrite generated or hand-authored tests. Upstream's safe-regeneration CLI remains a separate workflow, not silently substituted for onboarding.

## Tools and result states

| Forms26 tool | Purpose |
| --- | --- |
| `testkit_status` | Connection/version and the provider's native schemas; launch secrets are omitted |
| `testkit_read` | Allowlisted inspection, flow maps, export diffs and touch-log coverage within the workspace |
| `generate_post_development_tests` | Explicit post-development generation into a fresh run; requires the completion declaration and development reference |

`testkit_read` supports `inspect_apex_export`, `generate_flow_map`, `diff_apex_exports` and `analyze_coverage`. Its native path arguments are confined to the configured workspace. It cannot call generation tools or enable SQLcl through extra arguments.

| Status | Meaning |
| --- | --- |
| `GENERATED_NOT_EXECUTED` | Provider returned a recognized, nonzero generation result against unchanged inputs; no live tests ran |
| `QUALITY_GATE_FAILED` | Native policy rules failed or were blocked; the full report is retained |
| `GENERATION_FAILED` | Native invocation failed or returned an unrecognized generation report |
| `NO_TESTS_GENERATED` | Native report generated no spec files |
| `SOURCE_CHANGED` | Export, baseline or policy changed during generation; outputs need review/regeneration |

Non-success generation states also return an MCP tool error with structured evidence. A policy that was not configured remains `null`; it is not an implicit pass. Failed quality gates do not erase the report or masquerade as successful test execution.

SQLcl validation is explicitly **off** in this adapter, and it never launches Playwright. A native quality policy requiring SQLcl will therefore remain blocked. The generator's existing coverage rules apply: an actual prior touch log and baseline are needed where the native onboarding workflow requires them. Missing coverage prerequisites are reported rather than fabricated.

Exports are fingerprinted before/after generation, symlinked export entries are rejected, source/output overlap is prohibited, and the export scan is bounded to 64 MiB/10,000 files. This is drift detection, not a filesystem lock or a security audit.

## Validation completed

The actual built apx-testkit MCP was exercised together with the actual Oracle Forms MCP v0.15.0 in the same Forms26 process. Five upstream APEXlang fixture suites produced **13 spec files**, containing **40 test cases discovered by Playwright `--list`**:

| Fixture suite | Spec files | Discovered tests |
| --- | ---: | ---: |
| Reference employee page | 1 | 5 |
| Duplicate button labels | 3 | 8 |
| Navigation protection | 4 | 10 |
| Modal dialogs | 4 | 12 |
| Region resolution | 1 | 5 |

Authentication/navigation skips and verification gaps were retained. Discovery loads generated tests but does not execute them, open a browser or contact an APEX application. The selected apx-testkit MCP's own **52 tests** also passed. Forms26 has **31 automated tests** plus stdio discovery checks for all **15 tools**.

Reproduce nested generation with [scripts/check_testkit.py](../scripts/check_testkit.py): provide a QA config, fixture export paths, a fresh `--run-prefix` and `--development-ref`. Optional `--forms-upstream-config` exercises both child MCPs together. The CI job checks the pinned QA provider and performs generation and discovery separately.

No running migrated APEX app, live Oracle 26ai environment, end-to-end business-rule parity, or ORDS endpoint was verified by these checks.
