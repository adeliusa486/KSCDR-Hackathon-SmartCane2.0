# Smart cane - RESUME the smartcane152_v2 training after the PC was shut down.
#
# 3 Oct 2026, 22:10: Adeel shut the PC down during epoch 2 of 40. Epoch 1
# finished at 21:30 and its checkpoint is runs\detect\smartcane152_v2\weights\
# last.pt. Ultralytics resume reads every setting (batch 24, SGD, 40 epochs,
# augmentation) from that checkpoint and continues at the next epoch, in the
# same run folder. Work since the last finished epoch is lost, nothing else.
#
# Do NOT start train_v2.ps1 again: that starts from scratch in a new folder.
#
# Run (Task Scheduler, not WMI, see train_v2.ps1):
#   $a = New-ScheduledTaskAction -Execute powershell.exe -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File <repo>\code\training\train_v2_resume.ps1'
#   Set-ScheduledTask SmartcaneTrainV2 -Action $a
#   Start-ScheduledTask SmartcaneTrainV2
# Set MyASUS fan mode to Performance first (36 vs 20 images/s, see MEMORY.md).

param(
    [string]$D = "D:\smart cane 2.0\datasets",
    [string]$Py = "D:\smart cane 2.0\envs\venv\Scripts\python.exe"
)
$L = "$D\pipeline.log"
function Log($m) { Add-Content $L "$(Get-Date -Format HH:mm:ss) $m" }

$Last = "$D\runs\detect\smartcane152_v2\weights\last.pt"
Set-Location $D
if (-not (Test-Path $Last)) { Log "resume: no checkpoint at $Last, nothing started"; exit 1 }
$n = (Get-ChildItem "$D\train_v2*.log").Count
Copy-Item "$D\train_v2.log" "$D\train_v2_before_resume_$n.log" -ErrorAction SilentlyContinue
Log "resume: smartcane152_v2 from $Last"
& $Py -u "$PSScriptRoot\train.py" --data "$D\merged_v2\smartcane.yaml" --model $Last --resume --batch 24 --optimizer SGD --name smartcane152_v2 *> "$D\train_v2.log"
Log "train (resume) exited $LASTEXITCODE"
