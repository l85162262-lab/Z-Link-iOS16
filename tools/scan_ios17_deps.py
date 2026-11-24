#!/usr/bin/env python3
"""扫描 IPA 中引用的 iOS 17/18 新增 API 符号。

判断依据：Mach-O 未定义符号（N_UNDF|N_EXT）名称里是否包含已知 17+ API 关键字，
并区分强绑定 / 弱绑定。强绑定 + 系统版本低于符号要求 => 启动即崩。

用法：
    python scan_ios17_deps.py app.ipa
退出码：发现强绑定的 17+ 依赖时返回 1。
"""

import os
import struct
import sys
import tempfile
import zipfile

KNOWN = {
    "containerRelativeFrame": "17.0",
    "scrollTargetBehavior": "17.0",
    "scrollPosition2id6anchor": "17.0",
    "symbolEffect": "17.0",
    "containerBackground": "17.0",
    "ContentUnavailable": "17.0",
    "PhaseAnimator": "17.0",
    "KeyframeAnimator": "17.0",
    "onKeyPress": "17.0",
    "chartScrollableAxes": "17.0",
    "chartXSelection": "17.0",
    "LiveActivityIntent": "17.0",
    "viewIsAppearing": "17.0",
    "SwiftData": "17.0",
    "TipKit": "17.0",
    "onScrollGeometryChange": "18.0",
    "onGeometryChange": "18.0",
    "MeshGradient": "18.0",
    "zoomTransition": "18.0",
    "scrollPosition": "17.0",
}


def slices(data):
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


def undefined_symbols(data):
    out = []
    for off, _ in slices(data):
        if off + 32 > len(data):
            continue
        ncmds = struct.unpack("<I", data[off + 16:off + 20])[0]
        p = off + 32
        symtab = None
        for _ in range(ncmds):
            cmd, size = struct.unpack("<II", data[p:p + 8])
            if cmd == 0x2:
                symtab = struct.unpack("<IIII", data[p + 8:p + 24])
            p += size
        if not symtab:
            continue
        symoff, nsyms, stroff, strsize = symtab
        for i in range(nsyms):
            strx, ntype, sect, desc, value = struct.unpack("<IBBHQ", data[symoff + i * 16:symoff + (i + 1) * 16])
            if ntype & 0x01 and (ntype & 0x0e) == 0:
                name = data[stroff + strx:stroff + strsize].split(b"\x00")[0].decode("latin-1")
                out.append((name, bool(desc & 0x40)))
    return out


def main(path):
    work = tempfile.mkdtemp(prefix="scan-deps-")
    with zipfile.ZipFile(path) as z:
        z.extractall(work)
    strong_hits = 0
    for root, _, files in os.walk(work):
        for name in files:
            full = os.path.join(root, name)
            if os.path.islink(full) or not os.path.isfile(full) or os.path.getsize(full) < 4096:
                continue
            with open(full, "rb") as f:
                head = f.read(4)
            if struct.unpack("<I", head)[0] not in (0xFEEDFACF, 0xCAFEBABE, 0xCAFEBABF):
                continue
            with open(full, "rb") as f:
                data = f.read()
            syms = undefined_symbols(data)
            hits = []
            for s, weak in syms:
                for token, ver in KNOWN.items():
                    if token in s:
                        hits.append((token, ver, weak, s))
                        break
            if hits:
                print(f"\n== {os.path.relpath(full, work)} ({len(hits)} symbol(s))")
                for token, ver, weak, s in sorted(set(hits)):
                    tag = "WEAK" if weak else "STRONG"
                    print(f"  [{tag}] iOS {ver}+  {token}")
                    if not weak:
                        strong_hits += 1
    if strong_hits:
        print(f"\n发现 {strong_hits} 个强绑定 iOS 17+ 符号：仅改 MinimumOSVersion 会在启动时 Symbol not found。")
        return 1
    print("\n未发现强绑定 iOS 17+ 依赖。")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
