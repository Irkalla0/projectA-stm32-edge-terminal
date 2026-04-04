# Project A V2 Boot State Layout (Draft)

This file defines a compact boot-state blob for phase-2 rollback flow.

## 1. Purpose

- Persist active/pending slot selection.
- Track trial boot attempts.
- Record last upgrade outcome for diagnostics.
- Protect state integrity with CRC32.

## 2. Binary Layout (64 bytes)

Little-endian packed structure:

| Offset | Size | Field |
|---|---:|---|
| 0x00 | 4 | magic = `PAST` |
| 0x04 | 2 | state_version (`1`) |
| 0x06 | 1 | active_slot (`0=A`, `1=B`) |
| 0x07 | 1 | pending_slot (`0=A`, `1=B`, `0xFF=NONE`) |
| 0x08 | 1 | boot_attempts |
| 0x09 | 1 | last_result (`0=unknown`, `1=ok`, `2=rollback`) |
| 0x0A | 4 | seq (monotonic update counter) |
| 0x0E | 4 | slot_a_size |
| 0x12 | 4 | slot_a_crc32 |
| 0x16 | 4 | slot_b_size |
| 0x1A | 4 | slot_b_crc32 |
| 0x1E | 30 | reserved |
| 0x3C | 4 | crc32 of bytes `[0x00..0x3B]` |

## 3. State Transition Hints

- Upgrade start: set `pending_slot=B`, `boot_attempts=0`, `last_result=unknown`.
- First boot successful: set `active_slot=B`, clear `pending_slot`, `last_result=ok`.
- First boot repeatedly fails (e.g. >=3): clear `pending_slot`, `last_result=rollback`.

## 4. Tooling

Use:

`tools/boot_state_tool.py`

for:

- `create`
- `inspect`
- `set-pending`
- `confirm`
- `rollback`
- `fail-once`

