"""Read-only inventory of Conexo OS modules declared in config/modules.json."""
import argparse
import json
from pathlib import Path
from scripts.git_inventory import inspect_repo

def module_inventory(manifest_path, workspace):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported module manifest version")
    policy = manifest.get("policy", {})
    if policy.get("mode") != "read-only" or policy.get("network_access") is not False:
        raise ValueError("Manifest must enforce offline read-only mode")
    workspace = Path(workspace).expanduser().resolve()
    items = []
    seen = set()
    for entry in manifest["modules"]:
        name = entry["repository"].split("/")[-1]
        if entry["id"] in seen or not name or "/" not in entry["repository"]:
            raise ValueError("Invalid or duplicate module")
        seen.add(entry["id"])
        path = workspace / name
        state = inspect_repo(path)
        items.append({"id": entry["id"], "repository": entry["repository"],
                      "visibility": entry["visibility"], "purpose": entry["purpose"],
                      "archived": entry["archived"], "local": state})
    return {"mode": "read-only", "network_used": False, "workspace": str(workspace),
            "modules": items}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="config/modules.json")
    parser.add_argument("--workspace", default=str(Path.home()))
    parser.add_argument("--output")
    args = parser.parse_args()
    report = json.dumps(module_inventory(args.manifest, args.workspace),
                        ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    print(report, end="")

if __name__ == "__main__":
    main()
