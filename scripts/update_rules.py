"""
update_rules.py — Download the latest MTG Comprehensive Rules.

Fetches the current rules TXT from the Wizards of the Coast rules page and
saves it to ~/dev/set-reviews/MagicCompRules.txt.

Usage (from deq/):
  pdm run python scripts/update_rules.py
"""

import re
import sys
import urllib.request
from pathlib import Path

OUT = Path.home() / "dev" / "set-reviews" / "MagicCompRules.txt"
RULES_PAGE = "https://magic.wizards.com/en/rules"


def main():
    print("Fetching rules page to find latest TXT URL...", flush=True)
    req = urllib.request.Request(RULES_PAGE, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            html = f.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"ERROR: Could not fetch rules page: {e}", file=sys.stderr)
        sys.exit(1)

    match = re.search(
        r"https://media\.wizards\.com/\d+/downloads/MagicCompRules[^\"' ]+\.txt",
        html,
    )
    if not match:
        print("ERROR: Could not find comprehensive rules TXT URL on the rules page.", file=sys.stderr)
        sys.exit(1)

    url = match.group(0)
    print(f"Downloading: {url}", flush=True)

    req2 = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req2, timeout=60) as f:
            content = f.read()
    except Exception as e:
        print(f"ERROR: Could not download rules: {e}", file=sys.stderr)
        sys.exit(1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(content)
    lines = content.count(b"\n")
    print(f"Saved {len(content):,} bytes ({lines:,} lines) → {OUT}")


if __name__ == "__main__":
    main()
