"""Download pinned public test inputs with SHA256 verification; no code is executed."""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["upstream", "summit"], required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    manifest = json.loads((Path(__file__).resolve().parents[1] / "examples/public-examples.json").read_text())
    suite = manifest["suites"][args.suite]
    target = Path(args.out)
    target.mkdir(parents=True, exist_ok=True)
    for item in suite["files"]:
        if Path(item["filename"]).name != item["filename"]:
            raise ValueError("Manifest filenames must not contain directories")
        with urllib.request.urlopen(item["url"], timeout=30) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Example checksum mismatch: " + item["filename"])
        (target / item["filename"]).write_bytes(data)
    print("Downloaded", len(suite["files"]), "inputs from", suite["repository"], "at", suite["commit"])
    print("Source licensing:", suite["license_note"])
    print("Modules:", " ".join(item["module"] for item in suite["files"]))


if __name__ == "__main__":
    main()
