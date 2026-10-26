# Public example validation — Forms26 v0.2

Checks ran on October 26, 2026 using Python 3.12, Java 25 (Temurin), and the actual Oracle Forms MCP **v0.15.0** release. Its distribution SHA256 was verified as `d4b8d295dacb72d089ce43d0e314e1f79bd89b97f2d403e0ba778c021bac9eee`.

The test path was **MCP client → Forms26 → upstream stdio server**, using pre-exported XML/PLD in copy mode. No Oracle Forms binaries, live database, legacy PL/SQL, APEX import or REST endpoint were executed.

Each module was explicitly fetched/indexed, analyzed, enumerated through component pagination, checked for risks and mapped to an APEX blueprint. Source retrieval was exercised where code existed; API shells were checked for `NOT_PUBLISHED` on modules containing application blocks.

## Upstream fixtures

Source: [aoreshkov/oracle-forms-mcp](https://github.com/aoreshkov/oracle-forms-mcp/tree/3d222c3d13183daea143956a16f3b7abcb43b81b) at `3d222c3d13183daea143956a16f3b7abcb43b81b`.

| Module | Blocks | Items | Triggers | Program units | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| `ORDERS.fmb` | 3 | 5 | 3 | 3 | Pass; review warnings |
| `UTILS.pll` | 0 | 0 | 0 | 4 | Pass |
| `OBJECTS.olb` | 0 | 0 | 0 | 0 | Pass |
| `STYLES.fmb` | 0 | 0 | 0 | 0 | Pass |
| `TOOLBAR.fmb` | 1 | 2 | 2 | 1 | Pass |
| `PICKER.fmb` | 4 | 7 | 6 | 2 | Pass; review warnings |
| `ENTRY.fmb` | 2 | 3 | 2 | 1 | Pass; review warnings |
| `DUPES.fmb` | 3 | 4 | 5 | 0 | Pass |
| `MAINMENU.mmb` | 0 | 0 | 0 | 1 | Pass |
| `CLAIMS.fmb` | 2 | 9 | 1 | 0 | Pass; review warnings |

Pipeline failures: **0**.

## Independent Summit exports

Source: [jcgueriaud1/forms-summit-migration](https://github.com/jcgueriaud1/forms-summit-migration/tree/258c82b4a22fd7ccc517e3be6a05f25e52e31a0d) at `258c82b4a22fd7ccc517e3be6a05f25e52e31a0d`.

| Module | Blocks | Items | Triggers | Program units | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| `ORDERS.fmb` | 4 | 34 | 45 | 4 | Pass; review warnings |
| `CUSTOMERS.fmb` | 5 | 30 | 23 | 7 | Pass; review warnings |
| `PICK.fmb` | 4 | 8 | 9 | 0 | Pass; review warnings |
| `REG.fmb` | 5 | 29 | 22 | 7 | Pass; review warnings |
| `DEPT.fmb` | 1 | 3 | 0 | 0 | Pass |
| `M_SUMMIT.mmb` | 0 | 0 | 0 | 0 | Pass |
| `CUSTOMERS.mmb` | 0 | 0 | 0 | 6 | Pass |
| `CALENDAR.pll` | 0 | 0 | 0 | 2 | Pass |
| `D2KDLSTR.pll` | 0 | 0 | 0 | 2 | Pass |
| `PICKLIST.pll` | 0 | 0 | 0 | 2 | Pass |

Pipeline failures: **0**.

## Independent checks and interpretation

- For all seven Summit XML modules, block, item, trigger, program-unit, menu and menu-item counts independently matched a separate XML traversal of the original export.
- The property-class-only `STYLES.fmb` is now visible as three property classes. The old local parser returned no indexed components for this fixture.
- `UTILS.pll` exposes four distinct units, including a same-named package specification and body. The three Summit PLD libraries each expose two indexed units.
- Effective DML and unresolved property-class information are retained in region/API design inputs.
- Uncached/missing inherited definitions, inherited block/item structures and attached libraries produce review warnings. A passing pipeline check does **not** mean these dependencies were resolved or the business rules were converted.
- Object-library tabs/entries are retained as reusable definitions; they are not treated as application pages.
- Native proxy reads and rejection of write tools through the read-only proxy are included in the reproducible harness.

## Sources and reproduction

The upstream fixture suite is Apache-2.0. No license file was located in the independent Summit repository during this check, so its files are downloaded for local testing and are not vendored or redistributed. See [THIRD_PARTY.md](../THIRD_PARTY.md).

The [manifest](../examples/public-examples.json) pins every input URL and SHA256. Use [scripts/fetch_examples.py](../scripts/fetch_examples.py) and [scripts/check_upstream.py](../scripts/check_upstream.py), following [the integration instructions](upstream-integration.md). The GitHub Actions integration job repeats the ten upstream-fixture checks using the pinned release.

Oracle independently uses the Summit Customers/Orders application in its [Forms-to-APEX modernization example](https://blogs.oracle.com/apex/transforming-f2a-agent). That establishes the relevance of the demo; it does not certify these repository exports or this implementation.
