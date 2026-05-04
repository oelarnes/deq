import os
import subprocess
import sys
from pathlib import Path

spells_dir = Path(os.path.expanduser("~/dev/spells"))

result = subprocess.run(
    ["git", "-C", str(spells_dir), "branch", "--show-current"],
    capture_output=True,
    text=True,
)

branch = result.stdout.strip()

if branch != "main":
    print(f"ERROR: spells is on branch '{branch}', not 'main'.")
    print(f"  Run: git -C {spells_dir} checkout main")
    print("  Then re-run pdm install.")
    sys.exit(1)

print(f"spells is on main ✓")
