"""Binary regression checks using a locally built, untracked driver."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STOCK_HASH = "54fa3befc02df393077cebf96e018e3bf752cee61509897d945ab18c58c5e172"
PATCHED_HASH = "62868df275e49a7a345ebd9245d651e141a750fee1bfa6d9a8b1b627b1678278"


class PatchDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("CV2_STOCK_DRIVER")
        if not source:
            raise unittest.SkipTest("set CV2_STOCK_DRIVER to the pinned stock library")
        cls.stock = Path(source)
        if hashlib.sha256(cls.stock.read_bytes()).hexdigest() != STOCK_HASH:
            raise AssertionError("CV2_STOCK_DRIVER is not the pinned stock library")

    def run_patcher(self, source, output):
        return subprocess.run(
            [sys.executable, str(ROOT / "patch_driver.py"), str(source), str(output)],
            capture_output=True, text=True,
        )

    def test_patches_exact_stock_binary_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "patched.so"
            result = self.run_patcher(self.stock, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), PATCHED_HASH)
            result = self.run_patcher(output, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), PATCHED_HASH)
            result = subprocess.run(
                [sys.executable, str(ROOT / "patch_driver.py"), "--check", str(output)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("All 9 CV2 patches are applied", result.stdout)

    def test_rejects_changed_binary_without_overwriting_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "changed.so"
            output = Path(directory) / "output.so"
            data = bytearray(self.stock.read_bytes())
            data[-1] ^= 1  # Patch signatures remain present; full hash must catch this.
            source.write_bytes(data)
            output.write_bytes(b"existing build")
            result = self.run_patcher(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SHA-256 mismatch", result.stderr)
            self.assertEqual(output.read_bytes(), b"existing build")


if __name__ == "__main__":
    unittest.main()
