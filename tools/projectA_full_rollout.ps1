param(
  [ValidateSet("m1", "m2", "m3", "m4", "m5", "m6", "all")]
  [string]$Stage = "all",
  [string]$RepoRoot = "D:\codex\project A",
  [string]$Port = "COM6",
  [int]$Baud = 115200,
  [string]$OpenOcdExe = "",
  [string]$OpenOcdScripts = "",
  [string]$InterfaceCfg = "interface/cmsis-dap.cfg",
  [string]$TargetCfg = "target/stm32f4x.cfg",
  [int]$AdapterSpeed = 1000,
  [switch]$Execute
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
  param(
    [string]$Name,
    [string]$Command
  )
  Write-Host ""
  Write-Host "=== $Name ===" -ForegroundColor Cyan
  Write-Host $Command -ForegroundColor Yellow
  if ($Execute) {
    Invoke-Expression $Command
  }
}

function Stage-M1 {
  $elf = Join-Path $RepoRoot "projectA_day1_sht30_mx\Debug\projectA_day1_sht30_mx.elf"
  $uartCmd = Join-Path $RepoRoot "pc_tools\uart_cmd_once.py"

  if ($OpenOcdExe -and $OpenOcdScripts) {
    $flashCmd = "& `"$OpenOcdExe`" -s `"$OpenOcdScripts`" -f $InterfaceCfg -c `"transport select swd`" -c `"adapter speed $AdapterSpeed`" -f $TargetCfg -c `"program {$elf} verify reset exit`""
    Invoke-Step "M1-Flash Firmware" $flashCmd
  } else {
    Write-Host ""
    Write-Host "=== M1-Flash Firmware ===" -ForegroundColor Cyan
    Write-Host "Skipped: set -OpenOcdExe and -OpenOcdScripts to enable auto flash." -ForegroundColor DarkYellow
  }

  Invoke-Step "M1-GET_FLASH" "py `"$uartCmd`" --port $Port --baud $Baud --cmd GET_FLASH --timeout-s 3 --expect id=0xEF4018"
  Invoke-Step "M1-BOOT_SAVE" "py `"$uartCmd`" --port $Port --baud $Baud --cmd BOOT_SAVE --timeout-s 3"
  Invoke-Step "M1-BOOT_LOAD" "py `"$uartCmd`" --port $Port --baud $Baud --cmd BOOT_LOAD --timeout-s 3"
  Invoke-Step "M1-GET_BOOTSTATE" "py `"$uartCmd`" --port $Port --baud $Baud --cmd GET_BOOTSTATE --timeout-s 3"
}

