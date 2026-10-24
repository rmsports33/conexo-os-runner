#!/usr/bin/env python3
"""Conexo OS memory gate: read-only, stdlib-only, fail-closed on unknown evidence."""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TERMS = {
    'queue': ('queueworker', 'queue_worker', 'queue-worker', 'conexo-os-runner', 'fila', 'worker.py'),
    'executor': ('executor', 'autowake', 'localrunner', 'taskexecutor', 'queueworker', 'runner', 'dispatcher'),
    'recovery': ('recovery', 'recuperacao', 'recuperação', 'watchdog', 'retry', 'requeue'),
    'memory': ('agents.md', 'memory.md', 'decisions.md', 'memoria', 'memória', 'basic memory'),
}
ALLOWED_SUFFIX = {'.md', '.py', '.ps1', '.json', '.yml', '.yaml', '.toml'}
EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache'}
MAX_BYTES = 512_000

def tracked_files(repo):
    proc = subprocess.run(['git', '-C', str(repo), 'ls-files', '-z'], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError('Diretorio nao e um repositorio Git acessivel: ' + str(repo))
    return [repo / x.decode('utf-8', 'surrogateescape') for x in proc.stdout.split(b'\0') if x]

def inventory(repos):
    records = []
    for repo in repos:
        repo = Path(repo).resolve()
        for path in tracked_files(repo):
            if path.suffix.lower() not in ALLOWED_SUFFIX or any(x in EXCLUDED for x in path.parts):
                continue
            try:
                if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
                    continue
                body = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            for number, line in enumerate(body.splitlines(), 1):
                if len(line) > 1500:
                    continue
                matched = [category for category, variants in TERMS.items() if any(t in line.lower() for t in variants)]
                if matched:
                    records.append({'repo': str(repo), 'path': str(path.relative_to(repo)), 'line': number,
                                    'categories': matched, 'excerpt': line.strip()[:260]})
    return records

def assess(records, category):
    matches = [r for r in records if category in r['categories']]
    # An occurrence is evidence of a reference, not proof of implementation or execution.
    return {'category': category, 'decision': 'REVIEW_EXISTING' if matches else 'INSUFFICIENT_EVIDENCE',
            'evidence_count': len(matches), 'evidence': matches[:30],
            'safe_to_create_new': False,
            'reason': 'Referencias existentes requerem avaliacao antes de criar.' if matches else
                      'Busca nao comprovou ausencia; nao autorizar criacao automaticamente.'}

def main(argv=None):
    parser = argparse.ArgumentParser(description='Gate de memoria do Conexo OS (somente leitura)')
    parser.add_argument('--repo', action='append', required=True, help='Repositorio Git local; repetir para multiplos')
    parser.add_argument('--category', choices=sorted(TERMS), default='executor')
    parser.add_argument('--output', help='Caminho de relatorio JSON fora do repositorio')
    args = parser.parse_args(argv)
    try:
        records = inventory(args.repo)
        result = {'schema_version': 1, 'generated_utc': datetime.now(timezone.utc).isoformat(),
                  'repositories': [str(Path(x).resolve()) for x in args.repo], **assess(records, args.category)}
        serialized = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            dest = Path(args.output).resolve()
            if any(dest == Path(r).resolve() or Path(r).resolve() in dest.parents for r in args.repo):
                raise RuntimeError('Relatorio deve ser salvo fora dos repositorios para evitar alteracoes')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(serialized + '\n', encoding='utf-8')
        print(serialized)
        return 0 if result['decision'] == 'REVIEW_EXISTING' else 2
    except (OSError, RuntimeError) as exc:
        print('FALHA SEGURA: ' + str(exc), file=sys.stderr)
        return 3

if __name__ == '__main__':
    sys.exit(main())
