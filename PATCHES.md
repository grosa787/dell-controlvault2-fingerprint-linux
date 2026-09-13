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

## The 7 patches (applied by `patch_driver.py` via unique byte signatures)

| # | Site | Change | Why |
|---|------|--------|-----|
| 1 | `.rodata` id_table | USB PID `0x5842` → `0x5834` | so libfprint binds **our** device to this driver |
| 2 | device enumerator | PID-filter `je` → `jmp` (`74`→`eb`) | so the driver's libusb path also accepts `0x5834` |
| 3 | `dev_probe` | firmware-check err `0x1c` handled as success (`je` disp `1f`→`3a`) | the CV3 driver can't match our BCM5880 to a "Citadel" chip type and aborts; CV2 already runs resident firmware, so **nothing is flashed** — we just skip the bogus upgrade check |
| 4 | enroll state machine | CV2 status `0x59` routed to the normal status-`0` path | `0x59` is CV2's "enrollment data ready"; the stock driver treats it as a fatal `Device status = (89)`. Routing it correctly lets the **COMMIT** phase run so the template is actually stored in the chip |
| 5 | verify completion | drop the `edx!=0` short-circuit (6× `nop`) | CV2 returns a non-zero verify status the CV3 code doesn't know, so it completed without calling `verify_report` → `verify-unknown-error`. Now `verify_report` is always called and the match result is honored |
| 6 | commit wrapper | replace four empty identity arguments with lengths `8`/`21` and pointers to Dell's CV2 identity blobs | CV2 rejects the anonymous CV3 commit with `0x8d`/`0x24`; Dell's working WBF path supplies both blobs before command `0x6e` |
| 7 | one-use commit debug string | replace 29 bytes with the two identity blobs, including `BroadcomWBF\0` | provides mapped read-only storage for patch 6 without changing ELF segment sizes or offsets |

Patches 1–3 get the device **recognized, opened and capturing**.
Patches 4–7 are about actually **storing and matching** a template (match-on-chip).

The original commit routine accepts only status `0` or `0x34`, then parses two
returned values including the template handle. Status `0x8d` or `0x24` has no
returned handle and must remain an error. Bypassing that check creates a false
`enroll-completed` record with handle zero; verification and device deletion then
fail. With patches 6–7, a Latitude E7270 returned handle `3925315` (serialized
as `03925315`) and `fprintd-verify` reported `verify-match`, including after the
daemon exited, started again, and after a full system reboot.

## Tools used
`radare2`, `objdump`, `nm`, `readelf`, `pyusb`. No source — everything was
recovered by disassembly of the shipped `.so` and live USB probing on a real
Latitude 7490.

## Status / caveats
- The full enrollment, verification, daemon-restart, and reboot-persistence flow
  is confirmed on a Latitude E7270. Other laptops with USB ID `0a5c:5834` are
  expected to share the protocol but remain unverified.
- `0x59` / `0x89` are CV2 status codes recovered empirically. If your unit
  reports different codes during enroll/verify, capture `journalctl -u fprintd`
  with debug logging (see README) and the dispatch can be extended.
- Patches 6–7 use RIP-relative addresses for the exact tested Canonical binary.
  `build_from_upstream.sh` pins and checksum-verifies that revision; do not apply
  them blindly to a different driver build.
- This is an **unofficial** patch of a **proprietary** binary. It is not endorsed
  by Dell, Broadcom or Canonical. Use on hardware you own.