function Stage-M2 {
  $diag = Join-Path $RepoRoot "pc_tools\uart_link_diag.py"
  $upg = Join-Path $RepoRoot "pc_tools\uart_upgrade_client.py"
  $pkg = Join-Path $RepoRoot "build\v2\upgrade_package.bin"
  $logDir = Join-Path $RepoRoot "logs\upgrade"
  $ts = Get-Date -Format "yyyyMMdd_HHmmss"
  $upgLog = Join-Path $logDir "upgrade_once_$ts.log"

  if (!(Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

  Invoke-Step "M2-Link Diagnostics" "py `"$diag`" --port $Port --scan-seconds 2 --cmd-wait-seconds 1.2 --retries 2"
  Invoke-Step "M2-UART Upgrade Once" "py `"$upg`" --pkg `"$pkg`" --port $Port --chunk 128 --ack-timeout 12 --query-retries 5 --ctrl-char-delay-ms 20 --data-char-delay-ms 2 --preflush-newlines 1 --activate --confirm --abort-on-fail 2>&1 | Tee-Object -FilePath `"$upgLog`""
}

function Stage-M3 {
  $ana = Join-Path $RepoRoot "pc_tools\analyze_and_forecast.py"
  $v1 = Join-Path $RepoRoot "pc_tools\v1_regression_check.py"
  $csv1 = Join-Path $RepoRoot "logs\day11_demo_run.csv"
  $csv2 = Join-Path $RepoRoot "logs\day14_demo.csv"
  $out = Join-Path $RepoRoot "build\analysis"

  if (!(Test-Path $out)) { New-Item -ItemType Directory -Path $out -Force | Out-Null }
  Invoke-Step "M3-Analytics+Forecast" "py `"$ana`" `"$csv1`" `"$csv2`" --resample-seconds 30 --horizon-steps 60 --out-dir `"$out`""
  Invoke-Step "M3-V1 Regression" "py `"$v1`" `"$csv1`" --min-crc-pass-rate 0.99 --min-duration-s 600 --out-report `"$out\v1_regression_report.txt`" --out-json `"$out\v1_regression_metrics.json`""
}

function Stage-M4 {
  $agg = Join-Path $RepoRoot "pc_tools\distributed_aggregator.py"
  $sim = Join-Path $RepoRoot "pc_tools\mqtt_node_sim.py"
  $runCsv = Join-Path $RepoRoot "logs\run.csv"
  $outTel = Join-Path $RepoRoot "logs\distributed_telemetry.csv"
  $outEvt = Join-Path $RepoRoot "logs\distributed_events.csv"
  $outDb = Join-Path $RepoRoot "logs\distributed.db"

  if ($Execute) {
    Write-Host ""
    Write-Host "=== M4-Run Aggregator + Sim Node ===" -ForegroundColor Cyan
    $aggArgs = "`"$agg`" --enable-mqtt --mqtt-host 127.0.0.1 --mqtt-port 1883 --serial-csv `"$runCsv`" --out-telemetry `"$outTel`" --out-events `"$outEvt`" --out-db `"$outDb`" --runtime-s 130"
    $simArgs = "`"$sim`" --node-id esp32_sim_01 --mqtt-host 127.0.0.1 --mqtt-port 1883 --runtime-s 120"
    $pAgg = Start-Process -FilePath py -ArgumentList $aggArgs -PassThru
    Start-Sleep -Seconds 2
    $pSim = Start-Process -FilePath py -ArgumentList $simArgs -PassThru
    Wait-Process -Id $pSim.Id
    Wait-Process -Id $pAgg.Id
  } else {
    Invoke-Step "M4-Aggregator (print only)" "py `"$agg`" --enable-mqtt --mqtt-host 127.0.0.1 --mqtt-port 1883 --serial-csv `"$runCsv`" --out-telemetry `"$outTel`" --out-events `"$outEvt`" --out-db `"$outDb`" --runtime-s 130"
    Invoke-Step "M4-Sim Node (print only)" "py `"$sim`" --node-id esp32_sim_01 --mqtt-host 127.0.0.1 --mqtt-port 1883 --runtime-s 120"
  }
}

function Stage-M5 {
  $ana = Join-Path $RepoRoot "pc_tools\analyze_and_forecast.py"
  $dist = Join-Path $RepoRoot "logs\distributed_telemetry.csv"
  $out = Join-Path $RepoRoot "build\analysis"
  if (!(Test-Path $out)) { New-Item -ItemType Directory -Path $out -Force | Out-Null }
  Invoke-Step "M5-Anomaly Pack" "py `"$ana`" `"$dist`" --resample-seconds 30 --horizon-steps 60 --out-dir `"$out`""
}

function Stage-M6 {
  $v2 = Join-Path $RepoRoot "pc_tools\v2_reliability_report.py"
  $out = Join-Path $RepoRoot "build\analysis\v2_reliability_report.md"
  Invoke-Step "M6-V2 Reliability Report" "py `"$v2`" --out `"$out`""
  Write-Host ""
  Write-Host "M6 reminder:" -ForegroundColor Cyan
  Write-Host "Update docs/projectA_master_plan_full_sync_2026-04-14.md status fields and export final docx."
}

switch ($Stage) {
  "m1" { Stage-M1; break }
  "m2" { Stage-M2; break }
  "m3" { Stage-M3; break }
  "m4" { Stage-M4; break }
  "m5" { Stage-M5; break }
  "m6" { Stage-M6; break }
  "all" {
    Stage-M1
    Stage-M2
    Stage-M3
    Stage-M4
    Stage-M5
    Stage-M6
    break
  }
}

Write-Host ""
if ($Execute) {
  Write-Host "[DONE] Stage '$Stage' executed." -ForegroundColor Green
} else {
  Write-Host "[DONE] Stage '$Stage' commands printed. Add -Execute to run." -ForegroundColor Green
}

