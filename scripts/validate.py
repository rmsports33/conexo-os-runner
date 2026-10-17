"""Validate local JSON files without network access or arbitrary execution."""
import argparse
import json
from pathlib import Path


def validate(root: Path) -> int:
    files = sorted(root.rglob('*.json'))
    for path in files:
        if '.git' in path.parts:
            continue
        with path.open(encoding='utf-8') as handle:
            json.load(handle)
        print(f'OK: {path.relative_to(root)}')
    print(f'Validated {len(files)} JSON file(s)')
    return len(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', default='samples')
    args = parser.parse_args()
    validate(Path(args.directory))
