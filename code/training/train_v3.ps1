# Smart cane - smartcane152_v3: 2-day fine-tune with a watchdog (4 Oct 2026).
#
# Why: run v2 fell from mAP50 0.398 (epoch 2) to 0.360 and then 0.225 once
# warm-up ended at lr0 0.01. Adeel: finish within 2 days, avoid bad results,
# keep the model small enough for the cane.
#
# - Model stays YOLO11s (~9.4 M params), the size class of the yolov8s that
#   runs at ~58 FPS on the Hailo-8L. Nothing bigger.
# - Starts from v2's best.pt (epoch 2), new optimizer, lr0 0.002 with cosine
#   decay, 0.5 epoch warm-up, mosaic off for the last 4 epochs.
# - Ultralytics `time` fits the run into the hours left before the deadline
#   (46 h after this script starts), so it ends on time by itself.
# - Watchdog: every 5 min it reads results.csv. If, after 3+ epochs, the last
#   two epochs are both clearly below the run's best (latest < 80 % of best,
#   the one before < 90 %), it stops the run and retries from that run's
#   best.pt with half the learning rate. Max 3 attempts, never past the
#   deadline. best.pt of every attempt is kept.
#
# Run from Task Scheduler (not WMI), see train_v2.ps1.

param(
    [string]$D = "D:\smartcane-data",
    [string]$Py = "C:\ml\venv\Scripts\python.exe",
    [double]$BudgetHours = 46
)
$L = "$D\pipeline.log"
function Log($m) { Add-Content $L "$(Get-Date -Format 'MM-dd HH:mm:ss') v3: $m" }

function Read-Map50($run) {
    $csv = "$D\runs\detect\$run\results.csv"
    if (-not (Test-Path $csv)) { return @() }
    $rows = Import-Csv $csv
    return @($rows | ForEach-Object { [double]($_.PSObject.Properties | Where-Object { $_.Name.Trim() -eq 'metrics/mAP50(B)' }).Value })
}

Set-Location $D
$deadline = (Get-Date).AddHours($BudgetHours)
$weights = "$D\runs\detect\smartcane152_v2\weights\best.pt"
$lr = 0.002
Log "start, deadline $($deadline.ToString('MM-dd HH:mm')), from $weights"

for ($attempt = 1; $attempt -le 3; $attempt++) {
    $hours = [math]::Round(($deadline - (Get-Date)).TotalHours - 0.75, 2)
    if ($hours -lt 4) { Log "only $hours h left, no new attempt"; break }
    $name = if ($attempt -eq 1) { "smartcane152_v3" } else { "smartcane152_v3_try$attempt" }
    if (Test-Path "$D\runs\detect\$name") { Log "$name exists, stopping so nothing is overwritten"; break }
    $argList = @("-u", "$D\pipeline_code\train.py", "--data", "$D\merged_v2\smartcane.yaml",
        "--model", $weights, "--batch", "24", "--optimizer", "SGD", "--epochs", "100",
        "--lr0", "$lr", "--lrf", "0.05", "--cos-lr", "--warmup-epochs", "0.5",
        "--close-mosaic", "4", "--patience", "8", "--time", "$hours", "--name", $name)
    Log "attempt $attempt ($name): lr0 $lr, $hours h"
    $p = Start-Process -FilePath $Py -ArgumentList $argList -WorkingDirectory $D -NoNewWindow -PassThru `
        -RedirectStandardOutput "$D\train_$name.log" -RedirectStandardError "$D\train_$name.err.log"

    $failed = $false
    while (-not $p.HasExited) {
        Start-Sleep 300
        $m = Read-Map50 $name
        if ($m.Count -ge 3) {
            $best = ($m | Measure-Object -Maximum).Maximum
            $last = $m[-1]; $prev = $m[-2]
            if ($last -lt 0.8 * $best -and $prev -lt 0.9 * $best) {
                Log "attempt $attempt falling: last $last, prev $prev, best $best. Stopping."
                Get-CimInstance Win32_Process | Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*$name*" } |
                    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
                Start-Sleep 20
                Get-CimInstance Win32_Process | Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*multiprocessing*" } |
                    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
                $failed = $true
                break
            }
        }
    }
    $m = Read-Map50 $name
    $bestTxt = if ($m.Count) { ($m | Measure-Object -Maximum).Maximum } else { "none" }
    if (-not $failed) { Log "attempt $attempt ended (exit $($p.ExitCode)), $($m.Count) epochs, best mAP50 $bestTxt"; break }
    if (Test-Path "$D\runs\detect\$name\weights\best.pt") { $weights = "$D\runs\detect\$name\weights\best.pt" }
    $lr = $lr / 2
}
Log "done"
