#!/usr/bin/env python3
"""Simple CLI that lists and counts git branches on your system."""

import subprocess
import sys


def count_branches():
    """List and count local and remote git branches.

    Runs ``git branch -a``, categorises branches as local or remote,
    prints each branch name (marking the currently checked-out branch),
    and displays totals.  Exits with code 1 if git is unavailable or
    the working directory is not a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "branch", "-a"],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error: Not a git repo or git failed: {e.stderr.strip()}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: git is not installed or not found on PATH.")
        sys.exit(1)

    branches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    local = [b for b in branches if not b.startswith("remotes/")]
    remote = [b for b in branches if b.startswith("remotes/")]

    print(f"Local branches:  {len(local)}")
    for b in local:
        # git branch -a prefixes the current branch with '* '
        marker = "* " if b.startswith("*") else "  "
        print(f"  {marker}{b.lstrip('* ')}")

    print(f"\nRemote branches: {len(remote)}")
    for b in remote:
        print(f"    {b[len('remotes/'):] if b.startswith('remotes/') else b}")

    print(f"\nTotal: {len(branches)} branches")


if __name__ == "__main__":
    count_branches()
