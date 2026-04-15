# 项目A后续工作全量实施手册（接线+代码+命令+GitHub）

更新时间：2026-04-14
主分支：`codex/w25q128-integration`
仓库：`https://github.com/Irkalla0/projectA-stm32-edge-terminal`

## 1. 最终目标（完成定义）
- 完成硬件闭环：STM32 + W25Q128 + 串口 +（可选）ESP32节点。
- 完成软件闭环：采集、升级、分析预测、分布式汇聚、异常检测。
- 完成交付闭环：日志证据、报告文档、简历条目、GitHub可复现。

## 2. 硬件与接线（完整）

## 2.1 STM32烧录与调试（必须）

| 功能 | STM32引脚 | 连接设备 | 说明 |
|---|---|---|---|
| SWDIO | PA13 | 下载器 SWDIO | 烧录/调试 |
| SWCLK | PA14 | 下载器 SWCLK | 烧录/调试 |
| GND | GND | 下载器 GND | 共地 |
| 3V3(可选) | 3.3V | 下载器 VTref | 仅参考电压 |

注意：`BOOT0=0`（启动到主Flash）。

## 2.2 UART命令与日志（必须）

推荐口：USART1

| 功能 | STM32引脚 | CH340引脚 |
|---|---|---|
| TX | PA9 | RXD |
| RX | PA10 | TXD |
| GND | GND | GND |

备用口：USART2

| 功能 | STM32引脚 | CH340引脚 |
|---|---|---|
| TX | PA2 | RXD |
| RX | PA3 | TXD |
| GND | GND | GND |

## 2.3 W25Q128外部Flash（M1必须）

| W25Q128引脚 | STM32引脚 | 说明 |
|---|---|---|
| CLK | PA5 (SPI1_SCK) | SPI时钟 |
| DO / MISO | PA6 (SPI1_MISO) | Flash->MCU |
| DI / MOSI | PA7 (SPI1_MOSI) | MCU->Flash |
| CS | PB12 (GPIO输出) | 片选（低有效） |
| VCC | 3.3V | 只能3.3V |
| GND | GND | 共地 |
| WP# | 3.3V | 上拉防写保护 |
| HOLD# | 3.3V | 上拉防挂起 |

## 2.4 分布式节点（M4）
- ESP32节点（2块最佳，1块也可 + 1仿真节点）。
- 节点传感器可先仿真，不阻塞主流程。

---

## 3. 代码结构（你要改/要跑的文件）

## 3.1 固件
- `projectA_day1_sht30_mx/Core/Src/main.c`
- `projectA_day1_sht30_mx/Core/Src/stm32f4xx_hal_msp.c`

关键能力已集成：
- UART升级状态机 + BootState
- SPI1 + W25Q128识别/读写
- 串口命令：`GET_FLASH`、`BOOT_SAVE`、`BOOT_LOAD`

## 3.2 PC脚本
- `pc_tools/uart_cmd_once.py`（新增，一条命令一条验证）
- `pc_tools/uart_link_diag.py`
- `pc_tools/uart_upgrade_client.py`
- `pc_tools/v1_regression_check.py`
- `pc_tools/analyze_and_forecast.py`
- `pc_tools/distributed_aggregator.py`
- `pc_tools/mqtt_node_sim.py`
- `pc_tools/v2_reliability_report.py`

## 3.3 自动化执行脚本
- `tools/projectA_full_rollout.ps1`（新增，按M1~M6阶段执行）

---

## 4. 环境准备（一次性）

## 4.1 Python依赖
```powershell
py -m pip install pyserial pandas numpy scikit-learn statsmodels paho-mqtt
```

## 4.2 MQTT Broker（本机）
- 安装 Mosquitto，默认端口 `1883`。
- 启动后确认 `127.0.0.1:1883` 可访问。

## 4.3 固件编译与烧录
- 编译：STM32CubeIDE Build。
- 产物：`projectA_day1_sht30_mx/Debug/projectA_day1_sht30_mx.elf`
- 烧录（OpenOCD）参考 `README.md` 中命令，或 IDE 直接下载。

---

## 5. 完整执行步骤（M1~M6）

