# Bootloader Workspace (V2)

This directory is reserved for the Project A V2 bootloader sub-project.

Planned scope (phase 1):

- Enter boot mode and report version/capability.
- Receive image package over UART.
- Erase/write app area.
- Verify image CRC32 before activation.
- Persist minimal upgrade state for power-loss recovery.

Phase 2:

- Dual-slot / rollback with external SPI NOR flash.
- CAN transport path compatible with UART upgrade commands.
