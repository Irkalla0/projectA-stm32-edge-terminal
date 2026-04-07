# 项目A落地总策划（原版 + 升级版 + 数据分析预测 + 分布式网络 + 异常检测）

更新时间：2026-04-07  
项目目录：`D:\codex\project A`

---

## 1. 项目目标

将现有“单机采集 + 串口升级”系统升级为“可扩展的分布式智能监测系统”，实现以下闭环：

`采集 -> 处理 -> 升级 -> 多节点汇聚 -> 异常检测 -> 预测分析 -> 报告输出`

最终交付目标：

1. 可演示的稳定系统（V1 + V2 + 分布式 + 算法）
2. 可量化的测试指标（稳定性、准确性、预测效果）
3. 可直接用于求职的项目表达（简历 + 面试）

---

## 2. 当前已落地能力（原版 + 升级版）

### 2.1 原版（V1）已完成

1. STM32F407 + FreeRTOS 采集链路可运行（温湿度 + 距离/电流）
2. UART 告警帧与上位机链路可用（`CMD=0x01/0xA1`、`CMD=0x02/0xA2`）
3. 上位机支持中文UI、CSV落盘、串口容错
4. 双串口兜底（USART1 + USART2）

实测证据：

- `logs/day11_demo_report.txt`：`763/763` CRC 通过
- `logs/day14_demo_report.txt`：96 帧稳定、A1/A2 告警统计可追踪

### 2.2 升级版（V2）已完成

1. 升级协议与命令框架：`GET_VER / GET_CAP / UPG_* / GET_BOOTSTATE`
2. 升级工具链：`make_app_bin.py`、`pack_fw.py`、`uart_upgrade_client.py`
3. Boot State 布局与策略核心：`bootloader/include` + `boot_policy_sim.py`
4. 升级状态查询与激活确认流程已接入应用层

关键提交：

- `896730f`：V2 协议与工具脚手架
- `1eeb65d`：Boot State 集成与 activate/confirm 流程
- `3d55605`：Boot Policy 核心 + 本地回滚仿真

---

## 3. 目标扩展能力与总体架构

### 3.1 扩展能力

1. 数据分析与预测：日报 + 趋势预测 + 指标评估（MAE/MAPE/趋势方向）
2. 分布式传感网络：ESP32 节点通过 MQTT 汇聚到 PC（与 STM32 串口流并存）
3. 异常检测算法：规则 + EWMA/Z-score + IsolationForest 组合

### 3.2 架构升级

1. 设备侧：STM32（核心节点） + ESP32（扩展节点）
2. 通信侧：UART（本机链路） + MQTT（分布式链路）
3. 平台侧：聚合器统一落盘到 CSV/SQLite
4. 算法侧：统一数据流水线进行检测与预测
5. 展示侧：报告/事件库/预测结果用于答辩和面试

---

## 4. 硬件清单（最低预算优先）

| 类别 | 当前状态 | 最低新增建议 | 预算口径 |
|---|---|---|---|
| STM32F407主控 | 已有 | 无 | ¥0 |
| 调试器（ST-LINK/CMSIS-DAP） | 已有 | 无 | ¥0 |
| CH340串口模块 | 已有 | 备件1个（可选） | 约¥21 |
| W25Q128 | 在途 | 到货后接入回滚持久化 | 约¥10起（芯片） |
| ESP32节点板 | 需新增 | 2块（推荐） | 约¥70~¥180 |
| 传感器扩展 | 可复用现有 | 第二节点补1个SHT30（可选） | 约¥62 |

预算策略：

1. 立即开工版：`¥0`（先仿真节点 + 单实物节点）
2. 最低实物版：`¥70~¥180`（补2块ESP32）
3. 稳妥增强版：`¥130~¥260`（再补传感器与备件）

---

## 5. 软件栈清单

| 层级 | 软件/库 | 用途 | 必需性 |
|---|---|---|---|
| 固件开发 | STM32CubeIDE + OpenOCD | 编译/烧录/调试 | 必需 |
| 串口采集 | Python + pyserial | 数据采集与控制命令 | 必需 |
| 数据处理 | pandas + numpy | 清洗、聚合、特征 | 必需 |
| 异常检测 | scikit-learn + statsmodels | IsolationForest + EWMA/Z | 必需 |
| 时序预测 | statsmodels（可选Prophet） | 短期趋势预测 | 必需/可选 |
| 分布式消息 | Mosquitto + paho-mqtt | 多节点汇聚 | 必需 |
| 数据落盘 | CSV + SQLite | 原始数据与事件归档 | 必需 |

---

## 6. 公共接口与数据口径

### 6.1 UART 命令兼容策略

