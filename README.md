# Project A - STM32F407 多传感器边缘采集与异常告警终端

`项目A` 的实战开发仓库（从 0 到可演示版本）。当前代码以“先跑通端到端，再替换真实传感器”为策略推进。

## 1. 当前状态（2026-04-03）

- 固件已支持双告警链路：
  - `CMD=0x01/0xA1` 温湿度数据/告警
  - `CMD=0x02/0xA2` 距离电流数据/告警（当前可用模拟通道）
- 上位机已完成：中文 UI、连接状态提示、配置持久化、CSV 落盘
- 串口容错已增强：固件同时支持 `USART1(PA9/PA10)` 与 `USART2(PA2/PA3)`
- 日志与报告链路可用：`logs/*.csv` + `pc_tools/make_demo_report.py`

## 2. 快速启动

### 2.1 编译固件

使用 STM32CubeIDE 编译，或在 PowerShell 使用 GNU Toolchain + make（仓库已含 Debug makefile）。

### 2.2 烧录固件（CMSIS-DAP）

```powershell
& "D:\stm32cubelde\STM32CubeIDE_2.1.1\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.openocd.win32_2.4.400.202601091506\tools\bin\openocd.exe" `
  -s "D:\stm32cubelde\STM32CubeIDE_2.1.1\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.debug.openocd_2.3.300.202602021527\resources\openocd\st_scripts" `
  -f interface/cmsis-dap.cfg `
  -c "transport select swd" `
  -c "adapter speed 1000" `
  -f target/stm32f4x.cfg `
  -c "program {D:/codex/project A/projectA_day1_sht30_mx/Debug/projectA_day1_sht30_mx.elf} verify reset exit"
```

若用 ST-LINK，把 `interface/cmsis-dap.cfg` 改成 `interface/stlink.cfg`。

### 2.3 启动上位机

```powershell
py "D:\codex\project A\pc_tools\uart_frame_viewer.py" --port auto --baud 115200 --csv "D:\codex\project A\logs\run.csv"
```

## 3. 串口接线建议

推荐先用 `USART2`：

- `PA2` = TX（接 CH340 RXD）
- `PA3` = RX（接 CH340 TXD）
- `GND` 必须共地

备份口 `USART1`：

- `PA9` = TX（接 CH340 RXD）
- `PA10` = RX（接 CH340 TXD）

> 固件双串口都能收发，优先保证先看到日志，再接命令回路。

## 4. 排障手册（No data on COMx）

1. 先排除端口占用：不要同时开 `miniterm` 和 `uart_frame_viewer.py`
2. 单向监听法：只接 `TX + GND`，按 `RST` 看是否有 `BOOT_ / SIM / FRAME_HEX`
3. 端口探测脚本：

```powershell
py "D:\codex\project A\pc_tools\find_uart_port.py" --baud 115200 --duration 25
```

4. 若脚本提示 `noise_like` 高，通常是 RX 悬空/线序错/共地问题

## 5. 常用命令

```text
GET_PERIOD
SET_PERIOD 500
GET_THR
SET_THR_T 26.5
SET_THR_H 60
GET_THR2
SET_THR_D 900
SET_THR_I 800
```

## 6. 日志与报告

- 日志目录：`logs/`
- 报告脚本：

```powershell
py "D:\codex\project A\pc_tools\make_demo_report.py" "D:\codex\project A\logs\day11_demo_run.csv"
```

当 CSV 无帧数据时，报告会输出 `WARN: no frame rows found...`，用于快速识别串口链路问题。

## 7. 里程碑提交（节选）

- `8439492` Day1-Day10 基础整合
- `335b9fc` Day15 UI 中文化 + 串口状态显示
- `52837a1` 串口切到 USART2 (PA2/PA3)
- `e528c91` 双串口并行兜底（USART1 + USART2）

## 8. 剩余工作（硬件相关）

以下属于硬件在环，无法在纯离线条件下一次性完结：

- 接入真实 VL53L0X 替换模拟距离通道
- 板级最终接线固定与稳定性长跑（连续 30 分钟+）
- 最终演示录像与现场证据采集

## 9. V2 升级基础设施（已落地）

按《项目A_V2升级文档_新增硬件与软件清单.docx》，当前仓库已先落地第一批可执行基础设施：

- 升级协议草案文档：`docs/protocol/v2_upgrade_uart_protocol.md`
- 固件导出脚本：`tools/make_app_bin.py`
- 固件打包/校验脚本：`tools/pack_fw.py`
- 串口升级脚本：`pc_tools/uart_upgrade_client.py`
- V2 目录骨架：`bootloader/`、`app/`、`tools/`
- 固件命令能力扩展：`GET_VER / GET_CAP / UPG_*`（保持 V1 `GET_/SET_` 兼容）

推荐执行顺序：

1. 编译 `projectA_day1_sht30_mx` 得到最新 `elf`
2. 运行 `tools/make_app_bin.py` 导出 `build/v2/app.bin`
3. 运行 `tools/pack_fw.py pack` 生成 `app_with_header.bin` 与 `upgrade_package.bin`
4. 运行 `tools/pack_fw.py inspect --strict` 做离线完整性检查
5. 运行 `pc_tools/uart_upgrade_client.py` 走 UART 升级闭环

## 10. 下一阶段（按最小风险）

1. 固件新增 `GET_VER` / `GET_CAP`（保持 V1 协议兼容）
2. 在不破坏现有采样路径下，新增 UART 升级状态机命令：
   - `UPG_BEGIN / UPG_DATA / UPG_END / UPG_STATUS / UPG_ABORT`
3. 上位机新增“升级页”并复用现有串口链路
4. 完成异常用例：断电、错包、CRC 错、非法版本
5. 第二阶段再做外部 SPI Flash 回滚与 CAN 升级链路
