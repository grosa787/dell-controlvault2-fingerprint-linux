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

---

## Status

| Capability | State |
|---|---|
| Device detected by `libfprint`/`fprintd` | ✅ works (needs TOD-enabled libfprint) |
| Open / power-on | ✅ works |
| Fingerprint **capture** (sensor lights, grabs images) | ✅ works |
| **Enroll** → `enroll-completed` | ⚠️ **unit-dependent** — the commit step fails on many units (see below) |
| **Verify / match** (match-on-chip) | ⚠️ **unconfirmed** with patches 1–5 — reports say verify returns `no-match` for every finger |

The hard part is **match-on-chip**: the template lives in the chip's secure
storage. Patches **4–5** route some CV2 status codes, but CV2 firmwares differ
and several units return codes these patches do not handle. Reports so far:

| Status at failure | Where | Reported on | Issue |
|---|---|---|---|
| `Device status = (36)` / `0x24` | commit | Precision 3520, Latitude 5290, 5491, 5590, 7390 | #1, #2, #3, #5, #7, #9 |
| `Device status = (141)` / `0x8d` | commit (after a cancelled 4th capture) | Latitude 5290, 5490, 5590, 7390 | #2, #9, #12 |
| `0x89` forever, stuck after 1st stage | enroll update | Latitude 7390 2-in-1 | #4 |
| `0x100002` from `cv_open()` | session open | Latitude 7390 | #6 |
| constant `0x17` from identify | verify | Latitude 7390 | #5 |

These need new reverse-engineering work, not just a new constant — details and
what is known about each code are in [PATCHES.md](PATCHES.md#known-cv2-status-codes--open-problems).
A community fork reports enroll + verify working on a Latitude 7390 with
additional patches (#12); those patches are not part of this repository.

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
  during verify → that `NN` is the CV status to map. See `PATCHES.md` #4/#5.
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
Five byte-level patches turn the CV3 driver into a CV2 driver. Full
reverse-engineering write-up and the exact signatures are in
**[PATCHES.md](PATCHES.md)**. The patcher (`patch_driver.py`) applies them by
unique byte signature, so it survives minor upstream binary changes, and it
reproduces the working driver **byte-for-byte**. It is idempotent, prints
SHA-256 of input and output, and `python3 patch_driver.py --check <driver.so>`
reports which patches an installed driver carries.

## Repo layout
```
build_from_upstream.sh  fetch stock driver from Launchpad and patch it
install.sh              install the patched driver + assets (multi-distro)
uninstall.sh            remove it (restores a backed-up stock driver)
diagnose.sh             read-only report for bug reports
lib/common.sh           shared distro detection for the scripts above
patch_driver.py         the 5 byte-patches (signature based) + --check
prebuilt/               generated by build_from_upstream.sh (gitignored, proprietary)
firmware/               generated by build_from_upstream.sh (gitignored, proprietary)
udev/                   rule binding 0a5c:5834 to the driver
PATCHES.md              reverse-engineering notes + known status codes
CHANGELOG.md            release notes
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