## M1 W25持久化闭环（必须先做）
1. 完成W25接线（见2.3）。
2. 烧录最新固件。
3. 串口验证：
```powershell
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --cmd GET_FLASH --expect "id=0xEF4018"
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --cmd BOOT_SAVE
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --cmd BOOT_LOAD
py "D:\codex\project A\pc_tools\uart_cmd_once.py" --port COM6 --cmd GET_BOOTSTATE
```
4. 复位后再执行一次 `GET_BOOTSTATE`。

验收：能看到 `id=0xEF4018` 且 `BOOT_LOAD:OK`。

## M2 升级闭环（最小可靠性）
```powershell
py "D:\codex\project A\pc_tools\uart_link_diag.py" --port COM6 --scan-seconds 2 --cmd-wait-seconds 1.2 --retries 2

py "D:\codex\project A\pc_tools\uart_upgrade_client.py" `
  --pkg "D:\codex\project A\build\v2\upgrade_package.bin" `
  --port COM6 --chunk 128 --ack-timeout 12 --query-retries 5 `
  --ctrl-char-delay-ms 20 --data-char-delay-ms 2 --preflush-newlines 1 `
  --activate --confirm --abort-on-fail
```

验收：`UPG_STATUS:confirmed`，`pending=NONE`。

## M3 分析+预测闭环
```powershell
py "D:\codex\project A\pc_tools\analyze_and_forecast.py" `
  "D:\codex\project A\logs\day11_demo_run.csv" `
  "D:\codex\project A\logs\day14_demo.csv" `
  --resample-seconds 30 --horizon-steps 60 `
  --out-dir "D:\codex\project A\build\analysis"
```

验收：生成 `analysis_report.txt`、`forecast.csv`、`anomaly_events.csv`。

## M4 分布式最小拓扑（1实物+1仿真）
```powershell
py "D:\codex\project A\pc_tools\distributed_aggregator.py" `
  --enable-mqtt --mqtt-host 127.0.0.1 --mqtt-port 1883 `
  --serial-csv "D:\codex\project A\logs\run.csv" `
  --runtime-s 130

py "D:\codex\project A\pc_tools\mqtt_node_sim.py" `
  --node-id esp32_sim_01 --mqtt-host 127.0.0.1 --mqtt-port 1883 --runtime-s 120
```

验收：`logs/distributed_telemetry.csv` 与 `logs/distributed.db` 有双源数据。

## M5 异常检测组合
- 在 M3/M4 数据上继续运行 `analyze_and_forecast.py`。
- 输出并检查：异常事件条数、分级字段、分数与阈值。

## M6 文档与简历封板
1. 更新状态文档：`docs/projectA_master_plan_full_sync_2026-04-14.md`
2. 生成最终说明：`docs/项目A_最终版.docx`
3. 生成简历条目：`docs/resume_projectA_bullets.md`

---

## 6. 一键阶段脚本（推荐）

先只打印命令（安全）：
```powershell
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m1
```

执行阶段命令：
```powershell
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m1 -Port COM6 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m2 -Port COM6 -Execute
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m3 -Execute
```

如果要脚本内自动烧录，补充：
- `-OpenOcdExe <openocd.exe路径>`
- `-OpenOcdScripts <st_scripts目录路径>`

---

## 7. GitHub同步（每阶段做一次）

```powershell
git -C "D:\codex\project A" status --short
git -C "D:\codex\project A" add <本阶段变更文件>
git -C "D:\codex\project A" commit -m "feat(stage-Mx): <简要说明>"
git -C "D:\codex\project A" push
```

建议提交粒度：
- M1/M2 固件和升级脚本分开提交。
- M3/M4/M5 数据算法与聚合脚本分开提交。
- M6 文档与简历单独提交。

---

## 8. 最终交付清单（全部）
- 固件：可烧录 `elf` + 升级包 `upgrade_package.bin`
- 硬件：接线表 + 实机照片
- 脚本：`pc_tools/*.py` + `tools/projectA_full_rollout.ps1`
- 日志：`logs/upgrade/*.log`、`build/analysis/*`
- 文档：总计划、最终版docx、简历条目
- GitHub：分支可复现 + 提交历史清晰

## 9. 你现在立刻执行的第一条
```powershell
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage m1 -Port COM6 -Execute
```
