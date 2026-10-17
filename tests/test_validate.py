import json
import tempfile
import unittest
from pathlib import Path
from scripts.validate import validate


class ValidationTests(unittest.TestCase):
    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'sample.json').write_text(json.dumps({'ok': True}), encoding='utf-8')
            self.assertEqual(validate(Path(directory)), 1)

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'broken.json').write_text('{', encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError):
                validate(Path(directory))


if __name__ == '__main__':
    unittest.main()
