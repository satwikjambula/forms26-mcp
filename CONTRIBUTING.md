# Contributing

Start with a GitHub issue describing the behavior you want to improve. Small, focused pull requests are easiest to review.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_mcp.py
```

Install `'.[oracle]'` only if you need the optional driver. The automated suite must run without Oracle credentials; use mocked dictionary responses and synthetic Forms XML fixtures.

## Changes to conversion behavior

- Link a finding or mapping to a source component and preserve its SHA256 evidence.
- Add a meaningful fixture/case that demonstrates the behavior or bug.
- State which XML export formats and Oracle/APEX/ORDS versions were actually tested.
- Preserve the boundary between source inspection, draft generation and executed/verified migration.
- Keep credentials out of tool arguments, logs, fixtures and commits.
- Do not introduce arbitrary SQL execution or automatic publication as an incidental change.
- Consume and test pagination where results can be large.

Use only sample code and files you have the right to share. Reproduce customer issues with minimal synthetic fixtures. Contributions are made under the project's MIT License.

Communicate respectfully and focus reviews on specific technical behavior. Maintainers may close abusive, unrelated or sensitive-content submissions.
