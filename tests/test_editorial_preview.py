"""Real components, synthetic evidence, temporary SQLite; no live queues.

Set CONEXO_PREVIEW_REDACTOR and CONEXO_PREVIEW_MKT for the integration tests.
The --demo entry point only constructs a disposable test, not another worker.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.continuity import connect, enqueue
from scripts.editorial_preview import LABEL, PreviewConfig, preview
from scripts.worker import process_one, perform


def synthetic_job():
    contracts = []
    for i, name in enumerate(("Fone A", "Fone B")):
        primary, market = f"primary-{i}", f"market-{i}"
        contracts.append({
            "contract_version": "1.0", "content_type": "comparativo", "status": "PASS",
            "subject": {"name": name}, "specs_CANDIDATA": {"tela": "6 pol"},
            "sources": [
                {"id": primary, "kind": "primary", "status": "PASS",
                 "approved_by": "SIMULACAO_OFFLINE_REVISOR_FICTICIO",
                 "url": "https://news.samsung.com/br/simulacao-offline",
                 "retrieved_at": "2026-10-24"},
                {"id": market, "kind": "marketplace", "status": "PASS",
                 "approved_by": "SIMULACAO_OFFLINE_REVISOR_FICTICIO",
                 "url": f"https://www.amazon.com.br/dp/SIMULACAO{i}",
                 "retrieved_at": "2026-10-24"}],
            "claims": [
                {"id": f"spec-{i}", "claim_type": "spec", "field": "tela",
                 "subject": name, "value": "6 pol", "status": "PASS",
                 "evidence_ids": [primary]},
                {"id": f"price-{i}", "claim_type": "preco", "field": "preco",
                 "subject": name, "value": 1500 + i * 100, "status": "PASS",
                 "captured_at": "2026-10-24", "evidence_ids": [market]}]})
    return {"type": "editorial_preview", "simulation": LABEL, "contracts": contracts,
            "notas": {"Fone A": 7, "Fone B": 7},
            "criterios": [{"label": "tela", "vals": ["6 pol", "6 pol"], "win": -1}]}


class EditorialPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(os.environ.get(key) for key in ("CONEXO_PREVIEW_REDACTOR", "CONEXO_PREVIEW_MKT")):
            raise unittest.SkipTest("External checkouts not configured; use --redactor and --mkt")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conexo-editorial-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "queue.sqlite3"
        self.config = PreviewConfig(Path(os.environ["CONEXO_PREVIEW_REDACTOR"]),
                                    Path(os.environ["CONEXO_PREVIEW_MKT"]), self.root, True)

    def run_job(self, job):
        enqueue(self.db, "preview-test", job)
        return process_one(self.db, preview_config=self.config)

    def test_worker_to_real_redactor_and_mkt(self):
        # Parent cannot perform HTTP either. Child enforces its own independent guard.
        with patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
            result = self.run_job(synthetic_job())
        self.assertEqual(result["status"], "done", result)
        output = result["result"]
        self.assertEqual(output["acao"], "previa_local", output)
        self.assertEqual(output["mode"], LABEL)
        self.assertFalse(output["publication_allowed"])
        self.assertEqual(output["calls"], {"network": 0, "collection": 0,
                         "external_llm": 0, "wordpress": 0, "fixed_response": 1})
        self.assertEqual(output["redactor"]["provedor"], "injetado")
        self.assertEqual(Path(output["components"]["redactor"]),
                         self.config.redactor / "src" / "generator" / "render.py")
        self.assertEqual(Path(output["components"]["mkt_flow"]),
                         self.config.mkt / "mkt_flow_p0" / "comparativo_flow.py")
        self.assertTrue(output["mkt_structure"]["ok"])
        self.assertTrue(output["mkt_value"]["ok"])
        html = Path(output["artifacts"]["html"]).read_text(encoding="utf-8")
        self.assertIn(LABEL, html)
        self.assertIn("Fone A", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertNotIn("<script", html.lower())
        plan = json.loads(Path(output["artifacts"]["plan"]).read_text(encoding="utf-8"))
        self.assertFalse(plan["execute"])
        self.assertEqual(plan["params"]["products"], ["Fone A", "Fone B"])
        self.assertNotIn("<html", plan["params"]["content"].lower())
        report = json.loads(Path(output["artifacts"]["report"]).read_text(encoding="utf-8"))
        self.assertEqual(report["acao"], "previa_local")
        for file in output["artifacts"].values():
            self.assertTrue(Path(file).is_relative_to(self.root))
        with closing(connect(self.db)) as conn:
            saved = json.loads(conn.execute("SELECT result FROM task_results").fetchone()[0])
        self.assertEqual(saved, output)

    def test_missing_evidence_blocks(self):
        job = synthetic_job()
        job["contracts"][0]["sources"].pop()
        output = self.run_job(job)["result"]
        self.assertEqual(output["acao"], "bloqueado")
        self.assertNotIn("html", output["artifacts"])
        self.assertNotIn("plan", output["artifacts"])
        self.assertEqual(output["calls"]["fixed_response"], 0)

    def test_unauthorized_price_blocks(self):
        job = synthetic_job()
        # Generic contract validator accepts PASS, but the price gate requires
        # source retrieval >= claim capture date. Exercise the real renderer gate.
        job["contracts"][0]["claims"][1]["captured_at"] = "2026-10-25"
        output = self.run_job(job)["result"]
        self.assertEqual(output["reason"], "redator_bloqueou", output)
        self.assertIn("bloqueio_precos", output["redactor"])
        self.assertNotIn("plan", output["artifacts"])

    def test_publication_commands_modules_and_output_rejected(self):
        for field, value in (("publish", True), ("dry_run", False), ("command", "echo"),
                             ("module", "os"), ("output", str(self.root / "escape.html")),
                             ("chamar_llm", "external"), ("test_mode", True)):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    perform({**synthetic_job(), field: value}, preview_config=self.config)
        with self.assertRaises(ValueError):
            perform({**synthetic_job(), "simulation": "publish"}, preview_config=self.config)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_disabled_without_test_configuration(self):
        with self.assertRaises(ValueError):
            perform(synthetic_job())
        with self.assertRaises(ValueError):
            preview(synthetic_job(), PreviewConfig(self.config.redactor, self.config.mkt, self.root))

    def test_paths_validated_outside_payload(self):
        with self.assertRaises(ValueError):
            preview(synthetic_job(), PreviewConfig(self.root, self.config.mkt, self.root, True))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unapproved_specs_and_unattested_criteria_block(self):
        job = synthetic_job()
        job["contracts"][0]["claims"][0]["status"] = "UNKNOWN"
        self.assertEqual(preview(job, self.config)["acao"], "bloqueado")
        job = synthetic_job()
        job["criterios"][0]["vals"][0] = "99 pol"
        self.assertEqual(preview(job, self.config)["reason"], "criterio_sem_spec_aprovada")

    def test_no_credentials_or_publication_flags_reach_child(self):
        import subprocess
        original = subprocess.run
        seen = []
        def checked(*args, **kwargs):
            seen.append(kwargs["env"])
            return original(*args, **kwargs)
        with patch.dict(os.environ, {"WP_APP_PASSWORD": "TEST_ONLY", "GROQ_API_KEY": "TEST_ONLY",
                                     "COMPARATIVO_PUBLICACAO_ENABLED": "true"}):
            with patch("scripts.editorial_preview.subprocess.run", side_effect=checked):
                output = preview(synthetic_job(), self.config)
        self.assertEqual(output["acao"], "previa_local", output)
        self.assertNotIn("WP_APP_PASSWORD", seen[0])
        self.assertNotIn("GROQ_API_KEY", seen[0])
        self.assertFalse(output["flow"]["publicacao_ativa"])

    def test_guards_reject_actual_capability_attempts_in_child(self):
        import subprocess
        import scripts.editorial_preview as adapter
        config = self.config.validated()
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", adapter.__file__, "--probe-guards"],
            input=json.dumps({"redactor": str(config.redactor), "mkt": str(config.mkt)}),
            text=True, encoding="utf-8", capture_output=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}},
            cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        probes = json.loads(result.stdout)
        self.assertEqual(probes["probe_blocked"], {"collection": True, "external_llm": True,
                                                  "wordpress": True, "http": True, "socket": True})
        self.assertEqual(probes["calls"]["network"], 2)
        self.assertEqual(probes["calls"]["fixed_response"], 0)


def demo():
    parser = argparse.ArgumentParser(description="Disposable editorial simulation via existing worker")
    parser.add_argument("--demo", action="store_true", required=True)
    parser.add_argument("--redactor", type=Path, required=True)
    parser.add_argument("--mkt", type=Path, required=True)
    args = parser.parse_args()
    # Deliberately retain only this new temporary demo directory for human review.
    with tempfile.TemporaryDirectory(prefix="conexo-editorial-demo-", delete=False) as temp:
        root = Path(temp)
        config = PreviewConfig(args.redactor, args.mkt, root, True)
        enqueue(root / "demo.sqlite3", "simulation", synthetic_job())
        result = process_one(root / "demo.sqlite3", preview_config=config)
        print(json.dumps({"temporary_demo": temp, **result}, ensure_ascii=False, indent=2))
        if result.get("result", {}).get("acao") != "previa_local":
            raise SystemExit(1)


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--redactor")
        parser.add_argument("--mkt")
        args, remaining = parser.parse_known_args()
        if args.redactor:
            os.environ["CONEXO_PREVIEW_REDACTOR"] = args.redactor
        if args.mkt:
            os.environ["CONEXO_PREVIEW_MKT"] = args.mkt
        unittest.main(argv=[sys.argv[0], *remaining])
