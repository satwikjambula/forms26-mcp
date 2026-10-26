"""Generate an offline analysis bundle from one exported module."""
import argparse
import json
from pathlib import Path

from .core import Workspace, assessment, apex_plan, api_scaffold, findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    model = Workspace(args.root).parse(args.path)
    output = {"assessment": assessment(model), "risks": findings(model),
              "apex": apex_plan(model), "source_inventory": model}
    blocks = [c for c in model["components"] if c["kind"] == "Block"]
    if blocks:
        output["api_example"] = api_scaffold(model, blocks[0]["name"], "MIGRATION_SERVICE")
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
