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
- The CV2 chip answers correctly (`cv_get_ush_ver` returns status `0x0`), proving
  the protocol is shared between CV2 and CV3 — only the high-level driver gates
  differ.

## The 5 patches (applied by `patch_driver.py` via unique byte signatures)

| # | Site | Change | Why |
|---|------|--------|-----|
| 1 | `.rodata` id_table | USB PID `0x5842` → `0x5834` | so libfprint binds **our** device to this driver |
| 2 | device enumerator | PID-filter `je` → `jmp` (`74`→`eb`) | so the driver's libusb path also accepts `0x5834` |
| 3 | `dev_probe` | firmware-check err `0x1c` handled as success (`je` disp `1f`→`3a`) | the CV3 driver can't match our BCM5880 to a "Citadel" chip type and aborts; CV2 already runs resident firmware, so **nothing is flashed** — we just skip the bogus upgrade check |
| 4 | enroll state machine | CV2 status `0x59` routed to the normal status-`0` path | `0x59` is CV2's "enrollment data ready"; the stock driver treats it as a fatal `Device status = (89)`. Routing it correctly lets the **COMMIT** phase run so the template is actually stored in the chip |
| 5 | verify completion | drop the `edx!=0` short-circuit (6× `nop`) | CV2 returns a non-zero verify status the CV3 code doesn't know, so it completed without calling `verify_report` → `verify-unknown-error`. Now `verify_report` is always called and the match result is honored |

Patches 1–3 get the device **recognized, opened and capturing**.
Patches 4–5 are about actually **storing and matching** a template (match-on-chip).

## Tools used
`radare2`, `objdump`, `nm`, `readelf`, `pyusb`. No source — everything was
recovered by disassembly of the shipped `.so` and live USB probing on a real
Latitude 7490.

## Known CV2 status codes / open problems

Collected from user reports in the issue tracker. None of these is fixed by
patches 1–5; each needs more than swapping a constant. Codes printed by the
driver with `%x` (e.g. `cv_fingerprint_identify failed 89`) are **hex**;
`Device status = (NN)` from fprintd is **decimal**.

| Code | Seen in | What is known | Issues |
|---|---|---|---|
| `0x24` (36) | `cv_fingerprint_commit_enrollment` | The commit function's success gate accepts only `0` and `0x34`; `0x24` takes the error path before the template handle is saved. Changing the gate to `0x24` makes the commit report success, but the handle is still `0` and verify never matches (#3). Not applied here for that reason. | #1, #2, #3, #5, #7, #9 |
| `0x8d` (141) | commit | Follows a 4th capture that ended in `Update enrollment failed : cancel capture`; may mean "commit on a cancelled session". Intermittent on some units (#12). | #2, #9, #12 |
| `0x59` (89) | enroll update | Patch 4 routes it to the status-0 path, which starts the commit. A Windows A21 trace on a `0a5c:5833` unit shows no `0x59` in a successful enrollment (4 updates + 2 commits, all `0x00`), so treating it as "data ready" is an empirical workaround and may commit after only 3 samples. Patch 4 also replaces the stock `0xa4` retry check. | #4, #5 |
| `0x89` (137) | enroll update | Real "bad capture / retry" status. The stock driver re-captures without re-arming; the Windows stack sends command `0x8a` (enrollment started) before each new capture. Recovery needs an extra CV command, not a branch patch. Do **not** redirect the `0x89` branch (tried in #4 and #5, breaks enrollment). | #4, #5 |
| `0x17` | `cv_do_fingerprint_identify` | Constant for enrolled and unenrolled fingers; likely a pre-comparison failure. Separately, `cvif_fingerprint_identify` returns a zero-initialised local instead of the parsed result. | #5 |
| `0x1b`, `0x47` | identify | Seen instead of the CV3 "match" code `0x89`. | #2, #3 |
| `0x100002` | `cv_get_ush_ver()`, `cv_open()` | Chip never answers; session never opens. Seen on a unit with a factory-default USB serial that was possibly never provisioned. | #6 |

If your unit reports a different code, run `./diagnose.sh` with debug logging
enabled (see README) and attach the output to an issue.

## Status / caveats
- This is an **unofficial** patch of a **proprietary** binary. It is not endorsed
  by Dell, Broadcom or Canonical. Use on hardware you own.
