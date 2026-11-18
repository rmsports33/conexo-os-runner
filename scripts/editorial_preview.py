"""Test-only editorial bridge. Component paths are operator configuration, never jobs.

The isolated child imports only the updated redactor and the existing MKT gates.
No production mode is implemented. This is not a sandbox for untrusted Python.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

LABEL = "SIMULACAO_OFFLINE"
FIELDS = {"type", "simulation", "contracts", "notas", "criterios"}


@dataclass(frozen=True)
class PreviewConfig:
    redactor: Path
    mkt: Path
    temporary_root: Path
    test_mode: bool = False

    def validated(self):
        if self.test_mode is not True:
            raise ValueError("Editorial preview requires explicit test_mode")
        redactor, mkt, output = (Path(p).resolve(strict=True) for p in
                                 (self.redactor, self.mkt, self.temporary_root))
        required = ((redactor, "src/generator/render.py"),
                    (redactor, "src/editorial/prices.py"),
                    (redactor, "src/editorial/validation.py"),
                    (mkt, "mkt_flow_p0/comparativo_flow.py"),
                    (mkt, "mkt_flow_p0/comparativo_contract.py"))
        if redactor == mkt or not output.is_dir():
            raise ValueError("Invalid preview configuration")
        if not output.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise ValueError("Preview output must be in an operator-owned temporary directory")
        for root, relative in required:
            file = (root / relative).resolve(strict=True)
            if not file.is_file() or not file.is_relative_to(root):
                raise ValueError("Invalid component path")
        return PreviewConfig(redactor, mkt, output, True)


def check_payload(payload):
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValueError("editorial_preview accepts only type, simulation, contracts, notas, criterios")
    if payload["type"] != "editorial_preview" or payload["simulation"] != LABEL:
        raise ValueError("Only SIMULACAO_OFFLINE is supported; publication is forbidden")
    if not isinstance(payload["contracts"], list) or not 2 <= len(payload["contracts"]) <= 3:
        raise ValueError("Preview needs two or three product contracts")
    if len(json.dumps(payload)) > 100_000:
        raise ValueError("Preview payload too large")


def preview(payload, config=None):
    check_payload(payload)
    if config is None:
        raise ValueError("Editorial preview is disabled without operator test configuration")
    try:
        config = config.validated()
        # -I excludes cwd/PYTHONPATH/user site; -B prevents component pycache writes.
        # No environment credentials or publication flags are passed to the child.
        env = {k: v for k, v in os.environ.items()
               if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        proc = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()), "--child"],
            input=json.dumps({"redactor": str(config.redactor), "mkt": str(config.mkt),
                              "payload": payload}), text=True, encoding="utf-8",
            capture_output=True, timeout=30, env=env, cwd=config.temporary_root,
        )
        if proc.returncode:
            raise ValueError("Isolated preview failed closed: " + proc.stderr[-1500:])
        result = json.loads(proc.stdout)
        directory = Path(tempfile.mkdtemp(prefix="editorial-preview-", dir=config.temporary_root))
        html = result.pop("html", None)
        plan = result.pop("plan", None)
        artifacts = {"report": str(directory / "validation.json")}
        if html is not None:
            (directory / "preview.html").write_text(html, encoding="utf-8")
            artifacts["html"] = str(directory / "preview.html")
        if plan is not None:
            (directory / "delivery-plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            artifacts["plan"] = str(directory / "delivery-plan.json")
        (directory / "validation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**result, "artifacts": artifacts}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ValueError("Offline preview failed closed") from exc


def _child(request, *, probe=False):
    from contextlib import ExitStack
    from unittest.mock import patch
    from types import ModuleType

    calls = {"network": 0, "collection": 0, "external_llm": 0, "wordpress": 0,
             "fixed_response": 0}

    def deny(kind):
        def blocked(*args, **kwargs):
            calls[kind] += 1
            raise RuntimeError("Offline capability forbidden: " + kind)
        return blocked

    def audit(event, args):
        # urllib3 probes local IPv6 support at import by constructing a socket;
        # creation alone is not I/O. DNS, bind, connect and send remain forbidden.
        if event.startswith("socket.") and event != "socket.__new__":
            deny("network")()
        if event in {"subprocess.Popen", "os.system", "os.spawn", "os.exec"}:
            deny("network")()

    sys.addaudithook(audit)
    # Publisher imports requests even in dry-run. Replace the capability module
    # before that import, rather than initializing a real HTTP stack (which can
    # probe IPv6 with a local bind during import). No external dependency needed.
    http = ModuleType("requests")
    for attr in ("get", "post", "put", "delete", "request"):
        setattr(http, attr, deny("network"))
    class OfflineSession:
        request = staticmethod(deny("network"))
    from types import SimpleNamespace
    http.sessions = SimpleNamespace(Session=OfflineSession)
    http.Session = OfflineSession
    sys.modules["requests"] = http
    # Prevent imports of capability modules (also avoids dotenv loading).
    for name, attrs, kind in (
        ("src.evergreen", ["gerar_texto"], "external_llm"),
        ("src.collectors.ponte_redator", ["buscar_specs", "modelos_para_redator"], "collection"),
        ("mkt_flow_p0.rss_ingestor", ["fetch_feed", "buscar_novidades"], "collection"),
        ("mkt_flow_p0.extractor", ["extrair_conteudo"], "collection"),
        ("mkt_flow_p0.price_collector", ["gerar_price_history_para_modelos"], "collection"),
    ):
        module = ModuleType(name)
        for attr in attrs:
            setattr(module, attr, deny(kind))
        sys.modules[name] = module
    sys.path[:0] = [request["redactor"], request["mkt"]]
    from src.editorial.contract import contract_from_dict, EditorialContract
    from src.editorial.validation import validate_contract
    from src.generator import render
    from mkt_flow_p0 import comparativo_contract as C, comparativo_flow as F, wp_publisher as W
    for module, root in ((render, request["redactor"]), (C, request["mkt"]), (F, request["mkt"])):
        if not Path(module.__file__).resolve().is_relative_to(Path(root).resolve()):
            raise ValueError("Component origin mismatch")
    with ExitStack() as stack:
        import requests
        stack.enter_context(patch.object(requests.sessions.Session, "request", deny("network")))
        for name in ("publicar_comparativo", "executar_ferramenta_mcp", "publicar_no_wordpress"):
            stack.enter_context(patch.object(W, name, deny("wordpress")))
        if probe:
            import socket
            probes = {
                "collection": sys.modules["mkt_flow_p0.rss_ingestor"].fetch_feed,
                "external_llm": sys.modules["src.evergreen"].gerar_texto,
                "wordpress": W.publicar_comparativo,
                "http": lambda: requests.get("https://offline.invalid"),
                "socket": lambda: socket.create_connection(("127.0.0.1", 9)),
            }
            blocked = {}
            for key, function in probes.items():
                try:
                    function()
                except RuntimeError:
                    blocked[key] = True
                else:
                    blocked[key] = False
            return {"probe_blocked": blocked, "calls": calls}
        result = _convert(request["payload"], calls, contract_from_dict,
                          EditorialContract, validate_contract, render, C, F)
        result["components"] = {"redactor": str(Path(render.__file__).resolve()),
                                "mkt_flow": str(Path(F.__file__).resolve())}
        if any(calls[k] for k in ("network", "collection", "external_llm", "wordpress")):
            result.pop("html", None)
            result.pop("plan", None)
            result.update(acao="bloqueado", reason="capacidade_offline_violada")
        return result


def _convert(payload, calls, contract_from_dict, EditorialContract, validate_contract, render, C, F):
    check_payload(payload)
    report = {"mode": LABEL, "publication_allowed": False, "escreveu_remoto": False,
              "acao": "bloqueado", "validation": [], "calls": calls}

    def blocked(reason):
        report["reason"] = reason
        return report

    contracts = [contract_from_dict(raw) for raw in payload["contracts"]]
    models, history, sources, claims = [], {}, [], []
    ids, names = set(), set()
    for contract in contracts:
        validation = validate_contract(contract)
        report["validation"].append(validation.to_dict())
        name = contract.subject.get("name") or contract.subject.get("modelo")
        if (not isinstance(name, str) or not name.strip() or name in names
                or contract.content_type != "comparativo" or contract.status != "PASS"
                or not validation.publicable or not validation.data["specs_PASS"]):
            return blocked("contrato_editorial_nao_aprovado")
        names.add(name)
        for prefix, items in (("source", contract.sources), ("claim", contract.claims)):
            for item in items:
                key = (prefix, item.id)
                if key in ids:
                    return blocked("identificador_duplicado")
                ids.add(key)
        if any(c.subject != name for c in contract.claims):
            return blocked("claim_de_outro_produto")
        source_map = {s.id: s for s in contract.sources}
        spec_sources = [source_map[e] for c in contract.claims
                        if c.field in validation.data["specs_PASS"] for e in c.evidence_ids]
        primary = [s for s in spec_sources if s.kind == "primary"]
        if not primary:
            return blocked("fonte_primaria_ausente")
        # Explicit mapping: revalidated specs_PASS -> MKT ficha/specs. No candidates.
        approved = dict(validation.data["specs_PASS"])
        models.append({"nome": name, "specs": approved, "specs_PASS": approved,
                       "fonte": primary[0].url})
        prices = [c for c in contract.claims if c.claim_type in {"preco", "price"}
                  and c.field in {"preco", "price"}]
        if len(prices) != 1:
            return blocked("preco_obrigatorio_ausente_ou_ambiguo")
        price = prices[0]
        markets = [source_map[e] for e in price.evidence_ids
                   if source_map[e].kind == "marketplace"]
        if len(markets) != 1:
            return blocked("marketplace_ausente_ou_ambiguo")
        # PASS is not invented here. Renderer rechecks value/product/capture date.
        history[name] = [{"preco": price.value, "data": price.captured_at,
                          "fonte": markets[0].url, "produto": name}]
        sources.extend(contract.sources)
        claims.extend(contract.claims)
    combined = EditorialContract(content_type="comparativo", status="PASS",
                                 sources=sources, claims=claims)
    # Strict spec validation receives per-product contracts; the price gate needs
    # one combined envelope. Revalidated global IDs preserve every evidence link.
    # Both validators accept the combined envelope with no candidate spec merge.
    combined_check = validate_contract(combined)
    if not combined_check.publicable:
        return blocked("contrato_combinado_invalido")
    if (not isinstance(payload["notas"], dict) or set(payload["notas"]) != names
            or not isinstance(payload["criterios"], list)):
        return blocked("metadados_invalidos")
    # Table values must be existing approved specs, never new comparison claims.
    for criterion in payload["criterios"]:
        if not isinstance(criterion, dict) or set(criterion) != {"label", "vals", "win"}:
            return blocked("criterio_invalido")
        vals = criterion["vals"]
        if (not isinstance(vals, list) or len(vals) != len(models)
                or any(value != model["specs"].get(criterion["label"])
                       for value, model in zip(vals, models))):
            return blocked("criterio_sem_spec_aprovada")
        if criterion["win"] != -1:
            return blocked("vencedor_nao_atestado")

    def fixed_response(system, user):
        calls["fixed_response"] += 1
        return "## SIMULACAO_OFFLINE\n\nPrevia de teste com fichas sinteticas. Revisao humana obrigatoria."

    generated = render.gerar_comparativo(
        models, categoria="celular", price_history=history, chamar_llm=fixed_response,
        contrato_editorial=combined, modo_estrito=True, forcar=False)
    report["redactor"] = {k: v for k, v in generated.items() if k != "html"}
    if generated.get("erro"):
        return blocked("redator_bloqueou")
    # Keep original history: renderer deliberately strips marketplace metadata
    # internally. Reconstructing it from returned HTML would destroy provenance.
    kwargs = dict(modelos=models, price_history=history,
                  conteudo_html=generated["html"], titulo=generated["titulo"],
                  categoria="celular", notas=payload["notas"], criterios=payload["criterios"])
    flow = F.processar_comparativo(**kwargs, dry_run=True)
    report["flow"] = flow
    contract = C.construir_contrato(**kwargs)
    report["mkt_structure"] = C.validar_contrato(contract)
    report["mkt_value"] = C.avaliar_contrato(contract)
    if flow.get("acao") != "dry_run_ok":
        return blocked("gate_mkt_bloqueou")
    params = C.contrato_para_mcp(contract)
    # A standalone review page must not load Chart.js, ads, thumbnails or embeds.
    # CSP also applies when the reviewer opens the generated file in a browser.
    body = C.extrair_corpo_html(generated["html"])
    report["html"] = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
                      '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
                      'style-src \'unsafe-inline\'; form-action \'none\'; base-uri \'none\'">'
                      '<title>SIMULACAO_OFFLINE</title></head><body>'
                      '<p><strong>SIMULACAO_OFFLINE — dados sinteticos; nao publicar.</strong></p>'
                      + body + '</body></html>')
    report["plan"] = {"mode": LABEL, "execute": False, "publication_allowed": False,
                      "tool": "create_comparativo", "hypothetical_status": "draft",
                      "params": params, "requires_human_review": True}
    report["acao"] = "previa_local"
    return report


if __name__ == "__main__":
    if sys.argv[1:] not in (["--child"], ["--probe-guards"]):
        raise SystemExit("Internal isolated adapter; use the existing worker")
    try:
        print(json.dumps(_child(json.load(sys.stdin), probe=sys.argv[1] == "--probe-guards"), ensure_ascii=False))
    except Exception as exc:
        raise SystemExit(f"{type(exc).__name__}: {exc}")
