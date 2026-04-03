#!/usr/bin/env python3
"""
Pack and inspect Project A V2 firmware packages.

Package format:
  [64-byte header][raw app payload]
"""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path


MAGIC = b"PAFW"
HEADER_VERSION = 1
HEADER_FMT = "<4sHHIIHHHI16s12s10s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = version.strip().split(".")
    if len(parts) != 3:
        raise ValueError("version must be MAJOR.MINOR.PATCH")
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def _clean_ascii(text: str, max_len: int) -> bytes:
    raw = text.encode("ascii", errors="ignore")[:max_len]
    return raw.ljust(max_len, b"\x00")


def _get_git_sha_fallback() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out if out else "unknown"
    except Exception:
        return "unknown"


def pack_image(
    app_bin: Path,
    out_dir: Path,
    version: str,
    board: str,
    git_sha: str | None,
) -> dict:
    payload = app_bin.read_bytes()
    payload_size = len(payload)
    payload_crc = zlib.crc32(payload) & 0xFFFFFFFF
    ver_major, ver_minor, ver_patch = _parse_version(version)
    build_unix = int(time.time())
    git_short = (git_sha or _get_git_sha_fallback())[:12]

    header = struct.pack(
        HEADER_FMT,
        MAGIC,
        HEADER_SIZE,
        HEADER_VERSION,
        payload_size,
        payload_crc,
        ver_major,
        ver_minor,
        ver_patch,
        build_unix,
        _clean_ascii(board, 16),
        _clean_ascii(git_short, 12),
        b"\x00" * 10,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    app_with_header = out_dir / "app_with_header.bin"
    upgrade_pkg = out_dir / "upgrade_package.bin"
    manifest_path = out_dir / "upgrade_manifest.json"

    blob = header + payload
    app_with_header.write_bytes(blob)
    upgrade_pkg.write_bytes(blob)

    manifest = {
        "magic": MAGIC.decode("ascii"),
        "header_size": HEADER_SIZE,
        "header_version": HEADER_VERSION,
        "version": version,
        "board": board,
        "git_sha": git_short,
        "build_unix": build_unix,
        "image_size": payload_size,
        "image_crc32": f"0x{payload_crc:08X}",
        "app_bin": str(app_bin),
        "app_with_header_bin": str(app_with_header),
        "upgrade_package_bin": str(upgrade_pkg),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def inspect_package(pkg_path: Path) -> dict:
    data = pkg_path.read_bytes()
    if len(data) < HEADER_SIZE:
        raise ValueError(f"file too small: {len(data)} bytes")

    (
        magic,
        header_size,
        header_ver,
        image_size,
        image_crc,
        vmaj,
        vmin,
        vpat,
        build_unix,
        board_raw,
        sha_raw,
        _reserved,
    ) = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])

    if magic != MAGIC:
        raise ValueError(f"invalid magic: {magic!r}")
    if header_size != HEADER_SIZE:
        raise ValueError(f"invalid header_size: {header_size}")

    payload = data[HEADER_SIZE : HEADER_SIZE + image_size]
    calc_crc = zlib.crc32(payload) & 0xFFFFFFFF
    crc_ok = calc_crc == image_crc

    return {
        "path": str(pkg_path),
        "magic": magic.decode("ascii"),
        "header_size": header_size,
        "header_version": header_ver,
        "version": f"{vmaj}.{vmin}.{vpat}",
        "build_unix": build_unix,
        "board": board_raw.rstrip(b"\x00").decode("ascii", errors="ignore"),
        "git_sha": sha_raw.rstrip(b"\x00").decode("ascii", errors="ignore"),
        "image_size": image_size,
        "image_crc32_header": f"0x{image_crc:08X}",
        "image_crc32_calc": f"0x{calc_crc:08X}",
        "crc_ok": crc_ok,
        "total_file_size": len(data),
    }


def _cmd_pack(args: argparse.Namespace) -> int:
    manifest = pack_image(
        app_bin=Path(args.input).resolve(),
        out_dir=Path(args.out_dir).resolve(),
        version=args.version,
        board=args.board,
        git_sha=args.git_sha,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    info = inspect_package(Path(args.input).resolve())
    print(json.dumps(info, indent=2, ensure_ascii=False))
    if args.strict and not info["crc_ok"]:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pack/inspect Project A V2 firmware package")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pack = sub.add_parser("pack", help="pack app.bin into V2 package")
    p_pack.add_argument("--input", required=True, help="input app binary path")
    p_pack.add_argument("--version", required=True, help="semantic version, e.g. 2.0.0")
    p_pack.add_argument("--board", default="STM32F407ZGTx")
    p_pack.add_argument("--git-sha", default=None, help="optional short sha; auto from git when omitted")
    p_pack.add_argument("--out-dir", default="build/v2")
    p_pack.set_defaults(func=_cmd_pack)

    p_ins = sub.add_parser("inspect", help="inspect existing package")
    p_ins.add_argument("--input", required=True, help="package path")
    p_ins.add_argument("--strict", action="store_true", help="return non-zero when CRC check fails")
    p_ins.set_defaults(func=_cmd_inspect)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
