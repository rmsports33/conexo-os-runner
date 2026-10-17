
"""Generate a portable Conexo OS status report, offline."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read_json(path):
    path = Path(path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def generate_status(inventory, changes, history_path):
    if not isinstance(inventory, dict):
        raise ValueError("Module inventory is required")

    if inventory.get("mode") != "read-only":
        raise ValueError("Invalid inventory mode")

    if inventory.get("network_used") is not False:
        raise ValueError("Inventory must be offline")

    lines = [
        "# Conexo OS - Estado operacional",
        "",
        "Gerado em: " + datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        ),
        "",
        "## Arquitetura",
        "",
        "- Executor local: Python, SQLite e Agendador do Windows.",
        "- Inventario e historico: operacao offline.",
        "- Sincronizacao remota: nao executada.",
        "",
        "## Modulos",
        "",
        "| Modulo | Repositorio | Presente | Git |",
        "|---|---|---|---|",
    ]

    for module in inventory.get("modules", []):
        local = module.get("local", {})
        name = str(module.get("id", "?")).replace("|", "/").replace("\n", " ")
        repository = str(module.get("repository", "?")).replace(
            "|", "/"
        ).replace("\n", " ")

        exists = "Sim" if local.get("exists") else "Nao"
        git = "Sim" if local.get("git") else "Nao"

        lines.append(
            f"| {name} | {repository} | {exists} | {git} |"
        )

    lines.extend(["", "## Alteracoes detectadas", ""])

    if changes is None:
        lines.append("Relatorio de alteracoes indisponivel.")
    else:
        count = changes.get("change_count", 0)
        lines.append(f"Alteracoes na ultima comparacao: {count}.")
        for change in changes.get("changes", []):
            module_id = str(change.get("module", "?"))
            field = str(change.get("field", "?"))
            lines.append(f"- {module_id}: alteracao em {field}.")

    lines.extend(["", "## Historico", ""])

    history = Path(history_path)
    if history.is_file():
        with history.open(encoding="utf-8-sig") as file:
            count = sum(1 for line in file if line.strip())
        lines.append(f"Registros historicos: {count}.")
    else:
        lines.append("Historico indisponivel.")

    lines.extend([
        "",
        "## Governanca",
        "",
        "- Checkpoint de tarefas: nao localizado na auditoria.",
        "- M02.1: inventario integrado e publicado.",
        "- M02.2: historico e deteccao de mudancas publicados.",
        "- M03: memoria portatil em desenvolvimento.",
        "",
        "## Proxima acao",
        "",
        "Validar o resumo e preparar sincronizacao controlada "
        "com o repositorio privado Conexo OS.",
        "",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inventory",
        default="local-state/modules-latest.json",
    )
    parser.add_argument(
        "--changes",
        default="local-state/modules-changes.json",
    )
    parser.add_argument(
        "--history",
        default="local-state/modules-history.jsonl",
    )
    parser.add_argument(
        "--output",
        default="local-state/CONEXO_STATUS.md",
    )

    args = parser.parse_args()

    text = generate_status(
        read_json(args.inventory),
        read_json(args.changes),
        args.history,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")

    print(f"Status generated: {output}")


if __name__ == "__main__":
    main()
