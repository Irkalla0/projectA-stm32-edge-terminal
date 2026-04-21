# V2/最终版工具链

## 构建应用二进制

```powershell
py "D:\codex\project A\tools\make_app_bin.py" --elf "D:\codex\project A\projectA_day1_sht30_mx\Debug\projectA_day1_sht30_mx.elf" --out "D:\codex\project A\build\v2\app.bin"
```

## 打包升级固件

```powershell
py "D:\codex\project A\tools\pack_fw.py" pack --input "D:\codex\project A\build\v2\app.bin" --version 2.0.0 --board STM32F407ZGTx --out-dir "D:\codex\project A\build\v2"
```

## 校验升级包完整性

```powershell
py "D:\codex\project A\tools\pack_fw.py" inspect --input "D:\codex\project A\build\v2\upgrade_package.bin" --strict
```

## 升级链路（并行）

```powershell
py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport parallel --port COM6 --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm --abort-on-fail
```

## 全流程脚本

```powershell
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage all -Port COM6 -Transport parallel -CanInterface slcan -CanChannel COM8 -CanBitrate 500000
```

## 发布 GitHub Release（含附件）

```powershell
$env:GITHUB_TOKEN='YOUR_PAT'
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\release_publish_all.ps1" -Tag v2.0.0-final -OverwriteAssets
```

### 干跑预览（不实际发布）

```powershell
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\release_publish_all.ps1" -Tag v2.0.0-final -DryRun
```