保持原有 `GET_/SET_` 命令，继续支持：

- `GET_VER`
- `GET_CAP`
- `GET_BOOTSTATE`
- `UPG_BEGIN / UPG_DATA / UPG_END / UPG_STATUS / UPG_ACTIVATE / UPG_CONFIRM / UPG_ABORT`

### 6.2 MQTT 主题

- `projectA/node/{node_id}/telemetry`
- `projectA/node/{node_id}/event`
- `projectA/cmd/{node_id}`

### 6.3 统一遥测字段

`ts,node_id,temp_c,hum_rh,dist_mm,curr_ma,seq,cmd,crc_ok,source`

### 6.4 统一异常事件字段

`event_id,ts,node_id,level,anomaly_type,score,threshold,detail,ack,source`

---

## 7. 分阶段落地计划（5周）

### Week 1：V1基线固化

1. 输出 V1 回归报告（CRC、时长、序号连续性）
2. 明确演示脚本与验收阈值
3. 完成命令链路健康度检查（可选日志解析）

交付：

- `pc_tools/v1_regression_check.py`
- `build/analysis/v1_regression_report.txt`

### Week 1-2：V2升级可靠性固化

1. 固化升级命令流程与状态观测
2. 建立可靠性测试矩阵（正常/错包/CRC/非法版本/中断）
3. W25Q未到前做仿真；到货后补持久化回滚

交付：

- `pc_tools/v2_reliability_report.py`
- `build/analysis/v2_reliability_report.md`

### Week 2-3：分析预测能力落地

1. 统一数据流水线：采集 -> 清洗 -> 特征 -> 检测 -> 预测 -> 报告
2. 输出异常事件库与预测结果
3. 形成日报模板

交付：

- `pc_tools/analyze_and_forecast.py`
- `build/analysis/analysis_report.txt`

### Week 3-4：分布式网络落地

1. MQTT 聚合器接入
2. 节点仿真与掉线恢复验证
3. UART + MQTT 数据融合入库

交付：

- `pc_tools/distributed_aggregator.py`
- `pc_tools/mqtt_node_sim.py`
- `logs/distributed.db`

### Week 4-5：异常检测强化与验收

1. 规则 + 统计 + 模型融合评分
2. 误报漏报统计与阈值调优
3. 回放异常事件，形成最终演示报告

交付：

- `build/analysis/anomaly_events.csv`
- 最终答辩材料（图表 + 结论）

---

## 8. 验收标准

1. V1回归：连续 30 分钟采集，CRC通过率 >= 99%
2. V2可靠性：至少 3 轮升级激活确认，异常用例可观测可回退
3. 分布式网络：2 节点并发，单节点掉线 30 秒内识别
4. 异常检测：4类异常召回率 >= 90%，误报率 <= 10%
5. 预测效果：30 分钟窗口，MAPE <= 15%，趋势方向准确率 >= 80%

---

## 9. 本仓库新增实现清单（本次落地）

1. `pc_tools/v1_regression_check.py`
2. `pc_tools/v2_reliability_report.py`
3. `pc_tools/analyze_and_forecast.py`
4. `pc_tools/distributed_aggregator.py`
5. `pc_tools/mqtt_node_sim.py`
6. `pc_tools/README.md`

---

## 10. 简历写法（可直接使用）

### 10.1 项目名称

`项目A：分布式多传感边缘监测终端（STM32F407 + FreeRTOS + MQTT）`

### 10.2 三条项目描述（可投版）

1. 负责 STM32 多源采集与告警链路开发，完成设备端到上位机闭环，实测单轮演示 `763/763` 帧 CRC 全通过。  
2. 设计并落地 UART 升级协议与 Boot State 回滚策略，实现升级状态可观测、失败可回退。  
3. 在原系统上扩展 MQTT 多节点汇聚、异常检测与短期预测能力，形成采集-分析-预测-告警一体化方案。  

### 10.3 STAR 面试表达模板

1. S（场景）：设备侧监测链路分散，数据与升级流程不可统一观测。  
2. T（任务）：在有限预算下完成稳定采集、可靠升级、分布式扩展与算法能力闭环。  
3. A（行动）：搭建 UART + MQTT 双通道，统一数据模型，实施规则+统计+模型融合检测，并引入短期预测。  
4. R（结果）：系统具备可回归、可升级、可扩展、可量化能力，形成可复现实验报告与可投递项目表述。  

### 10.4 建议关键词（ATS）

`STM32`、`FreeRTOS`、`UART`、`MQTT`、`异常检测`、`时序预测`、`IsolationForest`、`Holt-Winters`、`OpenOCD`、`嵌入式系统联调`

