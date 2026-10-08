# Smart cane - start the smartcane152_v2 training from Windows Task Scheduler.
#
# 3 Oct 2026: training launched by after_pseudo.ps1 through WMI
# (Win32_Process.Create) died silently while scanning labels, together with
# the watcher. WMI provider hosts run under a job with MemoryPerHost 512 MB,
# training needs several GB. Task Scheduler has no such limit and does not
# depend on any chat or terminal staying open.
#
# Batch 24, not 12: at 12 the main process was CPU-bound issuing GPU work
# (GPU mostly idle, py-spy: ~30 % in the MuSGD optimizer step). Ultralytics
# accumulates to nbs=64 either way, so the training maths barely changes.
# Measured 3 Oct: 1.6 it/s at batch 12 in Balanced fan mode, 3.0 it/s at
# batch 12 with MyASUS fan profile on Performance. Batch 24 alone gave ~21
# images/s with the CPU held at ~43 % (laptop power limit, Performance mode
# on), about the same per unit of CPU speed. Hence SGD (Adeel approved): the
# MuSGD step costs the same per image at any batch size.
#
# Register (once):
#   $a = New-ScheduledTaskAction -Execute powershell.exe -Argument '-NoProfile -ExecutionPolicy Bypass -File <repo>\code\training\train_v2.ps1'
#   $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -Priority 4
#   Register-ScheduledTask SmartcaneTrainV2 -Action $a -Settings $s
#   Start-ScheduledTask SmartcaneTrainV2

param(
    [string]$D = "D:\smart cane 2.0\datasets",
    [string]$Py = "D:\smart cane 2.0\envs\venv\Scripts\python.exe"
)
$L = "$D\pipeline.log"
function Log($m) { Add-Content $L "$(Get-Date -Format HH:mm:ss) $m" }

Set-Location $D
Log "start: train YOLO11s, 152 classes, 40 epochs (GPU), from Task Scheduler"
& $Py -u "$PSScriptRoot\train.py" --data "$D\merged_v2\smartcane.yaml" --model yolo11s.pt --epochs 40 --batch 24 --optimizer SGD --name smartcane152_v2 *> "$D\train_v2.log"
Log "train exited $LASTEXITCODE"
