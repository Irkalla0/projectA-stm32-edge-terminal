# Bootloader F407 Workspace

Independent bootloader workspace for Project A final delivery.

## Responsibilities

- verify slot images (A/B)
- read/write redundant boot state on W25Q128
- select active/pending slot
- rollback after failed trial attempts
- jump to selected application slot
- accept upgrade data from UART/CAN tunnel

## Memory Layout

- Bootloader: `0x08000000 ~ 0x0801FFFF`
- App Slot A: `0x08020000 ~ 0x0807FFFF`
- App Slot B: `0x08080000 ~ 0x080DFFFF`
- Reserved: `0x080E0000 ~ 0x080FFFFF`

## Source Files

- `include/boot_cfg.h`: flash map and constants
- `include/boot_storage.h`: W25 boot-state storage interface
- `include/boot_upgrade.h`: upgrade session interface
- `src/boot_storage_w25.c`: redundant boot-state persistence
- `src/boot_upgrade.c`: slot metadata and commit/rollback flow
- `src/main.c`: boot decision + jump skeleton

This workspace is intentionally decoupled from application logic to preserve clear boot/app boundaries.
