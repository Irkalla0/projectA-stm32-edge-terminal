#!/usr/bin/env python3
"""
Export application ELF to raw BIN for V2 packaging.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _find_objcopy() -> Path | None:
    from_path = shutil.which("arm-none-eabi-objcopy")
    if from_path:
        return Path(from_path)

    # Fallback: common STM32CubeIDE plugin location used in this workspace.
    plugin_root = Path(r"D:\stm32cubelde\STM32CubeIDE_2.1.1\STM32CubeIDE\plugins")
    if plugin_root.exists():
        matches = sorted(plugin_root.rglob("arm-none-eabi-objcopy.exe"))
        if matches:
            return matches[-1]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Create app.bin from app ELF")
    parser.add_argument(
        "--elf",
        default="projectA_day1_sht30_mx/Debug/projectA_day1_sht30_mx.elf",
        help="input ELF path",
    )
    parser.add_argument("--out", default="build/v2/app.bin", help="output BIN path")
    args = parser.parse_args()

    objcopy = _find_objcopy()
    if not objcopy:
        print("[ERR] arm-none-eabi-objcopy not found in PATH or CubeIDE plugins.")
        return 2

    elf = Path(args.elf).resolve()
    out = Path(args.out).resolve()
    if not elf.exists():
        print(f"[ERR] ELF not found: {elf}")
        return 2

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(objcopy), "-O", "binary", str(elf), str(out)]
    print("[INFO] run:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"[OK] app bin generated: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
