# Application Workspace (Final)

Application firmware project: `projectA_day1_sht30_mx/`

## Responsibilities

- multi-sensor acquisition and threshold alarms
- custom frame protocol (`0xAA55 + payload + CRC16`)
- dual-UART command interaction and fault tolerance
- runtime handshake with boot state and upgrade status
- CAN command tunnel endpoint for parallel upgrade channel

## Key commands

- acquisition: `GET_PERIOD`, `SET_PERIOD`, `GET_THR`, `SET_THR_*`, `GET_THR2`, `SET_THR_*`
- upgrade/runtime: `GET_VER`, `GET_CAP`, `GET_FLASH`, `GET_BOOTSTATE`, `UPG_*`

Bootloader ownership remains in `bootloader_f407/` and `bootloader/` shared protocol core.
