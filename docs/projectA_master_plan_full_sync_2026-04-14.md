# 项目A全量执行总计划（同步版）

更新时间：2026-04-14
适用分支：`codex/w25q128-integration`
仓库：`https://github.com/Irkalla0/projectA-stm32-edge-terminal`

## 0. 计划边界与原则
- 目标：把项目A从“可跑”收敛为“可演示 + 可交付 + 可写简历”的完整项目。
- 覆盖范围：原版V1、升级版V2、数据分析预测、分布式网络、异常检测、文档与简历输出。
- 去重原则：已完成能力只保留一次，不重复拆分；未完成部分按最短闭环推进。
- 交付优先级：先闭环、再增强、最后美化。

## 1. 当前基线（已完成）
### 1.1 固件与链路
- 已完成 STM32F407 + FreeRTOS 基础采集与告警链路。
- 已完成 UART 升级协议主流程：`UPG_BEGIN -> UPG_DATA -> UPG_END -> UPG_ACTIVATE -> UPG_CONFIRM`。
- 已完成双串口命令解析隔离与升级期间串口抗干扰优化。

### 1.2 工具链
- 已完成 `pc_tools/uart_upgrade_client.py` 增强（超时/重试/字符延时等）。
- 已完成 `pc_tools/uart_link_diag.py` 串口健康诊断工具。

### 1.3 Git管理
- 已创建并推送工作分支：`codex/w25q128-integration`。
- 关键提交已在远端：`5b9cd4a`。

## 2. 全量里程碑（含未完成项）

## M1. W25Q128持久化闭环（进行中）
状态：`IN_PROGRESS`
目标：Boot State 从内存态升级到外部Flash持久化，支持重启后恢复。

步骤：
1. 硬件接线（SPI1）：`PA5-SCK`、`PA6-MISO`、`PA7-MOSI`、`PB12-CS`、`3.3V`、`GND`，`/WP` `/HOLD` 上拉。
2. 烧录当前分支固件。
3. 串口验证一次：`GET_FLASH`（或`FLASH_ID`）返回 `0xEF4018`。
4. 执行：`BOOT_SAVE` -> 复位 -> `BOOT_LOAD` -> `GET_BOOTSTATE`。

产出：
- 一条成功串口日志（含`FLASH:id=0xEF4018`和`BOOT_LOAD:OK`）。

验收：
- 冷启动后 `GET_BOOTSTATE` 与保存前一致。

## M2. V2升级最小可靠性闭环（待做）
状态：`TODO`
目标：在有W25持久化前提下确认升级链路完整可复现。

步骤：
1. 固定端口（优先`COM6`）执行一次完整升级（含activate/confirm）。
2. 仅做一次复位后状态查询：`GET_BOOTSTATE`、`UPG_STATUS`。
3. 保存升级日志到 `logs/upgrade/`。

产出：
- 升级成功日志文件（1份）。

验收：
- `UPG_STATUS:confirmed`
- `pending=NONE`
- `active_slot` 按预期切换。

## M3. 数据分析与预测（待做）
状态：`TODO`
目标：形成可展示的“采集->分析->预测->报告”最小闭环。

步骤：
1. 统一数据字段：`ts,node_id,temp_c,hum_rh,dist_mm,curr_ma,seq,crc_ok,source`。
2. 数据清洗与窗口聚合（5min/30min）。
3. 异常评分（EWMA/Z-score）+ 30~60分钟短期预测（Holt-Winters）。
4. 生成日报图表（趋势图+异常摘要）。

产出：
- `build/analysis/daily_report_*.md`
- `build/analysis/forecast_*.png`

验收：
- 报告可一键复现；输出包含 MAE/MAPE 和趋势方向准确率。

## M4. 分布式传感网络（待做）
状态：`TODO`
目标：实现 `STM32串口流 + MQTT节点流` 的统一汇聚。

步骤：
1. 先搭最小拓扑：`1实物STM32 + 1仿真节点`。
2. 启动 MQTT Broker（本机）。
3. 接入主题：
   - `projectA/node/{node_id}/telemetry`
   - `projectA/node/{node_id}/event`
   - `projectA/cmd/{node_id}`
4. 聚合服务统一落盘（CSV+SQLite）。

产出：
- `pc_tools/distributed_aggregator.py`
- `logs/distributed_*.db`

验收：
- 双源数据同屏/同库可追踪；单节点掉线可识别。

## M5. 异常检测组合（待做）
状态：`TODO`
目标：端侧规则 + 中心侧模型双层检测。

步骤：
1. 端侧规则：阈值越界/突变/导数超限。
2. 中心侧模型：`IsolationForest + EWMA/Z-score`。
3. 告警分级：`P1/P2/P3`，附 `score/threshold/detail`。
4. 建事件库并统计误报漏报。

产出：
- `build/analysis/anomaly_events_*.csv`
- `build/analysis/anomaly_eval_*.md`

验收：
- 可回放异常样本；有召回率与误报率统计。

## M6. 演示封板与文档（待做）
状态：`TODO`
目标：形成“可投递”的最终包。

步骤：
1. 统一演示脚本（上电->采集->告警->升级->恢复->分析展示）。
2. 输出最终项目文档（docx，结构固定）。
3. 输出简历版本（3条成果 + 指标）。
4. 整理答辩用一页总览（架构+指标+日志证据）。

产出：
- `docs/项目A_最终版.docx`
- `docs/projectA_one_page_summary.md`
- `docs/resume_projectA_bullets.md`

验收：
- 不依赖口头补充即可让他人按文档复现演示流程。

## 3. 验收指标（最终版）
- V1回归：30分钟采集，CRC通过率 `>=99%`
- V2可靠性：至少1轮完整升级闭环 + 复位后状态正确
- 分布式：2节点（可1实物+1仿真）并发数据可汇聚
- 异常检测：至少4类异常可识别并可回放
- 预测：30分钟窗口输出 `MAPE` 与趋势方向准确率

## 4. 执行顺序（最短路径）
1. `M1` W25持久化闭环
2. `M2` 升级闭环一次成功并留证据
3. `M3` 分析预测最小可视化
4. `M4` 分布式最小拓扑
5. `M5` 异常检测组合
6. `M6` 文档/简历封板

## 5. GitHub同步策略（本计划）
- 计划文件路径：`docs/projectA_master_plan_full_sync_2026-04-14.md`
- 提交粒度：仅计划文档单独提交，避免混入无关改动。
- 分支：`codex/w25q128-integration`
- 推送后作为后续执行唯一任务清单。

## 6. 每次开工使用模板
```text
今日目标：<M1/M2/...>
输入条件：<硬件/端口/分支/文件>
执行步骤：<1..N>
输出证据：<日志路径/截图/报表>
是否达成：<YES/NO>
阻塞项：<无/具体问题>
```
