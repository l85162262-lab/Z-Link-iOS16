#!/usr/bin/env python3
"""把 IPA 的部署目标降到指定 iOS 版本。

同时处理两处：
  1. 每个 bundle（.app / .appex / .framework）Info.plist 的 MinimumOSVersion
  2. 每个 Mach-O 的 LC_BUILD_VERSION.minos（含 fat/arm64 slice）

用法：
    python lower_minos.py input.ipa output.ipa --min-os 16.7
"""

import argparse
import hashlib
import os
import plistlib
import shutil
import struct
import sys
import tempfile
import zipfile

LC_BUILD_VERSION = 0x32
LC_VERSION_MIN_IPHONEOS = 0x25


def parse_version(text):
    parts = [int(p) for p in text.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def pack_version(v):
    return (v[0] << 16) | (v[1] << 8) | v[2]


def format_version(x):
    return f"{x >> 16}.{(x >> 8) & 0xff}.{x & 0xff}"


def macho_slices(data):
    magic = struct.unpack(">I", data[:4])[0]
    if magic == 0xCAFEBABE:
        n = struct.unpack(">I", data[4:8])[0]
        return [(struct.unpack(">5I", data[8 + i * 20:28 + i * 20])[2],
                 struct.unpack(">5I", data[8 + i * 20:28 + i * 20])[3]) for i in range(n)]
    if magic == 0xCAFEBABF:
        n = struct.unpack(">I", data[4:8])[0]
        out = []
        for i in range(n):
            _, _, off, size, _, _ = struct.unpack(">IIQQII", data[8 + i * 32:40 + i * 32])
            out.append((off, size))
        return out
    return [(0, len(data))]


def is_macho(data):
    if len(data) < 32:
        return False
    magic_le = struct.unpack("<I", data[:4])[0]
    return magic_le in (0xFEEDFACF, 0xFEEDFACE, 0xCAFEBABE, 0xCAFEBABF) or \
        struct.unpack(">I", data[:4])[0] in (0xCAFEBABE, 0xCAFEBABF)


def patch_macho(path, target):
    with open(path, "rb") as f:
        data = bytearray(f.read())
    if not is_macho(data):
        return []
    changes = []
    for s_off, _ in macho_slices(bytes(data)):
        ncmds = struct.unpack("<I", data[s_off + 16:s_off + 20])[0]
        p = s_off + 32
        for _ in range(ncmds):
            cmd, size = struct.unpack("<II", data[p:p + 8])
            if cmd == LC_BUILD_VERSION:
                old = struct.unpack("<I", data[p + 12:p + 16])[0]
                data[p + 12:p + 16] = struct.pack("<I", pack_version(target))
                changes.append((p + 12, old, pack_version(target)))
            elif cmd == LC_VERSION_MIN_IPHONEOS:
                old = struct.unpack("<I", data[p + 8:p + 12])[0]
                data[p + 8:p + 12] = struct.pack("<I", pack_version(target))
                changes.append((p + 8, old, pack_version(target)))
            p += size
    with open(path, "wb") as f:
        f.write(data)
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--min-os", default="16.7")
    args = ap.parse_args()

    target = parse_version(args.min_os)
    target_str = ".".join(str(x) for x in target[:2])

    work = tempfile.mkdtemp(prefix="lower-minos-")
    try:
        with zipfile.ZipFile(args.input) as z:
            z.extractall(work)

        # 1. Info.plist
        plist_changes = []
        for root, _, files in os.walk(work):
            if "Info.plist" not in files:
                continue
            if not any(seg.endswith((".app", ".appex", ".framework")) for seg in root.split(os.sep)):
                continue
            path = os.path.join(root, "Info.plist")
            with open(path, "rb") as f:
                pl = plistlib.load(f)
            old = pl.get("MinimumOSVersion")
            if old is None or tuple(int(x) for x in str(old).split(".")[:2]) >= target[:2]:
                pl["MinimumOSVersion"] = target_str
                with open(path, "wb") as f:
                    plistlib.dump(pl, f, fmt=plistlib.FMT_BINARY, sort_keys=False)
                plist_changes.append((os.path.relpath(path, work), old, target_str))

        # 2. Mach-O
        macho_changes = []
        for root, _, files in os.walk(work):
            for name in files:
                path = os.path.join(root, name)
                if os.path.islink(path) or not os.path.isfile(path):
                    continue
                with open(path, "rb") as f:
                    head = f.read(4)
                if len(head) < 4:
                    continue
                if struct.unpack("<I", head)[0] not in (0xFEEDFACF, 0xCAFEBABE, 0xCAFEBABF):
                    continue
                changes = patch_macho(path, target)
                for off, old, new in changes:
                    macho_changes.append((os.path.relpath(path, work), off, old, new))

        # 3. 重新打包，保留可执行位
        def mode_for(rel):
            base = os.path.basename(rel)
            if rel.count(os.sep) == 2 and base not in ("Info.plist",):
                return 0o755
            return 0o644

        if os.path.exists(args.output):
            os.remove(args.output)
        with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for root, dirs, files in os.walk(work):
                dirs.sort()
                for name in sorted(files):
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, work).replace(os.sep, "/")
                    info = zipfile.ZipInfo(rel)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = (0o100000 | mode_for(rel)) << 16
                    with open(full, "rb") as f:
                        z.writestr(info, f.read())

        print(f"[plist] {len(plist_changes)} bundle(s)")
        for rel, old, new in plist_changes:
            print(f"  {rel}: {old} -> {new}")
        print(f"[macho] {len(macho_changes)} build-version command(s)")
        for rel, off, old, new in macho_changes:
            print(f"  {rel} @ {off:#x}: {format_version(old)} -> {format_version(new)}")
        print(f"[out] {args.output}")
        print(f"[sha256] {hashlib.sha256(open(args.output, 'rb').read()).hexdigest()}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
