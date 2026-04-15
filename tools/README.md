# V2/Final Toolchain

## Build app binary

```powershell
py "D:\codex\project A\tools\make_app_bin.py" --elf "D:\codex\project A\projectA_day1_sht30_mx\Debug\projectA_day1_sht30_mx.elf" --out "D:\codex\project A\build\v2\app.bin"
```

## Pack firmware package

```powershell
py "D:\codex\project A\tools\pack_fw.py" pack --input "D:\codex\project A\build\v2\app.bin" --version 2.0.0 --board STM32F407ZGTx --out-dir "D:\codex\project A\build\v2"
```

## Inspect package integrity

```powershell
py "D:\codex\project A\tools\pack_fw.py" inspect --input "D:\codex\project A\build\v2\upgrade_package.bin" --strict
```

## Upgrade transports

```powershell
py "D:\codex\project A\pc_tools\upgrade_client.py" --pkg "D:\codex\project A\build\v2\upgrade_package.bin" --transport parallel --port COM6 --can-interface slcan --can-channel COM8 --can-bitrate 500000 --activate --confirm --abort-on-fail
```

## Full rollout script

```powershell
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\projectA_full_rollout.ps1" -Stage all -Port COM6 -Transport parallel -CanInterface slcan -CanChannel COM8 -CanBitrate 500000
```

## Publish GitHub release (with assets)

```powershell
$env:GITHUB_TOKEN='YOUR_PAT'
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\release_publish_all.ps1" -Tag v2.0.0-final -OverwriteAssets
```

### Dry run

```powershell
powershell -ExecutionPolicy Bypass -File "D:\codex\project A\tools\release_publish_all.ps1" -Tag v2.0.0-final -DryRun
```
