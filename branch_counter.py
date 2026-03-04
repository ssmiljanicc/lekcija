#!/usr/bin/env python3
"""Simple CLI that counts git branches on your system."""

import subprocess
import sys


def count_branches():
    try:
        result = subprocess.run(
            ["git", "branch", "-a"],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error: Not a git repo or git failed: {e.stderr.strip()}")
        sys.exit(1)

    branches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    local = [b for b in branches if not b.startswith("remotes/")]
    remote = [b for b in branches if b.startswith("remotes/")]

    print(f"Local branches:  {len(local)}")
    for b in local:
        marker = "* " if b.startswith("*") else "  "
        print(f"  {marker}{b.lstrip('* ')}")

    print(f"\nRemote branches: {len(remote)}")
    for b in remote:
        print(f"    {b.removeprefix('remotes/')}")

    print(f"\nTotal: {len(branches)} branches")


if __name__ == "__main__":
    count_branches()
