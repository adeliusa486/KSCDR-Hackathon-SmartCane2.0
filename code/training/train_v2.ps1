# Smart cane - start the smartcane152_v2 training from Windows Task Scheduler.
#
# 3 Oct 2026: training launched by after_pseudo.ps1 through WMI
# (Win32_Process.Create) died silently while scanning labels, together with
# the watcher. WMI provider hosts run under a job with MemoryPerHost 512 MB,
# training needs several GB. Task Scheduler has no such limit and does not
# depend on any chat or terminal staying open.
#
# Register (once):
#   $a = New-ScheduledTaskAction -Execute powershell.exe -Argument '-NoProfile -ExecutionPolicy Bypass -File D:\smartcane-data\pipeline_code\train_v2.ps1'
#   $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -Priority 4
#   Register-ScheduledTask SmartcaneTrainV2 -Action $a -Settings $s
#   Start-ScheduledTask SmartcaneTrainV2

param(
    [string]$D = "D:\smartcane-data",
    [string]$Py = "C:\ml\venv\Scripts\python.exe"
)
$L = "$D\pipeline.log"
function Log($m) { Add-Content $L "$(Get-Date -Format HH:mm:ss) $m" }

Set-Location $D
Log "start: train YOLO11s, 152 classes, 40 epochs (GPU), from Task Scheduler"
& $Py -u "$D\pipeline_code\train.py" --data "$D\merged_v2\smartcane.yaml" --model yolo11s.pt --epochs 40 --batch 12 --name smartcane152_v2 *> "$D\train_v2.log"
Log "train exited $LASTEXITCODE"
