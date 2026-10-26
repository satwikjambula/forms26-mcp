# Forms26 MCP

[![CI](https://github.com/satwikjambula/forms26-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/satwikjambula/forms26-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A working Python MCP server for developer-assisted Oracle Forms modernization to **Oracle APEX and ORDS APIs on Oracle AI Database 26ai**.

Export a Forms module to XML, connect this server to your coding assistant, inspect the original rules, verify database objects, and draft a shared PL/SQL service layer. APEX processes and REST handlers should call that same service layer.

This is an independent starter implementation inspired by the workflow in the [Pretius article](https://pretius.com/blog/oracle-forms-migration). It does not reproduce Pretius proprietary code, prompts, training data, estimation history, or accuracy claims.

## What works now

| Capability | Output |
| --- | --- |
| XML inventory and parsing | Blocks, items, triggers, program units, LOVs, record groups, relations, menus, attached-library references |
| Source inspection | Original code with component IDs, file SHA256 and chunked retrieval |
| Migration assessment | Transparent complexity factors; optional illustrative hours using your team's rate |
| Risk detection | Navigation, transactions, Forms session state, cross-form calls, desktop/report integrations, dynamic SQL and subclass references |
| APEX planning | Region suggestions, trigger mappings and behavior-based acceptance criteria |
| API scaffolding | PL/SQL package shell, unpublished ORDS handler and draft OpenAPI 3.1 contract |
| Optional database verification | Fixed dictionary queries for objects, columns and constraints in one configured schema |
| Host AI workflow | Reusable MCP prompt that asks your coding assistant to review and translate the actual source |

The server uses **stdio** and runs alongside your development tools. Oracle Database does not host this Python process. Your MCP client supplies the language model; this project has no model API keys, paid inference calls, or AI-provider dependency.

Version 0.2 adds an optional adapter for [aoreshkov/oracle-forms-mcp](https://github.com/aoreshkov/oracle-forms-mcp): Forms26 can use its indexed Forms, menus, object libraries and PLD libraries as inputs to the migration tools. See [upstream setup](docs/upstream-integration.md), [public-example results](docs/public-example-validation.md) and [third-party attribution](THIRD_PARTY.md).

## Run it

Requires Python 3.11 or later. From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m forms26_mcp.server --root /absolute/path/to/exported-forms
```

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

A stdio MCP server waits for an MCP client's JSON-RPC requests; running it in a terminal does not open a web interface. Configure the client using [examples/mcp-config.json](examples/mcp-config.json), replacing both absolute paths. The example uses the common `mcpServers` shape; adapt the wrapper if your client requires a different configuration format. Set the client's command to the interpreter inside this virtual environment, where the project was installed.

Test without a database:

```bash
.venv/bin/python -m forms26_mcp.demo --root examples --path orders_fmb.xml --out demo-output.json
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_mcp.py
```

The included XML is a synthetic order-entry form. The included `examples/demo-output.json` shows its actual analysis and scaffolds.

## Export existing Forms modules

Use Oracle's Forms2XML utility in a licensed/authorized Forms development environment:

```text
frmf2xml USE_PROPERTY_IDS=NO DUMP=ALL customers.fmb orders.fmb
```

The corresponding exports are normally named `customers_fmb.xml` and `orders_fmb.xml`. Oracle also documents Binary-to-XML conversion in Forms Builder. This server reads XML; it does not decode FMB binaries or install Oracle Forms.

Place exported modules beneath a dedicated allowed root. Attached PLL library bodies, inherited object definitions and external integration code must be supplied and reviewed separately; seeing a library reference does not resolve its implementation.

The export options and broader migration inputs are described in Oracle's [APEX 5.0 Forms migration guide](https://docs.oracle.com/cd/E59726_01/doc.50/e39148/appmgr_forms.htm). Its metadata concepts inform our [coverage and gap map](docs/oracle-migration-baseline.md). Historical APEX wizard and generation instructions are not promises about the installed target release. The optional upstream server handles PLL-to-PLD conversion and PLD inspection when configured; the local XML parser does not. Reports XML parsing remains unsupported.

## Connect Oracle 26ai for schema checks

Install the optional driver:

```bash
.venv/bin/python -m pip install -e '.[oracle]'
```

Set the following environment variables **in the environment that launches the MCP process**:

| Variable | Purpose |
| --- | --- |
| `ORACLE_DSN` | Oracle connect string, e.g. `db.example:1521/app_pdb` |
| `ORACLE_USER` | Dedicated account with the necessary dictionary visibility |
| `ORACLE_PASSWORD` | Password provided through your local secret mechanism |
| `ORACLE_SCHEMA` | One target owner, e.g. `APP` |
| `ORACLE_CONFIG_DIR` | Optional directory containing `tnsnames.ora` |
| `ORACLE_WALLET_LOCATION` | Optional wallet directory for python-oracledb Thin mode |
| `ORACLE_WALLET_PASSWORD` | Optional wallet password |

The project does not load `.env` automatically. Have your shell, IDE or MCP launcher inject secrets; keep them out of source control and chat prompts. The sample MCP configuration deliberately contains no credentials.

`inspect_database_objects(["ORDERS", "ORDER_LINES"])` queries only `ALL_OBJECTS`, `ALL_TAB_COLUMNS`, `ALL_CONSTRAINTS` and `ALL_CONS_COLUMNS`, with owner/object names bound as values. It starts a read-only transaction and uses connection/call timeouts. There is no arbitrary SQL, PL/SQL execution or database write tool. Names are restricted to simple unquoted ASCII identifiers up to 30 characters for this MVP; quoted, qualified and longer identifiers need a later extension. Synonyms are reported as objects but are not resolved to their targets.

An absent object means it is absent from the configured account's view; it may exist with insufficient visibility. Dictionary checks do not inspect application rows, package bodies, grants, VPD behavior or installed APEX/ORDS compatibility. Use database privileges appropriate to a metadata reader; dictionary visibility alone does not make an overprivileged account safe.

## Tools

| Tool | Main arguments |
| --- | --- |
| `list_forms` | `offset`, `limit` |
| `analyze_form` | `path`, optional `hours_per_point` |
| `list_components` | `path`, optional exact `kind`, `offset`, `limit` |
| `get_source` | `path`, `component_id`, character `offset`, `limit` |
| `migration_risks` | `path`, `offset`, `limit` |
| `plan_apex` | `path` |
| `draft_api` | `path`, exact `block_name`, `package_name` |
| `inspect_database_objects` | `names`: 1–20 object names |
| `upstream_status` | Connection, version and native tool schemas; no launch secrets |
| `upstream_read` | `tool_name`, `arguments`: allowlisted inspection/search calls |
| `upstream_fetch` | `module`: explicit conversion/copy and cache indexing |
| `upstream_annotate` | `tool_name`, `arguments`: annotation writes, disabled by default |

Resource: `forms26://workflow`. Prompt: `modernize_form(path)`.

With upstream configured, use the same analysis/source/APEX/API tools with `path: "upstream:ORDERS.fmb"` or `"upstream:UTILS.pll"`. Call `upstream_fetch` first. Native reads, including cross-module search and raw XML inspection, are available through `upstream_read`; get exact argument schemas from `upstream_status`. No read call automatically converts a module. Operator-owned launch configuration is never accepted as a tool argument.

Keep the file SHA256 with each review: component IDs are stable for unchanged XML traversal, but can change when an export changes. Consume every result page and source chunk before concluding that a module has been fully inspected. XML is capped at 32 MiB per module. Normal external DTD declarations are tolerated without fetching DTD content; XML entities are rejected.

Example instruction to your MCP-enabled assistant:

> Modernize orders_fmb.xml for APEX and ORDS on Oracle 26ai. Use the modernize_form prompt. Read all relevant source, verify ORDERS and ORDER_LINES, and identify missing library logic. Propose a shared PL/SQL package, APEX mappings and an API contract. Show source evidence and unresolved assumptions. Prepare development changes for review and report exactly which checks ran.

## What still needs implementation in a real migration

**The API generator creates shells, not translated business rules.** Its package deliberately raises `-20001` until the actual rules are implemented; its ORDS module is `NOT_PUBLISHED`, and its response handler is incomplete. The OpenAPI document is explicitly a draft. No SQL returned by these tools is executed.

The APEX output is a design blueprint, **not an importable application**. A developer or host coding assistant must generate the application using a supported workflow for the installed APEX release, compile/test the service packages, configure ORDS authorization and response serialization, and verify behavior against the original Forms application. This project does not assume that an arbitrary APEX export format or undocumented internal package is stable.

The intended migration flow is:

1. Export and inventory modules and libraries.
2. Inspect metadata and source; resolve dependencies and subclassing.
3. Confirm database objects and document gaps.
4. Move reviewed business rules into shared PL/SQL services with explicit inputs.
5. Rebuild screens in APEX; expose selected operations through authenticated ORDS APIs.
6. Test validation parity, transaction boundaries, master/detail behavior, row authorization, concurrency, error handling and API retries in a development schema.
7. Plan phased cutover and rollback using the application's operational requirements.

The server is a backend for that workflow. It does not automatically deliver a completed migration, production REST service or deployed APEX app.

## Estimation and limitations

Complexity points use the visible factors returned by `analyze_form`: base weight, blocks, groups of items, code units, nonblank code lines, risks, libraries and relations. These are **uncalibrated planning heuristics**. They are not Pretius estimates. Hours are returned only when you provide `hours_per_point`; the high end applies an explicit illustrative factor of 1.75. Calibrate against completed modules and add separate allowances for unresolved libraries, integration work, UAT, deployment and training.

Local parsing handles common Forms2XML attribute-based, namespaced and property-element representations. The upstream adapter additionally retains property classes, effective item DML, source ranges, inherited-body status and unresolved dependencies. It refuses automatic migration when the upstream index or block details are truncated; native inspection is still available. SQL/PLSQL scanning is lexical and deliberately ignores comments/string literals; it is not a compiler, complete dependency graph or Forms runtime emulator. Validate it against your own exports before portfolio-wide use. Review prompt injection and sensitive content in legacy files as project data; the host model controls what it sends to its AI provider.

Oracle AI Database 26ai is the intended target. The XML analysis does not need an Oracle connection. **No live 26ai, APEX or ORDS environment was available for validation of this starter**, so database compatibility, PL/SQL compilation and application imports have not been certified. Pinning the tested MCP v1 maintenance SDK avoids silently adopting the incompatible v2 API; upgrading should include a deliberate protocol regression check.

## References

- [Oracle: APEX 5.0 Forms conversion guide](https://docs.oracle.com/cd/E59726_01/doc.50/e39148/appmgr_forms.htm) — historical conversion inputs, metadata review and annotations; see the explicit coverage/gap map.
- [Pretius: Oracle Forms migration](https://pretius.com/blog/oracle-forms-migration) — inspiration for assessment, risk review and assisted modernization.
- [Oracle: Forms2XML conversion](https://blogs.oracle.com/apex/forms-to-apex-converting-fmbs-to-xml) — source export procedure.
- [Oracle: MCP-assisted Forms modernization](https://blogs.oracle.com/apex/transforming-f2a-agent) — source inspection, object verification and reusable database logic.
- [Oracle SQLcl MCP](https://docs.oracle.com/en/database/oracle/sql-developer-command-line/26.3/sqcug/starting-managing-sqlcl-mcp-server.html) — optional companion for separately governed database development; this project does not enable it automatically.
- [ORDS PL/SQL reference](https://docs.oracle.com/en/database/oracle/oracle-rest-data-services/26.3/orddg/ORDS-reference.html) — module, template and handler APIs.
- [Official MCP Python SDK v1 documentation](https://py.sdk.modelcontextprotocol.io/v1/) — pinned stdio server implementation.

## Suggested next increment

Use one actual Forms XML export and a development-schema metadata snapshot to validate the parser, implement one shared validation service, build one APEX page and one ORDS endpoint, and compare their behavior with the original form. A proven vertical slice is the basis for extending conversion coverage.

## Contributing and license

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md), the [roadmap](ROADMAP.md), and [security reporting guidance](SECURITY.md). This is an alpha developer tool. Examples are synthetic; do not contribute customer exports, credentials, wallets, or proprietary code.

Released under the [MIT License](LICENSE). Oracle, APEX and Pretius names identify external products and references; this project is independent and is not endorsed by those organizations. Oracle software, documentation and third-party dependencies retain their own licenses.
