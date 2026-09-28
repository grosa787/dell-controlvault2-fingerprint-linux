# Reverse-engineering notes & patch rationale

The fingerprint sensor on many Dell Latitude laptops (e.g. **7390/7480/7490**,
E7470, 5590, …) is a **Broadcom BCM5880 "USH" / Dell ControlVault 2**, exposed
on USB as `0a5c:5834`. It is a secure micro-controller that does **match-on-chip**
fingerprint over a vendor-specific interface. Open-source `libfprint` does not
support it, and the community considered it unsupported for ~10 years.

Dell/Canonical *do* ship a closed binary driver — `libfprint-2-tod-1-broadcom.so`
(a libfprint "TOD" / Touch-OEM-Driver) — but it targets the newer **ControlVault 3
"Citadel"** sensors (`0a5c:5842/5843/5844/5845`). This project makes that binary
drive the older CV2 `0a5c:5834` by patching the few places where it is
hard-wired to CV3.

## How the device actually talks (recovered from the driver's `processCommand`)
- Interface **0** (class `0xFE`, "USH w/touch sensor") is the fingerprint channel.
  Endpoints: bulk OUT `0x01`, bulk IN `0x81`, interrupt IN `0x85`.
- The driver sends a **raw 44-byte "CV command"** to bulk OUT `0x01` (no SPI
  wrapper), then reads a 32-byte status from interrupt IN `0x85`, then the
  payload from bulk IN `0x81`.
- The 44-byte CV header (from `cvhEncapsulateCmd`):
  `+0x00 u32=1 | +0x04 u32 total_len | +0x08 u16 command_id | +0x0a u16 flags |
   +0x0c u32 lib_ver | +0x28 u32 num_params | +0x2c params…`
- The CV2 chip answers correctly (`cv_get_ush_ver` returns status `0x0`), showing
  compatibility for this command. Other commands require the CV2 arguments below.

## The 9 patches (applied by `patch_driver.py` via unique byte signatures)

| # | Site | Change | Why |
|---|------|--------|-----|
| 1 | `.rodata` id_table | USB PID `0x5842` → `0x5834` | so libfprint binds **our** device to this driver |
| 2 | device enumerator | PID-filter `je` → `jmp` (`74`→`eb`) | so the driver's libusb path also accepts `0x5834` |
| 3 | `dev_probe` | firmware-check err `0x1c` handled as success (`je` disp `1f`→`3a`) | the CV3 driver can't match our BCM5880 to a "Citadel" chip type and aborts; CV2 already runs resident firmware, so **nothing is flashed** — we just skip the bogus upgrade check |
| 4 | update wrapper, `0x2b164` | map `0x59` to the existing `0x89` sample-retry path, replacing only an error log | `0x59` is `CV_FP_MATCH_GENERAL_ERROR`, not data-ready; never commit the missing output token. Original `0xa4` rollback handling remains intact |
| 5 | verify completion, `0xd510` | keep the command-status check; report `0x89` as a scan retry and other nonzero statuses as no match | stock error handling completed without `verify_report`; now report a retry error (`FPI_MATCH_ERROR`) or no match before `verify_complete(NULL)`. Match data is used only when command status is 0 |
| 6 | commit wrapper, `0x2b251` | provide object attributes (8 bytes) and authorization (21 bytes) instead of zero arguments | CV2 rejects the empty attributes/authorization parameters in command `0x6e` |
| 7 | removed debug string, `0x358c0` | store the 29 bytes of attributes and authorization | read-only storage for patch 6 without extending ELF segments |
| 8 | delete wrapper, `0x2b3c3` | supply 21-byte authorization list from commit | empty auth produced `CV_AUTH_FAIL` (8); authenticated deletion now returns success |
| 9 | identify callback, `0xd39e` | report `0x89` as a scan retry, replacing status dispatch and a diagnostic log | use `identify_report(NULL, NULL, retry)` then `identify_complete(NULL)`; retain successful matches, no match for other errors, and session cleanup |

Patches 1–3 get the device **recognized, opened and capturing**.
Patches 4–5 handle failed samples without treating them as success.
Patches 6–7 supply commit arguments; patch 8 supplies deletion authorization.
Patch 9 adds invalid-image retries to identify, complementing verify patch 5.

