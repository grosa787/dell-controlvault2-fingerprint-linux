#!/usr/bin/env python3
"""
patch_driver.py - turn Dell/Canonical's proprietary ControlVault3 fingerprint
driver (libfprint-2-tod-1-broadcom.so) into one that drives the older
ControlVault2 (Broadcom BCM5880, USB 0a5c:5834) sensor.

It applies 7 byte-level patches by unique signature search. Patches 6 and 7 use
RIP-relative addresses calculated for the tested upstream binary, so use the
pinned input fetched and checksum-verified by build_from_upstream.sh.

Usage:
    python3 patch_driver.py <input.so> <output.so>

Where <input.so> is the STOCK driver from Canonical's OEM repo:
    git clone -b upstream \\
      https://git.launchpad.net/~oem-solutions-engineers/libfprint-2-tod1-broadcom/+git/libfprint-2-tod1-broadcom
    -> usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so

See PATCHES.md for the full reverse-engineering rationale of every patch.
"""
import sys

# (description, find_bytes, replace_bytes). Each `find` must occur exactly once.
PATCHES = [
    ("1. id_table: add USB PID 0x5834 (was 0x5842) so libfprint binds our device",
     bytes.fromhex("42580000 5c0a0000".replace(" ", "")),
     bytes.fromhex("34580000 5c0a0000".replace(" ", ""))),

    ("2. USB enumerator: accept PID 0x5834 (turn the PID filter `je` into `jmp`)",
     bytes.fromhex("66f7c1fdff 740c".replace(" ", "")),
     bytes.fromhex("66f7c1fdff eb0c".replace(" ", ""))),

    ("3. dev_probe: treat 'cannot determine chip type' (err 0x1c) as success "
     "(CV2 has resident firmware; nothing is flashed)",
     bytes.fromhex("83f81c 741f"),
     bytes.fromhex("83f81c 743a")),

    ("4. enroll: map CV2 'enrollment data ready' status 0x59 to the normal "
     "status-0 path so the template-COMMIT phase runs",
     bytes.fromhex("4181fda4000000 0f84fd010000".replace(" ", "")),
     bytes.fromhex("4181fd59000000 0f84160000 00".replace(" ", ""))),

    ("5. verify: always call verify_report (drop the `edx!=0` short-circuit) so "
     "CV2's non-zero verify status no longer becomes verify-unknown-error",
     bytes.fromhex("85d2 0f858a000000 83f801".replace(" ", "")),
     bytes.fromhex("85d2 909090909090 83f801".replace(" ", ""))),

    ("6. commit: pass Dell CV2's two identity blobs instead of empty identity "
     "arguments (the replaced instructions include a one-use debug log call)",
     bytes.fromhex(
         "bf01000000 488d3563a60000 e80e02feff 4883ec08 418b7d00 "
         "4531c9 53 4531c0 31c9 31d2 6a00 4889ee 488d44241c 50"
         .replace(" ", "")),
     bytes.fromhex(
         "4883ec08 418b7d00 4c8d0d68a60000 53 41b815000000 "
         "488d0d52a60000 ba08000000 6a00 4889ee 488d44241c 50 9090"
         .replace(" ", ""))),

    ("7. commit: store Dell CV2 identity blobs in the removed debug string",
     b"call cv_fingerprint_commit_enrollment\n"[:29],
     bytes.fromhex(
         "0000040004000000 "
         "0101ff0000000d000c42726f6164636f6d57424600"
         .replace(" ", ""))),
]


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    with open(sys.argv[1], "rb") as f:
        data = bytearray(f.read())

    for desc, find, repl in PATCHES:
        assert len(find) == len(repl), "patch length mismatch: " + desc
        n = data.count(find)
        if n == 0:
            sys.exit("FAILED: signature not found for patch:\n  " + desc +
                     "\n  (is this the right libfprint-2-tod-1-broadcom.so?)")
        if n > 1:
            sys.exit("FAILED: signature ambiguous (%d hits) for patch:\n  %s" % (n, desc))
        data[data.index(find):data.index(find) + len(find)] = repl
        print("[ok] " + desc)

    with open(sys.argv[2], "wb") as f:
        f.write(data)
    print("\nPatched driver written to: " + sys.argv[2])


if __name__ == "__main__":
    main()
