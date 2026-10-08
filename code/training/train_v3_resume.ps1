# Smart cane - resume smartcane152_v3 after a pause (5 Oct 2026, Adeel paused
# it for 2 h to rest the laptop). Continues from last.pt at the next epoch,
# same settings (lr schedule, time budget, 27 epochs) read from the checkpoint.

param(
    [string]$D = "D:\smartcane-data",
    [string]$Py = "C:\ml\venv\Scripts\python.exe"
)
$L = "$D\pipeline.log"
function Log($m) { Add-Content $L "$(Get-Date -Format 'MM-dd HH:mm:ss') v3: $m" }
$Last = "$D\runs\detect\smartcane152_v3\weights\last.pt"
Set-Location $D
if (-not (Test-Path $Last)) { Log "resume: no $Last"; exit 1 }
Copy-Item "$D\train_smartcane152_v3.log" "$D\train_smartcane152_v3_before_pause.log" -ErrorAction SilentlyContinue
Log "resume after pause from $Last"
& $Py -u "$D\pipeline_code\train.py" --data "$D\merged_v2\smartcane.yaml" --model $Last --resume --batch 24 --optimizer SGD --name smartcane152_v3 *> "$D\train_smartcane152_v3.log"
Log "resume exited $LASTEXITCODE"
