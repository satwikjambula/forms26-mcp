# Starter validation

## Version 0.3 post-development QA validation

- 31 automated Forms26 tests pass; all 15 tools pass stdio discovery/protocol checks.
- The actual apx-testkit repository at revision `10565ad65f8533b8aab8fa55ac1f546abfcd37aa` builds successfully; its 52 MCP tests pass.
- Client → Forms26 → apx-testkit generation passed across five native APEXlang fixture suites while the actual Oracle Forms MCP v0.15.0 was also connected.
- Generated 13 spec files with 40 test cases successfully discovered by Playwright `--list`. No browser or application was contacted.
- Completion gating, source drift, workspace bounds, protected existing output, generation-only status and retained native quality failures are covered by QA adapter tests.

See [docs/post-development-testing.md](docs/post-development-testing.md) for versions, results, configuration and outstanding live checks.

## Version 0.2 integration validation

- 20 automated tests passed, including nine new adapter tests.
- Local stdio discovery and protocol checks passed with all 12 Forms26 tools.
- The actual upstream v0.15.0 distribution was downloaded and its published SHA256 verified.
- Ten upstream fixtures and ten independent Summit exports passed the nested MCP test path (client → Forms26 → upstream), including PLD libraries, menus, property classes and inherited-source cases.
- Raw XML counts independently matched the normalized block/item/trigger/program-unit/menu counts for all seven Summit XML modules.
- Source truncation, identity mismatches, unconfigured/disabled operations, source drift and the read/write tool boundary are covered by adapter tests.

Sources, pinned revisions, module results and reproduction instructions are in [docs/public-example-validation.md](docs/public-example-validation.md). These checks do not establish compiled business-rule correctness, APEX importability or live Oracle 26ai compatibility.

## Version 0.1 baseline

Validated on October 26, 2026 using Python 3.12.14, MCP Python SDK 1.30.0, defusedxml 0.7.1 and python-oracledb 4.0.2.

## Checks completed

- 11 automated unit/workflow tests passed.
- Real MCP stdio subprocess initialization passed.
- All eight tools were discovered and called successfully.
- Component pagination, source chunking, invalid-path handling and invalid-identifier handling passed over the MCP protocol.
- Workflow resource and modernization prompt retrieval passed.
- A package wheel built and installed successfully; imports and the sample analysis worked from the installed package.
- A synthetic Forms2XML-style module produced the included demo-output.json.

Unit checks covered original code preservation, master/detail metadata, namespace/property-style XML, source-linked risks, literal/comment masking, external entity rejection, directory traversal/symlink confinement, unpublished API scaffolding, estimation calibration bounds and database configuration limits.

Database tests used a mocked driver to confirm fixed dictionary SQL, bound owner/object parameters, read-only transaction setup, rollback and sanitized errors. They do not establish live database compatibility.

## Checks requiring your environment

- Parse an actual export from your Oracle Forms installation and resolve libraries/subclassing.
- Connect to the development Oracle AI Database 26ai service.
- Confirm object visibility, keys, constraints, grants and row authorization.
- Translate and compile actual business rules in shared PL/SQL packages.
- Generate/import an application using the installed APEX release and test against Forms behavior.
- Complete ORDS request/response behavior and authentication, and test in a development schema.

The API outputs are deliberate scaffolds and the APEX output is a design blueprint. No completed business-rule conversion, Oracle compilation, APEX import or ORDS publication was claimed or performed.
