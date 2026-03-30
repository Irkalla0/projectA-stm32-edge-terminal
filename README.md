# Project A - STM32F407 多传感器边缘采集与异常告警终端

本仓库是 `项目A` 的实战开发记录，面向从 0 开始的嵌入式学习与演示交付。  
当前已完成：UART 协议、温湿度采集/模拟、双通道告警、上位机波形与参数配置、配置持久化。

## 1. 项目目标

- 主控：`STM32F407ZGT6`
- 串口通信：`USART1 @ 115200`
- 协议要求：帧头、命令字、长度、序号、时间戳、CRC16
- 上位机：实时波形 + 参数下发 + CSV 记录
- 告警：至少两类（当前实现 A1 温湿度、A2 距离/电流）

## 2. 已实现功能（截至 Day13）

- `CMD=0x01`：温湿度数据帧
- `CMD=0xA1`：温湿度告警帧
- `CMD=0x02`：距离/电流数据帧（当前为模拟通道）
- `CMD=0xA2`：距离/电流告警帧（当前为模拟通道）
- 参数命令：
  - `SET_PERIOD / GET_PERIOD`
  - `SET_THR_T / SET_THR_H / GET_THR`
  - `SET_THR_D / SET_THR_I / GET_THR2`
- 上位机工具：
  - 自动识别串口
  - 波形显示与告警帧打印
  - CSV 落盘
  - 按钮配置（GET/SET/PRESET）
  - 配置持久化（`viewer_config.json` 自动保存与自动下发）

## 3. 仓库结构

```text
project A/
├─ projectA_day1_sht30_mx/      # STM32CubeIDE 工程
├─ pc_tools/
│  ├─ uart_frame_viewer.py      # 上位机波形与命令工具
│  └─ find_uart_port.py         # 串口辅助探测脚本
├─ logs/                        # 实验记录与 CSV 证据
└─ README.md
```

## 4. 本地开发环境

- Windows 11
- STM32CubeIDE 2.1.1
- Python 3.x
- OpenOCD（使用 CubeIDE 自带）

## 5. 烧录步骤（CMSIS-DAP / Mini HSDAP）

先在 CubeIDE 编译生成 `elf`，然后在 PowerShell 执行：

```powershell
& "D:\stm32cubelde\STM32CubeIDE_2.1.1\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.openocd.win32_2.4.400.202601091506\tools\bin\openocd.exe" `
  -s "D:\stm32cubelde\STM32CubeIDE_2.1.1\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.debug.openocd_2.3.300.202602021527\resources\openocd\st_scripts" `
  -f interface/cmsis-dap.cfg `
  -c "transport select swd" `
  -c "adapter speed 1000" `
  -f target/stm32f4x.cfg `
  -c "program {D:/codex/project A/projectA_day1_sht30_mx/Debug/projectA_day1_sht30_mx.elf} verify reset exit"
```

成功标志：

- `** Programming Finished **`
- `** Verified OK **`

## 6. 上位机运行

```powershell
py "D:\codex\project A\pc_tools\uart_frame_viewer.py" --port auto --baud 115200 --csv "D:\codex\project A\logs\run.csv"
```

可选参数：

- `--set-period 500`：启动后设置采样周期
- `--points 180`：波形显示点数
- `--raw`：打印未识别原始行

## 7. 常用串口命令

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

## 8. Git 历史里程碑

- `8439492`：Day1-Day10 基础功能与协议/工具整合
- `05b1828`：仓库清理（忽略本地备份）
- `2dc8bc1`：Day12 上位机按钮化命令控制
- `5ea5acf`：Day13 参数持久化与自动恢复

## 9. 后续计划

- Day14：UI 中文化 + 连接状态灯
- Day15+：接入真实 VL53L0X（焊接后）替换模拟距离通道
- 后续阶段：FreeRTOS 多任务拆分与模块化

