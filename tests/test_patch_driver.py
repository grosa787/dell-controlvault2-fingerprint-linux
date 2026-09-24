"""Optional integration tests use a locally obtained proprietary stock binary."""
import hashlib
import os
import runpy
import shutil
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
STOCK = os.environ.get("CV2_STOCK_DRIVER")
EXPECTED = "62868df275e49a7a345ebd9245d651e141a750fee1bfa6d9a8b1b627b1678278"


class PatchTests(unittest.TestCase):
    def run_patch(self, source, destination):
        return subprocess.run(
            [sys.executable, str(ROOT / "patch_driver.py"), str(source), str(destination)],
            capture_output=True, text=True,
        )

    def test_invalid_input_preserves_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "in.so", Path(directory) / "out.so"
            source.write_bytes(b"not an ELF driver")
            output.write_bytes(b"keep previous build")
            result = self.run_patch(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), b"keep previous build")

    def test_atomic_write_replaces_output_without_modifying_previous_inode(self):
        write_atomic = runpy.run_path(str(ROOT / "patch_driver.py"))["write_atomic"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, previous = root / "out.so", root / "previous.so"
            output.write_bytes(b"old driver")
            os.link(output, previous)
            write_atomic(output, b"new driver")
            self.assertEqual(output.read_bytes(), b"new driver")
            self.assertEqual(previous.read_bytes(), b"old driver")
            self.assertEqual(set(root.iterdir()), {output, previous})

    def test_atomic_write_failure_preserves_output_and_removes_temporary_file(self):
        write_atomic = runpy.run_path(str(ROOT / "patch_driver.py"))["write_atomic"]
        original_temporary_file = tempfile.NamedTemporaryFile
        for failure in ("write", "replace"):
            with self.subTest(stage=failure), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "out.so"
                output.write_bytes(b"keep previous build")

                def temporary_file(*args, **kwargs):
                    stream = original_temporary_file(*args, **kwargs)
                    if failure == "write":
                        original_write = stream.write

                        def partial_write(data):
                            original_write(data[:2])
                            raise OSError("simulated write failure")

                        stream.write = partial_write
                    return stream

                with mock.patch.object(tempfile, "NamedTemporaryFile", side_effect=temporary_file), \
                     mock.patch.object(os, "replace", side_effect=OSError("simulated replace failure")):
                    with self.assertRaises(OSError):
                        write_atomic(output, b"new driver")
                self.assertEqual(output.read_bytes(), b"keep previous build")
                self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_package_rejects_stale_cached_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("build_deb.sh", "patch_driver.py"):
                shutil.copyfile(ROOT / name, root / name)
            for name in ("prebuilt", "firmware", "udev"):
                (root / name).mkdir()
            (root / "prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so").write_bytes(b"old driver")
            (root / "firmware/dummy.bin").write_bytes(b"firmware")
            (root / "udev/61-broadcom-cv2-5834.rules").write_text("# fixture\n")
            output = root / "out.deb"
            result = subprocess.run(
                ["bash", str(root / "build_deb.sh"), str(output)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checksum mismatch", result.stderr)
            self.assertFalse(output.exists())

    def test_install_rejects_stale_driver_before_system_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("install.sh", "patch_driver.py"):
                shutil.copyfile(ROOT / name, root / name)
            (root / "prebuilt").mkdir()
            (root / "prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so").write_bytes(b"old driver")
            commands = root / "commands"
            commands.mkdir()
            marker = root / "system-command-called"
            # Intercept privileged and mutating commands even if tests run as root.
            for name in ("sudo", "mkdir", "install", "cp", "udevadm", "systemctl"):
                stub = commands / name
                stub.write_text('#!/bin/sh\nprintf called > "$INSTALL_TEST_MARKER"\nexit 99\n')
                stub.chmod(0o755)
            result = subprocess.run(
                ["bash", str(root / "install.sh")], capture_output=True, text=True,
                env={**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                     "INSTALL_TEST_MARKER": str(marker)},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists(), "installer reached a system command before rejecting input")
            self.assertIn("checksum mismatch", result.stderr)

    @unittest.skipUnless(STOCK, "set CV2_STOCK_DRIVER to the pinned stock library")
    def test_enrollment_update_preserves_success_retry_and_error_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.so"
            harness = Path(directory) / "harness"
            result = self.run_patch(STOCK, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([
                "cc", "-Wall", "-Wextra", "-Werror", "-rdynamic",
                str(ROOT / "tests/enrollment_status_harness.c"), "-ldl", "-o", str(harness),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([str(harness), str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(STOCK, "set CV2_STOCK_DRIVER to the pinned stock library")
    def test_verify_requires_success_and_retries_invalid_image(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.so"
            harness = Path(directory) / "harness"
            result = self.run_patch(STOCK, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([
                "cc", "-Wall", "-Wextra", "-Werror", "-rdynamic",
                str(ROOT / "tests/verify_status_harness.c"), "-ldl", "-o", str(harness),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([str(harness), str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(STOCK, "set CV2_STOCK_DRIVER to the pinned stock library")
    def test_identify_retries_invalid_image_without_trusting_stale_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.so"
            harness = Path(directory) / "harness"
            result = self.run_patch(STOCK, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([
                "cc", "-Wall", "-Wextra", "-Werror", "-rdynamic",
                str(ROOT / "tests/identify_status_harness.c"), "-ldl", "-o", str(harness),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([str(harness), str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(STOCK, "set CV2_STOCK_DRIVER to the pinned stock library")
    def test_delete_authorization_and_status_propagation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.so"
            harness = Path(directory) / "harness"
            result = self.run_patch(STOCK, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([
                "cc", "-Wall", "-Wextra", "-Werror", "-rdynamic",
                str(ROOT / "tests/delete_auth_harness.c"), "-ldl", "-o", str(harness),
            ], check=True, capture_output=True, text=True)
            result = subprocess.run([str(harness), str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(STOCK, "set CV2_STOCK_DRIVER to the pinned stock library")
    def test_commit_encoding_and_output_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.so"
            result = self.run_patch(STOCK, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = output.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), EXPECTED)
            # Unknown commit status must still branch to the error path.
            self.assertEqual(data[0xdd27:0xdd30], bytes.fromhex("4585ed0f8548020000"))
            # .text/.rodata virtual addresses equal file offsets in pinned ELF.
            authorization = 0x2b260 + struct.unpack_from("<i", data, 0x2b25c)[0]
            attributes = 0x2b26e + struct.unpack_from("<i", data, 0x2b26a)[0]
            self.assertEqual(data[attributes:attributes + 8], bytes.fromhex("0000040004000000"))
            self.assertEqual(data[authorization:authorization + 21], bytes.fromhex(
                "0101ff0000000d000c42726f6164636f6d57424600"))

    @unittest.skipUnless(STOCK, "set CV2_STOCK_DRIVER to the pinned stock library")
    def test_changed_binary_rejected_even_with_matching_signatures(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "in.so", Path(directory) / "out.so"
            data = bytearray(Path(STOCK).read_bytes())
            data[-1] ^= 1  # None of the patch signatures changes.
            source.write_bytes(data)
            output.write_bytes(b"keep previous build")
            result = self.run_patch(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), b"keep previous build")


if __name__ == "__main__":
    unittest.main()
