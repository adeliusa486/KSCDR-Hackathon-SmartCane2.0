# Smart cane - run clean_pseudo.py between pseudo-labelling and training.
#
# 3 Oct 2026: the running chain (pseudo_label.py, then train.py) was started
# before the bad-box check. smartcane.yaml was renamed to smartcane.yaml.hold
# so the chain's train.py exits at once with "no dataset descriptor". This
# script waits for that, removes the bad boxes, checks a second dry run finds
# none left, puts smartcane.yaml back and starts the same training.
#
# Launch detached so it survives the chat that started it:
#   Invoke-CimMethod Win32_Process -MethodName Create -Arguments @{CommandLine=
#     'powershell -NoProfile -ExecutionPolicy Bypass -File <repo>\code\training\after_pseudo.ps1'}

param(
    [string]$D = "D:\smart cane 2.0\datasets",
    [string]$Py = "D:\smart cane 2.0\envs\venv\Scripts\python.exe",
    [int]$Poll = 30
)
# No $ErrorActionPreference = "Stop": in PowerShell 5.1 a native program's
# stderr (Ultralytics progress) would then end the script. Exit codes are
# checked explicitly instead.
$Data = "$D\merged_v2"
$Code = $PSScriptRoot
$L    = "$D\pipeline.log"

function Log($m) { Add-Content $L "$(Get-Date -Format HH:mm:ss) $m" }

Log "watcher: waiting for pseudo-label to finish and the held train.py to exit"
while ($true) {
    $text = Get-Content $L -Raw
    $i = $text.LastIndexOf("start: pseudo-label train/val (GPU")
    $tail = $text.Substring([Math]::Max(0, $i))
    if ($tail -match "STOPPED: pseudo-label exited") {
        Log "watcher: pseudo-label failed, nothing cleaned, no training started"
        exit 1
    }
    if ($tail -match "done: pseudo-label" -and $tail -match "train exited") { break }
    Start-Sleep -Seconds $Poll
}
if (-not ((Get-Content "$D\pseudo_v2.log" -Tail 1) -match "^done:")) {
    Log "watcher: STOPPED, pseudo_v2.log does not end with done:"
    exit 1
}
if (Test-Path "$D\train_v2.log") { Move-Item "$D\train_v2.log" "$D\train_v2_held.log" -Force }

Log "start: clean_pseudo (bonnet + stop sign boxes)"
Set-Location $Code
& $Py -u clean_pseudo.py --data $Data --apply *> "$D\clean_v2.log"
if ($LASTEXITCODE -ne 0) { Log "watcher: STOPPED, clean_pseudo exited $LASTEXITCODE"; exit 1 }
& $Py -u clean_pseudo.py --data $Data *> "$D\clean_v2_check.log"
$rc = $LASTEXITCODE
$check = Get-Content "$D\clean_v2_check.log" -Raw
if ($rc -ne 0 -or $check -notmatch "would be removed: 0 in 0 files") {
    Log "watcher: STOPPED, a second dry run still finds boxes to remove (clean_v2_check.log)"
    exit 1
}
Log "done: clean_pseudo, $((Get-Content "$D\clean_v2.log" | Select-String 'label lines').Line)"

Log "start: relabel MTSD stop signs (traffic sign -> stop sign)"
& $Py -u relabel_mtsd_stop.py --data $Data --mtsd "$D\raw\mapillary_mtsd" --apply *> "$D\relabel_v2.log"
if ($LASTEXITCODE -ne 0) { Log "watcher: STOPPED, relabel_mtsd_stop exited $LASTEXITCODE"; exit 1 }
& $Py -u relabel_mtsd_stop.py --data $Data --mtsd "$D\raw\mapillary_mtsd" *> "$D\relabel_v2_check.log"
$rc = $LASTEXITCODE
$check = Get-Content "$D\relabel_v2_check.log" -Raw
if ($rc -ne 0 -or $check -notmatch "to change: 0") {
    Log "watcher: STOPPED, a second relabel dry run still finds boxes to change (relabel_v2_check.log)"
    exit 1
}
Log "done: relabel, $((Get-Content "$D\relabel_v2.log" | Select-String 'changed').Line)"

Move-Item "$Data\smartcane.yaml.hold" "$Data\smartcane.yaml"
Set-Location $D
Log "start: train YOLO11s, 152 classes, 40 epochs (GPU), started by the watcher"
& $Py -u "$Code\train.py" --data "$Data\smartcane.yaml" --model yolo11s.pt --epochs 40 --batch 12 --name smartcane152_v2 *> "$D\train_v2.log"
Log "train exited $LASTEXITCODE"
