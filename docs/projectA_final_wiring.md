# 项目A 最终版接线指南

更新日期：2026-04-15

## 1. 核心板与调试口

| 功能 | STM32F407 引脚 | 连接对象 | 说明 |
|---|---|---|---|
| SWDIO | PA13 | 调试器 SWDIO | 下载/调试 |
| SWCLK | PA14 | 调试器 SWCLK | 下载/调试 |
| GND | GND | 调试器 GND | 共地 |
| VTref | 3V3 | 调试器 VTref | 可选参考 |

启动模式：保持 `BOOT0 = 0`。

## 2. UART（双口容错）

### 主串口 UART1

| 功能 | STM32 引脚 | CH340 |
|---|---|---|
| TX | PA9 | RXD |
| RX | PA10 | TXD |
| GND | GND | GND |

### 备串口 UART2

| 功能 | STM32 引脚 | CH340 |
|---|---|---|
| TX | PA2 | RXD |
| RX | PA3 | TXD |
| GND | GND | GND |

## 3. W25Q128（SPI1）

| W25Q128 引脚 | STM32 引脚 | 说明 |
|---|---|---|
| CLK | PA5 | SPI1_SCK |
| DO/MISO | PA6 | SPI1_MISO |
| DI/MOSI | PA7 | SPI1_MOSI |
| CS | PB12 | 低电平有效 |
| VCC | 3V3 | 仅 3.3V |
| GND | GND | 共地 |
| WP# | 3V3 | 上拉 |
| HOLD# | 3V3 | 上拉 |

## 4. CAN 升级链路（CAN1）

| 功能 | STM32 引脚 | 收发器 | 总线 |
|---|---|---|---|
| CAN_RX | PA11 | SN65HVD230 RXD | - |
| CAN_TX | PA12 | SN65HVD230 TXD | - |
| CANH | - | SN65HVD230 CANH | CANH |
| CANL | - | SN65HVD230 CANL | CANL |
| VCC | 3V3 | SN65HVD230 VCC | 3.3V |
| GND | GND | SN65HVD230 GND | 共地 |

- CAN 总线两端都需要 120R 终端电阻。
- USB2CAN 与设备端波特率保持一致（默认 500000）。

## 5. 传感器（4 路异构）

### SHT30（I2C1）

| 功能 | STM32 引脚 |
|---|---|
| SCL | PB6 |
| SDA | PB7 |
| VCC | 3V3 |
| GND | GND |

### VL53L0X + INA219（I2C2）

| 功能 | STM32 引脚 |
|---|---|
| SCL | PB10 |
| SDA | PB11 |
| VCC | 3V3 |
| GND | GND |

- 确保 INA219 地址不与其他 I2C2 从设备冲突。
- I2C 建议保留上拉（典型 4.7k）。

## 6. ESP32 分布式节点

- 最终展示建议：2 个物理 ESP32 + 1 个 STM32 核心节点。
- MQTT Broker：`127.0.0.1:1883`
- 主题根：`projectA/node/{node_id}/...`

## 7. 上电联调检查清单

1. 修改接线前务必先断电。
2. 确认全部模块兼容 3.3V。
3. 检查 MCU、串口、CAN、传感器是否共地。
4. 烧录后确认串口启动日志正常。
5. 依次执行 `GET_FLASH`、`GET_BOOTSTATE`，再启动 Viewer。
