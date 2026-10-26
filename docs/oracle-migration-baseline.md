# Oracle migration guide: coverage and gaps

Reviewed reference: [Oracle Application Express 5.0 — Converting an Oracle Forms Application](https://docs.oracle.com/cd/E59726_01/doc.50/e39148/appmgr_forms.htm), reviewed October 26, 2026.

This exact page was reviewed after the initial starter implementation, when supplied by the project requester. Earlier inputs were Oracle's Forms2XML blog and newer MCP-assisted modernization guidance, alongside the Pretius workflow description. This document records that distinction rather than implying the original implementation covered this guide completely.

Version 0.2 adds an optional adapter for Oracle Forms MCP. The table below records the original local-parser baseline; [upstream integration](upstream-integration.md) now provides PLD ingestion, property-class/inheritance metadata, native cross-module search and persistent annotations. Reports XML and completed APEX generation remain gaps. The adapter reads an external server; it does not add those parsers to the local XML implementation.

The linked guide is historical APEX 5.0 documentation. It describes a migration workshop and application generation capabilities for that release. The database target (26ai) and APEX release are separate version choices; the project's installed APEX/ORDS capabilities must be verified independently.

| Oracle guide area | Starter status | Required follow-up |
| --- | --- | --- |
| FMB/MMB/OLB exported with Forms2XML | Common XML structures parsed; one module per file | Validate actual export variants and inherited/default properties |
| English export tags and `USE_PROPERTY_IDS=NO` | English tag/property names expected; export command documented | Detect and explain incompatible exports explicitly |
| `DUMP=ALL` versus overridden properties | Parser reads supplied properties | Prefer full-property exports for assessment; resolve missing/default/inherited semantics |
| PLL libraries converted to PLD text | Attached-library references only | Implement bounded plain-text library ingestion and link calls to definitions |
| Reports converted to XML | Not supported; Reports XML fails the Forms-module check | Separate Reports parser, query extraction and report migration plan |
| Workspace/users and schema preparation | Not provisioned by this server | Confirm workspace, parsing schema, grants and target versions |
| Database tables, views and other required objects | Optional dictionary checks | Verify all dependencies, privileges, synonyms and application semantics |
| Blocks, items, triggers, program units, record groups and LOVs | Common metadata retained | Validate completeness with real exports; review source before mapping |
| Alerts, applicability and manual conversion status | No complete coverage or persistent review store | Add explicit metadata and review-state support |
| Block-to-region and master/detail decisions | Draft region suggestions; relation metadata retained | Verify query/update behavior and transaction ownership |
| Annotations and completion tracking | Not implemented | Store applicability, decisions and test evidence tied to file hashes |
| APEX application generation | Design blueprint only | Use a supported, verified workflow for the installed APEX release |
| APIs on a shared PL/SQL layer | Project extension: package and unpublished ORDS shells | Translate actual rules; implement serialization, authorization and tests |

The guide notes that its conversion process supports table/view-based blocks and does not support synonym-based blocks. That is a historical tool limitation, not a universal prohibition on modern Oracle application designs. This server reports visible synonym objects but does not resolve them; any such dependency remains unresolved.

Oracle's documented inputs extend beyond a single FMB export. A complete assessment therefore needs associated libraries, menus, object libraries, reports and database objects. Module-level point scores cannot stand in for a verified portfolio migration estimate.

No historical application-generation capability is claimed as implemented by this repository. Generated SQL remains a draft until compiled and exercised; APEX mappings remain blueprints until the actual application is built and tested.
