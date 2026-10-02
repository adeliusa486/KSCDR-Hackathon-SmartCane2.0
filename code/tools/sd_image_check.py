"""Smart cane - check a raw SD card image of the Pi without mounting it.

Reads the MBR, the FAT32 boot sector of partition 1 and the ext4 superblock
of partition 2, and prints what a restore depends on: the disk signature
(the PARTUUID in cmdline.txt), partition layout, filesystem magic numbers,
and whether both filesystems were left clean by the shutdown.

    python sd_image_check.py backups/sd_2026-10-02.img
    python sd_image_check.py IMAGE --partuuid 4cd0d5a4 --p1 536870912 --p2 31369723904

Exit status 0 only if every check passes. Works on a .partial file too, as
long as it already covers the start of partition 2.
"""
import argparse
import struct
import sys
from datetime import datetime, timezone

SECTOR = 512


def ts(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if t else "never"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--partuuid", default="4cd0d5a4", help="expected MBR disk signature, hex")
    ap.add_argument("--p1", type=int, default=536870912, help="expected partition 1 size, bytes")
    ap.add_argument("--p2", type=int, default=31369723904, help="expected partition 2 size, bytes")
    a = ap.parse_args()

    fails = []

    def check(ok, what):
        print(f"  [{'PASS' if ok else 'FAIL'}] {what}")
        if not ok:
            fails.append(what)

    with open(a.image, "rb") as f:
        mbr = f.read(SECTOR)
        print("MBR")
        check(mbr[510:512] == b"\x55\xaa", "boot signature 55 AA")
        sig = struct.unpack_from("<I", mbr, 0x1B8)[0]
        check(f"{sig:08x}" == a.partuuid.lower(), f"disk signature {sig:08x} (cmdline.txt PARTUUID {a.partuuid})")
        parts = []
        for i in range(4):
            e = mbr[0x1BE + 16 * i: 0x1BE + 16 * (i + 1)]
            ptype = e[4]
            start, count = struct.unpack_from("<II", e, 8)
            if ptype:
                parts.append((i + 1, ptype, start, count))
                print(f"    p{i + 1}: type 0x{ptype:02x} start sector {start} sectors {count} = {count * SECTOR} bytes")
        check(len(parts) == 2, "two partitions")
        if len(parts) != 2:
            return report(fails)
        (_, t1, s1, c1), (_, t2, s2, c2) = parts
        check(t1 == 0x0C and c1 * SECTOR == a.p1, f"p1 FAT32 LBA (0x0c), {a.p1} bytes")
        check(t2 == 0x83 and c2 * SECTOR == a.p2, f"p2 Linux (0x83), {a.p2} bytes")

        print("p1 FAT32 (/boot/firmware)")
        f.seek(s1 * SECTOR)
        bs = f.read(SECTOR)
        check(bs[510:512] == b"\x55\xaa", "boot sector signature 55 AA")
        check(bs[0x52:0x5A] == b"FAT32   ", f"filesystem type '{bs[0x52:0x5A].decode(errors='replace')}'")
        bps, spc, reserved = struct.unpack_from("<HBH", bs, 0x0B)
        label = bs[0x47:0x52].decode(errors="replace").strip()
        vol_id = struct.unpack_from("<I", bs, 0x43)[0]
        print(f"    label '{label}', volume id {vol_id:08x}, {bps} bytes/sector, {spc} sectors/cluster")
        # FAT[1] carries the clean-shutdown bit (0x08000000) and the
        # no-hard-errors bit (0x04000000). Linux vfat clears the first while mounted.
        f.seek(s1 * SECTOR + reserved * bps + 4)
        fat1 = struct.unpack("<I", f.read(4))[0]
        check(bool(fat1 & 0x08000000), f"FAT clean-shutdown bit set (FAT[1] = {fat1:08x})")
        check(bool(fat1 & 0x04000000), "FAT no-hard-errors bit set")

        print("p2 ext4 (/)")
        f.seek(s2 * SECTOR + 1024)
        sb = f.read(1024)
        if len(sb) < 1024:
            check(False, "image covers the p2 superblock (file too short so far)")
            return report(fails)
        magic = struct.unpack_from("<H", sb, 0x38)[0]
        check(magic == 0xEF53, f"superblock magic {magic:04x}")
        blocks_lo, = struct.unpack_from("<I", sb, 0x04)
        log_bs, = struct.unpack_from("<I", sb, 0x18)
        mtime, wtime = struct.unpack_from("<II", sb, 0x2C)
        mnt_count, = struct.unpack_from("<H", sb, 0x34)
        state, errors_behaviour = struct.unpack_from("<HH", sb, 0x3A)
        incompat, = struct.unpack_from("<I", sb, 0x60)
        uuid = sb[0x68:0x78].hex()
        name = sb[0x78:0x88].split(b"\0")[0].decode(errors="replace")
        blocks_hi, = struct.unpack_from("<I", sb, 0x150) if incompat & 0x80 else (0,)
        err_count, = struct.unpack_from("<I", sb, 0x194)
        bsize = 1024 << log_bs
        fs_bytes = ((blocks_hi << 32) | blocks_lo) * bsize
        print(f"    label '{name}', uuid {uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:]}")
        print(f"    block size {bsize}, filesystem {fs_bytes} bytes, mount count {mnt_count}")
        print(f"    last mount {ts(mtime)}, last write {ts(wtime)}")
        check(fs_bytes <= a.p2, "filesystem fits inside p2")
        check(bool(state & 1), f"state 'clean' bit set (s_state = {state})")
        check(not state & 2, "no 'errors detected' bit")
        check(not incompat & 0x4, f"journal needs_recovery flag clear (incompat = {incompat:08x})")
        check(err_count == 0, f"error count {err_count}")

    return report(fails)


def report(fails):
    print()
    print("ALL CHECKS PASS" if not fails else f"{len(fails)} CHECK(S) FAILED")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
