"""Exercise build-script filesystem behavior without network or vendor binaries."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildTests(unittest.TestCase):
    def run_build(self, root, failure=""):
        shutil.copyfile(ROOT / "build_from_upstream.sh", root / "build_from_upstream.sh")
        commands = root / "commands"
        commands.mkdir()
        work = root / "work"
        work.mkdir()
        git = commands / "git"
        git.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
import sys
args = sys.argv[1:]
if args[0] == "init":
    Path(args[-1]).mkdir()
elif args[2] == "fetch" and os.environ["BUILD_TEST_FAILURE"] == "fetch":
    sys.exit(37)
elif args[2] == "checkout":
    root = Path(args[1])
    stock = root / "usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so"
    stock.parent.mkdir(parents=True)
    stock.write_bytes(b"stock fixture")
    if os.environ["BUILD_TEST_FAILURE"] != "missing-firmware":
        firmware = root / "var/lib/fprint/fw"
        firmware.mkdir(parents=True)
        (firmware / "blob.bin").write_bytes(b"new firmware")
''')
        git.chmod(0o755)
        (root / "patch_driver.py").write_text('''import os
from pathlib import Path
import sys
if os.environ["BUILD_TEST_FAILURE"] == "patch":
    sys.exit(38)
Path(sys.argv[2]).write_bytes(b"patched fixture")
''')
        firmware = root / "firmware"
        firmware.mkdir()
        if failure == "copy":
            (firmware / "blob.bin").mkdir()  # A real cp error, even when run as root.
        else:
            (firmware / "blob.bin").write_bytes(b"stale firmware")
        (firmware / "NOTICE.txt").write_text("keep notice")
        return subprocess.run(
            ["bash", str(root / "build_from_upstream.sh")], capture_output=True, text=True,
            env={**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                 "TMPDIR": str(work), "BUILD_TEST_FAILURE": failure},
        )

    def test_refreshes_firmware_and_cleans_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_build(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "firmware/blob.bin").read_bytes(), b"new firmware")
            self.assertEqual((root / "firmware/NOTICE.txt").read_text(), "keep notice")
            self.assertEqual(list((root / "work").iterdir()), [])

    def test_failures_are_reported_and_workspace_is_cleaned(self):
        for failure in ("fetch", "patch", "copy", "missing-firmware"):
            with self.subTest(stage=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result = self.run_build(root, failure)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("[*] Done.", result.stdout)
                self.assertEqual(list((root / "work").iterdir()), [])
                if failure in ("copy", "missing-firmware"):
                    self.assertTrue(result.stderr, "copy errors must remain visible")


if __name__ == "__main__":
    unittest.main()
