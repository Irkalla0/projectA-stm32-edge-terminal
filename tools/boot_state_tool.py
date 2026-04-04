#!/usr/bin/env python3
"""
Project A V2 boot state helper.

This tool creates and updates a fixed-size boot-state blob that can later be
stored in internal flash or external SPI NOR for rollback decisions.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


MAGIC = b"PAST"
STATE_VERSION = 1
SLOT_NONE = 0xFF

RESULT_UNKNOWN = 0
RESULT_OK = 1
RESULT_ROLLBACK = 2

STATE_FMT = "<4sHBBBBIIIII30sI"
STATE_SIZE = struct.calcsize(STATE_FMT)


@dataclass
class BootState:
    active_slot: int = 0
    pending_slot: int = SLOT_NONE
    boot_attempts: int = 0
    last_result: int = RESULT_UNKNOWN
    seq: int = 0
    slot_a_size: int = 0
    slot_a_crc32: int = 0
    slot_b_size: int = 0
    slot_b_crc32: int = 0


def _slot_to_num(slot: str) -> int:
    s = slot.strip().upper()
    if s == "A":
        return 0
    if s == "B":
        return 1
    if s == "NONE":
        return SLOT_NONE
    raise ValueError("slot must be A/B/NONE")


def _slot_to_text(slot: int) -> str:
    if slot == 0:
        return "A"
    if slot == 1:
        return "B"
    if slot == SLOT_NONE:
        return "NONE"
    return f"UNKNOWN({slot})"


def _result_to_text(result: int) -> str:
    if result == RESULT_UNKNOWN:
        return "unknown"
    if result == RESULT_OK:
        return "ok"
    if result == RESULT_ROLLBACK:
        return "rollback"
    return f"unknown({result})"


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def pack_state(state: BootState) -> bytes:
    pre_crc = struct.pack(
        "<4sHBBBBIIIII30s",
        MAGIC,
        STATE_VERSION,
        state.active_slot & 0xFF,
        state.pending_slot & 0xFF,
        state.boot_attempts & 0xFF,
        state.last_result & 0xFF,
        state.seq & 0xFFFFFFFF,
        state.slot_a_size & 0xFFFFFFFF,
        state.slot_a_crc32 & 0xFFFFFFFF,
        state.slot_b_size & 0xFFFFFFFF,
        state.slot_b_crc32 & 0xFFFFFFFF,
        b"\x00" * 30,
    )
    crc = _crc32(pre_crc)
    return struct.pack(STATE_FMT, *struct.unpack("<4sHBBBBIIIII30s", pre_crc), crc)


def unpack_state(blob: bytes) -> tuple[BootState, dict]:
    if len(blob) != STATE_SIZE:
        raise ValueError(f"state size mismatch: got {len(blob)} expected {STATE_SIZE}")
    (
        magic,
        version,
        active_slot,
        pending_slot,
        boot_attempts,
        last_result,
        seq,
        slot_a_size,
        slot_a_crc32,
        slot_b_size,
        slot_b_crc32,
        reserved,
        crc_read,
    ) = struct.unpack(STATE_FMT, blob)

    pre_crc = struct.pack(
        "<4sHBBBBIIIII30s",
        magic,
        version,
        active_slot,
        pending_slot,
        boot_attempts,
        last_result,
        seq,
        slot_a_size,
        slot_a_crc32,
        slot_b_size,
        slot_b_crc32,
        reserved,
    )
    crc_calc = _crc32(pre_crc)

    if magic != MAGIC:
        raise ValueError(f"bad magic: {magic!r}")
    if version != STATE_VERSION:
        raise ValueError(f"unsupported state version: {version}")

    state = BootState(
        active_slot=active_slot,
        pending_slot=pending_slot,
        boot_attempts=boot_attempts,
        last_result=last_result,
        seq=seq,
        slot_a_size=slot_a_size,
        slot_a_crc32=slot_a_crc32,
        slot_b_size=slot_b_size,
        slot_b_crc32=slot_b_crc32,
    )
    info = {
        "crc_read": f"0x{crc_read:08X}",
        "crc_calc": f"0x{crc_calc:08X}",
        "crc_ok": crc_read == crc_calc,
    }
    return state, info


def state_to_json(state: BootState, extra: dict | None = None) -> dict:
    out = {
        "active_slot": _slot_to_text(state.active_slot),
        "pending_slot": _slot_to_text(state.pending_slot),
        "boot_attempts": state.boot_attempts,
        "last_result": _result_to_text(state.last_result),
        "seq": state.seq,
        "slot_a_size": state.slot_a_size,
        "slot_a_crc32": f"0x{state.slot_a_crc32:08X}",
        "slot_b_size": state.slot_b_size,
        "slot_b_crc32": f"0x{state.slot_b_crc32:08X}",
    }
    if extra:
        out.update(extra)
    return out


def load_state(path: Path) -> BootState:
    blob = path.read_bytes()
    state, _info = unpack_state(blob)
    return state


def save_state(path: Path, state: BootState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack_state(state))


def cmd_create(args: argparse.Namespace) -> int:
    state = BootState(
        active_slot=_slot_to_num(args.active_slot),
        pending_slot=_slot_to_num(args.pending_slot),
        boot_attempts=max(0, min(args.boot_attempts, 255)),
        last_result=args.last_result,
        seq=max(0, args.seq),
        slot_a_size=max(0, args.slot_a_size),
        slot_a_crc32=args.slot_a_crc32 & 0xFFFFFFFF,
        slot_b_size=max(0, args.slot_b_size),
        slot_b_crc32=args.slot_b_crc32 & 0xFFFFFFFF,
    )
    save_state(Path(args.out).resolve(), state)
    print(json.dumps(state_to_json(state, {"path": str(Path(args.out).resolve())}), indent=2))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    blob = Path(args.input).resolve().read_bytes()
    state, info = unpack_state(blob)
    print(json.dumps(state_to_json(state, info | {"path": str(Path(args.input).resolve())}), indent=2))
    if args.strict and not info["crc_ok"]:
        return 2
    return 0


def _load_mutable(path: str) -> tuple[Path, BootState]:
    in_path = Path(path).resolve()
    return in_path, load_state(in_path)


def _write_mutable(path: Path, state: BootState, out: str | None) -> Path:
    dst = Path(out).resolve() if out else path
    save_state(dst, state)
    return dst


def cmd_set_pending(args: argparse.Namespace) -> int:
    path, state = _load_mutable(args.input)
    state.pending_slot = _slot_to_num(args.slot)
    state.boot_attempts = 0
    state.last_result = RESULT_UNKNOWN
    state.seq += 1
    dst = _write_mutable(path, state, args.out)
    print(json.dumps(state_to_json(state, {"path": str(dst)}), indent=2))
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    path, state = _load_mutable(args.input)
    slot = _slot_to_num(args.slot)
    if slot not in (0, 1):
        raise ValueError("--slot for confirm must be A or B")
    state.active_slot = slot
    state.pending_slot = SLOT_NONE
    state.boot_attempts = 0
    state.last_result = RESULT_OK
    state.seq += 1
    dst = _write_mutable(path, state, args.out)
    print(json.dumps(state_to_json(state, {"path": str(dst)}), indent=2))
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    path, state = _load_mutable(args.input)
    state.pending_slot = SLOT_NONE
    state.boot_attempts = 0
    state.last_result = RESULT_ROLLBACK
    state.seq += 1
    dst = _write_mutable(path, state, args.out)
    print(json.dumps(state_to_json(state, {"path": str(dst)}), indent=2))
    return 0


def cmd_fail_once(args: argparse.Namespace) -> int:
    path, state = _load_mutable(args.input)
    state.boot_attempts = min(255, state.boot_attempts + 1)
    state.seq += 1
    if state.boot_attempts >= args.max_attempts and state.pending_slot != SLOT_NONE:
        state.pending_slot = SLOT_NONE
        state.last_result = RESULT_ROLLBACK
        state.boot_attempts = 0
    dst = _write_mutable(path, state, args.out)
    print(json.dumps(state_to_json(state, {"path": str(dst)}), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Project A V2 boot-state helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="create a new boot_state.bin")
    p_create.add_argument("--out", required=True)
    p_create.add_argument("--active-slot", default="A", choices=["A", "B"])
    p_create.add_argument("--pending-slot", default="NONE", choices=["A", "B", "NONE"])
    p_create.add_argument("--boot-attempts", type=int, default=0)
    p_create.add_argument("--last-result", type=int, default=RESULT_UNKNOWN, choices=[0, 1, 2])
    p_create.add_argument("--seq", type=int, default=0)
    p_create.add_argument("--slot-a-size", type=int, default=0)
    p_create.add_argument("--slot-a-crc32", type=lambda x: int(x, 0), default=0)
    p_create.add_argument("--slot-b-size", type=int, default=0)
    p_create.add_argument("--slot-b-crc32", type=lambda x: int(x, 0), default=0)
    p_create.set_defaults(func=cmd_create)

    p_inspect = sub.add_parser("inspect", help="inspect boot_state.bin")
    p_inspect.add_argument("--input", required=True)
    p_inspect.add_argument("--strict", action="store_true")
    p_inspect.set_defaults(func=cmd_inspect)

    p_pending = sub.add_parser("set-pending", help="mark a slot as pending activation")
    p_pending.add_argument("--input", required=True)
    p_pending.add_argument("--slot", required=True, choices=["A", "B"])
    p_pending.add_argument("--out")
    p_pending.set_defaults(func=cmd_set_pending)

    p_confirm = sub.add_parser("confirm", help="confirm pending slot as active")
    p_confirm.add_argument("--input", required=True)
    p_confirm.add_argument("--slot", required=True, choices=["A", "B"])
    p_confirm.add_argument("--out")
    p_confirm.set_defaults(func=cmd_confirm)

    p_rollback = sub.add_parser("rollback", help="clear pending slot and mark rollback")
    p_rollback.add_argument("--input", required=True)
    p_rollback.add_argument("--out")
    p_rollback.set_defaults(func=cmd_rollback)

    p_fail = sub.add_parser("fail-once", help="simulate one failed trial boot")
    p_fail.add_argument("--input", required=True)
    p_fail.add_argument("--max-attempts", type=int, default=3)
    p_fail.add_argument("--out")
    p_fail.set_defaults(func=cmd_fail_once)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
