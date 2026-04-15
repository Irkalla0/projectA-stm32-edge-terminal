# Project A Final Wiring Guide

Updated: 2026-04-15

## 1. Core Board and Debug

| Function | STM32F407 Pin | Target | Notes |
|---|---|---|---|
| SWDIO | PA13 | debugger SWDIO | flashing/debug |
| SWCLK | PA14 | debugger SWCLK | flashing/debug |
| GND | GND | debugger GND | common ground |
| VTref | 3V3 | debugger VTref | optional reference |

Boot mode: keep `BOOT0 = 0`.

## 2. UART (Dual Redundancy)

### Primary UART1

| Function | STM32 Pin | CH340 |
|---|---|---|
| TX | PA9 | RXD |
| RX | PA10 | TXD |
| GND | GND | GND |

### Backup UART2

| Function | STM32 Pin | CH340 |
|---|---|---|
| TX | PA2 | RXD |
| RX | PA3 | TXD |
| GND | GND | GND |

## 3. W25Q128 (SPI1)

| W25Q128 Pin | STM32 Pin | Notes |
|---|---|---|
| CLK | PA5 | SPI1_SCK |
| DO/MISO | PA6 | SPI1_MISO |
| DI/MOSI | PA7 | SPI1_MOSI |
| CS | PB12 | low active |
| VCC | 3V3 | 3.3V only |
| GND | GND | common ground |
| WP# | 3V3 | pull-up |
| HOLD# | 3V3 | pull-up |

## 4. CAN Upgrade Link (CAN1)

| Function | STM32 Pin | Transceiver | Bus |
|---|---|---|---|
| CAN_RX | PA11 | SN65HVD230 RXD | - |
| CAN_TX | PA12 | SN65HVD230 TXD | - |
| CANH | - | SN65HVD230 CANH | CANH |
| CANL | - | SN65HVD230 CANL | CANL |
| VCC | 3V3 | SN65HVD230 VCC | 3.3V |
| GND | GND | SN65HVD230 GND | common ground |

- Add 120R termination at both ends of CAN bus.
- USB2CAN should use the same bitrate (default 500000).

## 5. Sensors (4-Channel Heterogeneous)

### SHT30 on I2C1

| Function | STM32 Pin |
|---|---|
| SCL | PB6 |
| SDA | PB7 |
| VCC | 3V3 |
| GND | GND |

### VL53L0X + INA219 on I2C2

| Function | STM32 Pin |
|---|---|
| SCL | PB10 |
| SDA | PB11 |
| VCC | 3V3 |
| GND | GND |

- Ensure INA219 address differs from any other I2C2 slave.
- Keep I2C pull-ups (4.7k typical).

## 6. ESP32 Distributed Nodes

- Node count for showcase: 2 physical ESP32 + 1 STM32 core node.
- MQTT broker host: `127.0.0.1:1883`.
- Node topic root: `projectA/node/{node_id}/...`.

## 7. Bring-up Checklist

1. Power off before wiring updates.
2. Verify all modules are 3.3V compatible.
3. Check common ground for MCU, UART, CAN, sensors.
4. Flash firmware and confirm serial boot log.
5. Run `GET_FLASH`, `GET_BOOTSTATE`, then start viewer.
