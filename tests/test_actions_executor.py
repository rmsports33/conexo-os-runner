import json
import unittest

from scripts.actions_executor import execute_synthetic

SHA = "a" * 40


class ActionsExecutorTests(unittest.TestCase):
    def call(self, payload, **overrides):
        args = {
            "task_id": "synthetic-001",
            "contract_sha": SHA,
            "payload_json": json.dumps(payload),
            "repository": "rmsports33/conexo-os",
            "execution_sha": "b" * 40,
            "run_id": "12345",
            "run_attempt": "1",
        }
        args.update(overrides)
        return execute_synthetic(**args)

    def test_echo_returns_review_receipt_not_verified(self):
        receipt = self.call({"type": "echo", "value": "ok"})
        self.assertEqual(receipt["status"], "REVIEW")
        self.assertEqual(receipt["result"], {"echo": "ok"})
        self.assertFalse(receipt["authorization_verified"])
        self.assertFalse(receipt["contract_verified"])
        self.assertFalse(receipt["execution_identity_independently_verified"])
        self.assertEqual(receipt["executor"], "github-actions")
        self.assertEqual(len(receipt["result_sha256"]), 64)

    def test_count_is_supported(self):
        receipt = self.call({"type": "count", "items": [1, 2, 3]})
        self.assertEqual(receipt["status"], "REVIEW")
        self.assertEqual(receipt["result"], {"count": 3})

    def test_shell_or_unknown_task_is_blocked(self):
        receipt = self.call({"type": "execute_shell", "command": "echo unsafe"})
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(any(x.startswith("payload_rejected:") for x in receipt["errors"]))
        self.assertIsNone(receipt["result"])

    def test_malformed_contract_sha_is_blocked(self):
        receipt = self.call({"type": "echo", "value": "ok"}, contract_sha="main")
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("contract_sha_invalid", receipt["errors"])

    def test_payload_must_be_object(self):
        receipt = self.call(["not", "an", "object"])
        self.assertEqual(receipt["status"], "BLOCKED")

    def test_payload_size_is_bounded(self):
        receipt = self.call({"type": "echo", "value": "x"}, payload_json=' ' * 16385)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("payload_size_invalid", receipt["errors"])


if __name__ == "__main__":
    unittest.main()
