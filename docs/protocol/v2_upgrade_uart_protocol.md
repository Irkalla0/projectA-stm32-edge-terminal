# Project A V2 UART Upgrade Protocol (Draft)

This document defines a minimal upgrade protocol that can be implemented on top
of the current UART text-command channel without breaking V1 telemetry.

## 1. Goals

- Keep V1 data path (`FRAME_HEX`, `SET_*`, `GET_*`) backward compatible.
- Add V2 firmware update flow with explicit state and error codes.
- Support resume/retry by using `offset` + `chunk_crc32`.

## 2. Capability Negotiation

Host should query capability before upgrade:

- `GET_VER`
- `GET_CAP`

Suggested responses:

- `VER:app=1.4.0,boot=0.1.0`
- `CAP:upgrade_uart=1,max_chunk=128,dual_slot=0`

## 3. Upgrade State Model

- `idle`
- `receiving`
- `received`
- `activating`
- `pending_confirm`
- `confirmed`
- `rollback_required`
- `error`

Status query:

- request: `UPG_STATUS`
- response: `UPG_STATUS:<state>,off=<bytes>,err=<code>`

## 4. Command Set (Text Line Based)

### 4.1 Begin

- request:
  `UPG_BEGIN <ver> <size> <image_crc32>`
- response:
  - `UPG_ACK BEGIN off=0`
  - or `UPG_NACK BEGIN <err>`

### 4.2 Data Chunk

- request:
  `UPG_DATA <offset> <hex_payload> <chunk_crc32>`
- response:
  - `UPG_ACK DATA off=<next_offset>`
  - or `UPG_NACK DATA <err>`

### 4.3 End

- request:
  `UPG_END`
- response:
  - `UPG_ACK END`
  - or `UPG_NACK END <err>`

### 4.4 Activate

- request:
  `UPG_ACTIVATE`
- response:
  - `UPG_ACK ACTIVATE`
  - device reboots

### 4.5 Confirm First Boot

- request:
  `UPG_CONFIRM`
- response:
  - `UPG_ACK CONFIRM`

### 4.6 Abort

- request:
  `UPG_ABORT`
- response:
  - `UPG_ACK ABORT`

## 5. Error Codes (Recommended)

- `E_STATE`: invalid state transition
- `E_ARG`: invalid parameter
- `E_OFF`: offset mismatch
- `E_CRC_CHUNK`: chunk crc mismatch
- `E_CRC_IMAGE`: full image crc mismatch
- `E_FLASH`: flash erase/write failed
- `E_VER`: illegal version or downgrade not allowed
- `E_TIMEOUT`: transfer timeout

## 6. Upgrade Package

Use `tools/pack_fw.py` to generate package with a fixed 64-byte header:

- magic
- header size/version
- image size/crc32
- semantic version
- build unix timestamp
- board id
- git short sha

## 7. Implementation Notes

- Phase 1 can be single-slot (no rollback) but must persist state.
- Phase 2 can add external SPI flash and dual-slot rollback.
- Keep max chunk small first (64/128 bytes) for robust UART recovery.
- Current firmware implementation validates `UPG_*` state and CRC in RAM for integration testing.
- Flash write/swap/rollback is reserved for the next step (`bootloader/` + app jump flow).
