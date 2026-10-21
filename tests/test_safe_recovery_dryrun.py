"""Testes do dry-run de scripts/safe_recovery (M04.17B).

Objetivo: garantir que o modo dry-run NUNCA altera os ficheiros SQLite
(DB/WAL/SHM), mesmo quando a tabela task_leases ainda nao existe, e que o
modo --apply mantem o comportamento de recuperacao.

Todos os bancos usados sao sinteticos e descartaveis (tempfile).
"""
import hashlib
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.continuity import SCHEMA, connect, enqueue
from scripts.ownership import acquire, prepare
from scripts.safe_recovery import recover_safe

STALE = datetime.now(timezone.utc) - timedelta(hours=6)


def sha256(path):
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot(db):
    """Estado de DB/WAL/SHM: existencia, tamanho e hash."""
    state = {}
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db) + suffix)
        state[suffix or ".db"] = {
            "exists": p.exists(),
            "bytes": p.stat().st_size if p.exists() else 0,
            "sha256": sha256(p),
        }
    return state


class SafeRecoveryDryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "queue.sqlite3"
        self.clock = datetime.now(timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    # ---------- helpers ----------

    def _seed(self, *, with_leases=True, wal=False):
        """Cria banco sintetico com tarefas nos tres estados de recuperacao."""
        with closing(connect(self.db)) as conn:
            with conn:
                if wal:
                    conn.execute("PRAGMA journal_mode=WAL")
                if with_leases:
                    prepare(conn)
                else:
                    conn.execute("DROP TABLE IF EXISTS task_leases")
            conn.commit()

        enqueue(self.db, "T-RETRY", {"type": "echo", "value": "alfa"})
        enqueue(self.db, "T-EXHAUST", {"type": "count", "items": [1, 2, 3]})
        enqueue(self.db, "T-SKIP", {"type": "shell", "cmd": "echo pwn"})

        with closing(connect(self.db)) as conn:
            with conn:
                for tid, attempts in (("T-RETRY", 1), ("T-EXHAUST", 3), ("T-SKIP", 1)):
                    conn.execute(
                        "UPDATE tasks SET status='running', updated_at=?, attempts=? WHERE id=?",
                        (STALE.isoformat(), attempts, tid),
                    )
            conn.commit()

        if with_leases:
            # leases reais, com heartbeat antigo
            for tid in ("T-RETRY", "T-EXHAUST", "T-SKIP"):
                acquire(self.db, "test-owner")
            with closing(connect(self.db)) as conn:
                with conn:
                    for tid in ("T-RETRY", "T-EXHAUST", "T-SKIP"):
                        conn.execute("UPDATE tasks SET updated_at=?, attempts=? WHERE id=?",
                                     (STALE.isoformat(),
                                      3 if tid == "T-EXHAUST" else 1, tid))
                        conn.execute("UPDATE task_leases SET heartbeat_at=? WHERE task_id=?",
                                     (STALE.isoformat(), tid))
                conn.commit()
        else:
            with closing(connect(self.db)) as conn:
                with conn:
                    conn.execute("DROP TABLE IF EXISTS task_leases")
                conn.commit()

    # ---------- POSITIVOS: o dry-run classifica tarefas ----------

    def test_dry_run_classifica_tarefas_elegiveis(self):
        self._seed(with_leases=True)
        result = recover_safe(self.db, clock=self.clock)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["retry"], ["T-RETRY"])
        self.assertEqual(result["exhausted"], ["T-EXHAUST"])
        self.assertEqual(result["skipped"], ["T-SKIP"])

    def test_dry_run_classifica_sem_tabela_leases(self):
        self._seed(with_leases=False)
        result = recover_safe(self.db, clock=self.clock)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["retry"], ["T-RETRY"])
        self.assertEqual(result["exhausted"], ["T-EXHAUST"])
        self.assertEqual(result["skipped"], ["T-SKIP"])

    # ---------- NEGATIVOS: o dry-run NAO escreve ----------

    def test_dry_run_nao_altera_ficheiros_com_leases(self):
        self._seed(with_leases=True)
        before = snapshot(self.db)
        recover_safe(self.db, clock=self.clock)
        self.assertEqual(before, snapshot(self.db),
                         "dry-run alterou DB/WAL/SHM apesar de task_leases existir")

    def test_dry_run_nao_altera_ficheiros_sem_leases(self):
        """Regressao do defeito M04.16A: prepare(conn) criava a tabela em dry-run."""
        self._seed(with_leases=False)
        before = snapshot(self.db)
        recover_safe(self.db, clock=self.clock)
        after = snapshot(self.db)
        self.assertEqual(before, after,
                         "dry-run alterou DB/WAL/SHM ao criar task_leases")
        self.assertTrue(after[".db"]["exists"])
        with closing(sqlite3.connect(self.db)) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        self.assertEqual(tables, ["tasks"],
                         "dry-run criou schema no ficheiro do banco")

    def test_dry_run_nao_altera_ficheiros_em_wal(self):
        self._seed(with_leases=True, wal=True)
        before = snapshot(self.db)
        recover_safe(self.db, clock=self.clock)
        after = snapshot(self.db)
        self.assertEqual(before[".db"], after[".db"])
        self.assertEqual(before["-wal"], after["-wal"],
                         "dry-run escreveu no ficheiro -wal")
        self.assertEqual(before["-shm"], after["-shm"],
                         "dry-run escreveu no ficheiro -shm")

    def test_dry_run_nao_altera_dados_das_tarefas(self):
        self._seed(with_leases=True)
        with closing(connect(self.db)) as conn:
            with conn:
                before = conn.execute(
                    "SELECT id,status,attempts FROM tasks ORDER BY id").fetchall()
        recover_safe(self.db, clock=self.clock)
        with closing(connect(self.db)) as conn:
            with conn:
                after = conn.execute(
                    "SELECT id,status,attempts FROM tasks ORDER BY id").fetchall()
        self.assertEqual(before, after)

    # ---------- --apply mantem o comportamento (banco sintetico) ----------

    def test_apply_muda_estados_como_antes(self):
        self._seed(with_leases=True)
        result = recover_safe(self.db, clock=self.clock, apply=True)
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["retry"], ["T-RETRY"])
        self.assertEqual(result["exhausted"], ["T-EXHAUST"])
        with closing(connect(self.db)) as conn:
            with conn:
                estados = dict(conn.execute(
                    "SELECT id,status FROM tasks WHERE id IN ('T-RETRY','T-EXHAUST')"))
        self.assertEqual(estados["T-RETRY"], "pending")
        self.assertEqual(estados["T-EXHAUST"], "failed")

    def test_apply_cria_tabela_leases_se_faltar(self):
        """--apply continua a poder criar schema (comportamento pre-existente)."""
        self._seed(with_leases=False)
        result = recover_safe(self.db, clock=self.clock, apply=True)
        self.assertFalse(result["dry_run"])
        with closing(sqlite3.connect(self.db)) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        self.assertIn("task_leases", tables)


if __name__ == "__main__":
    unittest.main()
