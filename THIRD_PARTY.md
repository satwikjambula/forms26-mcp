# External integration and test sources

Forms26 is independently implemented and MIT-licensed. No `oracle-forms-mcp` implementation, JAR, Oracle executable or external example source is vendored in this repository or Python package.

## Oracle Forms MCP

- Project: https://github.com/aoreshkov/oracle-forms-mcp
- Author notice: `oracle-forms-mcp — Copyright 2026 Atanas Oreshkov`
- Upstream license: Apache License 2.0; see its LICENSE and NOTICE.
- Tested runtime: upstream release v0.15.0.
- Reviewed source/fixture revision: `3d222c3d13183daea143956a16f3b7abcb43b81b`.

Forms26 calls the public MCP interface of a separately installed upstream process. Keep the upstream distribution and its license/notices intact. Forms26's MIT license does not replace the upstream license.

## External examples

The [example manifest](examples/public-examples.json) contains pinned URLs and SHA256 hashes, not the example source files. `scripts/fetch_examples.py` downloads them to a directory you choose for local testing.

- Upstream's ten synthetic module fixtures are provided by its Apache-2.0 repository.
- The ten Summit exports come from https://github.com/jcgueriaud1/forms-summit-migration at revision `258c82b4a22fd7ccc517e3be6a05f25e52e31a0d`. No repository license file was located during this check. They were read/downloaded for testing and are not redistributed here or relicensed as MIT.

Oracle's Summit demo is also referenced by Oracle's Forms modernization articles. Oracle software and sample materials retain their respective terms. Merely appearing in a public repository does not make a file MIT-licensed.

## apx-testkit

- Project: https://github.com/satwikjambula/apx-testkit
- Upstream license: Apache-2.0.
- Tested revision: `10565ad65f8533b8aab8fa55ac1f546abfcd37aa` (MCP version `0.1.0`).
- Forms26 calls its public stdio MCP interface and delegates to its deterministic generator. No generator implementation or upstream fixture source is vendored here.
- Its testkit runtime must be installed separately in the consuming Playwright test project. Keep upstream's distribution and license notices intact.
