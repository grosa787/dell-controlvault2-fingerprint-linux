"""Exercise legacy upgrades/removal in temporary directories, without device access."""
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STOCK = os.environ.get("CV2_STOCK_DRIVER")


@unittest.skipUnless(STOCK, "set CV2_STOCK_DRIVER to the pinned stock library")
class DriverLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("install.sh", "uninstall.sh", "patch_driver.py"):
            shutil.copyfile(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "lib", self.root / "lib")
        shutil.copytree(ROOT / "udev", self.root / "udev")
        for name in ("tod", "prebuilt", "firmware", "commands"):
            (self.root / name).mkdir()
        (self.root / "firmware/fixture.bin").write_bytes(b"firmware")
        self.installed = self.root / "tod/libfprint-2-tod-1-broadcom.so"
        self.backup = self.root / "backup/libfprint-2-tod-1-broadcom.so"
        self.stock = Path(STOCK).read_bytes()
        definitions = runpy.run_path(str(ROOT / "patch_driver.py"))
        # Recreate v1.1.0: patches 1–3 are shared; the old patches 4–5 differ.
        data = self.stock
        for _, find, replacement in definitions["PATCHES"][:3]:
            data = data.replace(find, replacement)
        self.partial = data
        data = data.replace(bytes.fromhex("4181fda40000000f84fd010000"),
                            bytes.fromhex("4181fd590000000f8416000000"))
        self.legacy = data.replace(bytes.fromhex("85d20f858a00000083f801"),
                                   bytes.fromhex("85d290909090909083f801"))
        output = self.root / "prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"
        subprocess.run([sys.executable, str(ROOT / "patch_driver.py"), STOCK, str(output)],
                       check=True, capture_output=True)
        self.current = output.read_bytes()

        # Confine every system destination and device probe to the fixture.
        with (self.root / "lib/common.sh").open("a") as f:
            f.write('''
SUDO=""
TOD_DIR_CANDIDATES=("$CV2_TEST_ROOT/tod")
FW_DIR="$CV2_TEST_ROOT/installed-firmware"
BACKUP_DIR="$CV2_TEST_ROOT/backup"
UDEV_DIR="$CV2_TEST_ROOT/rules"
LEGACY_UDEV_DIR="$CV2_TEST_ROOT/legacy-rules"
find_libfprint_libs() { echo "$CV2_TEST_ROOT/libfprint.so"; }
libfprint_has_tod() { return 0; }
detect_tod_dir() { echo "$CV2_TEST_ROOT/tod"; }
find_cv2_usb() { echo "$CV2_TEST_ROOT/usb"; }
''')
        for name in ("udevadm", "systemctl", "ldd", "restorecon"):
            stub = self.root / "commands" / name
            stub.write_text('#!/bin/sh\nexit 0\n')
            stub.chmod(0o755)
        self.env = {**os.environ, "CV2_TEST_ROOT": str(self.root),
                    "PATH": str(self.root / "commands") + os.pathsep + os.environ["PATH"]}

    def run_script(self, name):
        result = subprocess.run(["bash", str(self.root / name)], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_check_allows_only_known_legacy_and_current_builds_for_removal(self):
        for name, data, strict, compatible in (
            ("stock", self.stock, 1, 1),
            ("legacy", self.legacy, 1, 0),
            ("current", self.current, 0, 0),
            ("partial", self.partial, 1, 1),
            ("unknown", b"unknown driver", 1, 1),
            ("modified-legacy", self.legacy + b"modified", 1, 1),
            ("modified-current", self.current + b"modified", 1, 1),
        ):
            with self.subTest(build=name):
                self.installed.write_bytes(data)
                for flags, expected in (([], strict), (["--allow-legacy"], compatible)):
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "patch_driver.py"), "--check",
                         *flags, str(self.installed)], capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, expected, result.stderr)
                    if name == "legacy":
                        self.assertIn("legacy", result.stdout.lower())
                self.assertEqual(self.installed.read_bytes(), data)

    def test_uninstall_preserves_stock_unknown_partial_and_modified_builds(self):
        for data in (self.stock, b"unknown", self.partial,
                     self.legacy + b"modified", self.current + b"modified"):
            with self.subTest(digest=data[-8:]):
                self.installed.write_bytes(data)
                self.run_script("uninstall.sh")
                self.assertEqual(self.installed.read_bytes(), data)

    def test_uninstall_removes_legacy_and_current_builds(self):
        for name, data in (("legacy", self.legacy), ("current", self.current)):
            with self.subTest(build=name):
                self.installed.write_bytes(data)
                self.run_script("uninstall.sh")
                self.assertFalse(self.installed.exists())

    def test_uninstall_restores_stock_backup_for_legacy_and_current_builds(self):
        for name, data in (("legacy", self.legacy), ("current", self.current)):
            with self.subTest(build=name):
                self.installed.write_bytes(data)
                self.backup.parent.mkdir(exist_ok=True)
                self.backup.write_bytes(self.stock)
                (self.backup.parent / "original-path").write_text(str(self.installed) + "\n")
                self.run_script("uninstall.sh")
                self.assertEqual(self.installed.read_bytes(), self.stock)
                self.assertFalse(self.backup.exists())

    def test_upgrade_does_not_back_up_legacy_as_stock(self):
        self.installed.write_bytes(self.legacy)
        self.run_script("install.sh")
        self.assertEqual(self.installed.read_bytes(), self.current)
        self.assertFalse(self.backup.exists())
        self.run_script("uninstall.sh")
        self.assertFalse(self.installed.exists())

    def test_install_rejects_legacy_build_before_overwriting_stock(self):
        self.installed.write_bytes(self.stock)
        output = self.root / "prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"
        output.write_bytes(self.legacy)
        result = subprocess.run(["bash", str(self.root / "install.sh")], env=self.env,
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a fully patched driver", result.stderr)
        self.assertEqual(self.installed.read_bytes(), self.stock)
        self.assertFalse(self.backup.exists())

    def test_upgrade_preserves_existing_stock_backup(self):
        self.installed.write_bytes(self.legacy)
        self.backup.parent.mkdir()
        self.backup.write_bytes(self.stock)
        (self.backup.parent / "original-path").write_text(str(self.installed) + "\n")
        self.run_script("install.sh")
        self.assertEqual(self.installed.read_bytes(), self.current)
        self.assertEqual(self.backup.read_bytes(), self.stock)
        self.run_script("uninstall.sh")
        self.assertEqual(self.installed.read_bytes(), self.stock)

    def test_fresh_install_preserves_stock_backup_and_restores_it(self):
        self.installed.write_bytes(self.stock)
        self.run_script("install.sh")
        self.assertEqual(self.installed.read_bytes(), self.current)
        self.assertEqual(self.backup.read_bytes(), self.stock)
        self.run_script("uninstall.sh")
        self.assertEqual(self.installed.read_bytes(), self.stock)


if __name__ == "__main__":
    unittest.main()
