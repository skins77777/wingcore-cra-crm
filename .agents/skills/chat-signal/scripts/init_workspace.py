#!/usr/bin/env python3
"""Create local customer records without overwriting, network access or deployment."""
import argparse
import json
from pathlib import Path
import sys


def initialize(project: Path, company_name: str) -> Path:
    project = project.expanduser().resolve(strict=True)
    if not project.is_dir() or not company_name.strip():
        raise ValueError("Project must be a directory and company name must be nonempty")
    assets = Path(__file__).resolve().parents[1] / "assets"
    names = ("handoff.json", "deployment.md", "acceptance.md", "operations.md")
    contents = {name: (assets / name).read_text(encoding="utf-8") for name in names}
    contract = json.loads(contents["handoff.json"])
    contract["companyName"] = company_name.strip()
    contents["handoff.json"] = json.dumps(contract, ensure_ascii=False, indent=2) + "\n"
    destination = project / "chat-signal"
    # mkdir without exist_ok refuses existing directories, files and symlinks.
    destination.mkdir(mode=0o700)
    for name, content in contents.items():
        with (destination / name).open("x", encoding="utf-8") as output:
            output.write(content)
        (destination / name).chmod(0o600)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--company-name", required=True)
    args = parser.parse_args()
    try:
        initialize(args.project, args.company_name)
    except (OSError, ValueError):
        print("Initialization refused or incomplete. Check project/assets and existing records; nothing is deleted or overwritten.", file=sys.stderr)
        return 2
    print("Created four local records under chat-signal/. No services were contacted or deployed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
