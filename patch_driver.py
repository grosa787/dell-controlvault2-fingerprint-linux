#!/usr/bin/env python3
"""
patch_driver.py - turn Dell/Canonical's proprietary ControlVault3 fingerprint
driver (libfprint-2-tod-1-broadcom.so) into one that drives the older
ControlVault2 (Broadcom BCM5880, USB 0a5c:5834) sensor.

Applies nine patches to the pinned Canonical binary. The commit arguments fix
uses RIP-relative addresses, so patching accepts only the pinned stock binary
or the exact patched output, verified by SHA-256.
Commit attributes and authorization adapted from PR #8 by aegan977:
https://github.com/grosa787/dell-controlvault2-fingerprint-linux/pull/8

Usage:
    python3 patch_driver.py <input.so> <output.so>   apply the patches (idempotent)
    python3 patch_driver.py --check <driver.so>      report which patches are applied
    python3 patch_driver.py --check --allow-legacy <driver.so>
        also recognize the known five-patch build for removal / backup decisions

Where <input.so> is the STOCK driver from Canonical's OEM repository at revision
f7d31fcb9f6952d7d76ba50287e000c29760589d. Use build_from_upstream.sh to fetch that
exact revision and apply the patches. The stock library's path in the repository:
    usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so

See PATCHES.md for the full reverse-engineering rationale of every patch.
"""
import hashlib
import os
import sys
import tempfile

STOCK_SHA256 = "54fa3befc02df393077cebf96e018e3bf752cee61509897d945ab18c58c5e172"
PATCHED_SHA256 = "62868df275e49a7a345ebd9245d651e141a750fee1bfa6d9a8b1b627b1678278"
# v1.1.0's five patches applied to the pinned stock binary.
LEGACY_PATCHED_SHA256 = "23e524729bec0c1bcac8861b2c1db77b1319607668a3fe23833e44bc54a5ac88"

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

    ("4. enroll: retry 0x59; preserve success, rollback and other errors",
     bytes.fromhex("488d3525a70000 bf01000000 31c0 e8f902feff"),
     bytes.fromhex("4183fc59 750d 41bc89000000 eb0a 9090909090")),

    ("5. verify: retry 0x89; use match data only on command success",
     bytes.fromhex("488d15ac1c0200be8000000031ff31c0e8dbe3ffffeb87660f1f840000000000"),
     bytes.fromhex("81fa890000000f856fffffff31ffe8fdf0ffff4889c131d26aff5ee976ffffff")),

    ("6. commit: supply CV2 object attributes and authorization",
     bytes.fromhex(
         "bf01000000 488d3563a60000 e80e02feff 4883ec08 418b7d00 "
         "4531c9 53 4531c0 31c9 31d2 6a00 4889ee 488d44241c 50"
         .replace(" ", "")),
     bytes.fromhex(
         "4883ec08 418b7d00 4c8d0d68a60000 53 41b815000000 "
         "488d0d52a60000 ba08000000 6a00 4889ee 488d44241c 50 9090"
         .replace(" ", ""))),

    ("7. commit: store Dell CV2 attributes and authorization in the removed debug string",
     b"call cv_fingerprint_commit_enrollment\n"[:29],
     bytes.fromhex(
         "0000040004000000 "
         "0101ff0000000d000c42726f6164636f6d57424600"
         .replace(" ", ""))),

    ("8. delete: supply the same passphrase authorization list as commit",
     bytes.fromhex("4531c9 4531c0 31c9 31d2 e97e0dfeff 660f1f440000"),
     bytes.fromhex("4531c9 4531c0 488d0df8a40000 6a155a e9780dfeff")),

    ("9. identify: retry 0x89; preserve successful matches and other-error no-match",
     bytes.fromhex("85d2756e488d15ea1d020083f8017442be8000000031ff31c0e844e5ffff"),
     bytes.fromhex("85d2741581fa89000000751231ffe86ff2ffff4889c1eb089083f8017434")),
]


def write_atomic(path, data):
    temporary = None
    try:
        # Use the destination filesystem so os.replace remains atomic.
        with tempfile.NamedTemporaryFile(
            dir=os.path.dirname(os.path.abspath(path)), prefix=".patch-driver-", delete=False,
        ) as f:
            temporary = f.name
            f.write(data)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def patch_state(data, find, repl):
    """'stock', 'patched', or 'missing' (signature absent or ambiguous)."""
    n_find, n_repl = data.count(find), data.count(repl)
    if n_find == 1 and n_repl == 0:
        return "stock"
    if n_find == 0 and n_repl == 1:
        return "patched"
    return "missing"


def check(path, allow_legacy=False):
    with open(path, "rb") as f:
        data = f.read()
    print("file:   " + path)
    print("sha256: " + sha256(data))
    if sha256(data) == LEGACY_PATCHED_SHA256:
        print("\nKnown legacy CV2 driver (five patches).")
        print("Rebuild with ./build_from_upstream.sh before installing the current patches.")
        return 0 if allow_legacy else 1
    states = [patch_state(data, find, repl) for _, find, repl in PATCHES]
    for (desc, _, _), state in zip(PATCHES, states):
        print("[%-7s] %s" % (state, desc.split(":")[0]))
    if all(s == "patched" for s in states):
        if sha256(data) != PATCHED_SHA256:
            print("\nPatched driver SHA-256 mismatch; rebuild with ./build_from_upstream.sh")
            return 1
        print("\nAll %d CV2 patches are applied." % len(PATCHES))
        return 0
    if all(s == "stock" for s in states):
        print("\nThis is the STOCK driver (no CV2 patches).")
        return 1
    print("\nPartially patched or unknown driver build.")
    return 1


def main():
    if len(sys.argv) == 4 and sys.argv[1:3] == ["--check", "--allow-legacy"]:
        sys.exit(check(sys.argv[3], allow_legacy=True))
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        sys.exit(check(sys.argv[2]))
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    with open(sys.argv[1], "rb") as f:
        data = bytearray(f.read())
    print("input sha256:  " + sha256(data))

    # Relative addresses in the new patches require the tested binary layout.
    # Accept our exact output too, preserving idempotent re-patching.
    if sha256(data) not in (STOCK_SHA256, PATCHED_SHA256):
        sys.exit("FAILED: driver SHA-256 mismatch; use build_from_upstream.sh")

    for desc, find, repl in PATCHES:
        assert len(find) == len(repl), "patch length mismatch: " + desc
        state = patch_state(data, find, repl)
        if state == "patched":
            print("[already] " + desc)
            continue
        if state == "missing":
            n = data.count(find)
            if n > 1:
                sys.exit("FAILED: signature ambiguous (%d hits) for patch:\n  %s" % (n, desc))
            sys.exit("FAILED: signature not found for patch:\n  " + desc +
                     "\n  (is this the right libfprint-2-tod-1-broadcom.so?)")
        off = data.index(find)
        data[off:off + len(find)] = repl
        print("[ok] " + desc)

    if sha256(data) != PATCHED_SHA256:
        sys.exit("FAILED: patched driver SHA-256 mismatch; output was not written")

    write_atomic(sys.argv[2], data)
    print("output sha256: " + sha256(data))
    print("\nPatched driver written to: " + sys.argv[2])


if __name__ == "__main__":
    main()
