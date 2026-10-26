# Integrating Oracle Forms MCP

Forms26 v0.2 can launch [Oracle Forms MCP](https://github.com/aoreshkov/oracle-forms-mcp) as a child stdio MCP server, inspect it through native tools, and normalize its indexed modules into Forms26 migration inputs. Upstream remains a separately installed Apache-2.0 component; our adapter is independent MIT code. See [THIRD_PARTY.md](../THIRD_PARTY.md).

## Install and configure

1. Install upstream using its documented instructions. The tested native release is **v0.15.0** and needs **Java 25**. Its Docker distribution uses pre-converted files; native conversion requires your authorized Oracle Forms installation.
2. Install Forms26: `python -m pip install -e .` from the project directory.
3. Copy [examples/upstream-config.json](../examples/upstream-config.json) to an operator-owned `upstream-config.local.json`; set the executable and Forms directory to real paths.
4. Launch Forms26:

```bash
python -m forms26_mcp.server --upstream-config /absolute/path/upstream-config.local.json
```

You may also provide `--root /absolute/path/exported-xml` to keep local XML analysis available. The `FORMS26_UPSTREAM_CONFIG` environment variable is equivalent to the flag. Configure your MCP client using [examples/mcp-config-upstream.json](../examples/mcp-config-upstream.json).

The upstream config has `command` (one executable), `args` (an array), `env` (a string map), `timeout_seconds` (1–600, default 180) and `allow_annotations` (boolean, default false). The command is passed to the MCP SDK as executable/argv, never to a shell. Put `JAVA_HOME`, `ORACLE_HOME`, or other required upstream settings in its `env`; Forms26 database credentials are not implicitly forwarded. Do not commit a configuration containing secrets.

An optional Docker configuration uses `command: "docker"` and args like `run`, `-i`, `--rm`, volume mappings, `ghcr.io/aoreshkov/oracle-forms-mcp:0.15.0`, `--forms-dir`, `/forms`. Verify the image tag in upstream's releases before using it; the native v0.15.0 distribution is what was exercised here. Persist the cache/annotation volume if using Docker. Forms26 neither downloads nor installs upstream automatically.

## Use it

Example MCP tool calls:

```json
{"name":"upstream_status","arguments":{}}
{"name":"upstream_read","arguments":{"tool_name":"list_modules","arguments":{"limit":20}}}
{"name":"upstream_fetch","arguments":{"module":"ORDERS.fmb"}}
{"name":"analyze_form","arguments":{"path":"upstream:ORDERS.fmb"}}
{"name":"plan_apex","arguments":{"path":"upstream:ORDERS.fmb"}}
{"name":"draft_api","arguments":{"path":"upstream:ORDERS.fmb","block_name":"ORDERS","package_name":"ORDERS_SERVICE"}}
```

Use `.mmb` for menus, `.pll` for libraries and `.olb` for object libraries. Fetch parent modules and attached libraries explicitly before requesting inheritance resolution. Analyze attached libraries separately; a form's count is not a recursive portfolio inventory.

`upstream_status` returns exact native schemas. `upstream_read` forwards allowlisted reads, including search, source/XML reads and annotation lookup. It rejects fetch/annotation mutation tools. `upstream_fetch` is a separately annotated cache/converter write. `upstream_annotate` can forward `annotate_element`, `relate_elements` and `remove_annotation` only when `allow_annotations` is enabled; its tool annotation advertises mutation and potential deletion.

## Migration evidence

Normalized components retain upstream metadata, effective item DML, source references and inherited-body status. APEX regions include `legacy_semantics`; API field hints include `effective_dml` and the block's legacy semantics. These are design inputs, not live database facts.

Each result includes the source SHA256, upstream version, index version, a migration snapshot hash and any resolved parent fingerprints. File hashes distinguish source provenance from the normalized migration snapshot. The adapter re-reads the index after inspection and rejects detected drift. It does not claim a transactionally locked multi-process snapshot.

Unresolved property classes, inherited structures and library dependencies are explicit warnings. A blank inherited body is preserved as `body_source: "inherited"`; it is never relabeled as a genuinely empty implementation. Full inherited block/item structures still need parent inspection, even when a trigger's source resolves.

## Bounds and failure behavior

- Automatic normalization needs a complete upstream index resource and untruncated block details. If upstream serves a digest or truncated details, the adapter stops and directs you to native inspection; it does not silently produce a partial migration plan.
- Source reads follow line pagination and reject a cut line, non-progressing continuation or oversized body. Normalization is bounded to 20,000 components and four million code characters per module.
- An upstream source SHA256 and matching module identity are required.
- Object-library entries remain reusable definitions, not automatically generated application regions. Use native `get_object_xml` to inspect their details.
- Conversion and annotation writes belong to upstream's local stores. No new Oracle DML/DDL execution or REST publication tool is introduced.
- The child process and MCP session are owned by Forms26's lifespan and closed when Forms26 exits.

## Reproduce the example checks

```bash
python scripts/fetch_examples.py --suite upstream --out .external-examples/upstream
python scripts/fetch_examples.py --suite summit --out .external-examples/summit
```

Point your upstream config's `--forms-dir` at one downloaded directory. The fetcher prints the module identities. Then:

```bash
python scripts/check_upstream.py --config upstream-config.local.json --modules ORDERS.fmb UTILS.pll STYLES.fmb --output upstream-results.json
```

This runs **client → Forms26 → actual upstream server**, explicitly fetches the selected modules, and exercises native reads, analysis, component pagination, source retrieval, risks, APEX planning and API shells. It does not run legacy business logic or connect to Oracle. See the [public-example validation report](public-example-validation.md) for the tested source revisions and outcomes.
