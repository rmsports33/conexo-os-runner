"""Read-only inventory of local Git repositories. No network or credentials."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

def inspect_repo(path):
    path = Path(path).expanduser().resolve()
    result = {"path": str(path), "exists": path.is_dir(), "git": False}
    if not result["exists"]:
        return result
    def git(*args):
        p = subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                           text=True, timeout=10, check=False)
        return p.stdout.strip() if p.returncode == 0 else None
    try:
        root = git("rev-parse", "--show-toplevel")
        if root is None or Path(root).resolve() != path:
            return result
        result["git"] = True
        result["branch"] = git("branch", "--show-current")
        result["commit"] = git("rev-parse", "HEAD")
        result["dirty"] = bool(git("status", "--porcelain"))
        result["remote_configured"] = bool(git("remote"))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        result["error"] = "git unavailable or timed out"
    return result

def inventory(paths):
    return {"generated_utc": datetime.now(timezone.utc).isoformat(),
            "network_used": False,
            "repositories": [inspect_repo(p) for p in paths]}

def main():
    parser = argparse.ArgumentParser(description="Offline read-only Git inventory")
    parser.add_argument("paths", nargs="+", help="Local repository folders")
    parser.add_argument("--output", help="Optional local JSON report")
    args = parser.parse_args()
    report = json.dumps(inventory(args.paths), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    print(report, end="")

if __name__ == "__main__":
    main()
