# Dell ControlVault 2 fingerprint on Linux (Broadcom BCM5880, `0a5c:5834`)

Make the **Dell ControlVault 2 / Broadcom BCM5880 "USH"** fingerprint reader
(USB ID **`0a5c:5834`**) work under Linux with `fprintd` / `libfprint`.

This reader is found on many **Dell Latitude** laptops (7390, 7480, **7490**,
E7470, 5290, 5490, 5590, …). It has been considered *unsupported on Linux for
about a decade* — `libfprint` does not recognise it, and Dell only ships a closed
driver for the newer ControlVault **3** sensors.

This repo patches that closed driver so it also drives the older CV2 chip.

> ⚠️ **Unofficial.** Not affiliated with or endorsed by Dell, Broadcom or
> Canonical. It patches a **proprietary** binary. Use it on hardware you own.

---

## Is this for me?
Run `lsusb`. If you see:

```
Bus 00x Device 00x: ID 0a5c:5834 Broadcom Corp. 5880
```

…and `fprintd-enroll` says *"No devices available"*, this is for you.

---

## Install

This repo ships **only the patches**, not Dell's proprietary binary. The patched
driver is built locally from Canonical's stock OEM driver. You need `git`,
`python3`, `fprintd` and a **TOD-enabled `libfprint`** (x86_64 only):

| Distro | TOD-enabled libfprint | Driver directory (auto-detected) |
|---|---|---|
| Debian / Ubuntu / Mint | `sudo apt install libfprint-2-tod1` | `/usr/lib/x86_64-linux-gnu/libfprint-2/tod-1` |
| openSUSE | `sudo zypper install libfprint-2-tod1` | `/usr/lib64/libfprint-2/tod-1` |
| Arch / CachyOS | AUR `libfprint-tod` | `/usr/lib/libfprint-2/tod-1` |
| Fedora | official `libfprint` has **no** TOD support — a TOD build is required (not provided here) | `/usr/lib64/libfprint-2/tod-1` |

Without TOD support fprintd logs `No driver found for USB device 0A5C:5834` and
`fprintd-enroll` keeps saying *"No devices available"*. `install.sh` now checks
this and stops with a hint instead of installing a driver that is never loaded.

```bash
git clone https://github.com/grosa787/dell-controlvault2-fingerprint-linux
cd dell-controlvault2-fingerprint-linux
./build_from_upstream.sh     # fetch stock driver from Canonical's OEM repo + apply patches
sudo ./install.sh            # install driver + udev rule + firmware, restart fprintd
fprintd-enroll               # enroll a finger (press, lift, repeat ~4-8x)
fprintd-verify               # test recognition
sudo pam-auth-update         # (optional) enable fingerprint login & sudo
```

If an OS / `libfprint` update ever wipes it, run `./install.sh` again (re-run
`./build_from_upstream.sh` first if the build was cleaned).

`install.sh` options (environment variables):
- `TOD_DIR=<dir>` — override the auto-detected TOD driver directory.
- `FORCE=1` — install even if libfprint does not look TOD-enabled.

A stock `libfprint-2-tod-1-broadcom.so` from a distro package is backed up to
`/var/lib/fprint/cv2-backup/` and restored by `./uninstall.sh`.

### Optional local Debian / Ubuntu package

As an alternative to `install.sh`, build a local package with `dpkg-deb`:

```bash
./build_deb.sh /tmp/broadcom-cv2.deb
sudo apt install /tmp/broadcom-cv2.deb
# To remove the package:
sudo apt remove libfprint-2-tod1-broadcom-cv2
```

The package uses the Debian amd64 TOD directory and depends on `libfprint-2-tod1`.
Its udev rule is package-owned under `/usr/lib/udev/rules.d`; manual installation
continues to use `/etc/udev/rules.d`. Use one installation method at a time;
run `./uninstall.sh` before switching from a manual installation to the package.
The generated package contains proprietary driver/firmware files for local use;
it is not committed to this repository.

---

## Status

| Capability | State |
|---|---|
| Device detected by `libfprint`/`fprintd` | ✅ works (needs TOD-enabled libfprint) |
| Open / power-on | ✅ works |
| Fingerprint **capture** (sensor lights, grabs images) | ✅ works |
| **Enroll** → `enroll-completed` | Confirmed on the tested Latitude 7490 with the updated patches; other units need validation |
| **Verify / match** (match-on-chip) | Confirmed on that Latitude 7490, including login after a full reboot |
| Authenticated template deletion | Confirmed on that Latitude 7490 |

The hard part is **match-on-chip**: the template lives in the chip's secure
storage. Updated patches **4–5** handle failed samples without accepting them
as success; patches **6–8** supply CV2 storage and deletion arguments, and patch
**9** adds identify retries. Identify retries are covered by native callback
tests; multi-finger validation through `fprintd` is still pending.

The reports below describe problems with the earlier patches 1–5. They remain
useful for tracking other CV2 units; the Latitude 7490 result does not establish
that these problems are resolved on every device:

| Status at failure | Where | Reported on | Issue |
|---|---|---|---|
| `Device status = (36)` / `0x24` | commit | Precision 3520, Latitude 5290, 5491, 5590, 7390 | #1, #2, #3, #5, #7, #9 |
| `Device status = (141)` / `0x8d` | commit (after a cancelled 4th capture) | Latitude 5290, 5490, 5590, 7390 | #2, #9, #12 |
| `0x89` forever, stuck after 1st stage | enroll update | Latitude 7390 2-in-1 | #4 |
| `0x100002` from `cv_open()` | session open | Latitude 7390 | #6 |
| constant `0x17` from identify | verify | Latitude 7390 | #5 |

Details, the scope of the new fixes, and remaining open problems are in
[PATCHES.md](PATCHES.md#known-cv2-status-codes--open-problems). The commit
attributes and authorization changes are adapted from
[aegan977's PR #8](https://github.com/grosa787/dell-controlvault2-fingerprint-linux/pull/8).
A community fork also reports enroll + verify working on a Latitude 7390 (#12).

> Tip while enrolling: **lift your finger completely between presses** and shift
> its position a little each time. Failed grabs are ignored and harmless.

---

## Troubleshooting

**Collect a report first:** `./diagnose.sh > report.txt` (read-only). It shows
the USB device, whether libfprint has TOD support, the installed driver's
SHA-256 and patch state, the udev rule, and the relevant fprintd log lines.
Review it, then attach it to an issue.

**Enable debug logging** (to read what the chip returns):
```bash
sudo mkdir -p /etc/systemd/system/fprintd.service.d
printf '[Service]\nEnvironment=G_MESSAGES_DEBUG=all\nEnvironment=LIBFPRINT_DEBUG=3\n' \
  | sudo tee /etc/systemd/system/fprintd.service.d/debug.conf
sudo systemctl daemon-reload && sudo systemctl restart fprintd
# reproduce, then:
sudo journalctl -u fprintd --since "2 min ago" -o cat
```

- `Device status = (NN)` (decimal) during enroll, or `identify failed 0xNN`
  during verify → include that status in the diagnostic report. See `PATCHES.md`
  for the known codes and how the patches handle them.
- Re-list / clear prints: `fprintd-list "$USER"`, `fprintd-delete "$USER"`.
- `No driver found for USB device 0A5C:5834` / *"No devices available"* →
  libfprint without TOD support, or the driver is in a directory libfprint
  does not scan. Run `./diagnose.sh`.
- *"Device disabled to prevent overheating"* after a failed enroll → libfprint's
  thermal model; `sudo systemctl restart fprintd` and retry.
- The `GTask … finalized without ever returning` warnings are harmless; they
  appear on working units too.

---

## How it works
Nine byte-level patches turn the CV3 driver into a CV2 driver. Full
reverse-engineering write-up and the exact signatures are in
**[PATCHES.md](PATCHES.md)**. The patcher (`patch_driver.py`) applies them by
unique byte signature. The new commit/authorization patches also use relative
addresses, so `build_from_upstream.sh` fetches the tested Canonical revision and
the patcher verifies input and output SHA-256. It reproduces the working driver
**byte-for-byte**. It is idempotent for the exact patched output, prints
SHA-256 of input and output, and `python3 patch_driver.py --check <driver.so>`
reports which patches an installed driver carries and verifies the completed
build's checksum. To upgrade from the earlier five-patch driver, rerun
`./build_from_upstream.sh` and install the new build.

## Repo layout
```
build_from_upstream.sh  fetch stock driver from Launchpad and patch it
build_deb.sh            optional local Debian / Ubuntu package
install.sh              install the patched driver + assets (multi-distro)
uninstall.sh            remove it (restores a backed-up stock driver)
diagnose.sh             read-only report for bug reports
lib/common.sh           shared distro detection for the scripts above
patch_driver.py         the 9 byte-patches (signature based, pinned build) + --check
prebuilt/               generated by build_from_upstream.sh (gitignored, proprietary)
firmware/               generated by build_from_upstream.sh (gitignored, proprietary)
udev/                   rule binding 0a5c:5834 to the driver
PATCHES.md              reverse-engineering notes + known status codes
CHANGELOG.md            release notes
tests/                  regression tests and native callback harnesses
```

## Legal / license
The driver and firmware are **proprietary Dell/Canonical/Broadcom** artifacts and
are **not** distributed here: `build_from_upstream.sh` downloads them from
Canonical's OEM repo and patches them on your machine. There is no open license
on those binaries. The patches, scripts and docs in this repo are released under
the MIT license.

## Credits
Reverse-engineered from the shipped `.so` with `radare2` + `pyusb` on a Dell
Latitude 7490. USB transport groundwork inspired by the NFC work in
[`jacekkow/controlvault2-nfc-enable`](https://github.com/jacekkow/controlvault2-nfc-enable).