## Tools used
`radare2`, `objdump`, `nm`, `readelf`, `pyusb`. No source — everything was
recovered by disassembly of the shipped `.so` and live USB probing on a real
Latitude 7490.

## Known CV2 status codes / open problems

Collected from reports against the earlier patches 1–5. The updated patches
address commit arguments and retry reporting on the tested Latitude 7490; the
other reported units still need validation. Codes printed by the
driver with `%x` (e.g. `cv_fingerprint_identify failed 89`) are **hex**;
`Device status = (NN)` from fprintd is **decimal**.

| Code | Seen in | What is known | Issues |
|---|---|---|---|
| `0x24` (36) | `cv_fingerprint_commit_enrollment` | The commit function's success gate accepts only `0` and `0x34`; `0x24` takes the error path before the template handle is saved. Changing the gate to `0x24` makes the commit report success, but the handle is still `0` and verify never matches (#3). Not applied here for that reason. Patches 6–7 instead supply the missing object attributes and authorization; the original success gate remains intact. | #1, #2, #3, #5, #7, #9 |
| `0x8d` (141) | commit | The host SDK names this `CV_NO_VALID_FP_TEMPLATE`. Reports follow a 4th capture that ended in `Update enrollment failed : cancel capture`; intermittent on some units (#12). Resolution on those units is unconfirmed. | #2, #9, #12 |
| `0x59` (89) | enroll update | The earlier patch 4 routed it to the status-0 path, which started the commit. A Windows A21 trace on a `0a5c:5833` unit shows no `0x59` in a successful enrollment (4 updates + 2 commits, all `0x00`), so treating it as "data ready" is an empirical workaround and may commit after only 3 samples. That patch also replaced the stock `0xa4` rollback check. Updated patch 4 uses the SDK definition `CV_FP_MATCH_GENERAL_ERROR` to request another sample and preserves the original rollback handling. | #4, #5 |
| `0x89` (137) | enroll update | Real "bad capture / retry" status. The stock driver re-captures without re-arming; the Windows stack sends command `0x8a` (enrollment started) before each new capture. Recovery needs an extra CV command, not a branch patch. The updated patches leave that enrollment branch intact. Patches 5 and 9 report retries for `0x89` in verify/identify callbacks; they do not implement enrollment re-arming. | #4, #5 |
| `0x17` | `cv_do_fingerprint_identify` | Constant for enrolled and unenrolled fingers; likely a pre-comparison failure. Separately, `cvif_fingerprint_identify` returns a zero-initialised local instead of the parsed result. | #5 |
| `0x1b`, `0x47` | identify | Reported during identify. The host SDK defines `0x89` as an invalid image, not a match. Updated patches keep nonzero command statuses out of the successful-match path; these units still need investigation. | #2, #3 |
| `0x100002` | `cv_get_ush_ver()`, `cv_open()` | Chip never answers; session never opens. Seen on a unit with a factory-default USB serial that was possibly never provisioned. | #6 |

If your unit reports a different code, run `./diagnose.sh` with debug logging
enabled (see README) and attach the output to an issue.

## Status / caveats
- `0x59` is `CV_FP_MATCH_GENERAL_ERROR`; `0x89` is `CV_NO_VALID_FP_IMAGE`.
  Neither indicates successful enrollment or a valid match. See the SDK
  definitions below; unknown errors must not be converted to success.
- On the tested Latitude 7490, enrollment and authenticated deletion succeeded,
  with consistent fingerprint verification and successful login after a full
  reboot. The contributor also confirmed rejection of an unenrolled finger.
  See [tests](tests/README.md) for regression checks.
- The identify retry patch is covered by native callback tests; validation with
  multiple enrolled fingers through `fprintd` is still pending. Retry errors are
  reported before completion as required by the
  [libfprint API](https://fprint.freedesktop.org/libfprint-dev/libfprint-2-Internal-FpDevice.html#fpi-device-identify-report).
- This is an **unofficial** patch of a **proprietary** binary. It is not endorsed
  by Dell, Broadcom or Canonical. Use on hardware you own.

## Pinned binary and addressing

Canonical OEM revision: `f7d31fcb9f6952d7d76ba50287e000c29760589d`.

- Stock SHA-256: `54fa3befc02df393077cebf96e018e3bf752cee61509897d945ab18c58c5e172`
- Patched SHA-256: `62868df275e49a7a345ebd9245d651e141a750fee1bfa6d9a8b1b627b1678278`

The patcher checks both hashes and unique, equal-length signatures. Re-applying
to the exact patched output succeeds without changing its bytes. `--check` keeps
the per-patch status report and requires the expected output hash before reporting
a complete build. Older five-patch or partially patched libraries must be rebuilt
from stock with `build_from_upstream.sh`. Input pinning
is essential: the patches contain relative branches and RIP-relative addresses,
which cannot safely be validated by matching the replaced instructions alone.
The file size and ELF segment layout are unchanged.

The earlier five-patch build from v1.1.0 has SHA-256
`23e524729bec0c1bcac8861b2c1db77b1319607668a3fe23833e44bc54a5ac88` when applied
to the pinned stock binary. `--check` identifies it as legacy and exits nonzero:
it does not contain the current fixes. `--check --allow-legacy` also accepts
that exact build for removal and backup decisions. This lets the uninstaller
remove an older installation and keeps the installer from backing up a legacy
patched driver as stock. Unknown or modified builds are not accepted for removal.

## Commit and deletion arguments

The commit fix is adapted from
[aegan977's PR #8](https://github.com/grosa787/dell-controlvault2-fingerprint-linux/pull/8).
The data at `0x358c0` contains 8 bytes of object attributes
(`0000040004000000`) followed at `0x358c8` by a 21-byte authorization list
(`0101ff0000000d000c42726f6164636f6d57424600`). This is a
`CV_AUTH_PASSPHRASE` list containing Dell's fixed `BroadcomWBF` value, not a user
identity or a fingerprint template.

The commit wrapper points to both fields. The delete wrapper passes the same
authorization pointer/length while preserving its session and object arguments,
null callbacks, and downstream return status. Empty deletion authorization
produced `CV_AUTH_FAIL` (8) on the tested device. The vendor completion callback
maps failures misleadingly to “print not found”; patch 8 supplies the missing
authorization without changing that callback's error mapping.

## Reverse-engineering sources

Canonical's older 5.12.018 library at revision
`7ee01c0cb5d04432f978f21b843428bfb04f00c4` includes DWARF enumerations read with
`readelf --debug-dump=info`:

| Hex | Name |
|---|---|
| 0x08 | CV_AUTH_FAIL |
| 0x24 | CV_OBJECT_ATTRIBUTES_INVALID |
| 0x59 | CV_FP_MATCH_GENERAL_ERROR |
| 0x89 | CV_NO_VALID_FP_IMAGE |
| 0x8d | CV_NO_VALID_FP_TEMPLATE |
| 0x8f | CV_MORE_DATA |
| 0xa4 | CV_FP_SENSOR_ROLLBACK_REQUIRED |

That library's SHA-256 is
`bfb5e72fc04b4e07189a04da5cdd51cb4b69405bd1ebf7ba92031db066d7bd4a`.
These are host SDK definitions consistent with the observed paths, not proof
that every CV2 firmware version behaves identically.

Dell's [ControlVault2 Windows package 4.10.12.13 A19](https://www.dell.com/support/home/en-us/drivers/driversdetails?driverid=ckgx6)
provides independent reference arguments. The downloaded executable's SHA-256 is
`aa5583a4c5d0ca459ee6653bcbcd2108df5d5c39986dddfcadcfa0eb824946ba`.
Disassembly of its x64 WBF libraries showed:

- `BrcmStorageAdapter.dll`: authorization construction at `0x180006be0`,
  `CSS_SetupAuthSession` at `0x180006c84` and `CSS_DeleteObject` at `0x180006cc0`.
- `bipdll.dll`: `CSS_DeleteObject` forwards authorization to `cv_delete` at
  `0x180011584`.

The Windows binaries were inspected, not installed or used to flash the device.
