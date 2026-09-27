# Changelog

## 1.1.0 — 2026-09-27

Installer and diagnostics release. The binary patches (1–5) are unchanged.

### Fixed
- `install.sh` only worked on Debian/Ubuntu: it always installed to
  `/usr/lib/x86_64-linux-gnu/libfprint-2/tod-1`. It now uses the TOD directory
  compiled into the installed libfprint, falling back to the Fedora/openSUSE
  (`/usr/lib64/...`) and Arch (`/usr/lib/...`) paths; `TOD_DIR=` overrides it.
  (#6, #9, #10)
- `install.sh` installed the driver even when libfprint has no TOD support, so
  fprintd kept reporting "No devices available". It now stops with per-distro
  instructions (`FORCE=1` overrides). It also stops when the driver has
  unresolved library dependencies (`ldd`), or the build is not fully patched.
  (#10, possibly #11)
- `udevadm trigger` without `--action=add` did not re-run rules that only match
  on "add". The trigger is now limited to `0a5c:5834` and uses `--action=add`. (#12)
- Installing over a distro-packaged `libfprint-2-tod-1-broadcom.so` destroyed
  it and `uninstall.sh` deleted it. The stock driver is now backed up to
  `/var/lib/fprint/cv2-backup/` and restored on uninstall; `uninstall.sh` only
  removes a driver that `patch_driver.py --check` identifies as patched.
- `build_from_upstream.sh` leaked its temp directory on failure and silently
  ignored missing firmware blobs.
- `patch_driver.py` failed with "signature not found" when run on an already
  patched driver; it is now idempotent.

### Added
- `diagnose.sh`: read-only bug-report helper (USB device, libfprint TOD
  support, driver SHA-256 and patch state, udev rule, filtered fprintd log).
- `patch_driver.py --check <driver.so>` and SHA-256 output.
- SELinux: `restorecon` on the installed files when available.
- README: per-distro prerequisites, honest enroll/verify status, table of
  reported failure codes. PATCHES.md: known CV2 status codes and open problems.

### Changed
- The udev rule is installed to `/etc/udev/rules.d` (the old copy in
  `/lib/udev/rules.d` is removed).

### Known issues
- Enrollment commit fails with status `0x24` or `0x8d` on many units, and
  verify is unconfirmed with patches 1–5. See PATCHES.md.

## 1.0.0

- First public release: patches 1–5, patch-only distribution.
