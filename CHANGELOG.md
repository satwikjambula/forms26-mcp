# Changelog

## 0.3.0 — 2026-10-26

- Connect the separately installed `satwikjambula/apx-testkit` MCP for post-development QA.
- Add QA status/schema discovery, allowlisted reads and native onboarding/test generation for completed APEXlang exports.
- Record development references, export fingerprints and optional Forms migration evidence in a persistent handoff.
- Protect existing test outputs with fresh run directories; retain quality failures, source drift, skipped cases and generation-only status.
- Keep SQLcl and live Playwright execution separate from generation.
- Add 11 QA adapter tests and a real-provider harness; validate five fixture suites producing 13 spec files and 40 Playwright-discovered tests.

## 0.2.0 — 2026-10-26

- Integrate the separately installed `aoreshkov/oracle-forms-mcp` through a managed stdio adapter.
- Add upstream status/schema discovery, allowlisted reads, explicit module fetching and opt-in annotation writes.
- Accept `upstream:NAME.fmb`/`.mmb`/`.pll`/`.olb` in the existing migration tools.
- Retain property classes, effective DML, inherited-body status, source references and provenance hashes; stop normalization on truncated or drifting evidence.
- Add nine adapter tests, a real-server protocol harness and pinned public-example downloads.
- Validate ten upstream fixtures and ten independent Summit exports through the actual upstream v0.15.0 release, including forms, menus, object libraries and PLD libraries.

Live Oracle schema checks, business-rule compilation, APEX imports and REST runtime behavior still require a development environment.

## 0.1.0 — 2026-10-26

- Initial public alpha of the Forms26 MCP server, under the MIT License.
- Eight stdio MCP tools for XML inventory, analysis, source inspection, risk review, APEX planning, API shells and optional database metadata checks.
- Synthetic order-entry example, 11 automated tests and an end-to-end MCP check.
- Explicit Oracle APEX 5.0 migration-guide coverage/gap map and development roadmap.
- Contribution guidance, security reporting guidance, issue templates and CI configuration.

This release provides developer-assisted analysis and scaffolding. Live Oracle 26ai compatibility, translated business rules, APEX application generation and published REST services have not been validated.
